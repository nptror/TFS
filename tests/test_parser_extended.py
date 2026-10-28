"""Regression cases from the user's mixed chat history, including each hidden revision."""

from datetime import date
from pathlib import Path

import pytest

from app.formatter import format_text
from app.main import checked_data
from app.parser import parse_message
from app.validator import absence_count, validate


@pytest.mark.parametrize("text", ["12c6vắng 0", "12c6v 0", "12c6v0", "12c6 v:0", "12c6 vắng0"])
def test_attached_class_and_absence_marker(text):
    records = parse_message(text)["lop"]
    assert len(records) == 1
    assert records[0]["ten_lop"] == "12C6"
    assert records[0]["so_vang_khai_bao"] == 0
    assert records[0]["hoc_sinh"] == []


def test_abbreviated_student_name():
    record = parse_message("12c7 v1 h.l bảo ngọc")["lop"][0]
    assert record["hoc_sinh"] == [{"ten": "H.L Bảo Ngọc", "loai": "K"}]


@pytest.mark.parametrize("status", ["T", "t", "T 1t", "T 2t", "T2t", "trễ", "đi trễ", "muộn"])
def test_late_status_is_not_an_absence(status):
    record = parse_message(f"12C14 vắng 0\nNgọc Mai ({status})")["lop"][0]
    assert record["hoc_sinh"] == []
    assert absence_count(record) == 0
    assert record["excluded_late"] == ["Ngọc Mai"]


def test_declared_absent_but_all_students_are_late():
    record = parse_message("Lớp 12C1\nVắng 2\nPhan Nhựt Quang (T), Trần Lam Hoàng Giang (T)")["lop"][0]
    assert record["so_vang_khai_bao"] == 2
    assert absence_count(record) == 0
    assert record["hoc_sinh"] == []
    result = validate({"lop": [record]}, ["12C1"])
    assert any(w["code"] == "count_mismatch" for w in result["warnings"])
    assert "12C1 Vắng  0" in format_text(result["data"], "Sáng", date(2026,10,24), 1)


def test_inline_late_suffix_does_not_swallow_following_absence():
    record = parse_message("12C9 vắng 2 An (P), Bình (trễ), Chi (K)")["lop"][0]
    assert record["hoc_sinh"] == [{"ten": "An", "loai": "P"}, {"ten": "Chi", "loai": "K"}]
    assert record["excluded_late"] == ["Bình"]


@pytest.mark.parametrize("text,expected", [
    ("12C18 Vắng không phép: An, Bình", ["K", "K"]),
    ("12C18 Vắng có phép: (2) An, Bình", ["P", "P"]),
    ("12C18 Vắng không phép: (3) An, Bình(P), Chi", ["K", "P", "K"]),
])
def test_group_phrase_with_optional_count_passes_api_schema(text, expected):
    result = checked_data(parse_message(text))
    assert [s["loai"] for s in result["lop"][0]["hoc_sinh"]] == expected
    assert not any(w["code"] == "group_mismatch" for w in validate(result, ["12C18"])["warnings"])


def test_preserve_unknown_parenthesized_status_for_review():
    record = parse_message("12C9 vắng 1 An (X)")["lop"][0]
    assert record["hoc_sinh"] == [{"ten": "An", "loai": None}]
    result = validate({"lop": [record]}, ["12C9"])
    assert any("(X)" in (w.get("raw") or w["message"]) for w in result["warnings"])


def test_standalone_numeric_count_without_vang_is_not_an_ordinal():
    record = parse_message("12C9 3 An (P), Bình (K)")["lop"][0]
    assert record["so_vang_khai_bao"] == 3
    assert len(record["hoc_sinh"]) == 2


def test_chat_header_only_drops_sender_and_timestamp():
    text = "[24/10/2026 07:19:35] Người gửi: 12c13 vắng 0\n[24/10/2026 07:20:00] Người khác: đã nhận\n[24/10/2026 07:21:00] Lan: 12c2 vắng 0"
    result = parse_message(text)
    assert all(not r["hoc_sinh"] for r in result["lop"])
    assert result["unrecognized"] == ["đã nhận"]


