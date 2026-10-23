from datetime import date
import unicodedata

import pytest

from app.formatter import format_text, format_title, split_report_header
from app.parser import parse_message
from app.validator import absence_count, validate


SAMPLE = """user nhập Lớp 12C9 vắng 3
Nhật Huy (P)
Tuấn Huy (P)
Duy Hải (K)
12c11 vắng 1 phương thảo
12C3 vắng Tuấn Anh(K),Minh Trí(P), Khánh Nguyên (K), Thanh Huy(P), Trung Nghĩa (P), Duy Thành (P)
12c2 sĩ số40 văng 0
10C6 Vắng  4K Thanh Luân, Minh Nhật, Gia Tuấn, Quốc Huy 1P Huy Hoàng
10C5 Vắng  1K Quang Thanh
12C17 Vắng  Trúc Vy, Mai Phương Uyên (P), Thu Hương (P)"""


@pytest.fixture
def sample_records():
    return {record["ten_lop"]: record for record in parse_message(SAMPLE)["lop"]}


@pytest.mark.parametrize("code,expected", [
    ("12C9", [("Nhật Huy", "P"), ("Tuấn Huy", "P"), ("Duy Hải", "K")]),
    ("12C11", [("Phương Thảo", None)]),
    ("12C3", [("Tuấn Anh", "K"), ("Minh Trí", "P"), ("Khánh Nguyên", "K"),
              ("Thanh Huy", "P"), ("Trung Nghĩa", "P"), ("Duy Thành", "P")]),
    ("12C2", []),
    ("10C6", [("Thanh Luân", "K"), ("Minh Nhật", "K"), ("Gia Tuấn", "K"), ("Quốc Huy", "K"), ("Huy Hoàng", "P")]),
    ("10C5", [("Quang Thanh", "K")]),
    ("12C17", [("Trúc Vy", None), ("Mai Phương Uyên", "P"), ("Thu Hương", "P")]),
])
def test_every_sample_class(sample_records, code, expected):
    record = sample_records[code]
    assert [(s["ten"], s["loai"]) for s in record["hoc_sinh"]] == expected
    assert absence_count(record) == len(expected)


def test_sample_size_and_warning_details(sample_records):
    assert sample_records["12C2"]["si_so"] == 40
    assert sample_records["10C6"]["so_vang_khai_bao"] == 5
    result = validate(parse_message(SAMPLE), list(sample_records))
    unclear = {w["class_name"] for w in result["warnings"] if w["code"] == "unknown_status"}
    assert unclear == {"12C11", "12C17"}
    assert any(w["raw"] == "user nhập" for w in result["warnings"])
    assert not any(w["code"] == "count_mismatch" for w in result["warnings"])


def test_exact_sample_output(sample_records):
    data = validate(parse_message(SAMPLE), list(sample_records))["data"]
    assert format_text(data, "Chiều", date(2026, 10, 23), 1) == """Chiều thứ 6, ngày 23/10/2026, ca 1:
10C5 Vắng  1 Quang Thanh (K)
10C6 Vắng  5 Thanh Luân (K), Minh Nhật (K), Gia Tuấn (K), Quốc Huy (K), Huy Hoàng (P)

12C2 Vắng  0
12C3 Vắng  6 Tuấn Anh (K), Minh Trí (P), Khánh Nguyên (K), Thanh Huy (P), Trung Nghĩa (P), Duy Thành (P)
12C9 Vắng  3 Nhật Huy (P), Tuấn Huy (P), Duy Hải (K)
12C11 Vắng  1 Phương Thảo (?)
12C17 Vắng  3 Trúc Vy (?), Mai Phương Uyên (P), Thu Hương (P)"""


@pytest.mark.parametrize("size", ["sĩ số 40", "sĩ số40", "ss 40", "si so 40", "SĨ SỐ:40"])
def test_size_variants(size):
    record = parse_message(f"Lớp 10 C 6 {size} văng 0")["lop"][0]
    assert (record["ten_lop"], record["si_so"], record["so_vang_khai_bao"]) == ("10C6", 40, 0)
    assert record["hoc_sinh"] == []


