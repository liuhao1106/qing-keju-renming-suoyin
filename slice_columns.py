# -*- coding: utf-8 -*-
"""把索引页按栏切成左右两张图，并按区间拼成多页 PDF 交给 PaddleOCR-VL。

用法:
  python slice_columns.py --pages 19-21 --out work/cols --pdf
  python slice_columns.py --pages 19-156 --out work/cols --pdf --chunk 23
"""
import argparse, json, os, sys
import numpy as np
import fitz
from PIL import Image, ImageOps

ZOOM = 300 / 72.0

def detect_rules(gray, min_frac=0.45):
    """竖线在下 45%~97% 的行区间内投影（避开标题区），横线在整页投影。

    扫描件每页深浅不同、线还会轻微漂移，故用较宽松的阈值 210 加 ±3px 水平膨胀，
    否则浅色页（p24/p36/p70 等）只剩一条框线。
    """
    H, W = gray.shape
    b = gray < 210
    bm = b.copy()
    for k in (1, 2, 3):
        bm = bm | np.roll(b, k, axis=1) | np.roll(b, -k, axis=1)
    y0, y1 = int(H * 0.45), int(H * 0.97)
    col = bm[y0:y1, :].sum(axis=0) / max(1, (y1 - y0))
    row = (gray < 128).sum(axis=1) / W
    def runs(frac, thr):
        idx = np.where(frac > thr)[0]
        out = []
        if len(idx) == 0:
            return out
        start = prev = idx[0]
        for x in idx[1:]:
            if x - prev <= 4:
                prev = x
            else:
                out.append((start, prev)); start = prev = x
        out.append((start, prev))
        return out
    vs = runs(col, 0.60)
    hs = runs(row, min_frac)
    return vs, hs

