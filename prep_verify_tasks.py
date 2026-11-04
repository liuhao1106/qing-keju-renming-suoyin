# -*- coding: utf-8 -*-
"""准备目验任务：
1) 把 276 张分栏图切成上下两半（40px 重叠）-> work/verify/half/
2) 随机抽 15 栏（固定种子）作为字准率抽样 -> work/verify/tasks/col_NN.json
3) 69 个罕见姓涉及页 -> 表头盲转录任务 -> work/verify/tasks/hdr_NN.json
"""
import json, os, random
from PIL import Image

ROOT = os.path.dirname(os.path.abspath(__file__))
V = os.path.join(ROOT, "work", "verify")
H = os.path.join(V, "half")
T = os.path.join(V, "tasks")
os.makedirs(H, exist_ok=True)
os.makedirs(T, exist_ok=True)

recs = [json.loads(l) for l in open(os.path.join(ROOT, "work/all/records.jsonl"), encoding="utf-8")]

# ---------- 1) 切半 ----------
for f in sorted(os.listdir(V)):
    if not f.endswith(".png"):
        continue
    stem = f[:-4]                      # p019_L
    src = os.path.join(V, f)
    im = Image.open(src)
    w, h = im.size
    mid = h // 2
    im.crop((0, 0, w, mid + 40)).save(os.path.join(H, stem + "_top.png"))
    im.crop((0, mid - 40, w, h)).save(os.path.join(H, stem + "_bot.png"))
print("halves done")

# ---------- 2) 抽样栏 ----------
cols = sorted({(r["page"], r["col"]) for r in recs})
random.seed(20261103)
sample = sorted(random.sample(cols, 15))
samp_entries = sum(1 for r in recs if r["type"] == "entry" and (r["page"], r["col"]) in sample)
print("sample cols:", [(p, c) for p, c in sample], "entries:", samp_entries)

by_col = {}
for r in recs:
    by_col.setdefault((r["page"], r["col"]), []).append(r)

tasks_col = []
for i, (pg, c) in enumerate(sample):
    rs = by_col[(pg, c)]
    tasks_col.append({
        "task": "col", "id": f"col_{i:02d}", "page": pg, "col": c,
        "images": [os.path.join(H, f"p{pg:03d}_{c}_top.png"), os.path.join(H, f"p{pg:03d}_{c}_bot.png")],
        "records": rs,
    })
json.dump(tasks_col, open(os.path.join(T, "col_tasks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------- 3) 表头盲转录任务（69 页，5 页/任务） ----------
audit = json.load(open(os.path.join(ROOT, "work/audit_surnames.json"), encoding="utf-8"))
suspect = {}
for k in ("A_common_mate", "B_qz_mismatch", "C_rest"):
    for r in audit[k]:
        suspect.setdefault(r["surname"], r)
pages = sorted({r["loc"][0] for r in suspect.values()})
print("header pages:", len(pages))

heads_by_page = {}
for r in recs:
    if r["type"] == "head":
        heads_by_page.setdefault(r["page"], []).append(r)

tasks_hdr = []
CHUNK = 5
for i in range(0, len(pages), CHUNK):
    pgs = pages[i:i + CHUNK]
    tasks_hdr.append({
        "task": "hdr", "id": f"hdr_{i//CHUNK:02d}", "pages": pgs,
        "images": {str(pg): [os.path.join(H, f"p{pg:03d}_L_top.png"), os.path.join(H, f"p{pg:03d}_L_bot.png"),
                             os.path.join(H, f"p{pg:03d}_R_top.png"), os.path.join(H, f"p{pg:03d}_R_bot.png")]
                   for pg in pgs},
        "expected_suspects": {str(pg): [r["surname"] for r in suspect.values() if r["loc"][0] == pg] for pg in pgs},
    })
json.dump(tasks_hdr, open(os.path.join(T, "hdr_tasks.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"col tasks: {len(tasks_col)}, hdr tasks: {len(tasks_hdr)}")
