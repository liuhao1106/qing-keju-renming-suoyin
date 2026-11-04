# -*- coding: utf-8 -*-
"""罕见姓程序化审计：找出可疑的姓氏表头误读。

信号（按强度）：
A. 同 (code,sub) 组里有条目数 >=10 的常见姓 —— 罕见姓很可能是它的形近误读
B. 检字表(work/qz/surnames.json)把该 code 映射到别的字
C. 其余罕见姓（≤2 条）—— 无程序化信号，列为待目验低优先级
输出: work/audit_surnames.json（分级清单）
"""
import json, os
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
recs = [json.loads(l) for l in open(os.path.join(ROOT, "work/all/records.jsonl"), encoding="utf-8")]

KNOWN_FIX = {"傳", "日", "鼓", "爲", "星"}  # build_output.FIX 已修正的表头

ent = [r for r in recs if r["type"] == "entry"]
cnt = Counter(r["surname"] for r in ent)

heads = [r for r in recs if r["type"] == "head"]
# 头继承链上 code/sub 已在解析时补全（bare head 也带 code/sub）
grp = defaultdict(list)          # (code,sub) -> [(char, page, col)]
for h in heads:
    grp[(h.get("code", ""), h.get("sub", ""))].append((h["char"], h["page"], h["col"]))

qz = json.load(open(os.path.join(ROOT, "work/qz/surnames.json"), encoding="utf-8"))
qz_by_code = defaultdict(list)
for ch, c in qz.items():
    qz_by_code[c].append(ch)

A, B, C = [], [], []
seen = set()
for sn, n in cnt.items():
    if n > 2:
        continue
    if sn in KNOWN_FIX:
        continue
    # 找该姓的表头位置
    locs = [(h["page"], h["col"]) for h in heads if h["char"] == sn]
    code_sub = [(h.get("code", ""), h.get("sub", "")) for h in heads if h["char"] == sn]
    cs = code_sub[0] if code_sub else ("", "")
    mates = [c for c, *_ in grp.get(cs, []) if c != sn]
    common_mates = [m for m in mates if cnt.get(m, 0) >= 10]
    qz_cands = [c for c in qz_by_code.get(cs[0], []) if c != sn and cnt.get(c, 0) >= 10]
    row = {"surname": sn, "n": n, "code": cs[0], "sub": cs[1],
           "loc": locs[0] if locs else None,
           "mates": sorted(set(mates)), "common_mates": sorted(set(common_mates)),
           "qz_cands": sorted(set(qz_cands))}
    if common_mates:
        A.append(row)
    elif qz_cands:
        B.append(row)
    else:
        C.append(row)

A.sort(key=lambda r: -r["n"])
B.sort(key=lambda r: -r["n"])
C.sort(key=lambda r: -r["n"])
out = {"A_common_mate": A, "B_qz_mismatch": B, "C_rest": C}
json.dump(out, open(os.path.join(ROOT, "work/audit_surnames.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print(f"罕见姓(≤2条)共 {len(A)+len(B)+len(C)} 个")
print(f"A 同组常见姓(强嫌疑) {len(A)}:")
for r in A:
    print(f"  {r['surname']}(n={r['n']}) {r['code']}_{r['sub']} p{r['loc'][0]}{r['loc'][1]}"
          f" 同组: {r['common_mates']} qz:{r['qz_cands']}")
print(f"B 检字表冲突 {len(B)}:")
for r in B:
    print(f"  {r['surname']}(n={r['n']}) {r['code']}_{r['sub']} p{r['loc'][0]}{r['loc'][1]} qz:{r['qz_cands']}")
print(f"C 无信号待目验 {len(C)}: " + " ".join(r["surname"] for r in C[:60]))
