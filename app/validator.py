"""Chuẩn bị danh sách lớp và sinh cảnh báo; không làm thay đổi dữ liệu gốc."""

from copy import deepcopy
import re

from .models import normalize_class
from .parser import deduplicate


def class_sort_key(record: dict) -> tuple:
    grade, letter, number = re.fullmatch(r"(10|11|12)([A-Z])(\d+)", record["ten_lop"]).groups()
    return int(grade), int(number), letter


def absence_count(record: dict) -> int | None:
    if record["hoc_sinh"] or record.get("excluded_late"):
        return len(record["hoc_sinh"])
    # Không biến báo thiếu tên thành Vắng 0: giữ số khai báo, kèm cảnh báo.
    return record["so_vang_khai_bao"]


def validate(data: dict, configured_classes: list[str]) -> dict:
    data = deepcopy(data)
    classes = list(dict.fromkeys(normalize_class(code) for code in configured_classes))
    records = deduplicate(data.get("lop", []))
    seen = {record["ten_lop"] for record in records}
    for code in classes:
        if code not in seen:
            records.append({"ten_lop": code, "si_so": None, "so_vang_khai_bao": None,
                            "hoc_sinh": [], "reported": False})
    records.sort(key=class_sort_key)
    warnings = []

    def warn(code, message, class_name=None, raw=None):
        warnings.append({"code": code, "class_name": class_name, "message": message, "raw": raw})

    for record in records:
        code = record["ten_lop"]
        count = len(record["hoc_sinh"])
        declared = record["so_vang_khai_bao"]
        if not record.get("reported", True):
            warn("missing", "Chưa báo.", code)
        elif not count and declared is None and not record.get("excluded_late"):
            warn("no_information", "Có mã lớp nhưng chưa có thông tin vắng.", code)
        if classes and code not in classes:
            warn("unknown_class", "Mã lớp không có trong config.json; kiểm tra lại.", code)
        if declared is not None and declared != count:
            warn("count_mismatch", f"Khai báo {declared} vắng nhưng liệt kê {count} tên.", code)
        unclear = [student["ten"] for student in record["hoc_sinh"] if student["loai"] is None]
        if unclear:
            warn("unknown_status", "Chưa rõ P/K: " + ", ".join(unclear) + ".", code)
        if record.get("defaulted_k"):
            warn("default_k", "Không ghi P/K, mặc định K: " + ", ".join(record["defaulted_k"]) + ".", code)
        if record.get("overwritten", 0):
            warn("overwritten", f"Đã ghi đè {record['overwritten']} lần; dùng lần báo cuối cùng.", code)
        for group in record.get("groups", []):
            if group["khai_bao"] is not None and group["khai_bao"] != group["thuc_te"]:
                warn("group_mismatch", f"Nhóm {group['khai_bao']}{group['loai']} có {group['thuc_te']} tên.", code)
        for fragment in record.get("unrecognized", []):
            warn("unrecognized", "Đoạn chưa nhận diện được; kiểm tra bản gốc.", code, fragment)
        for note in record.get("parse_notes", []):
            warn("ambiguous", note, code)
        if record["si_so"] is not None and (absence_count(record) or 0) > record["si_so"]:
            warn("exceeds_size", "Số vắng lớn hơn sĩ số.", code)
    for fragment in data.get("unrecognized", []):
        warn("unassigned", "Đoạn không thuộc lớp nào; cần kiểm tra.", raw=fragment)
    return {"data": {"lop": records, "unrecognized": data.get("unrecognized", [])},
            "warnings": warnings}

