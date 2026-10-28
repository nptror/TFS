"""Parser regex có trạng thái cho tin nhắn báo vắng.

Regex chỉ nhận token: mã lớp, số đếm, số thứ tự, trạng thái, phân cách.
Trạng thái của khối quyết định token thuộc danh sách vắng hay đi trễ.
Không xóa cả đuôi chuỗi khi gặp "trễ", không suy đoán P/K.
"""

import re
import unicodedata

from .models import normalize_class, normalize_name


# Cho phép mã lớp dính đúng từ khóa đã biết, không nhận nhầm "12C6foobar".
CLASS_RE = re.compile(
    r"(?<!\w)(?:lớp\s*[:=]?\s*)?(10|11|12)\s*([a-z])\s*(\d{1,3})"
    r"(?=$|[^\w]|(?:vắng|văng|vang|vắg)(?![^\W\d_])|v(?=\s*[:=]?\s*\d))", re.I,
)
SIZE_RE = re.compile(r"(?<!\w)(?:sĩ\s*số|si\s*so|ss)\s*[:=]?\s*(\d+)(?!\d)", re.I)
ABSENCE_PATTERN = (
    r"(?<!\w)(?:báo\s*vắng|báo\s*vang|ds\s*vắng|danh\s*sách\s*vắng|"
    r"vắng|văng|vang|vắg|vg|v)(?![^\W\d_])\s*[:=]?\s*"
)
FULL_ATTENDANCE_PATTERN = (
    r"(?:^|(?<=\n))[ \t:=-]*(?:lớp\s*)?(?:"
    r"đi\s*đủ|di\s*du|đầy\s*đủ|day\s*du|có\s*mặt\s*đủ|hiện\s*diện\s*đủ|"
    r"đủ\s*(?:sĩ\s*số|ss)|(?:sĩ\s*số|ss)\s*đủ|"
    r"không\s*ai\s*vắng|không\s*vắng|ko\s*vắng|k\s*vắng|khong\s*vang|đủ|du"
    r")(?!\w)(?:[ \t]+(?:ạ|a|nha|nhé|nhe|cả)(?!\w))?"
)
CHAT_HEADER_RE = re.compile(
    r"^[ \t]*(?:"
    r"\[\s*\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?(?:[ ,T]+\d{1,2}:\d{1,2}(?::\d{1,2})?)?\s*\]"
    r"|\[\s*\d{1,2}:\d{1,2}(?::\d{1,2})?(?:[ ,]+\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)?\s*\]"
    r"|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}[ ,T]+\d{1,2}:\d{1,2}(?::\d{1,2})?[ \t]*[-:]?"
    r")[ \t]*", re.I | re.M,
)
LATE_PATTERN = (
    r"(?<!\w)(?:học\s*sinh\s*đi\s*trễ|hs\s*đi\s*trễ|đi\s*trễ|"
    r"đến\s*muộn|vào\s*trễ|trễ|muộn)(?![^\W\d_])\s*[:=]?\s*"
)
# Từ đệm trong câu nói ("bạn ạ. Gia Vỹ"), không phải một phần tên. Không gồm "nha" vì là tên thật.
FILLER_RE = re.compile(r"(?<!\w)(?:bạn|ạ|dạ|nhé|nhe)(?!\w)[.!]*", re.I)
# "Tên K" / "Tên p": chữ P/K đơn lẻ cuối tên là trạng thái.
TRAILING_STATUS_RE = re.compile(r"\s+([PK])$", re.I)
ARRIVED_PATTERN = (
    r"(?<!\w)(?:đã\s*)?(?:vào\s*lớp|đến\s*lớp|có\s*mặt|đã\s*đến)"
    r"(?:\s*(?:rồi|rùi|r)(?!\w))?(?!\w)"
)
TOKEN_RE = re.compile(
    # Số trong ngoặc đứng trước status; "(3)" là số đếm, không phải trạng thái.
    r"(?P<paren_count>\(\s*(?P<paren_number>\d+)\s*\))"
    r"|(?P<status>\(\s*(?P<individual>[^()\n]+?)\s*\))"
    r"|(?P<full>" + FULL_ATTENDANCE_PATTERN + r")"
    r"|(?P<absence>" + ABSENCE_PATTERN + r")"
    r"|(?P<late>" + LATE_PATTERN + r")"
    r"|(?P<arrived>" + ARRIVED_PATTERN + r")"
    r"|(?P<group>(?<!\w)(?:(?P<group_count>\d+)\s*(?P<group_kind>[PK])(?:\s*[:=])?(?!\w)"
    r"|(?P<label_kind>[PK])\s*[:=]))"
    r"|(?P<group_phrase>(?<!\w)(?P<phrase_kind>"
    r"không\s*phép|khong\s*phep|ko\s*phép|ko\s*phep|k\s*phép|k\s*phep|kp|"
    r"có\s*phép|co\s*phep|c\s*phép|cp)(?!\w)[ \t]*[:=]?[ \t]*"
    r"(?:\(\s*(?P<phrase_count1>\d+)\s*\)|(?P<phrase_count2>\d+)(?![\w]))?"
    r"(?P<phrase_all>(?<!\w)(?:hết|cả|tất\s*cả|toàn\s*bộ)(?!\w))?)"
    r"|(?P<number_token>(?<!\w)(?P<number>\d+)(?!\w)(?P<ordinal>[.)/\-])?)"
    r"|(?P<separator>[,;\n]+)",
    re.I,
)
# Dấu chấm giữa chữ cho tên viết tắt như "h.l bảo ngọc"; không tự mở rộng họ tên.
NAME_RE = re.compile(r"[^\W\d_]+\.?(?:[\s'’.\-]+[^\W\d_]+\.?)*", re.UNICODE)
META_LINE_RE = re.compile(r"^\s*(?:đoạn này|đây là dữ liệu|dữ liệu mới|chỉ lấy lớp)\b", re.I)
SUPPLEMENT_RE = re.compile(r"^[\s:,.\-]*(?:bổ\s*sung|bo\s*sung|bs|thêm)(?!\w)", re.I)
TRIM = " \t\r\n:=-•–—\"'“”‘’"
COURTESY_WORDS = {
    "ạ", "a", "dạ", "da", "dạ em gửi", "dạ gửi", "em gửi", "gửi ạ", "gửi",
    "báo cáo", "xin báo cáo", "em xin báo cáo", "dạ báo cáo", "kính gửi",
    "nhé", "nha", "nhe", "ạ nha", "ạ nhé", "nhé ạ", "cô ơi", "thầy ơi",
    "dạ cô", "dạ thầy", "cảm ơn", "cam on", "thanks", "thank",
}
COURTESY_RE = re.compile(
    r"^(?:dạ\s*)?(?:em\s*)?(?:xin\s*)?(?:gửi|báo\s*cáo|báo\s*vắng)?"
    r"\s*(?:ạ|a|nha|nhé|nhe)?$", re.I,
)


