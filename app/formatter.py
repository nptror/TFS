"""Định dạng text và đọc lại tiêu đề do người dùng sửa."""

from datetime import date
import re

from .validator import absence_count, class_sort_key


HEADER_RE = re.compile(
    r"^\s*(Sáng|Chiều)\s+(?:thứ\s+[2-7]|Chủ\s+nhật),\s*ngày\s+"
    r"(\d{1,2})/(\d{1,2})/(\d{4}),\s*ca\s+(\d+)\s*:?\s*$", re.I
)


def format_title(buoi: str, ngay: date, ca: int) -> str:
    weekday = "Chủ nhật" if ngay.weekday() == 6 else f"thứ {ngay.weekday() + 2}"
    return f"{buoi} {weekday}, ngày {ngay:%d/%m/%Y}, ca {ca}"


def format_class(record: dict) -> str:
    count = absence_count(record)
    line = f"{record['ten_lop']} Vắng  {'' if count is None else count}"
    if record["hoc_sinh"]:
        line += " " + ", ".join(f"{s['ten']} ({s['loai'] or '?'})" for s in record["hoc_sinh"])
    return line


def format_text(data: dict, buoi: str, ngay: date, ca: int) -> str:
    lines = [format_title(buoi, ngay, ca) + ":"]
    last_grade = None
    for record in sorted(data["lop"], key=class_sort_key):
        grade = record["ten_lop"][:2]
        if last_grade is not None and grade != last_grade:
            lines.append("")
        lines.append(format_class(record))
        last_grade = grade
    return "\n".join(lines)


def split_report_header(text: str) -> tuple[str, dict | None]:
    lines = text.lstrip().splitlines()
    if not lines:
        return text, None
    match = HEADER_RE.fullmatch(lines[0])
    if match:
        buoi, day, month, year, ca = match.groups()
        parsed_date = date(int(year), int(month), int(day))
        if not 1 <= int(ca) <= 99:
            raise ValueError("Ca trong tiêu đề phải từ 1 đến 99.")
        return "\n".join(lines[1:]), {"buoi": buoi.capitalize(), "ngay": parsed_date, "ca": int(ca)}
    if re.match(r"\s*(Sáng|Chiều)\s+", lines[0], re.I):
        raise ValueError("Tiêu đề chưa đúng mẫu. Ví dụ: Chiều thứ 6, ngày 23/10/2026, ca 1:")
    return text, None

