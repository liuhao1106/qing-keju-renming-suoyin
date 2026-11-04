# -*- coding: utf-8 -*-
"""把目验核实的 5 处漏头/错挂修正应用到 records（2026-11-03 全量抽检产物）。

背景：PaddleOCR-VL 把 4 个表头的下标读成字母（s/o/a）导致解析为噪声，
另有 1 个表头（蒲）OCR 本身漏识。相关条目此前误挂到上一姓氏。

修正（全部经原图逐字核实）：
  p37L  1010₈ 靈  1 条（垕；即旧文档误作「王垕」者）
  p77R  3111₀ 江  45 条（慶楷…峯青 15 + p78L 德宣…鑑 30，误挂宋）
  p102L 4412₇ 蒲  2 条（明發、忭，误挂范）
  p102R 4416₉ 藩  1 条（恩元，误挂堵）
  p142L 7714₈ 闞  2 条（絅、毓岷）

用法: python apply_fixes.py --in work/all/records_v3.jsonl --out work/all/records.jsonl
（records_v3.jsonl 需已跑过 patch_p88）
"""
import argparse, json

FIXES = [
    # (定位条目 page, col, name, pref, 表头 code, sub, char)
    (37, "L", "垕", 379, "1010", "8", "靈"),
    (77, "R", "慶楷", 425, "3111", "0", "江"),
    (102, "R", "明發", 441, "4412", "7", "蒲"),
    (102, "R", "恩元", 437, "4416", "9", "藩"),
    (142, "L", "綱", 285, "7714", "8", "闞"),  # OCR 读「綱」，原图实为「絅」（见 NAME_FIX）
    # —— 以下 6 处为 qa[7] c2 倒序追查出的漏头（2026-11-03 逐一经原图核实）——
    (39, "L", "齊慶", 525, "1040", "0", "于"),     # p39L 栏首光杆「于」被丢（承干 1040₀），18 条误挂干
    (99, "L", "延齡", 491, "4220", "0", "蒯"),     # p98R 栏尾 4220₀ 蒯 被丢，3 条误挂彭
                                                    # （2026-11-04 二核：艹+朋+刂，前判「荊」误）
    (111, "R", "堃", 319, "4490", "4", "葉"),      # p111L 栏尾 4490₄ 葉 被丢，33+p112L 若干条误挂前姓
    (117, "L", "文盛", 491, "4722", "7", "郁"),    # p116R 栏尾 4722₇ 郁 被丢，8 条误挂楊
    (75, "R", "澍甘", 473, "3010", "6", "宣"),     # p75R 3010₆ 宣（栏中，前有印刷页码"3"）被丢，2 条误挂秋
    (147, "L", "福", 391, "8010", "4", "全"),      # p147L 8010₄ 全（栏中，前有印刷页码"8"）被丢，4 条误挂滕
    (145, "R", "榮春", 405, "7723", "2", "展"),    # p145L 栏底 7723₂ 展 被丢，1 条误挂周
]

# 跨栏表头的印刷位置：解析时归属到了下一栏首条之前，但书上印在前一栏栏尾。
# 键 = 定位条目所在的 (page, col)；值 = 表头实际印在的 (page, col) 栏尾。
# 键 = (定位条目 page, col, name)。用条目名而非仅页栏，避免同栏多个补头互相串位
# （p102R 既有「蒲」的定位条目明發、又有「藩」的恩元，仅用 (page,col) 会误挪）。
HEAD_AT = {
    (99, "L", "延齡"): (98, "R"),    # 4220₀ 蒯 印在 p98R 栏底
    (102, "R", "明發"): (102, "L"),  # 4412₇ 蒲 印在 p102L 栏底
    (111, "R", "堃"): (111, "L"),    # 4490₄ 葉 印在 p111L 栏底
    (117, "L", "文盛"): (116, "R"),  # 4722₇ 郁 印在 p116R 栏底
    (145, "R", "榮春"): (145, "L"),  # 7723₂ 展 印在 p145L 栏底
}

