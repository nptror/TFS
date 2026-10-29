"""Nhận dạng điểm số VIẾT TAY, chạy offline, không cần GPU / mô hình tải về.

Cách làm:
  1. Tách ô điểm thành từng chữ số + dấu phẩy (connected components).
  2. Phân loại từng chữ số bằng SVM trên đặc trưng HOG.
  3. Mô hình HỌC THÊM từ mỗi lần bạn duyệt/sửa điểm (lưu ở du_lieu_hoc/digits.npz),
     nên càng dùng càng quen nét chữ của giáo viên trường bạn.
"""
from __future__ import annotations

import os
import threading

import cv2
import numpy as np

SIZE = 28
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "du_lieu_hoc")
DATA_FILE = os.path.join(DATA_DIR, "digits.npz")
_lock = threading.Lock()


# ---------------- tách chữ số ----------------

def _ink_mask(cell: np.ndarray) -> np.ndarray:
    """Mặt nạ nét mực (ngưỡng Otsu theo độ tối) + loại phần đường kẻ ô sót ở mép."""
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    g = cv2.GaussianBlur(g, (3, 3), 0)
    t, bw = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    bg = np.percentile(g, 90)
    if bg - t < 25 or bg - np.percentile(g, 1) < 60:
        return np.zeros_like(bw)  # ô trống (không có nét đủ đậm)
    H, W = bw.shape
    # xoá đường kẻ ô (nét ngang/dọc rất dài) kể cả khi nó dính vào chữ số
    hl = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(W * 0.6), 1)))
    vl = cv2.morphologyEx(bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(H * 0.9))))
    bw = cv2.subtract(bw, cv2.dilate(cv2.bitwise_or(hl, vl), np.ones((3, 1), np.uint8)))
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw, 8)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        touches = x <= 1 or y <= 1 or x + w >= W - 1 or y + h >= H - 1
        line_like = (w > 0.5 * W and h < 0.2 * H) or (h > 0.8 * H and w < 0.1 * W)
        if line_like or (touches and a < 0.012 * H * W):
            bw[lab == i] = 0
        elif touches:
            # khối lớn chạm mép: chỉ cắt bỏ dải sát biên (thường là đường kẻ dính vào chữ)
            pass
    bw[:2, :] = 0
    bw[-2:, :] = 0
    bw[:, :2] = 0
    bw[:, -2:] = 0
    return bw


def _normalize(mask: np.ndarray) -> np.ndarray:
    """Đưa một chữ số về ảnh 28x28, giữ tỉ lệ, căn giữa (kiểu MNIST)."""
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return np.zeros((SIZE, SIZE), np.uint8)
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = m.shape
    s = 20.0 / max(h, w)
    m = cv2.resize(m, (max(1, int(round(w * s))), max(1, int(round(h * s)))), interpolation=cv2.INTER_AREA)
    out = np.zeros((SIZE, SIZE), np.uint8)
    y0, x0 = (SIZE - m.shape[0]) // 2, (SIZE - m.shape[1]) // 2
    out[y0:y0 + m.shape[0], x0:x0 + m.shape[1]] = m
    return out