def test_group_override_separators_and_unknown():
    record = parse_message("12 C9 vang 3K nhật huy ( p ) tuấn huy(K), duy hải (?) 1P thu hương")["lop"][0]
    assert [s["loai"] for s in record["hoc_sinh"]] == ["P", "K", None, "P"]
    assert [g["thuc_te"] for g in record["groups"]] == [3, 1]
    assert record["so_vang_khai_bao"] == 4


def test_group_status_does_not_reset_at_newline():
    record = parse_message("10C6 vắng 3K An\nBình; Chi 1P Dung")["lop"][0]
    assert [s["loai"] for s in record["hoc_sinh"]] == ["K", "K", "K", "P"]


def test_duplicate_keeps_latest_only():
    data = parse_message("12C9 vắng 1 An (K)\n12c9 vắng 0\n12 C9 vắng 1 bình(p)")
    assert len(data["lop"]) == 1
    assert data["lop"][0]["hoc_sinh"] == [{"ten": "Bình", "loai": "P"}]
    warnings = validate(data, ["12C9"])["warnings"]
    assert len(warnings) == 1 and warnings[0]["code"] == "overwritten"
    assert data["lop"][0]["overwritten"] == 2


def test_mismatch_unknown_and_no_information():
    data = parse_message("12C9 vắng 3 An(P), Bình\n10C10 Vắng\n11C1 vắng 2")
    result = validate(data, ["12C9", "10C10", "10C2"])
    codes = {w["code"] for w in result["warnings"]}
    assert {"count_mismatch", "unknown_status", "no_information", "missing", "unknown_class"} <= codes
    lines = format_text(result["data"], "Sáng", date(2026, 10, 25), 2).splitlines()
    assert "12C9 Vắng  2 An (P), Bình (?)" in lines
    assert "11C1 Vắng  2" in lines  # thiếu tên không được biến thành 0
    assert "10C2 Vắng  " in lines
    assert "10C10 Vắng  " in lines


def test_natural_sort_and_grade_separator():
    data = validate(parse_message("12C2 vắng 0 10C10 vắng 0 10C4 vắng 0 10C2 vắng 0 11C1 vắng 0"),
                    ["12C2", "10C10", "10C4", "10C2", "11C1"])["data"]
    assert [r["ten_lop"] for r in data["lop"]] == ["10C2", "10C4", "10C10", "11C1", "12C2"]
    assert format_text(data, "Chiều", date(2026, 10, 23), 1).count("\n\n") == 2


def test_unrecognized_preserved_and_false_class_not_matched():
    text = "abc110C6\nNội dung chưa có mã lớp"
    assert parse_message(text) == {"lop": [], "unrecognized": [text]}
    data = parse_message("12C9 vắng 1 An (P)\n??? https://example.org")
    assert data["lop"][0]["unrecognized"] == ["??? https://example.org"]


def test_unicode_decomposed_and_crlf():
    data = parse_message(unicodedata.normalize("NFD", "Lớp 12c9 vắng 1\r\nnhật huy(p)"))
    assert data["lop"][0]["hoc_sinh"] == [{"ten": "Nhật Huy", "loai": "P"}]


def test_group_declared_mismatch():
    result = validate(parse_message("10C6 vắng 4K An, Bình 1P Chi"), ["10C6"])
    assert {w["code"] for w in result["warnings"]} == {"count_mismatch", "group_mismatch"}


def test_sunday_and_edited_header():
    assert format_title("Sáng", date(2026, 10, 25), 3) == "Sáng Chủ nhật, ngày 25/10/2026, ca 3"
    body, meta = split_report_header("Chiều thứ 6, ngày 23/10/2026, ca 1:\n12C2 Vắng  0")
    assert body == "12C2 Vắng  0"
    assert meta == {"buoi": "Chiều", "ngay": date(2026, 10, 23), "ca": 1}


def test_validation_is_pure():
    data = parse_message("12C9 vắng 0")
    first = validate(data, ["12C9", "12C2"])
    second = validate(data, ["12C9", "12C2"])
    assert first == second
    assert len(data["lop"]) == 1

