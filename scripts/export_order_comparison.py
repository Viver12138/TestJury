"""Export paired live results and explicit AI adjudication into a comparison workbook."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import unicodedata
from dataclasses import fields
from datetime import datetime
from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.excel_report import VERDICTS, _Sheets, render_excel
from app.storage.models import ReviewJob


def read_json(path):return json.loads(path.read_text(encoding='utf-8'))


def full(report):
    c=(report or {}).get('review_completeness',{})
    return bool(c.get('complete') and c.get('blind')=='2/2' and c.get('vote')=='2/2')


def adopted_seed(record, review):
    matched={x['issue_no'] for x in review['issues'] if x['seed_match']}
    return any(x['issue_no'] in matched and x['status']=='adopted'
               for x in (record['job']['report_json'] or {}).get('issues',[]))


def job_from_saved(saved):
    values={f.name:saved[f.name] for f in fields(ReviewJob) if f.name in saved}
    for name in ('created_at','finished_at','started_at','report_locked_at','locked_at','lease_expires_at'):
        if values.get(name):values[name]=datetime.fromisoformat(values[name])
    return ReviewJob(**values)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--adjudication',type=Path,required=True)
    p.add_argument('--output',type=Path)
    p.add_argument('--allow-mock-self-check',action='store_true')
    args=p.parse_args()
    manifest=read_json(args.run/'manifest.json')
    assert manifest['status']=='completed'
    assert manifest['mode']=='live' or args.allow_mock_self_check,'Mock output requires an explicit self-check flag'
    assert manifest['terminal_tasks']==20
    dataset=read_json(ROOT/manifest['dataset'])
    assert hashlib.sha256((ROOT/manifest['dataset']).read_bytes()).hexdigest()==manifest['dataset_sha256']
    assert hashlib.sha256((ROOT/dataset['input_workbook']).read_bytes()).hexdigest()==dataset['input_sha256']
    adjudication=read_json(args.adjudication)
    assert adjudication['run_id']==manifest['run_id']
    assert adjudication['actor_type']=='ai' and not adjudication['independent_human_validation']
    if adjudication.get('fact_verification'):
        fact=adjudication['fact_verification']
        assert hashlib.sha256((ROOT/fact['path']).read_bytes()).hexdigest()==fact['sha256']
    saved={}
    for condition in ('knowledge_on','knowledge_off'):
        saved[condition]={}
        for path in sorted((args.run/condition).glob('ORDER-*.json')):
            record=read_json(path)
            assert record['code_fingerprint']==manifest['code_fingerprint']
            check=adjudication['records'][record['case_id']][condition]
            assert hashlib.sha256(path.read_bytes()).hexdigest()==check['report_sha256']
            report=record['job']['report_json']
            assert {x['issue_no'] for x in check['issues']}=={x['issue_no'] for x in (report or {}).get('issues',[])}
            if report:
                if condition=='knowledge_on':
                    assert report['versions']['kb_build_version']==manifest['knowledge_on_version']
                else:
                    assert report['versions']['kb_build_version']=='kb-none'
                    assert not (report.get('appendix',{}).get('knowledge_pack') or {}).get('evidence')
            saved[condition][record['case_id']]=record
        assert len(saved[condition])==10
    for identifier in saved['knowledge_on']:
        enabled=saved['knowledge_on'][identifier]['job']
        disabled=saved['knowledge_off'][identifier]['job']
        assert enabled['input_hash']==disabled['input_hash'],identifier
        assert enabled['request_payload']==disabled['request_payload'],identifier
    writer=_Sheets()
    overview=writer.sheet('对比总览',['项目','启用知识库','禁用知识库','说明'],[35,35,35,100])
    if manifest['mode']!='live':
        writer.append(overview,['仅限流程自检','Mock，不是真实模型评审','Mock，不是真实模型评审','不用于效果比较或用户验收。'])
    writer.append(overview,['实验对象','同一组10条带缺陷下单用例','同一组10条带缺陷下单用例','7条业务规则缺陷、3条通用质量缺陷；输入在评审前冻结。'])
    incomplete={c:[i for i,r in saved[c].items() if not full(r['job']['report_json'])] for c in saved}
    writer.append(overview,['不完整评审提醒',*['、'.join(incomplete[c]) or '无' for c in saved],
        '按实际盲评/投票人数核验完整性；即使原complete=true，人数不足也不计完整。本轮只执行一次，不追加预算挑选结果。'])
    writer.append(overview,['知识依据',manifest['knowledge_on_version'],'kb-none：不向模型提供知识','“数据库启用/禁用”在本实验中指知识库；任务存储数据库两组都启用。'])
    eligible=[case['case_id'] for case in dataset['cases'] if all(full(saved[c][case['case_id']]['job']['report_json'])
                                                               for c in saved)]
    for label,func,explanation in [
      ('已生成报告数',lambda c:sum(bool(r['job']['report_json']) for r in saved[c].values()),'包括带告警报告；失败单独列出。'),
      ('完整双模型评审数',lambda c:sum(full(r['job']['report_json']) for r in saved[c].values()),'complete=true且盲评2/2、投票2/2；不直接采用legacy full_participation。'),
      ('提出预埋主缺陷的用例数',lambda c:sum(adjudication['records'][i][c]['seed_detected'] for i in saved[c]),'逐条AI技术复核，含待复核问题；不等于独立人工准确率。'),
      ('主缺陷被原报告采纳的用例数',lambda c:sum(adopted_seed(r,adjudication['records'][i][c]) for i,r in saved[c].items()),'仅计与主缺陷对应且原报告status=adopted的问题；待确认、争议项不计入。不是人工批准数。'),
      ('发现总条数（含重复/额外项）',lambda c:sum(len((r['job']['report_json'] or {}).get('issues',[])) for r in saved[c].values()),'同一根因可能产生多条输出，不将每条输出当独立缺陷。'),
      ('完整配对子集检出数',lambda c:sum(adjudication['records'][i][c]['seed_detected'] for i in eligible),f'仅比较两组均完整的{len(eligible)}条。'),
      ('完整配对：主缺陷被采纳数',lambda c:sum(adopted_seed(saved[c][i],adjudication['records'][i][c]) for i in eligible),f'仅计两组均完整的{len(eligible)}条，且对应问题在原报告已采纳；不是人工批准数。'),
      ('预算耗尽的报告数',lambda c:sum(bool((r['job']['report_json'] or {}).get('appendix',{}).get('budget',{}).get('exhausted')) for r in saved[c].values()),'预算上限没有为获得更好结果而提高。'),
    ]:writer.append(overview,[label,func('knowledge_on'),func('knowledge_off'),explanation])
    for kind in ('业务规则','通用用例质量'):
        identifiers=[i for i,a in dataset['annotations'].items() if a['kind']==kind]
        writer.append(overview,[kind+'：主缺陷提出数',
            *[sum(adjudication['records'][i][c]['seed_detected'] for i in identifiers) for c in saved],
            f'共{len(identifiers)}条，含待确认或争议疑点；同一用例只计一次。'])
    for label,func,explanation in [
      ('聊天调用账面估算费用（元）',lambda r:sum(float(x['cost_actual'] if x['status']=='settled' else x['cost_reserved']) for x in r['budget_ledger']),
       '配置价格未核对供应商账单；不含向量查询费用，未知聊天调用保留预留。'),
      ('聊天Token（含未知预留）',lambda r:sum(x['tokens_actual'] if x['status']=='settled' else x['tokens_reserved'] for x in r['budget_ledger']),
       '含未结算调用的保守预留，不含向量查询Token。')]:
        writer.append(overview,[label,*[round(sum(func(r) for r in saved[c].values()),6) for c in saved],explanation])
    writer.append(overview,['模型','Qwen + DeepSeek','Qwen + DeepSeek','同一模型注册表、Prompt、Rubric和预算；Reranker两组均关闭。'])
    writer.append(overview,['结论边界','10条已知带缺陷样本','10条已知带缺陷样本','样本由开发者AI编写并复核，无独立盲标，不能计算真实误报率或外推整体准确率。'])
    compare=writer.sheet('逐条对比',['用例编号','用例标题','预埋主缺陷','正确行为 / 修正方向',
      '启用：AI结论','启用：主缺陷提出','启用：发现与建议','启用：目标规则检索','启用：完整性',
      '禁用：AI结论','禁用：主缺陷提出','禁用：发现与建议','禁用：完整性','对比分析'],
      [20,35,60,65,30,26,100,35,30,30,26,100,30,100])
    labels=writer.sheet('缺陷标注',['用例编号','缺陷类型','预埋缺陷','正确行为','相关规则','标注身份'],[20,25,85,95,40,30])
    reviewed=writer.sheet('逐条AI复核',['用例编号','条件','问题编号','判定','是否对应预埋主缺陷','理由','原报告SHA256'],
                          [20,22,12,30,26,100,68])
    for case in dataset['cases']:
        identifier=case['case_id'];annotation=dataset['annotations'][identifier]
        writer.append(labels,[identifier,annotation['kind'],annotation['defect'],annotation['correction'],annotation['rule_ids'],
                              'codex-delegated-reviewer（AI）'])
        columns=[]
        for condition in saved:
            record=saved[condition][identifier];report=record['job']['report_json'] or {}
            review=adjudication['records'][identifier][condition]
            c=report.get('review_completeness',{})
            completeness=f"{record['job']['status']}；盲评{c.get('blind','无')}、投票{c.get('vote','无')}；"+('完整' if full(report) else '不完整')
            finding_text='\n\n'.join(f"问题{x['issue_no']} [{x['severity']} / {x['status']}] {x['rationale']}\n建议：{x.get('suggestion') or '无'}" for x in report.get('issues',[]))
            if not report:finding_text='报告未生成，不能当作未发现缺陷。'
            elif not finding_text:finding_text='本轮未提出问题。'+('评审不完整，不能判定漏检。' if not full(report) else '')
            detected=('已提出，原报告已采纳' if adopted_seed(record,review) else
                      '已提出，仅待确认/争议' if review['seed_detected'] else '未提出')
            detected+=('（评审不完整）' if not full(report) else '')
            columns.extend([VERDICTS.get(report.get('ai_verdict'),'未形成结论'),detected,finding_text])
            if condition=='knowledge_on':
                docs={x['doc_id'] for x in (report.get('appendix',{}).get('knowledge_pack') or {}).get('evidence',[])}
                target=set(annotation['rule_ids'])
                columns.append('不依赖专门业务规则' if not target else ('已命中：'+','.join(sorted(docs&target)) if docs&target else '未检索到标注的目标规则'))
            columns.append(completeness)
            for issue in review['issues']:
                writer.append(reviewed,[identifier,'启用知识库' if condition=='knowledge_on' else '禁用知识库',issue['issue_no'],
                    issue['decision'],'是' if issue['seed_match'] else '否',issue['reason'],review['report_sha256']])
        writer.append(compare,[identifier,case['title'],annotation['defect'],annotation['correction'],*columns,
                               adjudication['records'][identifier]['comparison_note']])
        compare.row_dimensions[compare.max_row].height=150
    for condition in saved:
        group='启用' if condition=='knowledge_on' else '禁用'
        jobs=[job_from_saved(saved[condition][case['case_id']]['job']) for case in dataset['cases']]
        raw=load_workbook(BytesIO(render_excel(jobs,batch_id='paired-'+condition,total=10)))
        for title in ('评审汇总','问题明细','知识依据'):
            source=raw[title];headers=list(next(source.values))
            widths=[source.column_dimensions[source.cell(1,i).column_letter].width or 24 for i in range(1,len(headers)+1)]
            target=writer.sheet(group+'_'+title,headers,widths)
            for row in list(source.values)[1:]:
                values=list(row)
                if title=='评审汇总':
                    record=saved[condition][values[0]]
                    if not full(record['job']['report_json']):
                        counts=(record['job']['report_json'] or {}).get('review_completeness',{})
                        values[5]='不完整（按实际参与记录核验）'
                        values[16]=(values[16] or '')+f"\n导出核验：盲评{counts.get('blind','无')}、投票{counts.get('vote','无')}；原complete标志不代替实际人数。"
                writer.append(target,values)
        raw.close()
    source=load_workbook(ROOT/dataset['input_workbook'])
    sheet=source.active;headers=list(next(sheet.values));original=writer.sheet('原始用例',headers,[20,40,85,90,80,16,16,16])
    for row in list(sheet.values)[1:]:writer.append(original,list(row))
    source.close()
    config=writer.sheet('运行与限制',['项目','内容'],[38,120])
    writer.append(config,['运行ID',manifest['run_id']]);writer.append(config,['代码指纹',manifest['code_fingerprint']])
    writer.append(config,['输入工作簿SHA256',dataset['input_sha256']]);writer.append(config,['两组同一输入SHA256',dataset['case_input_sha256']])
    writer.append(config,['知识库禁用方式','禁用组创建任务时不解析/加载知识，冻结为kb-none；共同执行器严格按任务快照工作，不向禁用组提供知识片段。'])
    writer.append(config,['分配方法','每条用例成对安排；同一对内的条件顺序由固定种子20261113随机决定；并发2。'])
    writer.append(config,['缺陷标签隔离','模型看不到预埋缺陷、标注答案及两组比较标签；用例业务输入完全相同。'])
    writer.append(config,['复核身份','AI开发者同时编写用例与技术复核，不是独立人工盲标。'])
    writer.append(config,['完整性核验','本对比须complete=true、盲评2/2、投票2/2同时满足才计完整；原始JSON保留不改写。原报告采纳状态在不完整任务中也不代表投票完成。'])
    writer.append(config,['模型注册表说明','配置models可能包含未启用的jury_b；本轮为双模型，实际调用以每份原始结果的model_runs为准。'])
    writer.append(config,['业务接口执行','本实验评审测试用例文字，没有向MiniShop业务服务实际下单。'])
    writer.append(config,['存储数据库','两组均使用同一独立PostgreSQL临时库；本机应用库未改动；临时库清理状态：'+str(manifest['temporary_database_removed'])])
    if adjudication.get('fact_verification'):
        writer.append(config,['事实核验记录',adjudication['fact_verification']])
    for name,value in manifest['config'].items():writer.append(config,[name,value])
    for sheet in writer.book:
        sheet.sheet_properties.tabColor='254EDB' if sheet.title.startswith('启用') else '7B8798' if sheet.title.startswith('禁用') else '228867'
        sheet.sheet_view.zoomScale=80
        sheet.print_options.horizontalCentered=True
        sheet.page_setup.orientation='landscape'
        sheet.page_setup.paperSize=sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0
        sheet.sheet_properties.pageSetUpPr.fitToPage=True
        sheet.print_title_rows='1:1'
        for row in sheet.iter_rows(min_row=2):
            lines=1
            for cell in row:
                width=max(8,(sheet.column_dimensions[cell.column_letter].width or 24)-2)
                wrapped=sum(max(1,math.ceil(sum(2 if unicodedata.east_asian_width(ch) in 'WF' else 1
                            for ch in line)/width)) for line in str(cell.value or '').split('\n'))
                lines=max(lines,wrapped)
            sheet.row_dimensions[row[0].row].height=min(390,max(36,lines*15+12))
    compare.sheet_properties.tabColor='D28B19'
    compare.freeze_panes='C2'
    for cell in compare[1]:cell.font=Font(name='Microsoft YaHei',bold=True,color='FFFFFF')
    for col in range(5,10):compare.cell(1,col).fill=PatternFill('solid',fgColor='254EDB')
    for col in range(10,14):compare.cell(1,col).fill=PatternFill('solid',fgColor='66768A')
    default_name=('MiniShop_下单10条缺陷用例_知识库启用禁用评审对比.xlsx' if manifest['mode']=='live'
                  else 'Mock_流程自检_非实际评审.xlsx')
    output=args.output or args.run.parents[1]/default_name
    output.write_bytes(writer.save())
    check=load_workbook(output)
    assert check['逐条对比'].max_row==11 and check['缺陷标注'].max_row==11
    assert all(cell.data_type!='f' for sheet in check for row in sheet for cell in row)
    for condition in saved:
        sheet=check[('启用' if condition=='knowledge_on' else '禁用')+'_评审汇总']
        assert sheet.max_row==11
    check.close()
    receipt={'passed':True,'mode':manifest['mode'],'run_id':manifest['run_id'],'cases':10,'reports':manifest['reports'],
             'complete_pairs':len(eligible),'output':output.relative_to(ROOT).as_posix() if output.is_absolute() else output.as_posix(),
             'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'all_cells_nonformula':True,
             'independent_human_validation':False}
    (args.run/'workbook-validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(receipt,ensure_ascii=False))


if __name__=='__main__':main()
