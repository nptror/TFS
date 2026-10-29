"""FastAPI routes và điều phối. Chạy: uvicorn app.main:app --reload."""

from datetime import date
import json
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Form, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import ValidationError

from . import nhapdiem
from .excel_export import export_excel, export_filename
from .formatter import format_text, split_report_header
from .models import ExportRequest, ParsedReport, normalize_class
from .parser import parse_message
from .validator import absence_count, validate


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
app = FastAPI(title="Tổng hợp báo vắng", version="1.0.0")
app.include_router(nhapdiem.router)


@app.exception_handler(RequestValidationError)
async def request_validation_error(request, error):
    if request.url.path.startswith("/api/nhapdiem"):
        return JSONResponse(status_code=422, content={"detail": "Thiếu file Excel/PDF hoặc chưa chọn sheet và môn."})
    return JSONResponse(status_code=422, content={"detail":
        "Dữ liệu chưa hợp lệ. Kiểm tra buổi, ngày, ca (1–99) và độ dài nội dung."})


def read_classes() -> list[str]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
        classes = config["classes"]
        if not isinstance(classes, list) or len(classes) > 500:
            raise ValueError("Invalid class list")
        return list(dict.fromkeys(normalize_class(code) for code in classes))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise HTTPException(500, "Không đọc được danh sách lớp. Kiểm tra config.json có mảng classes hợp lệ.") from error


def checked_data(data: dict) -> dict:
    try:
        return ParsedReport.model_validate(data).model_dump()
    except ValidationError as error:
        raise HTTPException(422, "Dữ liệu vượt giới hạn hoặc có tên/mã lớp không hợp lệ. Hãy kiểm tra đầu vào.") from error


def make_result(data: dict, buoi: str, ngay: date, ca: int) -> dict:
    result = validate(checked_data(data), read_classes())
    records = result["data"]["lop"]
    result["text"] = format_text(result["data"], buoi, ngay, ca)
    result["session"] = {"buoi": buoi, "ngay": ngay.isoformat(), "ca": ca}
    result["summary"] = {
        "reported": sum(r.get("reported", True) for r in records),
        "classes": len(records),
        "absent": sum(absence_count(r) or 0 for r in records),
        "warnings": len(result["warnings"]),
    }
    return result


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(ROOT / "app" / "static" / "index.html")


@app.get("/api/config")
def get_config():
    return {"classes": read_classes()}


@app.post("/api/format")
async def format_report(
    buoi: Annotated[Literal["Sáng", "Chiều"], Form()],
    ngay: Annotated[date, Form()],
    ca: Annotated[int, Form(ge=1, le=99)],
    text: Annotated[str, Form(max_length=100000)] = "",
):
    if not text.strip():
        raise HTTPException(400, "Hãy dán tin nhắn cần chuẩn hóa.")
    return make_result(parse_message(text), buoi, ngay, ca)


def prepare_edited_report(payload: ExportRequest) -> dict:
    try:
        body, header = split_report_header(payload.text)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    data = parse_message(body)
    if not data["lop"]:
        raise HTTPException(400, "Bản kết quả chưa có mã lớp hợp lệ để xuất.")
    source = {r.ten_lop: r.model_dump() for r in payload.source_data.lop} if payload.source_data else {}
    for record in data["lop"]:
        original = source.get(record["ten_lop"])
        if original:
            # Mẫu text không hiện sĩ số: giữ sĩ số gốc trừ khi được sửa rõ trong text.
            if record["si_so"] is None:
                record["si_so"] = original["si_so"]
            unchanged = (record["hoc_sinh"] == original["hoc_sinh"]
                         and record["so_vang_khai_bao"] == absence_count(original)
                         and record["si_so"] == original["si_so"]
                         and not record.get("unrecognized") and not record.get("parse_notes")
                         and not record.get("overwritten"))
            if unchanged:
                for key in ("so_vang_khai_bao", "reported", "overwritten", "groups", "unrecognized", "parse_notes", "excluded_late"):
                    record[key] = original[key]
        # Dòng trống theo mẫu có ý nghĩa là chưa báo, kể cả nhập trực tiếp.
        if not record["hoc_sinh"] and record["so_vang_khai_bao"] is None and not record.get("excluded_late"):
            record["reported"] = False
    if payload.source_data:
        # Giữ phần ngoài lớp từ đầu vào để Excel không âm thầm bỏ mất cảnh báo.
        data["unrecognized"] = list(dict.fromkeys(data["unrecognized"] + payload.source_data.unrecognized))
    session = header or {"buoi": payload.buoi, "ngay": payload.ngay, "ca": payload.ca}
    return make_result(data, **session)


@app.post("/api/preview")
def preview_report(payload: ExportRequest):
    """Kiểm tra lại bản sửa tay mà không gọi AI hoặc ghi đè textarea."""
    return prepare_edited_report(payload)


@app.post("/api/export")
def download_excel(payload: ExportRequest):
    result = prepare_edited_report(payload)
    session = result["session"]
    session["ngay"] = date.fromisoformat(session["ngay"])
    workbook = export_excel(result["data"], result["warnings"], **session)
    filename = export_filename(**session)
    return StreamingResponse(workbook, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})
