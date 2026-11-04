# -*- coding: utf-8 -*-
"""把 records.jsonl（解析结果）重编成按姓氏排列的成果文件。

用法: python build_output.py --records work/all/records.jsonl --outdir output
产出: 按姓重编_全表.csv / .xlsx / .html  + 姓氏统计.csv
"""
import argparse, csv, html, json, os, re
from collections import Counter, defaultdict
from pypinyin import lazy_pinyin

# 已知 OCR 形近误认（表头单字）-> 正确姓氏
# 2026-11-03 全量抽检更新：撤销「鼓→戈」（p102R 原图明确是鼓 4414₇）；
# 新增「蒋→蔣」（p104L div 被模型写成简体，原图为繁体蔣 4424₇）
FIX = {
    "傳": "傅",   # 2324 傅
    "日": "甘",   # 4477 甘
    "爲": "為",
    "星": "童",   # 0010 童（p19L 表头实为「童」）
    "蒋": "蔣",   # 4424₇ 蔣
}
NOTE = re.compile(r"[（(]([^）)]*)[）)]")

# 复姓还原：本书对复姓按首字立头（如 0466₀ 諸 下挂 ～葛璋=諸葛璋），
# 已逐处目验原书表头确认（p27L諸/p51R司/p53R上/p63R皇/p122L申/p146R歐 均为单字头）。
# 姓名字段已是完整姓名（头字+余字），此处把姓氏列归到真实复姓。
COMPOUNDS = {
    "諸葛", "歐陽", "司馬", "司徒", "司空", "上官", "夏侯", "皇甫", "皇父",
    "尉遲", "長孫", "慕容", "宇文", "東方", "東郭", "獨孤", "公孫", "令狐",
    "淳于", "申屠", "鍾離", "聞人", "西門", "南宮", "第五", "萬俟", "拓跋",
    "呼延", "端木", "公冶", "澹臺", "梁丘", "左丘",
}


def split_compound(sn, nm):
    """把「諸+葛璋」还原成 姓氏=諸葛、名=璋；非复姓原样返回。"""
    if nm and (sn + nm[0]) in COMPOUNDS:
        return sn + nm[0], nm[1:]
    return sn, nm


def load(path):
    recs = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                recs.append(json.loads(line))
    return recs


def clean_name(n):
    n = n.strip("～").strip()
    n = re.sub(r"\s+", "", n)
    return n


def load_dict(path):
    """检字表 姓->四角码；反向 四角码->[姓]。"""
    try:
        d = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}, {}
    inv = {}
    for ch, code in d.items():
        inv.setdefault(code, []).append(ch)
    return d, inv


def build(recs, sd=None, inv=None):
    out = []
    fixed = []
    for r in recs:
        if r["type"] != "entry":
            continue
        sn = FIX.get(r["surname"], r["surname"])
        # 注：检字表 OCR 不完整（缺 曾/許/張 等常用姓），按号码反查会误改
        # （实测把「曾」改成「善」、「謝」改成「計」），故**不做**自动更正，
        # 只保留上面 FIX 里人工确认过的形近字。
        nm = clean_name(r["name"])
        if not nm:
            continue
        note = ""
        m = NOTE.search(nm)
        if m:
            note = m.group(1)
            nm = NOTE.sub("", nm)
        sn, nm = split_compound(sn, nm)          # 諸+葛璋 -> 諸葛 / 璋
        out.append({
            "surname": sn,
            "name": nm,
            "full": sn + nm,
            "juan": r.get("juan"),
            "page": r.get("pref"),
            "code": r.get("code", ""),
            "c2": r.get("c2", ""),
            "note": note[1:] if note.startswith("字") else note,  # 本索引只注「字X」，存「字」后正文
            "src_page": r.get("page"),
            "src_col": r.get("col"),
        })
    if fixed:
        from collections import Counter as _C
        agg = _C((a, b, c) for a, b, c, _, _ in fixed)
        print(f"按检字表修正姓氏 {len(fixed)} 处：" + "，".join(f"{a}->{b}({c})×{n}" for (a, b, c), n in agg.most_common()))
    # 去重（同姓同名同册同页）
    seen = set()
    uniq = []
    for e in out:
        k = (e["surname"], e["full"], e["juan"], e["page"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(e)
    return uniq


def sort_key(e):
    return (lazy_pinyin(e["surname"]), e["surname"], e["juan"] or 0, e["page"] or 0, e["name"])


def write_csv(rows, path):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["姓氏", "姓名", "册", "页", "四角号码", "字", "原书PDF页", "栏"])
        for e in rows:
            w.writerow([e["surname"], e["full"], e["juan"], e["page"], e["code"], e["note"],
                        e["src_page"], e["src_col"]])


def write_xlsx(rows, stat, path):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = "全表"
    head = ["姓氏", "姓名", "册", "页", "四角号码", "字", "原书PDF页", "栏"]
    ws.append(head)
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="4A6B8A")
        c.alignment = Alignment(horizontal="center")
    for e in rows:
        ws.append([e["surname"], e["full"], e["juan"], e["page"], e["code"], e["note"],
                   e["src_page"], e["src_col"]])
    for i, wd in enumerate([8, 14, 6, 6, 10, 12, 12, 5], start=1):
        ws.column_dimensions[get_column_letter(i)].width = wd
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    ws2 = wb.create_sheet("姓氏统计")
    ws2.append(["姓氏", "拼音", "条目数", "四角号码"])
    for c in ws2[1]:
        c.font = Font(bold=True)
    for sn, cnt in sorted(stat.items(), key=lambda kv: lazy_pinyin(kv[0])):
        codes = sorted({e["code"] for e in rows if e["surname"] == sn})
        ws2.append([sn, " ".join(lazy_pinyin(sn)), cnt, "/".join(codes)])
    for i, wd in enumerate([10, 16, 10, 20], start=1):
        ws2.column_dimensions[get_column_letter(i)].width = wd

    wb.save(path)


def write_html(rows, path, title):
    """实际实现在 html_build.py（繁简/异体通检 + 结果面板）。"""
    from html_build import write_html as _impl
    _impl(rows, path, title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--records", required=True)
    ap.add_argument("--outdir", default="output")
    ap.add_argument("--title", default="清代科舉人物家傳資料滙編·人名索引（按姓氏重編）")
    a = ap.parse_args()
    os.makedirs(a.outdir, exist_ok=True)
    sd, inv = load_dict("work/qz/surnames.json")
    rows = build(load(a.records), sd, inv)
    rows.sort(key=sort_key)
    stat = Counter(e["surname"] for e in rows)
    base = "按姓重编"
    write_csv(rows, os.path.join(a.outdir, base + "_全表.csv"))
    write_xlsx(rows, stat, os.path.join(a.outdir, base + "_全表.xlsx"))
    write_html(rows, os.path.join(a.outdir, base + ".html"), a.title)
    with open(os.path.join(a.outdir, "姓氏统计.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["姓氏", "拼音", "条目数"])
        for sn, c in sorted(stat.items(), key=lambda kv: lazy_pinyin(kv[0])):
            w.writerow([sn, " ".join(lazy_pinyin(sn)), c])
    print(f"条目 {len(rows)}，姓氏 {len(stat)} 个 -> {a.outdir}")
    print("前 20 大姓：", stat.most_common(20))


if __name__ == "__main__":
    main()
