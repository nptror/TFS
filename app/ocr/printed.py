"""Đọc phần chữ IN sẵn (SBD, lớp, họ tên, ngày sinh) bằng Tesseract (offline)."""
from __future__ import annotations

import re
import unicodedata

import cv2
import numpy as np
import os
import shutil

import pytesseract

# Windows: tự tìm tesseract.exe ở thư mục cài mặc định nếu chưa có trong PATH
if not shutil.which("tesseract"):
    for _p in (r"C:\Program Files\Tesseract-OCR\tesseract.exe",
               r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
               os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe")):
        if os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break


def _available_langs() -> set[str]:
    try:
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return {"eng"}


_LANGS = None


def name_lang() -> str:
    """Dùng gói 'vie' nếu đã cài (đọc được dấu), không thì 'eng' (mất dấu — vẫn ghép được)."""
    global _LANGS
    if _LANGS is None:
        _LANGS = _available_langs()
    return "vie" if "vie" in _LANGS else "eng"


def _prep(cell: np.ndarray, scale: float = 2.0) -> np.ndarray:
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    g = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return cv2.copyMakeBorder(bw, 15, 15, 15, 15, cv2.BORDER_CONSTANT, value=255)


def ocr(cell: np.ndarray, lang: str = "eng", whitelist: str | None = None, psm: int = 7) -> str:
    cfg = f"--psm {psm}"
    if whitelist:
        cfg += f" -c tessedit_char_whitelist={whitelist}"
    return pytesseract.image_to_string(_prep(cell), lang=lang, config=cfg).strip()


def read_date(cell) -> str:
    t = ocr(cell, whitelist="0123456789/")
    d = re.sub(r"[^0-9]", "", t)
    if len(d) == 8:
        return f"{d[:2]}/{d[2:4]}/{d[4:]}"
    return t


def read_sbd(cell) -> str:
    return re.sub(r"[^0-9]", "", ocr(cell, whitelist="0123456789"))


def read_class(cell) -> str:
    t = ocr(cell, whitelist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ").replace(" ", "")
    # sửa lỗi hay gặp với mã lớp dạng 11C14
    m = re.match(r"^(..)(C)?(..)$", t)
    if m and len(t) in (4, 5):
        grade = m.group(1).translate(str.maketrans("LIOT", "1101"))
        num = m.group(3).translate(str.maketrans("LIOSRB", "110588"))
        t = f"{grade}C{num}"
    return t


def read_name(cell) -> str:
    t = ocr(cell, lang=name_lang())
    return re.sub(r"\s+", " ", t)


# ---------- chuẩn hoá để so khớp ----------

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm_name(s: str) -> str:
    s = strip_accents(s).upper()
    s = re.sub(r"[^A-Z ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_date(s: str) -> str:
    d = re.sub(r"[^0-9]", "", str(s))
    return d if len(d) == 8 else ""
