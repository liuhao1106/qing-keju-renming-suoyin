# -*- coding: utf-8 -*-
"""把 p88R 的重新识别结果（上下两半）替换进 records.jsonl。

背景：p88R 原 OCR 把相邻两行并成一行表格行，导致 19 条姓名与册页错配。
已把该栏切成上下两半重跑（work/cols_p88/fix88_0、fix88_1），本脚本用
parse_columns.build() 以「湯 3612」为初始姓氏解析，并原位替换。

用法: python patch_p88.py [--records work/all/records.jsonl]
"""
import argparse, json, os
import parse_columns as P


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", default="work/all/records.jsonl")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    out = a.out or a.records

    top = "work/cols_p88/fix88_0/page_001.md"
    bot = "work/cols_p88/fix88_1/page_001.md"
    for p in (top, bot):
        if not os.path.exists(p):
            raise SystemExit(f"缺少 {p}")

    P.build([(88, top, bot)], "work/all/_p88_tmp.jsonl",
            verbose=True, seed={"surname": "湯", "code": "3612", "sub": "7", "c2": ""})
    new = [json.loads(l) for l in open("work/all/_p88_tmp.jsonl", encoding="utf-8")]

    old = [json.loads(l) for l in open(a.records, encoding="utf-8")]
    kept = [r for r in old if not (r["page"] == 88 and r["col"] == "R")]
    # 保持顺序：插在 p88L 之后
    idx = max(i for i, r in enumerate(kept) if r["page"] == 88 and r["col"] == "L") + 1
    merged = kept[:idx] + new + kept[idx:]

    with open(out, "w", encoding="utf-8") as f:
        for r in merged:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    old_n = sum(1 for r in old if r["page"] == 88 and r["col"] == "R" and r["type"] == "entry")
    new_n = sum(1 for r in new if r["type"] == "entry")
    print(f"\np88R: 旧 {old_n} 条 -> 新 {new_n} 条；总记录 {len(old)} -> {len(merged)}")


if __name__ == "__main__":
    main()
