"""Parser regex thuần, không I/O, không gọi AI.

parse_message(text) -> dict có khóa `lop`, tương thích schema đề bài.
Metadata bổ sung giữ số đếm nhóm, nội dung không nhận diện và lần ghi đè.
Không đoán ranh giới tên khi không có dấu phẩy, xuống dòng hoặc (P)/(K).
"""

import re
import unicodedata

from .models import normalize_class, normalize_name


CLASS_RE = re.compile(r"(?<!\w)(?:lớp\s*[:=]?\s*)?(10|11|12)\s*([a-z])\s*(\d{1,3})(?!\w)", re.I)
SIZE_RE = re.compile(r"(?<!\w)(?:sĩ\s*số|si\s*so|ss)\s*[:=]?\s*(\d+)(?!\d)", re.I)
FULL_ATTENDANCE_RE = re.compile(
    r"(?<!\w)(?:"
    r"đi\s*đủ|di\s*du|đầy\s*đủ|day\s*du|có\s*mặt\s*đủ|hiện\s*diện\s*đủ|"
    r"đủ\s*(?:sĩ\s*số|ss)|(?:sĩ\s*số|ss)\s*đủ|"
    r"không\s*vắng|ko\s*vắng|k\s*vắng|khong\s*vang|không\s*ai\s*vắng|"
    r"đủ|du"
    r")(?:\s*(?:ạ|a|nha|nhé|nhe|cả))?(?!\w)",
    re.I,
)
KEYWORD_RE = re.compile(
    r"(?<!\w)(?:báo\s*vắng|báo\s*vang|ds\s*vắng|danh\s*sách\s*vắng)(?:\s*[:=])?"
    r"|(?<!\w)(?:vắng|văng|vang|vắg|vg)(?:\s*[:=])?"
    r"|(?<!\w)v\s*[:=]"
    r"|(?<!\w)v\s+(?=\d)"
    r"|(?<!\w)lớp(?:\s*[:=])?",
    re.I,
)
# Prefix groups must be distinguished from a standalone total before consuming digits.
TOKEN_RE = re.compile(
    r"(?P<group>(?<!\w)(?P<count>\d+)\s*(?P<kind>[PK])(?!\w))"
    r"|(?P<status>\(\s*(?P<individual>[^)]+)\s*\))"
    r"|(?P<separator>[,;\n]+)", re.I
)
TOTAL_RE = re.compile(r"(?<!\w)\d+(?!\w)")
NAME_RE = re.compile(r"[^\W\d_]+(?:[\s'’\-][^\W\d_]+)*", re.UNICODE)

COURTESY_WORDS = {
    "ạ", "a", "dạ", "da", "dạ em gửi", "dạ gửi", "em gửi", "gửi ạ", "gửi",
    "báo cáo", "xin báo cáo", "em xin báo cáo", "dạ báo cáo",
    "nhé", "nha", "nhe", "ạ nha", "ạ nhé", "nhé ạ",
    "cô ơi", "thầy ơi", "dạ cô", "dạ thầy",
    "cảm ơn", "cam on", "thanks", "thank",
}
COURTESY_RE = re.compile(
    r"^(?:dạ\s*)?(?:em\s*)?(?:xin\s*)?(?:gửi|báo\s*cáo|báo\s*vắng)?\s*(?:ạ|a|nha|nhé|nhe)?$",
    re.I,
)