def is_courtesy(text: str) -> bool:
    return text.lower() in COURTESY_WORDS or bool(COURTESY_RE.fullmatch(text))


def normalize_status(raw: str | None) -> str | None:
    cleaned = " ".join((raw or "").split()).upper()
    if cleaned in ("P", "CP", "CÓ PHÉP", "CO PHEP", "P."):
        return "P"
    if cleaned in ("K", "KP", "KO", "KHÔNG PHÉP", "KHONG PHEP", "K."):
        return "K"
    if re.fullmatch(r"T(?:\s*\d+\s*(?:T|TIẾT|TIET))?", cleaned) or cleaned in (
        "TRỄ", "TRE", "ĐI TRỄ", "DI TRE", "MUỘN", "MUON", "ĐẾN MUỘN", "DEN MUON",
    ):
        return "LATE"
    return None


def _parse_block(code: str, raw: str, body: str) -> dict:
    record = {
        "ten_lop": code, "si_so": None, "so_vang_khai_bao": None,
        "hoc_sinh": [], "raw": raw.strip(), "reported": True,
        "overwritten": 0, "groups": [], "unrecognized": [], "parse_notes": [],
        "excluded_late": [], "defaulted_k": [],
    }
    body, supplement = SUPPLEMENT_RE.subn("", body)
    if supplement:
        record["supplement"] = True
    sizes = SIZE_RE.findall(body)
    if sizes:
        record["si_so"] = int(sizes[-1])
        if len(set(sizes)) > 1:
            record["parse_notes"].append("Có nhiều sĩ số khác nhau; dùng số cuối cùng.")
    body = SIZE_RE.sub(" ", body)
    # Tách "vắng2"/"v0" trước khi quét số: lookbehind của token số vẫn
    # nhìn ký tự gốc dù token từ khóa đã được tiêu thụ.
    body = re.sub(ABSENCE_PATTERN, lambda match: match[0] + " ", body, flags=re.I)
    body = FILLER_RE.sub(" ", body)
    group_index = None
    late_mode = False
    awaiting_total = False
    declarations = []
    pending = ""

    def flush(explicit_status=None, has_status=False, raw_status=None):
        nonlocal pending, awaiting_total
        fragment = pending.strip(TRIM)
        pending = ""
        if not fragment.strip(".…"):
            if has_status:
                record["unrecognized"].append(f"({raw_status or '?'}) không có tên")
            return
        if not has_status and is_courtesy(fragment):
            return
        tail = None if has_status else TRAILING_STATUS_RE.search(fragment)
        if tail:
            fragment, explicit_status, has_status = fragment[:tail.start()], tail[1].upper(), True
        name = normalize_name(fragment)
        if not NAME_RE.fullmatch(name):
            record["unrecognized"].append(fragment)
            return
        awaiting_total = False
        if explicit_status == "LATE" or late_mode:
            record["excluded_late"].append(name)
            return
        inherited = record["groups"][group_index]["loai"] if group_index is not None else None
        if not has_status and inherited is None:
            record["defaulted_k"].append(name)  # không ghi P/K = không phép; cảnh báo để người dùng biết
        record["hoc_sinh"].append({"ten": name, "loai": explicit_status if has_status else inherited or "K"})
        if has_status and explicit_status is None and raw_status and raw_status.strip() != "?":
            record["parse_notes"].append(f"Trạng thái ({raw_status.strip()}) của {name} chưa rõ; cần kiểm tra.")
        if group_index is not None:
            record["groups"][group_index]["thuc_te"] += 1

    cursor = 0
    for token in TOKEN_RE.finditer(body):
        pending += body[cursor:token.start()]
        if token["status"]:
            status = normalize_status(token["individual"])
            flush(status, has_status=True, raw_status=token["individual"])
        elif token["full"]:
            flush()
            declarations.append(0)
            awaiting_total = False
            late_mode = False
            group_index = None
        elif token["absence"]:
            flush()
            late_mode = False
            awaiting_total = True
            group_index = None
        elif token["arrived"]:
            # "X vào lớp rồi": X không vắng; bỏ khỏi danh sách nếu đã ghi nhầm.
            name = normalize_name(pending.strip(TRIM)) if pending.strip(TRIM) else None
            pending = ""
            if name:
                kept = [s for s in record["hoc_sinh"] if s["ten"] != name]
                if len(kept) == len(record["hoc_sinh"]):
                    record["excluded_late"].append(name)
                record["hoc_sinh"] = kept
        elif token["late"]:
            flush()
            late_mode = True
            group_index = None
        elif token["group_phrase"] and (token["phrase_all"] or not body[token.end():].strip(TRIM + ".!")):
            # "Nam, Tài, Đăng có phép hết": trạng thái đứng sau áp cho các tên chưa ghi P/K trước đó.
            flush()
            kind = "K" if token["phrase_kind"].lower().startswith("k") else "P"
            for student in record["hoc_sinh"]:
                if student["ten"] in record["defaulted_k"]:
                    student["loai"] = kind
            record["defaulted_k"] = []
        elif token["group"] or token["group_phrase"]:
            flush()
            if token["group"]:
                kind = (token["group_kind"] or token["label_kind"]).upper()
                count = int(token["group_count"]) if token["group_count"] else None
            else:
                kind = "K" if token["phrase_kind"].lower().startswith("k") else "P"
                count_text = token["phrase_count1"] or token["phrase_count2"]
                count = int(count_text) if count_text is not None else None
            if not late_mode:
                record["groups"].append({"loai": kind, "khai_bao": count, "thuc_te": 0})
                group_index = len(record["groups"]) - 1
            awaiting_total = False
        elif token["number_token"] or token["paren_count"]:
            flush()
            number = int(token["number"] or token["paren_number"])
            if late_mode:
                # Số trễ/số thứ tự không được nhập vào tổng vắng.
                pass
            elif not token["ordinal"] and (
                awaiting_total or (not declarations and not record["hoc_sinh"] and not record["groups"])
            ):
                declarations.append(number)
                awaiting_total = False
            # Những số còn lại là số thứ tự: chỉ tách tên, không cộng vào tổng.
        else:
            flush()
        cursor = token.end()
    pending += body[cursor:]
    flush()
    if declarations:
        record["so_vang_khai_bao"] = declarations[0]
        if len(set(declarations)) > 1:
            record["parse_notes"].append(
                "Có nhiều số vắng độc lập (" + ", ".join(map(str, declarations)) + "); cần kiểm tra."
            )
    elif record["groups"] and all(group["khai_bao"] is not None for group in record["groups"]):
        record["so_vang_khai_bao"] = sum(group["khai_bao"] for group in record["groups"])
    return record