def test_numbered_names_and_parenthesized_absence_totals():
    data = parse_message("Lớp 11c1 vắng2 1 tấn phát 2. Nhật uy\n12c18 vắng (1) Nguyễn Phan Đăng Khoa (k)")
    assert data["lop"][0]["so_vang_khai_bao"] == 2
    assert data["lop"][0]["hoc_sinh"] == [{"ten":"Tấn Phát","loai":"K"},{"ten":"Nhật Uy","loai":"K"}]
    assert data["lop"][1]["hoc_sinh"] == [{"ten":"Nguyễn Phan Đăng Khoa","loai":"K"}]
    assert data["lop"][1]["so_vang_khai_bao"] == 1


def test_full_attendance_and_student_named_du_are_distinct():
    data = parse_message("10C8 đi đủ\n10C10 đủ\n10C4 đủ ạ\n12C9 vắng 1 Trần Du (P)")
    assert all(r["so_vang_khai_bao"] == 0 for r in data["lop"][:3])
    assert data["lop"][3]["hoc_sinh"][0]["ten"] == "Trần Du"


def test_large_count_discrepancy_is_not_hidden_by_later_reports():
    text = (Path(__file__).parent / "fixtures" / "chat_history.txt").read_text(encoding="utf-8")
    start = text.index("Lớp 12c1\nVắng 28")
    end = text.index("[22/10/2026 13:55:41]", start)
    data = checked_data(parse_message(text[start:end]))
    record = data["lop"][0]
    assert record["so_vang_khai_bao"] == 28
    assert len(record["hoc_sinh"]) == 27
    assert sum(s["loai"] == "P" for s in record["hoc_sinh"]) == 5
    assert any(w["code"] == "count_mismatch" for w in validate(data, ["12C1"])["warnings"])


def test_can_return_to_absence_section_after_late_section():
    data = parse_message("12C18\nTrễ: (1) Nguyễn Phan Đăng Khoa\nVắng không phép: (3) An, Bình, Chi")
    record = data["lop"][0]
    assert record["so_vang_khai_bao"] == 3
    assert record["excluded_late"] == ["Nguyễn Phan Đăng Khoa"]
    assert [s["loai"] for s in record["hoc_sinh"]] == ["K", "K", "K"]


@pytest.mark.parametrize("body", [
    "Vắng : (3) Vũ Tuấn Anh(k),Nguyễn Hải Đăng(p),Phạm Quyết Tiến(k)",
    "Vắng không phép : (3) Vũ Tuấn Anh,Nguyễn Hải Đăng(P),Phạm Quyết Tiến\nTrễ: (1) Nguyễn Phan Đăng Khoa",
])
def test_absence_group_variants_not_hidden_by_last_revision(body):
    record = parse_message("Lớp: 12C18\nSĩ số : 32\n" + body)["lop"][0]
    assert record["si_so"] == 32
    assert record["so_vang_khai_bao"] == 3
    assert record["hoc_sinh"] == [
        {"ten": "Vũ Tuấn Anh", "loai": "K"},
        {"ten": "Nguyễn Hải Đăng", "loai": "P"},
        {"ten": "Phạm Quyết Tiến", "loai": "K"},
    ]


def test_full_pasted_history_last_report_wins():
    text = (Path(__file__).parent / "fixtures" / "chat_history.txt").read_text(encoding="utf-8")
    data = checked_data(parse_message(text))
    records = {r["ten_lop"]: r for r in data["lop"]}
    expected = {
        "10C3": [], "10C4": [], "10C5": [("Quang Thang","K")], "10C8": [], "10C10": [],
        "11C1": [("Tấn Phát","K"),("Nhật Uy","K")],
        "12C1": [], "12C2": [("Phan Quốc Việt","P")], "12C3": [("Ngọc Duy","P")], "12C4": [],
        "12C5": [("Vũ Duy Phong","P"),("Nguyễn Như Bảo Nam","P")], "12C6": [], "12C7": [], "12C8": [],
        "12C9": [("Duy Hải","K"),("Ngọc Đạt","K"),("Tuấn Huy","P")],
        "12C10": [("Nguyễn Văn Đức","P")], "12C11": [("Khánh Uyên","K"),("Ngô Ngọc","K")],
        "12C12": [("Trần Nguyễn Minh Anh","K"),("Lê Thị Ngọc Huyền","K")], "12C13": [("Quốc Đại","P")],
        "12C14": [], "12C15": [], "12C16": [("Huỳnh Tấn Tài","K")], "12C17": [("Trúc Vy","K")],
        "12C18": [], "12C19": [],
    }
    assert set(records) == set(expected)
    for code, names in expected.items():
        assert [(s["ten"],s["loai"]) for s in records[code]["hoc_sinh"]] == names, code
        assert absence_count(records[code]) == len(names), code
        assert records[code]["unrecognized"] == [], code
    assert records["12C10"]["si_so"] == 43
    assert records["12C17"]["si_so"] == 43
    assert records["12C14"]["excluded_late"] == ["Quang Vinh"]
    assert records["12C9"]["overwritten"] > 1
    assert data["unrecognized"] == ['đoạn này chỉ lấy lớp và văn "']


