"""Tách lưới bảng từ ảnh scan/ảnh chụp: chỉnh nghiêng, tìm đường kẻ, cắt ô."""
from __future__ import annotations

import cv2
import numpy as np


def pdf_to_images(pdf_bytes: bytes, dpi: int = 200) -> list[np.ndarray]:
    """Chuyển PDF thành danh sách ảnh BGR. Ưu tiên PyMuPDF, dự phòng pdftoppm."""
    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        out = []
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR if pix.n == 3 else cv2.COLOR_RGBA2BGR)
            out.append(img)
        return out
    except ImportError:
        import subprocess, tempfile, os, glob

        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "in.pdf")
            open(p, "wb").write(pdf_bytes)
            subprocess.run(["pdftoppm", "-r", str(dpi), "-png", p, os.path.join(d, "pg")], check=True)
            return [cv2.imread(f) for f in sorted(glob.glob(os.path.join(d, "pg*.png")))]


def _binarize(gray: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)


def _line_masks(bw: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = bw.shape
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, w // 25), 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(30, h // 30)))
    horiz = cv2.dilate(cv2.morphologyEx(bw, cv2.MORPH_OPEN, hk), np.ones((3, 3), np.uint8))
    vert = cv2.dilate(cv2.morphologyEx(bw, cv2.MORPH_OPEN, vk), np.ones((3, 3), np.uint8))
    return horiz, vert


def deskew(img: np.ndarray) -> np.ndarray:
    """Xoay ảnh cho các đường kẻ ngang nằm ngang (dựa trên Hough)."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    horiz, _ = _line_masks(_binarize(gray))
    lines = cv2.HoughLinesP(horiz, 1, np.pi / 1800, 200, minLineLength=img.shape[1] // 4, maxLineGap=20)
    if lines is None:
        return img
    angles = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for x1, y1, x2, y2 in lines.reshape(-1, 4)]
    angles = [a for a in angles if abs(a) < 10]
    if not angles:
        return img
    ang = float(np.median(angles))
    if abs(ang) < 0.05:
        return img
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), ang, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def _peaks(profile: np.ndarray, thr: float, min_gap: int) -> list[int]:
    """Gom các vị trí có giá trị > thr thành từng cụm, trả về tâm cụm."""
    idx = np.where(profile > thr)[0]
    if len(idx) == 0:
        return []
    groups, cur = [], [idx[0]]
    for i in idx[1:]:
        if i - cur[-1] <= 3:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
    groups.append(cur)
    centers = [int(np.mean(g)) for g in groups]
    merged = [centers[0]]
    for c in centers[1:]:
        if c - merged[-1] < min_gap:
            merged[-1] = (merged[-1] + c) // 2
        else:
            merged.append(c)
    return merged


class Table:
    """Kết quả tách bảng.
    img   : ảnh đã chỉnh nghiêng
    ys    : toạ độ các đường kẻ ngang (n_rows + 1)
    row_xs: với mỗi hàng, danh sách toạ độ đường kẻ dọc trong hàng đó
            (tìm riêng từng hàng nên chịu được ảnh chụp hơi méo)."""

    def __init__(self, img, ys, row_xs, header_row=0):
        self.img, self.ys, self.row_xs, self.header_row = img, ys, row_xs, header_row

    @property
    def n_rows(self):
        return len(self.ys) - 1

    def cell_box(self, row: int, name: str):
        a, b = COLUMNS[name]
        xs = self.row_xs[row]
        return xs[a], self.ys[row], xs[b], self.ys[row + 1]

    def cell(self, row: int, name: str, pad: int = 4) -> np.ndarray:
        x0, y0, x1, y1 = self.cell_box(row, name)
        H, W = self.img.shape[:2]
        x0, x1 = max(0, x0 + pad), min(W, x1 - pad)
        y0, y1 = max(0, y0 + pad), min(H, y1 - pad)
        return self.img[y0:max(y0 + 1, y1), x0:max(x0 + 1, x1)]

    def data_rows(self):
        return range(self.header_row + 1, self.n_rows)


# Thứ tự các đường kẻ dọc tính từ mép trái cột "Họ và tên" (cột rộng nhất).
# offset âm = bên trái. Ví dụ cột Điểm số nằm giữa đường +3 và +4.
COLUMNS = {
    "sbd": (-2, -1),
    "lop": (-1, 0),
    "ho_ten": (0, 1),
    "ngay_sinh": (1, 2),
    "ma_de": (2, 3),
    "diem_so": (3, 4),
    "diem_chu": (4, 5),
}
LINE_OFFSETS = list(range(-2, 6))  # các đường cần bám theo


def _row_peaks(vert, y0, y1):
    strip = vert[y0 + 2:y1 - 2]
    prof = strip.sum(axis=0) / 255.0
    return _peaks(prof, 0.7 * strip.shape[0], 8)


def find_table(img: np.ndarray) -> Table:
    img = deskew(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    horiz, vert = _line_masks(_binarize(gray))
    h, w = gray.shape
    ys = _peaks(horiz.sum(axis=1) / 255.0, 0.35 * w, 18)
    if len(ys) < 3:
        raise ValueError("Không tìm thấy bảng (không đủ đường kẻ ngang).")
    med = np.median(np.diff(ys))
    keep = [ys[0]]
    for y in ys[1:]:
        if y - keep[-1] >= 0.6 * med:
            keep.append(y)
    ys = keep

    # Dòng tiêu đề (dòng đầu, cao nhất) không có chữ viết tay -> đường kẻ tin cậy nhất.
    hdr = int(np.argmax(np.diff(ys[:3])))
    hx = _row_peaks(vert, ys[hdr], ys[hdr + 1])
    if len(hx) < 7:
        raise ValueError("Không nhận ra dòng tiêu đề của bảng.")
    gaps = np.diff(hx)
    i0 = int(np.argmax(gaps))  # mép trái cột Họ và tên
    anchors = {}
    for off in LINE_OFFSETS:
        j = i0 + off
        if 0 <= j < len(hx):
            anchors[off] = float(hx[j])
    # Ngoại suy đường bị mất ở mép (ảnh chụp bị cắt) bằng độ rộng trung bình
    unit = np.median(gaps[gaps < gaps.max()]) if len(gaps) > 1 else 100
    for off in LINE_OFFSETS:
        if off not in anchors:
            near = min(anchors, key=lambda k: abs(k - off))
            anchors[off] = anchors[near] + (off - near) * unit

    row_xs, cur = [], dict(anchors)
    for r in range(len(ys) - 1):
        peaks = np.array(_row_peaks(vert, ys[r], ys[r + 1]) or [-9999])
        nxt, shifts = {}, []
        for off, x in cur.items():
            k = int(np.argmin(np.abs(peaks - x)))
            if abs(peaks[k] - x) <= 15:
                nxt[off] = float(peaks[k])
                shifts.append(peaks[k] - x)
        drift = float(np.median(shifts)) if shifts else 0.0
        for off, x in cur.items():
            nxt.setdefault(off, x + drift)
        cur = nxt
        row_xs.append({k: int(round(v)) for k, v in cur.items()})
    return Table(img, ys, row_xs, header_row=hdr)


def extract_table(img: np.ndarray) -> Table:
    return find_table(img)