# 姓名单字修正（原图放大核实）：OCR 綱 -> 印刷絅（p142L 27 ～絅 99—285）
NAME_FIX = [
    (142, "L", 285, "綱", "絅"),
    (106, "L", 313, "—杜", "杜"),   # 印刷为 ～杜（单名），OCR 把～读成破折号
    (132, "R", 261, "存…", "存"),   # 印刷 ～存 后一字漫漶，按存字收录（见交付文档误差说明）
    (149, "L", 555, "日燈", "日灯"),  # 原图右旁为火+丁/工（非登），OCR 误作「燈」
    (154, "L", 399, "灏", "灝"),    # 原图繁体頁旁，OCR 输出简体
    (32, "R", 1, "灏", "灝"),       # 同上（p32R 92—1）
]

# 表头单字修正（转录/解析双方皆误，4x 放大裁决）
HEAD_FIX = [
    (26, "R", "諶", "譛"),   # 0461₁，言+甚=譛；其下条目「璋」随改姓（譛璋）
    (71, "R", "郃", "邰"),   # 2762₇，印码与 邰（台旁）相合、郃应作 8 头；转录亦读邰
    (89, "L", "遲", "逯"),   # 3730₃，原图辶+录（非犀）；其条目在下一栏首（～懿 16—431）
]

# 整行补录（原书有、OCR 整行漏收）。键：(page, col)；值：[(c2, name, juan, pref)]
MISSING_ROWS = {
    # p64R 栏首三行（目验 agent 发现）：无行首码，沿用上一行 c2=10
    (64, "R"): [("10", "可讀", 2, 481), ("10", "雲翥", 84, 317), ("10", "雲翹", 28, 351)],
}
# 同上，但插在栏尾（p48L 最后一行被裁切几何切掉，OCR 从未见过）
MISSING_ROWS_TAIL = {
    (48, "L"): [("25", "驤", 43, 73)],   # ～傳驤 43—73（原 PDF 页面可见，栏图裁切丢失）
}

# p88 结构修复（2026-11-04）：该页汤（湯）族跨栏，p88L 的裁图过宽把右栏上部一并读入，
# 而 patch_p88 又把右栏上半的重复识别结果塞进 p88R，造成①左栏多 17 行、②右栏首行
# 多出一条与「曜」重复的「暱」。此处把 17 行移回右栏首位、删掉重复行。
P88_RIGHT_TOP = ["翼然", "衡", "師淇", "繩和", "復蓀", "瀛", "汝和", "達", "肇曾",
                 "在寬", "希瑗", "壽潛", "懋功", "書田", "春", "振鵬", "曜"]


def base_row(prev, page, col, c2, nm, jy, pg):
    return {"page": page, "col": col, "type": "entry",
            "code": prev.get("code", ""), "surname": prev.get("surname", ""),
            "c2": c2, "name": nm, "juan": jy, "pref": pg, "tilde": True,
            "raw": f"（人工补：原图核实）～{nm} | {jy}—{pg}"}


def repair_p88(recs):
    li0 = next(i for i, r in enumerate(recs)
               if r["type"] == "entry" and r["page"] == 88 and r["col"] == "L"
               and r.get("name") == P88_RIGHT_TOP[0])
    li1 = next(i for i, r in enumerate(recs)
               if r["type"] == "entry" and r["page"] == 88 and r["col"] == "L"
               and r.get("name") == P88_RIGHT_TOP[-1])
    block = recs[li0:li1 + 1]
    names = [r["name"] for r in block]
    if names != P88_RIGHT_TOP:
        raise SystemExit(f"p88 结构非预期：{names}")
    del recs[li0:li1 + 1]
    for r in block:
        r["col"] = "R"
    # 删除右栏首行的重复「暱」（与左栏末行 曜 67—13—507 同址）
    dup = [i for i, r in enumerate(recs)
           if r["type"] == "entry" and r["page"] == 88 and r["col"] == "R" and r.get("name") == "暱"]
    for i in reversed(dup):
        del recs[i]
    # 插到右栏首条之前
    ins = next(i for i, r in enumerate(recs)
               if r["page"] == 88 and r["col"] == "R" and r["type"] == "entry")
    recs[ins:ins] = block
    print(f"p88: 右栏上 {len(block)} 行归位，删除重复行 {len(dup)} 条")


