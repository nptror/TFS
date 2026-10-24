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
    ("12C11", [("Phương Thảo", "K")]),
    ("12C3", [("Tuấn Anh", "K"), ("Minh Trí", "P"), ("Khánh Nguyên", "K"),
              ("Thanh Huy", "P"), ("Trung Nghĩa", "P"), ("Duy Thành", "P")]),
    ("12C2", []),
    ("10C6", [("Thanh Luân", "K"), ("Minh Nhật", "K"), ("Gia Tuấn", "K"), ("Quốc Huy", "K"), ("Huy Hoàng", "P")]),
    ("10C5", [("Quang Thanh", "K")]),
    ("12C17", [("Trúc Vy", "K"), ("Mai Phương Uyên", "P"), ("Thu Hương", "P")]),
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
    assert unclear == set()
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
12C11 Vắng  1 Phương Thảo (K)
12C17 Vắng  3 Trúc Vy (K), Mai Phương Uyên (P), Thu Hương (P)"""


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
    assert {"count_mismatch", "no_information", "missing", "unknown_class"} <= codes
    lines = format_text(result["data"], "Sáng", date(2026, 10, 25), 2).splitlines()
    assert "12C9 Vắng  2 An (P), Bình (K)" in lines
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


def test_user_real_world_case():
    raw_text = """Lớp 12C9 vắng 3
Nhật Huy (P)
Tuấn Huy (P)
Duy Hải (K)
12c11 vắng 1 phương thảo
12C3 vắng Tuấn Anh(K),Minh Trí(P), Khánh Nguyên (K), Thanh Huy(P), Trung Nghĩa (P), Duy Thành (P)
12c2 sĩ số40 văng 0
Lớp: 12C17
Sĩ số: 43
Vắng: Trúc Vy, Mai Phương Uyên (P), Thu Hương (P), Bảo Khanh (T)
12c8 vắng 0
12c16
v 1 lưu văn phát(p)
12c19
v:0
Lớp 10c4 vắng thịnh (p)
Dạ em gửi 10c6 ạ
10c2 đủ ạ
10C8 đi đủ ạ"""
    config_classes = [
        "10C2", "10C4", "10C5", "10C6", "10C10",
        "12C2", "12C3", "12C8", "12C9", "12C11", "12C12", "12C16", "12C17", "12C18"
    ]
    parsed = parse_message(raw_text)
    records = {r["ten_lop"]: r for r in parsed["lop"]}

    # 10C2 báo đủ ạ -> vắng 0, không có học sinh Đủ Ạ
    assert records["10C2"]["so_vang_khai_bao"] == 0
    assert records["10C2"]["hoc_sinh"] == []

    # 10C4 vắng thịnh (p) -> không bị dính "Dạ Em Gửi"
    assert len(records["10C4"]["hoc_sinh"]) == 1
    assert records["10C4"]["hoc_sinh"][0]["ten"] == "Thịnh"
    assert records["10C4"]["hoc_sinh"][0]["loai"] == "P"

    # 10C6 chỉ gửi "Dạ em gửi 10c6 ạ" -> không có học sinh tên Ạ
    assert records["10C6"]["hoc_sinh"] == []

    # 10C8 đi đủ ạ -> vắng 0
    assert records["10C8"]["so_vang_khai_bao"] == 0
    assert records["10C8"]["hoc_sinh"] == []

    # 12C16 v 1 lưu văn phát(p) -> 1 vắng, tên Lưu Văn Phát (P), không có chữ V
    assert records["12C16"]["so_vang_khai_bao"] == 1
    assert records["12C16"]["hoc_sinh"] == [{"ten": "Lưu Văn Phát", "loai": "P"}]

    # 12C19 v:0 -> vắng 0, không có học sinh tên V
    assert records["12C19"]["so_vang_khai_bao"] == 0
    assert records["12C19"]["hoc_sinh"] == []

    # 12C17 -> 3 vắng; Bảo Khanh (T) là đi trễ, không tính vào số vắng.
    assert records["12C17"]["si_so"] == 43
    assert len(records["12C17"]["hoc_sinh"]) == 3
    assert records["12C17"]["excluded_late"] == ["Bảo Khanh"]

    # Kiểm tra validate
    result = validate(parsed, config_classes)
    formatted = format_text(result["data"], "Sáng", date(2026, 10, 24), 1)

    assert "10C2 Vắng  0" in formatted
    assert "10C4 Vắng  1 Thịnh (P)" in formatted
    assert "10C8 Vắng  0" in formatted
    assert "12C16 Vắng  1 Lưu Văn Phát (P)" in formatted
    assert "12C17 Vắng  3 Trúc Vy (K), Mai Phương Uyên (P), Thu Hương (P)" in formatted
    assert "12C19 Vắng  0" in formatted

    # Cảnh báo không còn các cảnh báo sai/rác
    warning_msgs = [f"{w.get('class_name')}: {w['message']}" for w in result["warnings"]]
    for msg in warning_msgs:
        assert "Đủ Ạ" not in msg
        assert "Dạ Em Gửi" not in msg
        assert ": Ạ" not in msg
        assert "Đi Đủ Ạ" not in msg
        assert "Chưa rõ P/K: V" not in msg
        assert "Khai báo 0 vắng nhưng liệt kê 1 tên" not in msg


def test_user_zalo_chat_and_numbering_cases():
    user_input = """Lớp 11c1 vắng2 1 tấn phát 2. Nhật uy
