# -*- coding: utf-8 -*-
"""对几何检测失败的页，用同奇偶邻页的中位框线重切。

用法: python reframe.py --pdf <pdf> --meta work/cols_full/meta.json \
          --pages 25,87,94,96,112,133,145,153 --out work/cols_fix2 --chunk 8
"""
import argparse, json, os, statistics as st
import fitz, numpy as np
from PIL import Image, ImageOps
import slice_columns as S

ZOOM = 300 / 72


def rule_geometry(g):
    """用表格横线的两端定左右边界，用框内竖线定中缝。

    横线（首行/末行）横跨整个表框，其墨迹端点即 (x0, x1)，比竖线检测稳；
    中缝是有连续墨的竖线，取窗口内"墨最连续且最靠中间"的一列。
    """
    H, W = g.shape
    b = (g < 210)
    bm = b.copy()
    for k in (1, 2, 3):
        bm = bm | np.roll(b, k, 0) | np.roll(b, -k, 0)
    row = bm[:, int(W * 0.15):int(W * 0.9)].sum(1) / float(int(W * 0.9) - int(W * 0.15))
    idx = np.where(row > 0.5)[0]
    if len(idx) == 0:
        return None
    t, bt = int(idx[0]), int(idx[-1])
    band = bm[t:min(t + 14, H)]
    cols = np.where(band.sum(0) >= band.shape[0] * 0.6)[0]
    if len(cols) < 2:
        return None
    x0, x1 = int(cols[0]), int(cols[-1])
    if not (x1 - x0 > W * 0.5):
        return None
    body = b[int(t + 40):int(bt - 20), x0:x1]
    colf = body.sum(0) / float(body.shape[0])
    w = x1 - x0
    lo, hi = int(w * 0.25), int(w * 0.75)
    cen = w // 2
    cand = [x for x in range(lo, hi) if colf[x] > 0.70]
    if cand:
        gx = min(cand, key=lambda x: abs(x - cen))
    else:
        gx = cen
    return x0, x0 + gx, x1, t, bt


def valid(rec):
    f = rec["frame"]
    return 600 < f[1] - f[0] < 800 and 600 < f[2] - f[1] < 800


def ref_frame(meta_by_page, pno):
    """同奇偶、最近的若干有效页，取 frame 中位数。"""
    cands = []
    for side in (-1, 1):
        step = 2
        k = 0
        while len([c for c in cands if c[1] == side]) < 3 and k < 20:
            q = pno + side * step
            k += 1
            step += 2
            if q in meta_by_page and valid(meta_by_page[q]):
                cands.append((q, side, meta_by_page[q]["frame"]))
    if not cands:
        return None
    fs = [c[2] for c in cands]
    return [int(st.median([f[i] for f in fs])) for i in range(3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--meta", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", default="work/cols_fix2")
    ap.add_argument("--chunk", type=int, default=8)
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    meta = json.load(open(a.meta, encoding="utf-8"))
    by = {r["page"]: r for r in meta}
    pages = [int(x) for x in a.pages.split(",")]
    doc = fitz.open(a.pdf)

    sides = {"L": [], "R": []}
    out_meta = []
    for pno in pages:
        pix = doc[pno - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), colorspace=fitz.csGRAY)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        g = np.array(img)
        H, W = g.shape
        geo = rule_geometry(g)
        if geo is None:
            fr = ref_frame(by, pno)
            if fr is None:
                print(f"  ! p{pno} 无法定位")
                continue
            L, G, R = fr
            T, B = S.pick_horizontal([], H, W, gray=g, frame=[L, R])
        else:
            L, G, R, T, B = geo
        y0, y1 = max(0, T - 2), min(H, B + 3)
        boxes = {"L": (L + 4, y0, G - 3, y1), "R": (G + 3, y0, R - 4, y1)}
        for k, box in boxes.items():
            if box[2] - box[0] < 50 or box[3] - box[1] < 50:
                print(f"  ! p{pno}{k} 框太小 {box}")
                continue
            im = ImageOps.expand(img.crop(box), border=(14, 22, 14, 14), fill=255)
            sides[k].append((pno, im))
        print(f"p{pno} frame={[L, G, R]} top/bot={T}/{B}")
        out_meta.append({"page": pno, "frame": [L, G, R], "top": int(T), "bot": int(B),
                         "boxes": {k: [int(x) for x in v] for k, v in boxes.items()}})

    index = {"L": [], "R": []}
    for k in ("L", "R"):
        items = sides[k]
        for i in range(0, len(items), a.chunk):
            part = items[i:i + a.chunk]
            stem = f"{k}_{i//a.chunk:02d}_{part[0][0]:03d}_{part[-1][0]:03d}"
            path = os.path.join(a.out, stem + ".pdf")
            part[0][1].save(path, save_all=True, append_images=[im for _, im in part[1:]], resolution=300)
            index[k].append({"stem": stem, "pages": [p for p, _ in part], "count": len(part)})
            print("pdf:", path, len(part))

    json.dump(index, open(os.path.join(a.out, "index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(out_meta, open(os.path.join(a.out, "meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