def _merge(previous: dict, extra: dict) -> dict:
    """Tin "bổ sung" cộng thêm học sinh vào lần báo trước của cùng lớp."""
    merged = {**previous, "raw": previous["raw"] + "\n" + extra["raw"]}
    for key in ("hoc_sinh", "groups", "unrecognized", "parse_notes", "excluded_late", "defaulted_k"):
        merged[key] = previous.get(key, []) + extra.get(key, [])
    if previous["so_vang_khai_bao"] is not None or extra["so_vang_khai_bao"] is not None:
        # Phần nào không khai báo số thì lấy số tên của phần đó.
        merged["so_vang_khai_bao"] = sum(
            len(part["hoc_sinh"]) if part["so_vang_khai_bao"] is None else part["so_vang_khai_bao"]
            for part in (previous, extra))
    merged["si_so"] = extra["si_so"] if extra["si_so"] is not None else previous["si_so"]
    return merged


def deduplicate(records: list[dict]) -> list[dict]:
    """Lần báo cuối cùng thắng; tin "bổ sung" thì gộp thêm vào lần trước."""
    latest = {}
    for record in records:
        code = normalize_class(record["ten_lop"])
        record = {**record, "ten_lop": code}
        supplement = record.pop("supplement", False)
        if code in latest and supplement:
            record = _merge(latest[code], record)
        elif code in latest:
            record["overwritten"] = latest[code].get("overwritten", 0) + 1
        latest[code] = record
    return list(latest.values())


