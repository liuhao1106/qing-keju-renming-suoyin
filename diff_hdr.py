# -*- coding: utf-8 -*-
"""把表头盲转录结果（agent JSON）与解析记录比对。

转录 JSON 形如 {"id":"hdr2_00","pages":{"26":{"L":[{"kind":"coded","code":"0466","sub":"0","char":"諸"}],"R":[...]}}}
比对规则：按栏内顺序对齐；coded 比 code+char（sub 仅提示）；bare 只比 char。
parse 侧 bare 表头带继承码，视为与 transcription 的 bare 对应。
多出/缺失的表头都会列出。用法：
  python diff_hdr.py work/verify/results/hdr2_00.json
"""
import json, sys

recs = [json.loads(l) for l in open("work/all/records.jsonl", encoding="utf-8")]
heads = {}
for r in recs:
    if r["type"] == "head":
        heads.setdefault((r["page"], r["col"]), []).append(r)


def norm_char(c):
    # 与 build_output.FIX 对齐的已知异体归一
    return {"傳": "傅", "日": "甘", "爲": "為", "星": "童", "蒋": "蔣"}.get(c, c)


def diff_one(tj):
    tid = tj["id"]
    problems = []
    for pg, cols in tj["pages"].items():
        pg = int(pg)
        # 按页内阅读顺序（L 全栏 + R 全栏）比对：本书表头可能印在前栏栏尾，
        # 解析时归属到下一栏首，逐栏比会产生假的「错位」。
        tr_all = list(cols.get("L", [])) + list(cols.get("R", []))
        pa_all = heads.get((pg, "L"), []) + heads.get((pg, "R"), [])
        if len(tr_all) != len(pa_all):
            problems.append(f"p{pg}: 表头数量不符 转录{len(tr_all)} vs 解析{len(pa_all)} "
                            f"转录=[{','.join(h.get('char','?') for h in tr_all)}] "
                            f"解析=[{','.join(h.get('char','?') for h in pa_all)}]")
        for k in range(max(len(tr_all), len(pa_all))):
            t = tr_all[k] if k < len(tr_all) else None
            p_ = pa_all[k] if k < len(pa_all) else None
            if t is None:
                problems.append(f"p{pg}[{k}]: 解析多出 {p_.get('code')}_{p_.get('sub')} {p_.get('char')} (raw={p_.get('raw','')[:20]!r})")
                continue
            if p_ is None:
                problems.append(f"p{pg}[{k}]: 转录多出 {t.get('kind')} {t.get('code','')}_{t.get('sub','')} {t.get('char')} —— 疑似漏表头!")
                continue
            tc, pc = norm_char(t.get("char", "")), norm_char(p_.get("char", ""))
            if tc != pc:
                problems.append(f"p{pg}[{k}]: 字不同 转录={t.get('char')}(alt={t.get('alt','')}) 解析={p_.get('char')} "
                                f"(码: 转录{t.get('code','')} vs 解析{p_.get('code')})")
            elif t.get("kind") == "coded" and t.get("code") and t.get("code") != p_.get("code"):
                problems.append(f"p{pg}[{k}]: 码不同 {p_.get('char')}: 转录{t.get('code')}_{t.get('sub','')} vs 解析{p_.get('code')}_{p_.get('sub','')}")
        continue
        for col in ("L", "R"):
            tr = cols.get(col, [])
            pa = heads.get((pg, col), [])
            # 对齐：两侧都按顺序；先比数量
            if len(tr) != len(pa):
                problems.append(f"p{pg}{col}: 数量不符 转录{len(tr)} vs 解析{len(pa)} "
                                f"转录=[{','.join(h.get('char','?') for h in tr)}] "
                                f"解析=[{','.join(h.get('char','?') for h in pa)}]")
            for k in range(max(len(tr), len(pa))):
                t = tr[k] if k < len(tr) else None
                p = pa[k] if k < len(pa) else None
                if t is None:
                    problems.append(f"p{pg}{col}[{k}]: 解析多出 {p.get('code')}_{p.get('sub')} {p.get('char')} (raw={p.get('raw','')[:20]!r})")
                    continue
                if p is None:
                    problems.append(f"p{pg}{col}[{k}]: 转录多出 {t.get('kind')} {t.get('code','')}_{t.get('sub','')} {t.get('char')} —— 疑似漏表头!")
                    continue
                tc, pc = norm_char(t.get("char", "")), norm_char(p.get("char", ""))
                if tc != pc:
                    problems.append(f"p{pg}{col}[{k}]: 字不同 转录={t.get('char')}(alt={t.get('alt','')}) 解析={p.get('char')} "
                                    f"(码: 转录{t.get('code','')} vs 解析{p.get('code')})")
                elif t.get("kind") == "coded" and t.get("code") and t.get("code") != p.get("code"):
                    problems.append(f"p{pg}{col}[{k}]: 码不同 {p.get('char')}: 转录{t.get('code')}_{t.get('sub','')} vs 解析{p.get('code')}_{p.get('sub','')}")
                elif t.get("kind") == "coded" and t.get("code") and (t.get("sub") or "") != (p.get("sub") or ""):
                    problems.append(f"p{pg}{col}[{k}]: 附角不同 {p.get('char')}: 转录_{t.get('sub','')} vs 解析_{p.get('sub','')}（仅提示）")
    return tid, problems


if __name__ == "__main__":
    total = 0
    for path in sys.argv[1:]:
        tj = json.load(open(path, encoding="utf-8"))
        tid, problems = diff_one(tj)
        print(f"== {tid} ({path})")
        if not problems:
            print("   ✓ 全部一致")
        for p in problems:
            print("   ✗", p)
        total += len(problems)
    print(f"\n合计问题 {total} 处")
