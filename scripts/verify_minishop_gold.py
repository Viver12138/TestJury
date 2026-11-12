"""Verify seed-label business facts against archived MiniShop in a disposable SQLite DB.

Install the archived requirements in .tmp/minishop-runtime first. Authentication is
overridden with fixture identities; this verifies business rules, not JWT behavior.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=ROOT / 'datasets/minishop/v3')
    parser.add_argument('--output', type=Path, default=ROOT / 'evidence/M2/minishop_gold_source_verification.json')
    args = parser.parse_args()
    binding = yaml.safe_load((ROOT / 'kb_content/_delivery/source_binding.yaml').read_text(encoding='utf-8'))
    archive = ROOT / binding['snapshot_archive']['path']
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == binding['snapshot_archive']['sha256']
    dataset = args.dataset
    manifest = json.loads((dataset / 'manifest.json').read_text(encoding='utf-8'))
    for name, checksum in manifest['files'].items():
        path = (dataset / name).resolve()
        assert path.parent == dataset.resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum
    rows = [json.loads(line) for line in (dataset / 'review.jsonl').read_text(encoding='utf-8').splitlines()]
    families = list(dict.fromkeys(row['family'] for row in rows))
    with tempfile.TemporaryDirectory(prefix='minishop_gold_', dir=ROOT / '.tmp') as temp:
        work = Path(temp)
        with zipfile.ZipFile(archive) as source:
            for name in source.namelist():
                if name.startswith('Minishop/backend/') and not name.endswith('/'):
                    target = (work / Path(name).relative_to('Minishop/backend')).resolve()
                    assert target.is_relative_to(work.resolve())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read(name))
        os.environ['DATABASE_URL'] = 'sqlite:///' + (work / 'verification.sqlite').as_posix()
        os.environ['SEED_MEDIA_DIR'] = str(work / 'media')
        sys.path[:0] = [str(work), str(ROOT / '.tmp/minishop-runtime')]
        from fastapi.testclient import TestClient
        from app.main import app
        from app import models as m
        from app.database import Base, SessionLocal, engine, get_db
        from app.auth.dependencies import get_current_user
        app.router.on_startup.clear()  # supplied fixtures replace demo seed only in this test process
        results = []
        for family in families:
            Base.metadata.drop_all(engine)  # engine points only to the fresh TemporaryDirectory
            Base.metadata.create_all(engine)
            db = SessionLocal()
            identity = [2 if family in {'address', 'coupon_owner', 'ownership'} else 3 if family in {'ship', 'refund'} else 1]
            db.add_all([m.User(id=i, username='fixture'+str(i), password_hash='unused', role='ADMIN' if i == 3 else 'USER')
                        for i in (1, 2, 3)])
            db.add_all([
                m.Product(id=1, name='Fixture product', price=100, stock=10, sales=0, status='ON_SALE'),
                m.ProductSku(id=1, product_id=1, price=200 if family=='coupon_owner' else 100,
                             stock=1 if family=='stock' else 10, status='ACTIVE'),
                m.Address(id=1, user_id=1, receiver_name='A', phone='fixture'),
                m.Address(id=2, user_id=2, receiver_name='B', phone='fixture'),
                m.Coupon(id=7, name='Fixture coupon', threshold=100, discount_amount=10, status='ACTIVE',
                         end_time=datetime.now()+timedelta(days=1), used_quantity=1 if family=='cancel' else 0),
                m.UserCoupon(id=7, user_id=1, coupon_id=7, status='USED' if family=='cancel' else 'UNUSED',
                             used_order_id=10 if family=='cancel' else 0),
                m.CartItem(id=1, user_id=1, sku_id=1, quantity=1),
            ])
            if family in {'cancel','payment_retry','deduct','ship','ownership','unreachable','refund','payment_detail'}:
                db.add(m.Order(id=10, order_no='fixture-10', user_id=1,
                               status='REFUNDING' if family=='refund' else 'PENDING_PAYMENT',
                               total_amount=200, pay_amount=200, user_coupon_id=7 if family=='cancel' else 0))
                db.add(m.OrderItem(order_id=10, product_id=1, sku_id=1, price=100, quantity=2, subtotal=200))
            if family in {'payment_retry','deduct','unreachable'}:
                db.add(m.Payment(id=20, order_id=10, payment_no='fixture-20', status='PENDING', amount=200))
            if family=='refund':
                db.add(m.Refund(id=30, order_id=10, user_id=1, amount=200, status='PENDING'))
            db.commit()
            def session():
                yield db
            app.dependency_overrides[get_db] = session
            app.dependency_overrides[get_current_user] = lambda: db.get(m.User, identity[0])
            observed = []
            def send(method, url, body=None):
                response = client.request(method, url, json=body)
                observed.append({'method':method, 'url':url, 'status':response.status_code, 'body':response.json()})
                return response.status_code, response.json()
            try:
                with TestClient(app) as client:
                    request = {'items':[{'sku_id':1,'quantity':2 if family in {'amount','stock'} else 1}],
                               'address_id':2 if family=='coupon_owner' else 1}
                    if family in {'amount','address','stock','coupon_owner','create_effect'}:
                        if family=='amount': request['pay_amount']=0.01
                        if family=='coupon_owner': request['user_coupon_id']=7
                        status, body = send('POST','/api/orders',request)
                        expected = {'amount':201,'address':400,'stock':409,'coupon_owner':400,'create_effect':201}[family]
                        assert status==expected, observed
                        if family=='amount': assert body['data']['pay_amount']==200
                        if family in {'address','stock','coupon_owner'}: assert db.query(m.Order).count()==0
                        if family=='create_effect':
                            assert body['data']['status']=='PENDING_PAYMENT'
                            assert db.get(m.ProductSku,1).stock==10 and db.query(m.CartItem).count()==1
                            assert db.query(m.CartItem).one().quantity == 1
                            observed.append({'database_assertion': 'cart quantity unchanged', 'quantity': 1})
                    elif family in {'threshold','preview'}:
                        request['user_coupon_id']=7
                        if family=='preview': request.pop('address_id')
                        status, body = send('POST','/api/orders/preview',request)
                        assert status==200 and body['data']['pay_amount']==90
                        assert body['data']['total_amount']==100 and body['data']['discount_amount']==10
                        if family=='preview':
                            assert body['data']['address'] is None and db.query(m.Order).count()==0
                            assert db.get(m.UserCoupon,7).status=='UNUSED' and db.get(m.ProductSku,1).stock==10
                    elif family=='cancel':
                        assert send('POST','/api/orders/10/cancel')[0]==200
                        assert db.get(m.Order,10).status=='CANCELLED'
                        coupon=db.get(m.UserCoupon,7)
                        assert coupon.status=='UNUSED' and coupon.used_order_id==0 and db.get(m.Coupon,7).used_quantity==0
                    elif family=='payment_retry':
                        assert send('POST','/api/payments/20/fail')[0]==200
                        assert db.get(m.Payment,20).status=='FAILED' and db.get(m.Order,10).status=='PENDING_PAYMENT'
                        status, body=send('POST','/api/payments',{'order_id':10,'method':'WECHAT'})
                        assert status==201 and body['data']['status']=='PENDING' and body['data']['id']!=20
                    elif family in {'deduct','unreachable'}:
                        status, body=send('POST','/api/payments/20/success')
                        assert status==200 and body['data']['order_status']=='PAID'
                        if family=='deduct':
                            assert db.get(m.ProductSku,1).stock==8 and db.get(m.Product,1).stock==8
                            assert db.get(m.Product,1).sales==2 and db.query(m.InventoryLog).one().change_quantity==-2
                        else: assert send('GET','/api/orders/10')[1]['data']['status']=='PAID'
                    elif family=='ship':
                        assert send('POST','/api/admin/orders/10/ship',{'company':'顺丰','tracking_number':'SF001'})[0]==409
                        assert db.get(m.Order,10).status=='PENDING_PAYMENT'
                    elif family=='ownership':
                        assert send('GET','/api/orders/10')[0]==403
                        assert send('POST','/api/orders/10/cancel')[0]==404
                        assert db.get(m.Order,10).status=='PENDING_PAYMENT'
                    elif family=='refund':
                        assert send('POST','/api/admin/refunds/30/reject',{'reject_reason':'不满足条件'})[0]==200
                        assert db.get(m.Order,10).status=='PAID'
                    elif family=='payment_detail':
                        status, body=send('GET','/api/orders/10')
                        assert status==200 and not {'payment','shipment','refund'} & body['data'].keys()
                    else: raise ValueError('unverified family '+family)
                results.append({'family':family,'passed':True,'observed':observed})
            except Exception as exc:
                results.append({'family':family,'passed':False,'error':str(exc),'observed':observed})
            finally:
                app.dependency_overrides.clear()
                db.close()
        engine.dispose()
    proof={'source_commit':manifest['source_commit'],'archive_sha256':binding['snapshot_archive']['sha256'],
           'dataset_version':manifest['version'],'dataset_files':manifest['files'],'cases':results,
           'passed':all(r['passed'] for r in results),'limitations':['fixture authentication, not JWT testing',
           'business-fact probes, not independent review-quality labels'],'application_database_modified':False}
    output = args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8', newline='\n')
    print(json.dumps({'passed':proof['passed'],'families':len(results),
                      'failed':[r['family'] for r in results if not r['passed']]},ensure_ascii=False))
    return 0 if proof['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
