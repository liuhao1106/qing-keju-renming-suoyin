# -*- coding: utf-8 -*-
"""解析分栏 OCR 文本（HTML 表格或纯文本行）-> 人名记录。

用法: python parse_columns.py --dir work/cols_full --out records.jsonl

目录需含 index.json / meta.json（slice_columns.py 产出），页序 = 索引顺序。
阅读顺序是单一线性流：页内 左栏 -> 右栏，再下一页 左栏 -> 右栏。
"""
import argparse, json, os, re, html
from collections import OrderedDict

DASH = "—–‐‑−~～"
LATEX_NOISE = re.compile(r"[$\\{}\^_]")
TAG = re.compile(r"<[^>]+>")


def clean(s):
    """把 OCR 单元格文本洗成纯文本。"""
    s = TAG.sub("", s)
    s = html.unescape(s)
    s = s.replace("&nbsp;", " ").replace("\u3000", " ")
    # Unicode 下标数字归一化为 ASCII（2026-11-03：8211₄ 鍾 之类此前无法识别）
    for i, d in enumerate("₀₁₂₃₄₅₆₇₈₉"):
        s = s.replace(d, str(i))
    s = LATEX_NOISE.sub("", s)          # 去掉 $ _ { } \ ^（PaddleOCR 的下标 LaTeX 残留）
    for ch in "—–‐‑−":
        s = s.replace(ch, "—")
    s = s.replace("~", "～")
    s = re.sub(r"\s+", " ", s).strip()
    return s


# 表头：「0022 廖」「0022 2 廖」「3021 4 寇」「0022廖」「高」
P = "[。.、,，:：;；·]?"   # OCR 常在号码后加句点
HEAD_CODE = re.compile(rf"^(\d{{4}})\s*{P}\s*([0-9])?\s*{P}\s*([\u4e00-\u9fff])$")
HEAD_BARE = re.compile(r"^([\u4e00-\u9fff])$")
# 右侧册—页：「3—143」「100—81」
PAGE = re.compile(r"^([0-9]{1,3})\s*[—～]\s*([0-9]{1,4})$")
PAGE_SP = re.compile(r"^([0-9]{1,3})\s+([0-9]{1,4})$")   # OCR 丢了破折号: 「4 281」
# 左侧：「10 ～正亨」「～平」「27 ～俶威」「10 ～玉」
CELL = re.compile(r"^([0-9]{0,2})\s*[.。、]?\s*(～)?\s*(.*)$")
NOISE = re.compile(r"清代科舉|家傳資料|滙編|汇编|人名四角|號碼|号码|索引|^#{1,3}|^\d{1,4}$")


