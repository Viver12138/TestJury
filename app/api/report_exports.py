"""Download existing single/batch reports as Excel workbooks."""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_principal, get_storage
from app.core.auth import Principal
from app.core.errors import ApiError, ErrorCode
from app.services.excel_report import MIME, render_excel
from app.storage.port import Storage

router = APIRouter(prefix="/v1", tags=["reports"])


def _response(data: bytes, filename: str) -> Response:
    return Response(data, media_type=MIME, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})


@router.get("/reviews/{review_id}/report.xlsx")
async def single_excel(review_id: str, principal: Principal = Depends(get_principal),
                       storage: Storage = Depends(get_storage)):
    job = await storage.get_job(review_id)
    if job is None:
        raise ApiError(ErrorCode.NOT_FOUND, "评审任务不存在")
    if not job.report_json:
        raise ApiError(ErrorCode.NOT_FOUND, "报告尚未生成")
    return _response(await run_in_threadpool(render_excel, [job]), "TestJury-report.xlsx")


@router.get("/review-batches/{batch_id}/report.xlsx")
async def batch_excel(batch_id: str, principal: Principal = Depends(get_principal),
                      storage: Storage = Depends(get_storage)):
    batch = await storage.get_batch(batch_id)
    if batch is None:
        raise ApiError(ErrorCode.NOT_FOUND, "批次不存在")
    jobs = await storage.list_jobs(batch_id=batch_id, limit=500)
    data = await run_in_threadpool(render_excel, jobs, batch_id=batch_id, total=batch.total)
    return _response(data, "TestJury-batch-report.xlsx")