def insert_missing(recs):
    for (page, col), rows in MISSING_ROWS_TAIL.items():
        # 栏尾追加：插在该栏最后一条 entry 之后
        last = max(i for i, r in enumerate(recs)
                   if r["page"] == page and r["col"] == col and r["type"] == "entry")
        prev = recs[last]
        new = [dict(base_row(prev, page, col, c2, nm, jy, pg))
               for c2, nm, jy, pg in rows]
        recs[last + 1:last + 1] = new
        print(f"p{page}{col}: 栏尾补录 {len(new)} 条（{prev.get('surname')}）")
    for (page, col), rows in MISSING_ROWS.items():
        first = next((i for i, r in enumerate(recs)
                      if r["page"] == page and r["col"] == col and r["type"] == "entry"), None)
        if first is None:
            raise SystemExit(f"找不到 {page}{col} 首条")
        prev = recs[first - 1]
        new = [base_row(prev, page, col, c2, nm, jy, pg) for c2, nm, jy, pg in rows]
        recs[first:first] = new
        print(f"p{page}{col}: 补录漏收整行 {len(new)} 条（{prev.get('surname')}）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    recs = [json.loads(l) for l in open(a.inp, encoding="utf-8")]

    # 结构修复先做（改栏归属/补整行），再做表头重挂，最后改单字
    repair_p88(recs)
    insert_missing(recs)

    for page, col, name, pref, code, sub, ch in FIXES:
        # 找到该栏该表头之前最后一个 head 的位置，把新 head 插到它后面/或首条目之前
        start = None
        for i, r in enumerate(recs):
            if (r["type"] == "entry" and r["page"] == page and r["col"] == col
                    and r.get("name") == name and r.get("pref") == pref):
                start = i
                break
        if start is None:
            raise SystemExit(f"找不到定位条目 {page}{col} {name} {pref}")
        hp, hc = HEAD_AT.get((page, col, name), (page, col))
        if (hp, hc) != (page, col):
            # 放到实际印刷栏的栏尾
            tail = max(i for i, r in enumerate(recs)
                       if r["page"] == hp and r["col"] == hc and r["type"] == "entry")
            start = tail + 1
        head = {"page": hp, "col": hc, "type": "head", "code": code, "sub": sub,
                "char": ch, "raw": f"{code} {sub} {ch}（人工补：原图核实）"}
        recs.insert(start, head)
        # 重挂：从这里向后直到下一个 head；同时自检块内 c2 不应倒序（有则可能有新漏头）
        n = 0
        last_c2 = None
        for j in range(start + 1, len(recs)):
            r = recs[j]
            if r["type"] == "head":
                break
            c2 = r.get("c2") or ""
            if c2 and last_c2 and c2 < last_c2:
                print(f"  !! c2 倒序嫌疑 p{r['page']}{r['col']} {r.get('name')}: {last_c2}->{c2}")
            last_c2 = c2
            r["surname"] = ch
            r["code"] = code
            n += 1
        print(f"p{page}{col}: +表头 {code}_{sub} {ch}，重挂 {n} 条")

    # 姓名单字修正
    for page, col, pref, old, new in NAME_FIX:
        hit = False
        for r in recs:
            if (r["type"] == "entry" and r["page"] == page and r["col"] == col
                    and r.get("pref") == pref and r.get("name") == old):
                r["name"] = new
                hit = True
        print(f"p{page}{col}: 姓名 {old} -> {new}（{'✓' if hit else '未命中!'}）")

    # 表头单字修正（连同其下条目的姓一起改）
    for page, col, old, new in HEAD_FIX:
        hi = next((i for i, r in enumerate(recs)
                   if r["type"] == "head" and r["page"] == page and r["col"] == col
                   and r.get("char") == old), None)
        if hi is None:
            raise SystemExit(f"HEAD_FIX 找不到表头 {page}{col} {old}")
        recs[hi]["char"] = new
        recs[hi]["raw"] = recs[hi].get("raw", "") + f"（人工改：{old}->{new}）"
        n = 0
        for j in range(hi + 1, len(recs)):
            r = recs[j]
            if r["type"] == "head":
                break
            r["surname"] = new
            n += 1
        print(f"p{page}{col}: 表头 {old} -> {new}（{n} 条随改）")

    with open(a.out, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ents = sum(1 for r in recs if r["type"] == "entry")
    print(f"完成: 记录 {len(recs)}（条目 {ents}） -> {a.out}")


if __name__ == "__main__":
    main()
