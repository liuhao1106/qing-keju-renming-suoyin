# -*- coding: utf-8 -*-
"""渲染核验图：把 OCR 实际输入的分栏图从分块 PDF 还原为 PNG。

优先级（后者覆盖）：cols_full < cols_fix < cols_fix2（与 parse_columns 合并顺序一致）。
p88R 虽由 cols_p88 半栏重识别，但其基础裁切与 cols_full 相同，直接用 cols_full 图。
输出: work/verify/pNNN_L.png / pNNN_R.png（300dpi，与 OCR 输入一致）
"""
import json, os
import pymupdf as fitz

ROOT = os.path.dirname(os.path.abspath(__file__))
ZOOM = 300 / 72
OUT = os.path.join(ROOT, "work", "verify")
os.makedirs(OUT, exist_ok=True)

# page -> (dir, stem)，后写覆盖
pmap = {"L": {}, "R": {}}
for side in ("L", "R"):
    for dname in ("cols_full", "cols_fix", "cols_fix2"):
        d = os.path.join(ROOT, "work", dname)
        idx = json.load(open(os.path.join(d, "index.json"), encoding="utf-8"))
        for chunk in idx[side]:
            for i, pg in enumerate(chunk["pages"]):
                pmap[side][pg] = (dname, chunk["stem"], i)

n = 0
for side in ("L", "R"):
    # 按stem聚合，一个PDF开一次
    by_pdf = {}
    for pg, (dname, stem, i) in sorted(pmap[side].items()):
        by_pdf.setdefault((dname, stem), []).append((pg, i))
    for (dname, stem), pgs in by_pdf.items():
        pdf = os.path.join(ROOT, "work", dname, stem + ".pdf")
        doc = fitz.open(pdf)
        for pg, i in pgs:
            pix = doc[i].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM))
            fp = os.path.join(OUT, f"p{pg:03d}_{side}.png")
            pix.save(fp)
            n += 1
        doc.close()
print(f"rendered {n} images -> {OUT}")
