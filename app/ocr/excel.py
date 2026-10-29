"""Đọc danh sách học sinh từ file Excel có sẵn, ghép với dữ liệu OCR, ghi điểm."""
from __future__ import annotations

import datetime as dt
import re
import os
import shutil
import subprocess
import tempfile
from difflib import SequenceMatcher

import openpyxl

from .printed import norm_date, norm_name

HEADER_KEYS = {
    "ho_ten": ["HỌ VÀ TÊN", "HỌ TÊN"],
    "ngay_sinh": ["NGÀY SINH"],
    "lop": ["LỚP HỌC", "LỚP"],
    "sbd": ["SBD", "SỐ BÁO DANH"],
    "phong": ["PHÒNG"],
}


def ensure_xlsx(path: str) -> str:
    """openpyxl không mở được .xls -> chuyển sang .xlsx bằng LibreOffice (nếu có)."""
    if not path.lower().endswith(".xls"):
        return path
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        for p in [r"C:\Program Files\LibreOffice\program\soffice.exe",
                  r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                  "/Applications/LibreOffice.app/Contents/MacOS/soffice"]:
            if os.path.exists(p):
                exe = p
                break
    if not exe:
        raise RuntimeError("File .xls cũ: hãy mở bằng Excel và 'Lưu thành' .xlsx, "
                           "hoặc cài LibreOffice để chương trình tự chuyển.")
    out = tempfile.mkdtemp()
    subprocess.run([exe, "--headless", "--convert-to", "xlsx", "--outdir", out, path],
                   check=True, capture_output=True, timeout=180)
    base = os.path.splitext(os.path.basename(path))[0] + ".xlsx"
    return os.path.join(out, base)


def _cell_str(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%d/%m/%Y")
    return str(v).strip()


def find_header(ws, max_scan: int = 30):
    """Tìm dòng tiêu đề chứa 'Họ và tên' và trả về (dòng, {khoá: cột}, {tên môn: cột})."""
    for r in range(1, min(ws.max_row, max_scan) + 1):
        vals = {c.column: _cell_str(c.value).upper() for c in ws[r] if c.value is not None}
        if not any(v in HEADER_KEYS["ho_ten"] for v in vals.values()):
            continue
        cols = {}
        for key, names in HEADER_KEYS.items():
            for col, v in vals.items():
                if v in names and key not in cols:
                    cols[key] = col
        # các cột môn học: nằm sau cột "Phòng" (nếu có) hoặc là cột cuối
        start = cols.get("phong", max(vals))
        subjects = {v: col for col, v in sorted(vals.items()) if col > start}
        return r, cols, subjects
    raise ValueError(f"Sheet '{ws.title}': không tìm thấy dòng tiêu đề có 'Họ và tên'.")


def load_students(ws):
    hr, cols, subjects = find_header(ws)
    students = []
    for r in range(hr + 1, ws.max_row + 1):
        name = _cell_str(ws.cell(r, cols["ho_ten"]).value)
        if not name or name.startswith("="):
            continue
        students.append({
            "row": r,
            "ho_ten": name,
            "ngay_sinh": _cell_str(ws.cell(r, cols["ngay_sinh"]).value) if "ngay_sinh" in cols else "",
            "lop": _cell_str(ws.cell(r, cols["lop"]).value) if "lop" in cols else "",
            "sbd": _cell_str(ws.cell(r, cols["sbd"]).value) if "sbd" in cols else "",
            "phong": _cell_str(ws.cell(r, cols["phong"]).value) if "phong" in cols else "",
        })
    for s in students:
        s["_n"], s["_d"] = norm_name(s["ho_ten"]), norm_date(s["ngay_sinh"])
    return students, hr, cols, subjects


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def match(ocr_row: dict, students: list[dict]):
    """Trả về (học sinh khớp nhất, độ tin cậy 0..1, ghi chú).
    Khoá chính: ngày sinh + họ tên (SBD trên phiếu có thể KHÁC SBD trong Excel)."""
    n, d = norm_name(ocr_row.get("ho_ten", "")), norm_date(ocr_row.get("ngay_sinh", ""))
    lop = (ocr_row.get("lop") or "").upper()
    best, best_score = None, -1.0
    for s in students:
        score = 0.55 * _sim(n, s["_n"])
        if d and d == s["_d"]:
            score += 0.35
        if lop and lop == s["lop"].upper():
            score += 0.10
        if score > best_score:
            best, best_score = s, score
    note = ""
    if best is not None:
        if d and d != best["_d"]:
            note = "Ngày sinh không khớp"
        elif lop and re.fullmatch(r"\d{2}[A-Z]\d{1,2}", lop) and lop != best["lop"].upper():
            note = "Lớp không khớp"
    return best, round(best_score, 3), note


def write_scores(xlsx_in: str, xlsx_out: str, sheet: str, col: int, items: list[tuple[int, object]]):
    """items: [(dòng excel, giá trị)]. Giữ nguyên định dạng/công thức khác của file."""
    wb = openpyxl.load_workbook(xlsx_in)
    ws = wb[sheet]
    for r, v in items:
        ws.cell(r, col).value = v
    wb.save(xlsx_out)