def _chat_messages(text: str):
    """Giữ ranh giới tin nhắn: lời nhắn không có lớp không dính vào lớp trước."""
    for index, message in enumerate(CHAT_HEADER_RE.split(text)):
        if index:
            first_line = message.split("\n", 1)[0]
            colon = first_line.find(":")
            if colon >= 0 and not CLASS_RE.search(first_line[:colon]):
                message = message[colon + 1:].lstrip()
        yield message


def parse_message(text: str) -> dict:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    result = {"lop": [], "unrecognized": []}
    for message in _chat_messages(text):
        lines = []
        for line in message.splitlines():
            if META_LINE_RE.match(line):
                result["unrecognized"].append(line.strip())
            else:
                lines.append(line)
        message = "\n".join(lines)
        matches = list(CLASS_RE.finditer(message))
        prefix = message[:matches[0].start()] if matches else message
        if prefix.strip(TRIM) and not is_courtesy(prefix.strip(TRIM)):
            result["unrecognized"].append(prefix.strip())
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(message)
            # "Dạ em gửi 10C6 ạ" có phần chào trước mã lớp, không phải tên lớp trước.
            if index + 1 < len(matches):
                last_newline = message.rfind("\n", match.end(), end)
                between = message[last_newline + 1:end].strip(TRIM) if last_newline >= 0 else ""
                if between and is_courtesy(between):
                    end = last_newline
            raw = message[match.start():end]
            try:
                code = normalize_class(f"{match[1]}{match[2]}{match[3]}")
            except ValueError:
                result["unrecognized"].append(raw.strip())
                continue
            result["lop"].append(_parse_block(code, raw, message[match.end():end]))
    result["lop"] = deduplicate(result["lop"])
    return result


# Tên camelCase tiện dùng khi đối chiếu đặc tả cũ.
parseMessage = parse_message

