# -*- coding: utf-8 -*-
"""对解析结果做质检，输出可疑项清单。

用法: python qa.py --records work/all/records.jsonl [--dict work/qz/surnames.json]
"""
import argparse, json, re, sys
from collections import Counter, defaultdict

NOTE = re.compile(r"[（(][^）)]*[）)]")
CJK = re.compile(r"[^\u4e00-\u9fff（）()]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--dict", default="work/qz/surnames.json")
    a = ap.parse_args()

    recs = [json.loads(l) for l in open(a.records, encoding="utf-8") if l.strip()]
    ents = [r for r in recs if r["type"] == "entry"]
    try:
        sd = json.load(open(a.dict, encoding="utf-8"))
    except Exception:
        sd = {}

    print(f"记录 {len(recs)}，条目 {len(ents)}")

    # 1) 每栏条数
    percol = Counter((r["page"], r["col"]) for r in ents)
    bad = {k: v for k, v in percol.items() if v < 12 or v > 45}
    print(f"\n[1] 条数异常的栏（<12 或 >45）: {len(bad)}")
    for (p, c), v in sorted(bad.items()):
        print(f"    p{p}{c}: {v}")

    # 2) 册/页范围
    jb = [r for r in ents if not (1 <= (r.get("juan") or 0) <= 100)]
    pb = [r for r in ents if not (1 <= (r.get("pref") or 0) <= 650)]
    print(f"\n[2] 册号越界 {len(jb)}，页码越界 {len(pb)}")
    for r in (jb + pb)[:15]:
        print(f"    p{r['page']}{r['col']} {r['surname']}{r['name']} {r.get('juan')}—{r.get('pref')}")

    # 3) 姓名异常字符
    nb = [r for r in ents
          if CJK.search(NOTE.sub("", r["name"])) or len(r["name"]) > 8]
    print(f"\n[3] 姓名含异常字符/过长: {len(nb)}")
    for r in nb[:15]:
        print(f"    p{r['page']}{r['col']} {r['surname']} / {r['name']!r}")

    # 4) 姓氏不在检字表
    unknown = {}
    for r in ents:
        if sd and r["surname"] not in sd:
            unknown.setdefault(r["surname"], 0)
            unknown[r["surname"]] += 1
    print(f"\n[4] 姓氏不在检字表({len(sd)}字): {len(unknown)}")
    for s, c in sorted(unknown.items(), key=lambda kv: -kv[1]):
        pages = sorted({r["page"] for r in ents if r["surname"] == s})
        print(f"    {s} ×{c}  p{pages[0]}{'-' if len(pages) > 1 else ''}{pages[-1] if len(pages) > 1 else ''}")

    # 5) 同一姓氏条目跨多个不连续区块（表头丢失的迹象）
    spans = defaultdict(list)
    for r in recs:
        if r["type"] == "head":
            spans[r.get("surname") or r.get("char")].append((r["page"], r["col"]))
    far = {s: v for s, v in spans.items() if len(v) > 1 and v[-1][0] - v[0][0] > 5}
    print(f"\n[5] 同姓表头相距 >5 页（可能是误认）: {len(far)}")
    for s, v in list(far.items())[:20]:
        print(f"    {s}: {v}")

    # 7) 同一姓氏块内 c2 应递增（递减说明漏表头或串行）
    dec = []
    prev = None
    last_sn = None
    for r in ents:
        if r["surname"] != last_sn:
            last_sn, prev = r["surname"], None
        c2 = r.get("c2") or ""
        if re.fullmatch(r"\d{2}", c2):
            v = int(c2)
            if prev is not None and v < prev:
                dec.append((r, prev, v))
            prev = v
    print(f"\n[7] 姓氏块内号码倒序（疑似漏表头/串行）: {len(dec)}")
    for r, a0, b0 in dec[:20]:
        print(f"    p{r['page']}{r['col']} {r['surname']}{r['name']} {a0}->{b0}")

    # 8) 完全没有条目的页
    done = sorted({r["page"] for r in recs})
    miss = [p for p in range(19, 157) if p not in done]
    print(f"\n[8] 无记录的索引页: {len(miss)} {miss}")

    # 6) 空姓氏/重复
    print(f"\n[6] 姓氏总数 {len(set(r['surname'] for r in ents))}，条目最多 10 姓:",
          Counter(r['surname'] for r in ents).most_common(10))


if __name__ == "__main__":
    main()