def normalize_status(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().upper()
    if cleaned in ("P", "CP", "CÓ PHÉP", "CO PHEP", "P."):
        return "P"
    if cleaned in ("K", "KP", "KO", "KHÔNG PHÉP", "KHONG PHEP", "K."):
        return "K"
    return None


def _parse_block(code: str, raw: str, body: str) -> dict:
    record = {
        "ten_lop": code, "si_so": None, "so_vang_khai_bao": None,
        "hoc_sinh": [], "raw": raw.strip(), "reported": True,
        "overwritten": 0, "groups": [], "unrecognized": [], "parse_notes": [],
    }
    sizes = SIZE_RE.findall(body)
    if sizes:
        record["si_so"] = int(sizes[-1])
        if len(set(sizes)) > 1:
            record["parse_notes"].append("Có nhiều sĩ số khác nhau; dùng số cuối cùng.")
    body = SIZE_RE.sub(" ", body)
    has_full_attendance = bool(FULL_ATTENDANCE_RE.search(body))
    body = FULL_ATTENDANCE_RE.sub(" ", body)
    body = KEYWORD_RE.sub(" ", body)
    group_index = None
    pending = ""
    declarations = []

    def flush(explicit_status=None, has_status=False):
        nonlocal pending
        fragment = pending.strip(" \t\r\n:=-•–—")
        pending = ""
        if not fragment:
            if has_status:
                record["unrecognized"].append(f"({explicit_status or '?'}) không có tên")
            return
        if not has_status:
            if fragment.lower() in COURTESY_WORDS or COURTESY_RE.fullmatch(fragment):
                return
        # Numbers here are NOT part of a group prefix or sĩ số (already tokenized).
        totals = TOTAL_RE.findall(fragment)
        declarations.extend(int(value) for value in totals)
        fragment = TOTAL_RE.sub(" ", fragment).strip(" \t:=-•–—")
        if not fragment:
            return
        if not has_status:
            if fragment.lower() in COURTESY_WORDS or COURTESY_RE.fullmatch(fragment):
                return
        name = normalize_name(fragment)
        if not NAME_RE.fullmatch(name):
            record["unrecognized"].append(fragment)
            return
        inherited = record["groups"][group_index]["loai"] if group_index is not None else None
        record["hoc_sinh"].append({"ten": name, "loai": explicit_status if has_status else inherited})
        if group_index is not None:
            record["groups"][group_index]["thuc_te"] += 1

    cursor = 0
    for token in TOKEN_RE.finditer(body):
        pending += body[cursor:token.start()]
        if token["group"]:
            flush()
            record["groups"].append({
                "loai": token["kind"].upper(), "khai_bao": int(token["count"]), "thuc_te": 0,
            })
            group_index = len(record["groups"]) - 1
        elif token["status"]:
            status = normalize_status(token["individual"])
            flush(status, has_status=True)
        else:
            flush()
        cursor = token.end()
    pending += body[cursor:]
    flush()
    if declarations:
        record["so_vang_khai_bao"] = declarations[0]
        if len(declarations) > 1:
            record["parse_notes"].append(
                "Có nhiều số vắng độc lập (" + ", ".join(map(str, declarations)) + "); cần kiểm tra."
            )
    elif record["groups"]:
        record["so_vang_khai_bao"] = sum(group["khai_bao"] for group in record["groups"])
    elif has_full_attendance and not record["hoc_sinh"]:
        record["so_vang_khai_bao"] = 0
    return record


def deduplicate(records: list[dict]) -> list[dict]:
    """Cả JSON từ AI lẫn parser đều dùng quy tắc lần báo cuối cùng thắng."""
    latest = {}
    for record in records:
        code = normalize_class(record["ten_lop"])
        record = {**record, "ten_lop": code}
        if code in latest:
            record["overwritten"] = latest[code].get("overwritten", 0) + 1
        latest[code] = record
    return list(latest.values())


def parse_message(text: str) -> dict:
    text = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    matches = list(CLASS_RE.finditer(text))
    result = {"lop": [], "unrecognized": []}
    if not matches:
        if text.strip():
            result["unrecognized"].append(text.strip())
        return result
    prefix = text[:matches[0].start()].strip()
    if prefix:
        result["unrecognized"].append(prefix)
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        end = next_start
        if index + 1 < len(matches):
            last_nl = text.rfind("\n", match.end(), next_start)
            if last_nl != -1:
                between = text[last_nl + 1:next_start].strip()
                if between and (
                    between.lower() in COURTESY_WORDS
                    or COURTESY_RE.fullmatch(between)
                    or re.search(r"\b(?:dạ|em\s*gửi|gửi|báo\s*cáo|báo\s*vắng|kính\s*gửi)\b", between, re.I)
                ):
                    end = last_nl
        raw = text[match.start():end]
        try:
            code = normalize_class(f"{match[1]}{match[2]}{match[3]}")
        except ValueError:
            result["unrecognized"].append(raw.strip())
            continue
        result["lop"].append(_parse_block(code, raw, text[match.end():end]))
    result["lop"] = deduplicate(result["lop"])
    return result


# Tên camelCase tiện dùng khi đối chiếu đặc tả cũ.
parseMessage = parse_message