def test_filler_trailing_status_and_arrival():
    text = ("11c7 vắng 1 Thiện Thuận K ạ\nNguyễn Trung Kiên vào lớp r ạ\n"
            "Lớp 11c1 vắng1 1. Tấn phát\nLớp 11c4 vắng 1 bạn ạ. Gia Vỹ")
    records = {r["ten_lop"]: r for r in parse_message(text)["lop"]}
    assert records["11C7"]["hoc_sinh"] == [{"ten": "Thiện Thuận", "loai": "K"}]
    assert records["11C7"]["so_vang_khai_bao"] == 1
    assert records["11C1"]["hoc_sinh"] == [{"ten": "Tấn Phát", "loai": "K"}]
    assert records["11C4"]["hoc_sinh"] == [{"ten": "Gia Vỹ", "loai": "K"}]


def test_missing_status_defaults_to_k_with_warning():
    data = parse_message("Lớp 11c1 vắng2 1 tấn phát 2. Nhật uy\n12C9 vắng 1 An (P)")
    warnings = validate(data, ["11C1", "12C9"])["warnings"]
    assert [s["loai"] for s in data["lop"][0]["hoc_sinh"]] == ["K", "K"]
    assert [(w["class_name"], w["code"]) for w in warnings] == [("11C1", "default_k")]
    assert warnings[0]["message"] == "Không ghi P/K, mặc định K: Tấn Phát, Nhật Uy."


def test_full_class_supplement_and_trailing_status():
    text = ("[28/10/2026 13:18:20] Duy Nguyễn: 10C8 vắng Tấn Hậu (P) hồng quân (P)\n"
            "[28/10/2026 13:51:29] Đồng Quốc: 10C5 lớp đủ\n"
            "[28/10/2026 14:57:21] Tuấn Thương: Lớp 10c4 vắng nam , tài , đăng có phép hết ạ\n"
            "[28/10/2026 15:12:04] Duy Nguyễn: 10C8 bổ sung vắng minh quân (K)\n"
            "[28/10/2026 17:29:39] Xuân Hoa: 10c3 vắng không phép: trọng tú")
    result = validate(parse_message(text), [])
    records = {r["ten_lop"]: r for r in result["data"]["lop"]}
    status = lambda code: [(s["ten"], s["loai"]) for s in records[code]["hoc_sinh"]]
    assert status("10C8") == [("Tấn Hậu", "P"), ("Hồng Quân", "P"), ("Minh Quân", "K")]
    assert status("10C5") == [] and records["10C5"]["so_vang_khai_bao"] == 0
    assert status("10C4") == [("Nam", "P"), ("Tài", "P"), ("Đăng", "P")]
    assert status("10C3") == [("Trọng Tú", "K")]
    assert result["warnings"] == []


@pytest.mark.parametrize("text", [
    "10c1 vắng K: nguyễn văn a, trần thị c\nP: nguyễn văn b",
    "10c1 vắng\nK: nguyễn văn a, trần thị c\nP: nguyễn văn b,...",
    "10c1 vắng k: nguyễn văn a; trần thị c;.... p= nguyễn văn b",
])
def test_status_labels_without_count(text):
    result = validate(parse_message(text), [])
    record = result["data"]["lop"][0]
    assert [(s["ten"], s["loai"]) for s in record["hoc_sinh"]] == [
        ("Nguyễn Văn A", "K"), ("Trần Thị C", "K"), ("Nguyễn Văn B", "P")]
    assert result["warnings"] == []