def cells_of(row):
    return [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def read_rows(path):
    """返回 [(left, right_or_None), ...]，表格与纯文本两种格式都支持。"""
    text = open(path, encoding="utf-8").read()
    out = []
    if "<tr>" in text:
        # 2026-11-03 修复：PaddleOCR-VL 有时把表头输出成表格前的 <div>（如
        # 「7421_{4} 陸」），旧版只取 <tr> 导致整段姓氏挂到上一表头。
        # 现按出现位置合并 div 与 tr。
        items = []
        for m in re.finditer(r"<div[^>]*>(.*?)</div>", text, re.S):
            c = clean(m.group(1))
            if c:
                items.append((m.start(), (c, None)))
        for m in re.finditer(r"<tr>(.*?)</tr>", text, re.S):
            cs = [c for c in cells_of(m.group(1)) if c]
            if not cs:
                continue
            if len(cs) == 1:
                items.append((m.start(), (cs[0], None)))
            else:
                items.append((m.start(), (" ".join(cs[:-1]), cs[-1])))
        items.sort(key=lambda x: x[0])
        out = [v for _, v in items]
        return out, "table"

    lines = [clean(x) for x in text.splitlines()]
    lines = [x for x in lines if x and not NOISE.search(x)]
    i = 0
    while i < len(lines):
        line = lines[i]
        # 一行内「名  页码」
        m = re.match(r"^(.+?)\s{2,}(.+)$", line)
        if m:
            out.append((m.group(1), m.group(2)))
            i += 1
            continue
        # 名一行、页码一行
        if i + 1 < len(lines) and PAGE.match(lines[i + 1]) and not PAGE.match(line):
            out.append((line, lines[i + 1]))
            i += 2
            continue
        out.append((line, None))
        i += 1
    return out, "text"


def build(src, out_jsonl, verbose=True, seed=None):
    recs = []
    st = {"surname": None, "code": "", "sub": "", "c2": ""}
    if seed:
        st.update(seed)
    for page, pl, pr in src:
        for col, path in (("L", pl), ("R", pr)):
            if not path or not os.path.exists(path):
                if verbose:
                    print(f"  ! 缺页 p{page}{col}")
                continue
            rows, kind = read_rows(path)
            if verbose:
                print(f"== p{page}{col} ({kind}, {len(rows)}) 姓={st['surname']}")
            for left, right in rows:
                # 1) 表头
                if right is None:
                    m = HEAD_CODE.match(left) or HEAD_CODE.match(left.split(" ")[-3:] and " ".join(left.split()[-3:]))
                    if m:
                        # div+表格双份表头去重：同一栏连续两个同码带号表头 = 同一印刷行被读两次，
                        # 保留前者（div 在前，实测 div 字更准：季/甘/陸）
                        if (recs and recs[-1]["type"] == "head" and recs[-1]["page"] == page
                                and recs[-1]["col"] == col and recs[-1]["code"] == m.group(1)):
                            prev = recs[-1]
                            print(f"  ! 重复表头 p{page}{col}: {prev['code']}_{prev['sub']} {prev['char']}"
                                  f" vs {m.group(1)}_{m.group(2) or ''} {m.group(3)} —— 保留前者")
                            continue
                        st.update(code=m.group(1), sub=m.group(2) or "", surname=m.group(3), c2="")
                        recs.append({"page": page, "col": col, "type": "head", "code": st["code"],
                                     "sub": st["sub"], "char": st["surname"], "raw": left})
                        continue
                    if HEAD_BARE.match(left):
                        st.update(surname=left, c2="")
                        recs.append({"page": page, "col": col, "type": "head", "code": st["code"],
                                     "sub": st["sub"], "char": left, "raw": left})
                        continue
                    # 一格塞下「10 ～玉 92—83」
                    m2 = re.match(r"^(.*?)\s+([0-9]{1,3}\s*—\s*[0-9]{1,4})$", left)
                    if m2:
                        left, right = m2.group(1), m2.group(2)
                    else:
                        if not NOISE.search(left):
                            print(f"  ? 噪声 p{page}{col}: {left[:50]}")
                        continue
                # 2) 条目
                mp = PAGE.match(right or "") or PAGE_SP.match(right or "")
                if not mp:
                    # 页码列可能是「3—14 3」之类，取第一段
                    mp = re.search(r"([0-9]{1,3})\s*—\s*([0-9]{1,4})", right or "")
                    if not mp:
                        print(f"  ? 页码未识别 p{page}{col}: {left} | {right}")
                        continue
                juan, pref = int(mp.group(1)), int(mp.group(2))
                mc = CELL.match(left)
                if not mc:
                    print(f"  ? 姓名未识别 p{page}{col}: {left}")
                    continue
                c2, tilde, name = mc.group(1), mc.group(2), mc.group(3).strip()
                if not name:
                    print(f"  ? 空姓名 p{page}{col}: {left}")
                    continue
                if not st["surname"]:
                    print(f"  ! 无姓氏，丢弃 p{page}{col}: {left} | {right}")
                    continue
                if c2:
                    st["c2"] = c2
                recs.append({"page": page, "col": col, "type": "entry", "code": st["code"],
                             "surname": st["surname"], "c2": c2 or st["c2"], "name": name,
                             "juan": juan, "pref": pref, "tilde": bool(tilde),
                             "raw": f"{left} | {right}"})

    with open(out_jsonl, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ents = [r for r in recs if r["type"] == "entry"]
    print(f"\n条目 {len(ents)} / 记录 {len(recs)}  ->  {out_jsonl}")
    c = OrderedDict()
    for r in ents:
        c[r["surname"]] = c.get(r["surname"], 0) + 1
    print(f"姓氏 {len(c)} 个：", dict(c))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", help="单个 OCR 目录")
    ap.add_argument("--dirs", help="多个 OCR 目录(逗号分隔)，后者覆盖前者同页")
    ap.add_argument("--pages", default=None, help="只解析这些页，如 19-21 或 24,36")
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    dirs = [x.strip() for x in (a.dirs or a.dir).split(",") if x.strip()]
    paths = {"L": {}, "R": {}}
    used = 0
    for d in dirs:                      # 后者覆盖前者：修补页优先
        got = {"L": {}, "R": {}}
        idx_path = os.path.join(d, "index.json")
        meta_path = os.path.join(d, "meta.json")
        if os.path.exists(idx_path):
            index = json.load(open(idx_path, encoding="utf-8"))
            for side in ("L", "R"):
                for it in index[side]:
                    for i, pg in enumerate(it["pages"]):
                        got[side][pg] = os.path.join(d, "ocr_" + side, it["stem"], f"page_{i+1:03d}.md")
        elif os.path.exists(meta_path):
            meta = json.load(open(meta_path, encoding="utf-8"))
            for i, r in enumerate(meta):
                got["L"][r["page"]] = os.path.join(d, "ocr_L", f"page_{i+1:03d}.md")
                got["R"][r["page"]] = os.path.join(d, "ocr_R", f"page_{i+1:03d}.md")
        else:
            print(f"  ! {d} 缺 index.json/meta.json，跳过")
            continue
        used += 1
        for side in ("L", "R"):
            paths[side].update({k: v for k, v in got[side].items() if os.path.exists(v)})
    if not used:
        raise SystemExit("没有任何可用目录")

    pages = sorted(set(paths["L"]) | set(paths["R"]))
    if a.pages:
        sel = set()
        for part in a.pages.split(","):
            if "-" in part:
                x, y = part.split("-")
                sel |= set(range(int(x), int(y) + 1))
            else:
                sel.add(int(part))
        pages = [p for p in pages if p in sel]

    src = [(pg, paths["L"].get(pg), paths["R"].get(pg)) for pg in pages]
    build(src, a.out or os.path.join(d, "records.jsonl"), verbose=not a.quiet)


if __name__ == "__main__":
    main()