def pick_vertical(vs, W):
    """返回 (左框, 分隔线, 右框)。缺线时按对称/居中估计。"""
    cands = [((a + b) // 2, b - a + 1) for a, b in vs]
    cands = [c for c in cands if c[0] > W * 0.05]
    if not cands:
        return int(W * 0.2), int(W * 0.5), int(W * 0.8)
    xs = [c[0] for c in cands]
    left, right = min(xs), max(xs)
    if len(xs) >= 3:
        mid = [x for x in xs if left + (right - left) * 0.25 < x < left + (right - left) * 0.75]
        gutter = sorted(mid, key=lambda x: abs(x - (left + right) / 2))[0] if mid else (left + right) // 2
        return left, gutter, right
    if len(xs) == 2:
        span = right - left
        if span > W * 0.25:                       # 两条应是左右框，中线取中
            return left, (left + right) // 2, right
        gutter = right                            # 应是左框 + 中缝，右框按对称估
        return left, gutter, int(gutter + (gutter - left))
    return left, int(left + (W * 0.55 - left)), int(left + 2 * (W * 0.55 - left))

def line_span(gray, x, gap=6):
    """某竖线 x 的上下端（取首/末个“有墨水”的行，抗断线与噪点）。

    扫描件的框线会断成几段，用最长连续段会丢掉整段表格，故改为首末端，
    并要求 20 行窗口内至少 5 行有墨，避免灰尘点误判。
    """
    H, W = gray.shape
    band = gray[:, max(0, x - 2):min(W, x + 3)]
    dark = (band < 190).any(axis=1).astype(int)
    win = 20
    csum = np.convolve(dark, np.ones(win, dtype=int), mode="same")
    ok = np.where(csum >= 5)[0]
    if len(ok) == 0:
        return None
    return int(ok[0]), int(ok[-1])

def pick_horizontal(hs, H, W, gray=None, frame=None):
    if gray is not None and frame:
        b = (gray < 210)
        bm = b.copy()
        for k in (1, 2, 3):
            bm = bm | np.roll(b, k, axis=0) | np.roll(b, -k, axis=0)
        _l, _r = frame[0], frame[-1]
        x0, x1 = _l + 10, _r - 10
        if x1 - x0 > 100:
            row = bm[:, x0:x1].sum(axis=1) / float(x1 - x0)
            idx = np.where(row > 0.55)[0]
            if len(idx):
                return int(idx[0]), int(idx[-1])
        spans = [s for s in (line_span(gray, x) for x in frame) if s]
        spans = [s for s in spans if s[1] - s[0] > H * 0.5]
        if spans:
            return min(s[0] for s in spans), max(s[1] for s in spans)
    ys = [((a + b) // 2) for a, b in hs]
    if not ys:
        return int(H * 0.20), int(H * 0.92)
    top = min([y for y in ys if y < H * 0.45] or [int(H * 0.20)])
    bot = max([y for y in ys if y > H * 0.55] or [int(H * 0.92)])
    return top, bot

def slice_page(page, page_no, outdir, meta, save_png=True, dpi_zoom=ZOOM):
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi_zoom, dpi_zoom), colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    W, H = img.size
    g = np.array(img)
    vs, hs = detect_rules(g, 0.45)
    L, G, R = pick_vertical(vs, W)
    T, B = pick_horizontal(hs, H, W, gray=g, frame=[L, R])
    y0, y1 = max(0, T - 2), min(H, B + 3)
    boxes = {
        "L": (L + 4, y0, G - 3, y1),
        "R": (G + 3, y0, R - 4, y1),
    }
    rec = {"page": page_no, "W": int(W), "H": int(H),
           "vlines": [[int(a), int(b)] for a, b in vs],
           "hlines": [[int(a), int(b)] for a, b in hs],
           "frame": [int(L), int(G), int(R)], "top": int(T), "bot": int(B),
           "boxes": {k: [int(x) for x in v] for k, v in boxes.items()}}
    meta.append(rec)
    outs = {}
    for k, box in boxes.items():
        if box[2] - box[0] < 50 or box[3] - box[1] < 50:
            outs[k] = None
            continue
        im = img.crop(box)
        im = ImageOps.expand(im, border=(14, 22, 14, 14), fill=255)
        if save_png:
            im.save(os.path.join(outdir, f"p{page_no:03d}_{k}.png"))
        outs[k] = im
    return outs, rec

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", default="work/cols")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--chunks", action="store_true", help="生成分栏多页 PDF")
    ap.add_argument("--chunk", type=int, default=0, help="每份 PDF 页数, 0=不切")
    ap.add_argument("--nopng", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pages_list = []
    for part in a.pages.split(","):
        part = part.strip()
        if "-" in part:
            x, y = part.split("-"); pages_list += list(range(int(x), int(y) + 1))
        elif part:
            pages_list.append(int(part))
    s, e = pages_list[0], pages_list[-1]
    doc = fitz.open(a.pdf)
    meta = []
    imgs = {"L": [], "R": []}
    kept = {"L": [], "R": []}
    for pno in pages_list:
        page = doc[pno - 1]
        outs, rec = slice_page(page, pno, a.out, meta, save_png=not a.nopng)
        for k in ("L", "R"):
            if outs.get(k) is not None:
                imgs[k].append(outs[k])
                kept[k].append(pno)
    with open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    print(f"sliced {len(meta)} pages -> {a.out}")
    for r in meta[:3]:
        print(r["page"], r["frame"], r["top"], r["bot"], r["boxes"])
    if a.chunks:
        n = a.chunk or len(imgs["L"])
        index = {"L": [], "R": []}
        for k in ("L", "R"):
            lst, pg = imgs[k], kept[k]
            for i in range(0, len(lst), n):
                part = lst[i:i + n]
                pp = pg[i:i + n]
                stem = f"{k}_{i//n:02d}_{pp[0]:03d}_{pp[-1]:03d}"
                name = os.path.join(a.out, stem + ".pdf")
                part[0].save(name, save_all=True, append_images=part[1:], resolution=300.0)
                index[k].append({"stem": stem, "pages": pp, "count": len(part)})
                print("pdf:", name, len(part))
        with open(os.path.join(a.out, "index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()


# ---------------- 墨迹法几何（更稳，作为默认） ----------------

def ink_runs(col, thr=0.015, gap=28):
    """列投影 -> 连续墨迹区段，返回 [(x0, x1), ...]。"""
    on = col > thr
    runs = []
    s = None
    last = -10 ** 6
    for x, v in enumerate(on):
        if v:
            if s is None:
                s = x
            last = x
        elif s is not None and x - last > gap:
            runs.append((s, last))
            s = None
    if s is not None:
        runs.append((s, last))
    return runs


def ink_geometry(gray):
    """用正文墨迹判定 (x0, x1, gutter, top, bot)，不依赖框线是否存在。

    扫描件框线时有时无、页面还会整体偏移（如 p133 框线检测把中缝当左框），
    而正文墨迹始终是稳定的两栏块，故以墨迹为准。
    """
    H, W = gray.shape
    b = (gray < 170)
    # 列投影（避开页眉页脚）
    r0, r1 = int(H * 0.05), int(H * 0.97)
    col = b[r0:r1].sum(axis=0) / float(r1 - r0)
    runs = [r for r in ink_runs(col) if r[1] - r[0] > W * 0.15]
    if not runs:
        return None
    x0, x1 = max(runs, key=lambda r: r[1] - r[0])
    # 中缝：在正文块中间找墨最少的列
    lo = x0 + int((x1 - x0) * 0.35)
    hi = x0 + int((x1 - x0) * 0.65)
    seg = col[lo:hi]
    k = 21
    sm = np.convolve(seg, np.ones(k) / k, mode="same")
    g = lo + int(np.argmin(sm))
    # 行方向：正文首末行
    row = b[:, x0:x1].sum(axis=1) / float(x1 - x0)
    dk = row > 0.01
    win = 30
    cw = np.convolve(dk.astype(int), np.ones(win, dtype=int), mode="same")
    ok = np.where(cw >= 8)[0]
    if len(ok) == 0:
        return None
    top, bot = int(ok[0]), int(ok[-1])
    return x0, x1, g, top, bot
