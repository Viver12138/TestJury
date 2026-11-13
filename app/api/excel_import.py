"""Excel upload preview; actual review uses the existing batch queue."""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.core.auth import Principal, ensure_roles, get_principal
from app.services.excel_import import MAX_BYTES, parse_workbook, template_workbook

router = APIRouter(prefix="/v1/imports", tags=["excel"])


@router.get("/excel-template")
async def excel_template():
    data = await run_in_threadpool(template_workbook)
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="TestJury-template.xlsx"'})


@router.post("/excel")
async def preview_excel(file: UploadFile = File(...), principal: Principal = Depends(get_principal)):
    ensure_roles(principal, "reviewer")
    try:
        data = await file.read(MAX_BYTES + 1)
        return await run_in_threadpool(parse_workbook, data, file.filename or "")
    finally:
        await file.close()