10C8 đi đủ
10c10 đủ
10C5 vắng 1: Quang Thang (K)
Lớp 10c4 đủ ạ
Lớp 10c3 đủ ạ
[24/10/2026 07:19:35] Nguyễn Quốc khánh: 12c13 
Vắng 0
[24/10/2026 07:24:32] Quỳnh Vân: Lớp: 12C17
Sĩ số: 43
Vắng: Trúc Vy, Thụy Quỳnh Anh (P)
[24/10/2026 07:27:48] Thế Dân: 12c2 sĩ số 40 vắng0
[24/10/2026 07:48:45] Thanh Nhàn: 12C12
vắng 6
Trần Nguyễn Minh Anh ( P )
Nguyễn Thị Thu Ngân ( P )
Hồ Trần Minh An ( P ) 
Lê Thị Ngọc Huyền ( P )
Phạm Hoàng Nguyên
Võ Quốc Hiếu
[24/10/2026 08:55:00] Hân: 12c8 vắng 
Quốc Bảo(p)
[24/10/2026 09:26:16] Minh Quân: Lớp: 12C18
Sĩ số : 32 
Vắng không phép : (6)Vũ Tuấn Anh, Nguyễn xuân Duy,Trần Vũ Huy,Võ Phương Trà My,Phạm Quyết Tiến,Phạm Vũ Ngọc Trâm
Trễ :(2)  Nguyễn Huy Kiệt, Nguyễn Phan Đăng Khoa
[24/10/2026 09:43:10] Thái Anh Thư: 12C14
Vắng 1
Ngọc Mai (P)
[24/10/2026 09:48:01] Vinh Quang: 12c7 v3 quỳnh như(p),thanh trúc(p),thùy trâm(p)"""

    parsed = parse_message(user_input)
    records = {r["ten_lop"]: r for r in parsed["lop"]}

    # 1. 11C1: vắng2 + số thứ tự 1 tấn phát 2. Nhật uy
    assert records["11C1"]["so_vang_khai_bao"] == 2
    assert [(s["ten"], s["loai"]) for s in records["11C1"]["hoc_sinh"]] == [
        ("Tấn Phát", "K"), ("Nhật Uy", "K")
    ]
    assert records["11C1"]["unrecognized"] == []
    assert records["11C1"]["parse_notes"] == []

    # 2. Đủ / đi đủ / đủ ạ
    for code in ["10C8", "10C10", "10C4", "10C3"]:
        assert records[code]["so_vang_khai_bao"] == 0
        assert records[code]["hoc_sinh"] == []

    # 3. 10C5: vắng 1: Quang Thang (K)
    assert records["10C5"]["so_vang_khai_bao"] == 1
    assert [(s["ten"], s["loai"]) for s in records["10C5"]["hoc_sinh"]] == [("Quang Thang", "K")]

    # 4. 12C13: Vắng 0 (có timestamp Zalo)
    assert records["12C13"]["so_vang_khai_bao"] == 0
    assert records["12C13"]["hoc_sinh"] == []

    # 5. 12C17: sĩ số 43, 2 học sinh
    assert records["12C17"]["si_so"] == 43
    assert [(s["ten"], s["loai"]) for s in records["12C17"]["hoc_sinh"]] == [
        ("Trúc Vy", "K"), ("Thụy Quỳnh Anh", "P")
    ]

    # 6. 12C2: sĩ số 40 vắng0
    assert records["12C2"]["si_so"] == 40
    assert records["12C2"]["so_vang_khai_bao"] == 0
    assert records["12C2"]["hoc_sinh"] == []

    # 7. 12C12: vắng 6
    assert records["12C12"]["so_vang_khai_bao"] == 6
    assert len(records["12C12"]["hoc_sinh"]) == 6
    assert records["12C12"]["hoc_sinh"][0] == {"ten": "Trần Nguyễn Minh Anh", "loai": "P"}
    assert records["12C12"]["hoc_sinh"][4] == {"ten": "Phạm Hoàng Nguyên", "loai": "K"}

    # 8. 12C8: vắng / Quốc Bảo(p)
    assert [(s["ten"], s["loai"]) for s in records["12C8"]["hoc_sinh"]] == [("Quốc Bảo", "P")]

    # 9. 12C18: vắng không phép : (6)... và bỏ qua phần Trễ :(2)...
    assert records["12C18"]["si_so"] == 32
    assert records["12C18"]["so_vang_khai_bao"] == 6
    assert len(records["12C18"]["hoc_sinh"]) == 6
    assert all(s["loai"] == "K" for s in records["12C18"]["hoc_sinh"])
    assert [s["ten"] for s in records["12C18"]["hoc_sinh"]] == [
        "Vũ Tuấn Anh", "Nguyễn Xuân Duy", "Trần Vũ Huy",
        "Võ Phương Trà My", "Phạm Quyết Tiến", "Phạm Vũ Ngọc Trâm"
    ]
    # "Trễ" và danh sách đi trễ không được đưa vào danh sách học sinh hay unrecognized
    all_names_12c18 = [s["ten"] for s in records["12C18"]["hoc_sinh"]]
    assert "Trễ" not in all_names_12c18
    assert "Nguyễn Huy Kiệt" not in all_names_12c18
    assert "Nguyễn Phan Đăng Khoa" not in all_names_12c18
    assert records["12C18"]["unrecognized"] == []

    # 10. 12C14: Vắng 1
    assert records["12C14"]["so_vang_khai_bao"] == 1
    assert [(s["ten"], s["loai"]) for s in records["12C14"]["hoc_sinh"]] == [("Ngọc Mai", "P")]

    # 11. 12C7: v3 quỳnh như(p),thanh trúc(p),thùy trâm(p)
    assert records["12C7"]["so_vang_khai_bao"] == 3
    assert len(records["12C7"]["hoc_sinh"]) == 3
    assert [(s["ten"], s["loai"]) for s in records["12C7"]["hoc_sinh"]] == [
        ("Quỳnh Như", "P"), ("Thanh Trúc", "P"), ("Thùy Trâm", "P")
    ]

    # Không còn timestamp người gửi nào bị coi là rác toàn cục
    assert parsed["unrecognized"] == []

    # Validate và format thử
    all_classes = [
        "10C3", "10C4", "10C5", "10C8", "10C10",
        "11C1",
        "12C2", "12C7", "12C8", "12C12", "12C13", "12C14", "12C17", "12C18"
    ]
    val = validate(parsed, all_classes)
    formatted = format_text(val["data"], "Sáng", date(2026, 10, 24), 1)

    assert "11C1 Vắng  2 Tấn Phát (K), Nhật Uy (K)" in formatted
    assert "10C8 Vắng  0" in formatted
    assert "10C10 Vắng  0" in formatted
    assert "10C5 Vắng  1 Quang Thang (K)" in formatted
    assert "10C4 Vắng  0" in formatted
    assert "10C3 Vắng  0" in formatted
    assert "12C13 Vắng  0" in formatted
    assert "12C17 Vắng  2 Trúc Vy (K), Thụy Quỳnh Anh (P)" in formatted
    assert "12C2 Vắng  0" in formatted
    assert "12C12 Vắng  6 Trần Nguyễn Minh Anh (P), Nguyễn Thị Thu Ngân (P), Hồ Trần Minh An (P), Lê Thị Ngọc Huyền (P), Phạm Hoàng Nguyên (K), Võ Quốc Hiếu (K)" in formatted
    assert "12C8 Vắng  1 Quốc Bảo (P)" in formatted
    assert "12C18 Vắng  6 Vũ Tuấn Anh (K), Nguyễn Xuân Duy (K), Trần Vũ Huy (K), Võ Phương Trà My (K), Phạm Quyết Tiến (K), Phạm Vũ Ngọc Trâm (K)" in formatted
    assert "12C14 Vắng  1 Ngọc Mai (P)" in formatted
    assert "12C7 Vắng  3 Quỳnh Như (P), Thanh Trúc (P), Thùy Trâm (P)" in formatted


def test_late_students_are_completely_ignored():
    # 1. Multi-line Trễ section
    text_multiline = """12C18 Vắng 1 Tuấn Anh (P)
Trễ:
Nguyễn Huy Kiệt
Nguyễn Phan Đăng Khoa"""
    res1 = parse_message(text_multiline)
    assert [(s["ten"], s["loai"]) for s in res1["lop"][0]["hoc_sinh"]] == [("Tuấn Anh", "P")]
    assert res1["lop"][0]["unrecognized"] == []

    # 2. Inline status (trễ), (đi trễ), (muộn)
    text_inline = "12C18 Vắng 1: Tuấn Anh (P), Nguyễn Huy Kiệt (trễ), Phan Đăng Khoa (muộn)"
    res2 = parse_message(text_inline)
    assert [(s["ten"], s["loai"]) for s in res2["lop"][0]["hoc_sinh"]] == [("Tuấn Anh", "P")]

    # 3. Đi trễ on the same line without separator
    text_sameline = "10C2 vắng 1 Gia Huy (K) đi trễ: Bảo Long, Minh Quân"
    res3 = parse_message(text_sameline)
    assert [(s["ten"], s["loai"]) for s in res3["lop"][0]["hoc_sinh"]] == [("Gia Huy", "K")]
    assert res3["lop"][0]["unrecognized"] == []




