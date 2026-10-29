"""Luồng xử lý chính: PDF scan -> các dòng (học sinh + điểm) -> ghép với Excel."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from . import handwriting as hw
from . import printed
from .excel import match
from .grid import extract_table


def load_model() -> hw.DigitModel:
    X, y = hw.load_user_data()
    return hw.DigitModel().fit(X, y)


def to_data_url(img: np.ndarray, max_h: int = 60) -> str:
    if img.shape[0] > max_h:
        s = max_h / img.shape[0]
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()


def _read_printed(args):
    t, r = args
    return {
        "sbd": printed.read_sbd(t.cell(r, "sbd")),
        "lop": printed.read_class(t.cell(r, "lop")),
        "ho_ten": printed.read_name(t.cell(r, "ho_ten")),
        "ngay_sinh": printed.read_date(t.cell(r, "ngay_sinh")),
    }


def read_score_robust(model, t, r):
    """Đọc ô điểm với 3 cách cắt ô khác nhau và lấy đa số; nếu không thống nhất thì hạ độ tin cậy."""
    reads = [hw.read_score(model, t.cell(r, "diem_so", pad=p)) for p in (1, 2, 3)]
    main = reads[1]
    vals = [x["value"] for x in reads]
    if all(x.get("empty") for x in reads):
        return main
    best = max(set(vals), key=lambda v: (vals.count(v), v == main["value"]))
    agree = vals.count(best) / len(vals)
    pick = next(x for x in [main] + reads if x["value"] == best)
    out = dict(pick)
    out["empty"] = False
    out["conf"] = round(pick["conf"] * (1.0 if agree == 1 else 0.6), 3)
    return out


def process_pages(images, students, model, progress=None):
    """Trả về list dict, mỗi dict là một dòng trên phiếu điểm."""
    rows, tasks, tables = [], [], []
    for pi, img in enumerate(images):
        try:
            t = extract_table(img)
        except Exception as e:  # trang không có bảng
            tables.append((pi, None, str(e)))
            continue
        tables.append((pi, t, ""))
        for r in t.data_rows():
            tasks.append((pi, t, r))

    with ThreadPoolExecutor(max_workers=4) as ex:  # tesseract chạy song song
        futs = [ex.submit(_read_printed, (t, r)) for _, t, r in tasks]
        info = []
        for k, f in enumerate(futs):
            info.append(f.result())
            if progress:
                progress((k + 1) / max(1, len(futs)))

    for (pi, t, r), o in zip(tasks, info):
        score_cell = t.cell(r, "diem_so", pad=2)
        sc = read_score_robust(model, t, r)
        st, mconf, note = match(o, students) if students else (None, 0.0, "")
        x0, y0, _, y1 = t.cell_box(r, "diem_so")
        _, _, x1, _ = t.cell_box(r, "diem_chu")
        H, W = t.img.shape[:2]
        crop = t.img[max(0, y0 - 2):min(H, y1 + 2), max(0, x0 - 2):min(W, x1 + 2)]
        rows.append({
            "trang": pi + 1,
            "stt": r - t.header_row,
            "ocr": o,
            "diem": sc["value"],
            "conf": sc["conf"],
            "trong": sc.get("empty", False),
            "hs": st,
            "match_conf": mconf,
            "match_note": note,
            "anh_diem": to_data_url(crop),
            "anh_ten": to_data_url(t.img[y0:y1, t.cell_box(r, "sbd")[0]:t.cell_box(r, "ngay_sinh")[2]], 40),
            "_score_cell": score_cell,
        })
    errors = [(pi + 1, msg) for pi, t, msg in tables if t is None]
    return rows, errors