def segment(cell: np.ndarray):
    """Trả về (danh sách ảnh chữ số 28x28, vị trí dấu phẩy hoặc None, danh sách box).
    vị trí dấu phẩy = số chữ số đứng trước dấu phẩy."""
    bw = _ink_mask(cell)
    H, W = bw.shape
    # nối nét đứt theo chiều dọc để mỗi chữ số thành một khối
    joined = cv2.dilate(bw, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
    comps = []
    for i in range(1, n):
        x, y, w, h, _a = stats[i]
        ink = int(np.count_nonzero(bw[lab == i]))
        if ink < max(8, H * W * 0.003):
            continue
        comps.append([x, y, x + w, y + h, ink, [i]])
    if not comps:
        return [], None, []
    comps.sort(key=lambda c: c[0])
    # gộp khối chồng nhau theo chiều ngang (vd. nét ngang của số 7 tách rời)
    merged = []
    for c in comps:
        if merged:
            p = merged[-1]
            ov = min(p[2], c[2]) - max(p[0], c[0])
            if ov > 0.6 * min(p[2] - p[0], c[2] - c[0]):
                p[0], p[1], p[2], p[3] = min(p[0], c[0]), min(p[1], c[1]), max(p[2], c[2]), max(p[3], c[3])
                p[4] += c[4]
                p[5] += c[5]
                continue
        merged.append(c)
    maxh = max(c[3] - c[1] for c in merged)
    # tách khối quá rộng (2 chữ số dính nhau qua dấu phẩy) tại cột ít mực nhất
    split = []
    for c in merged:
        x0, y0, x1, y1, a, ids = c
        w, h = x1 - x0, y1 - y0
        if w > 1.15 * h and h > 0.6 * maxh:
            sub = (np.isin(lab[y0:y1, x0:x1], ids) & (bw[y0:y1, x0:x1] > 0))
            prof = sub.sum(axis=0).astype(float)
            lo, hi = int(w * 0.3), int(w * 0.7)
            cut = lo + int(np.argmin(prof[lo:hi])) if hi > lo else w // 2
            for (u0, u1) in ((0, cut), (cut, w)):
                part = sub[:, u0:u1]
                ys_ = np.nonzero(part.any(axis=1))[0]
                if len(ys_) == 0:
                    continue
                split.append([x0 + u0, y0 + ys_.min(), x0 + u1, y0 + ys_.max() + 1,
                              int(part.sum()), ids])
        else:
            split.append(c)
    merged = split
    maxa = max(c[4] for c in merged)
    digits, boxes, comma = [], [], None
    for c in merged:
        x0, y0, x1, y1, a, ids = c
        h = y1 - y0
        small = a < 0.22 * maxa or h < 0.45 * maxh
        if small:
            if digits and comma is None and (y0 + y1) / 2 > H * 0.4:
                comma = len(digits)
            continue
        m = (np.isin(lab[y0:y1, x0:x1], ids) & (bw[y0:y1, x0:x1] > 0)).astype(np.uint8) * 255
        digits.append(_normalize(m))
        boxes.append((x0, y0, x1, y1))
    if comma is not None and comma >= len(digits):
        comma = None
    return digits, comma, boxes


def compose(digs: list[int], comma) -> float | None:
    """Ghép các chữ số thành điểm. Điểm luôn có 1 chữ số thập phân (9,5 / 10,0)."""
    if not digs:
        return None
    s = "".join(map(str, digs))
    if comma is not None and 0 < comma < len(s):
        v = float(s[:comma] + "." + s[comma:comma + 1])
    elif len(s) == 1:
        v = float(s)
    else:
        v = float(s[:-1] + "." + s[-1])
    return v if 0 <= v <= 10 else None


# ---------------- phân loại ----------------

_hog = cv2.HOGDescriptor((SIZE, SIZE), (14, 14), (7, 7), (7, 7), 9)


def _deskew(img):
    m = cv2.moments(img)
    if abs(m["mu02"]) < 1e-2:
        return img
    skew = m["mu11"] / m["mu02"]
    M = np.float32([[1, skew, -0.5 * SIZE * skew], [0, 1, 0]])
    return cv2.warpAffine(img, M, (SIZE, SIZE), flags=cv2.WARP_INVERSE_MAP | cv2.INTER_LINEAR)


def features(imgs) -> np.ndarray:
    out = []
    for im in imgs:
        im = _deskew(im)
        h = _hog.compute(im).ravel()
        small = cv2.resize(im, (10, 10), interpolation=cv2.INTER_AREA).ravel() / 255.0
        out.append(np.concatenate([h, small * 0.5]))
    return np.array(out, np.float32)


def _augment(imgs, labels, n=4, seed=0):
    rng = np.random.default_rng(seed)
    X, y = list(imgs), list(labels)
    for im, lb in zip(imgs, labels):
        for _ in range(n):
            ang = rng.uniform(-12, 12)
            sc = rng.uniform(0.85, 1.1)
            M = cv2.getRotationMatrix2D((SIZE / 2, SIZE / 2), ang, sc)
            M[:, 2] += rng.uniform(-1.5, 1.5, 2)
            a = cv2.warpAffine(im, M, (SIZE, SIZE))
            if rng.random() < 0.5:
                k = np.ones((2, 2), np.uint8)
                a = cv2.dilate(a, k) if rng.random() < 0.5 else cv2.erode(a, k)
            X.append(a)
            y.append(lb)
    return X, y


def sklearn_seed():
    """Bộ chữ số viết tay có sẵn trong scikit-learn (1797 mẫu) làm dữ liệu khởi đầu."""
    from sklearn.datasets import load_digits

    d = load_digits()
    imgs = []
    for im in d.images:
        m = (im / 16.0 * 255).astype(np.uint8)
        m = cv2.resize(m, (20, 20), interpolation=cv2.INTER_CUBIC)
        imgs.append(_normalize((m > 60).astype(np.uint8) * 255))
    return imgs, list(d.target)


class DigitModel:
    def __init__(self):
        self.clf = None
        self.n_user = 0

    def fit(self, user_imgs, user_labels, use_seed=True):
        from sklearn.svm import SVC

        X, y = _augment(user_imgs, user_labels, n=12) if user_imgs else ([], [])
        if use_seed:
            si, sl = sklearn_seed()
            k = len(si) // 2 if user_imgs else len(si)  # có dữ liệu thật thì giảm tỉ trọng bộ mẫu
            X += si[:k]
            y += sl[:k]
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            self.clf = SVC(C=8, gamma="scale", probability=True).fit(features(X), y)
        self.n_user = len(user_imgs)
        return self

    def predict(self, imgs):
        """-> danh sách (chữ số, xác suất)"""
        if not imgs:
            return []
        P = self.clf.predict_proba(features(imgs))
        cls = self.clf.classes_
        return [(int(cls[i]), float(p[i])) for p, i in zip(P, P.argmax(1))]

    def predict_proba(self, imgs):
        return self.clf.predict_proba(features(imgs)), self.clf.classes_


def read_score(model: DigitModel, cell: np.ndarray):
    """-> dict(value, conf, digits, comma, n_digits). value=None nếu ô trống / không đọc được.
    Dùng ràng buộc 'điểm 0..10' để chọn tổ hợp chữ số hợp lệ có xác suất cao nhất."""
    digs, comma, boxes = segment(cell)
    if not digs:
        return {"value": None, "conf": 1.0, "empty": True, "digits": [], "comma": None}
    P, cls = model.predict_proba(digs)
    order = [np.argsort(-p)[:3] for p in P]
    best = None
    # duyệt các tổ hợp top-3 của mỗi chữ số (tối đa 3 chữ số -> 27 tổ hợp)
    import itertools

    for combo in itertools.product(*order):
        ds = [int(cls[i]) for i in combo]
        v = compose(ds, comma)
        if v is None:
            continue
        if len(ds) == 3 and ds[:2] != [1, 0]:
            continue  # 3 chữ số chỉ hợp lệ với 10,0
        pr = float(np.prod([P[k][i] for k, i in enumerate(combo)]))
        if best is None or pr > best[0]:
            best = (pr, v, ds)
    if best is None or len(digs) > 3:
        return {"value": None, "conf": 0.0, "empty": False, "digits": [], "comma": comma}
    conf = best[0] ** (1.0 / len(best[2]))  # trung bình nhân theo chữ số
    if len(best[2]) == 1:
        conf *= 0.5  # điểm hầu như luôn có phần thập phân -> 1 chữ số là đáng ngờ
    return {"value": best[1], "conf": round(conf, 3), "empty": False, "digits": best[2], "comma": comma}


# ---------------- lưu / học thêm ----------------

def load_user_data():
    if os.path.exists(DATA_FILE):
        d = np.load(DATA_FILE)
        return list(d["X"]), list(d["y"])
    return [], []


def add_user_samples(cell: np.ndarray, value: float):
    """Lưu các chữ số của một ô đã được xác nhận đúng để lần sau đọc tốt hơn."""
    digs, comma, _ = segment(cell)
    s = f"{value:.1f}".replace(".", "")
    if s.endswith("0") and len(digs) == len(s) - 1 and value == int(value):
        s = s  # ví dụ "8,0" viết thành "8" -> bỏ qua
    if len(digs) != len(s):
        return 0  # tách chữ số không khớp -> không học, tránh dạy sai
    with _lock:
        X, y = load_user_data()
        X += digs
        y += [int(ch) for ch in s]
        os.makedirs(DATA_DIR, exist_ok=True)
        np.savez_compressed(DATA_FILE, X=np.array(X, np.uint8), y=np.array(y, np.int64))
    return len(digs)
