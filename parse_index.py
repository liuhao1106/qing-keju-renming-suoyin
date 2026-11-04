# -*- coding: utf-8 -*-
"""Parse PaddleOCR-VL markdown of 《清代科举人物家传资料汇编·索引》 into records.

Layout of a body page (two columns, separated by a vertical rule):

    heading:  四角号码 + 附角 + 姓      e.g. 0022₂ 廖 / bare 廖 (same code group)
    entry:    [上二角码] ～名 [（字號）]        册—页

The OCR markdown renders the whole page as one HTML table whose cells keep the
left-to-right, top-to-bottom order.  Columns 0-1 are the left column (name, page)
and columns >=2 the right column.
"""
import re
import sys
import json
import html as _html
from pathlib import Path
from collections import Counter, defaultdict

CJK = r'\u4e00-\u9fff'
ENTRY_RE = re.compile(rf'^\s*(?P<code>\d{{2}})?\s*[～]\s*(?P<name>[{CJK}][^0-9]*?)\s*$')
HEAD_RE = re.compile(rf'^\s*(?P<code>\d{{3,4}})\s*[.,;:，、_\-]?\s*(?P<sub>\d)?\s*(?P<name>[{CJK}]{{1,3}})\s*$')
BARE_RE = re.compile(rf'^\s*(?P<name>[{CJK}]{{1,3}})\s*$')
PAGE_RE = re.compile(r'^\s*(?P<juan>\d{1,2})\s*[—–]\s*(?P<page>\d{1,4})\s*$')


def norm(s):
    s = _html.unescape(s or '')
    s = re.sub(r'<[^>]+>', '', s)
    s = s.replace('\u3000', ' ').replace('\xa0', ' ')
    s = s.replace('〜', '～').replace('~', '～').replace('−', '—')
    # LaTeX leftovers such as  $ _{{2}} $  ->  2
    s = re.sub(r'\$\s*_?\s*\{+\s*(\d)\s*\}+?\s*\$', r'\1', s)
    s = s.replace('$', '').replace('{', '').replace('}', '')
    s = re.sub(r'(?<=\d)[-–－~～]+(?=\d)', '—', s)
    s = re.sub(r'[ \t]+', ' ', s)
    return s.strip()


def parse_table(tbl):
    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', tbl, re.S | re.I)
    grid = []
    occupied = set()
    for r, rowhtml in enumerate(rows):
        cells = re.findall(r'<t[dh]([^>]*)>(.*?)</t[dh]>', rowhtml, re.S | re.I)
        row = {}
        col = 0
        for attrs, content in cells:
            while (r, col) in occupied:
                col += 1
            rs = re.search(r'rowspan=["\']?(\d+)', attrs)
            cs = re.search(r'colspan=["\']?(\d+)', attrs)
            rs = int(rs.group(1)) if rs else 1
            cs = int(cs.group(1)) if cs else 1
            txt = norm(content)
            row[col] = txt
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((r + dr, col + dc))
            for dc in range(1, cs):
                row[col + dc] = ''
            col += cs
        grid.append(row)
    return grid


def classify(t):
    if not t:
        return None, None
    m = ENTRY_RE.match(t)
    if m:
        return 'entry', m
    m = PAGE_RE.match(t)
    if m:
        return 'page', m
    m = HEAD_RE.match(t)
    if m:
        return 'head', m
    m = BARE_RE.match(t)
    if m:
        return 'head', m
    return None, None


def page_tokens(md):
    """Yield (col_side, kind, text, match) in reading order for one page."""
    tables = re.findall(r'<table.*?</table>', md, re.S | re.I)
    if not tables:
        return []
    grid = []
    for tbl in tables:
        grid.extend(parse_table(tbl))
    width = max((max(g.keys()) + 1) for g in grid if g) if grid else 0
    split = 2 if width >= 4 else max(1, width // 2)
    left, right = [], []
    for row in grid:
        for c in sorted(row):
            t = row[c]
            kind, m = classify(t)
            if kind is None:
                continue
            item = (kind, t, m)
            (left if c < split else right).append(item)
    return left + right


def build_records(pages):
    recs, warns = [], []
    cur = None
    cur_code = None
    pending = None
    for pno, md in enumerate(pages, 1):
        for kind, t, m in page_tokens(md):
            if kind == 'head':
                if m.re.groupindex.get('code') and m.group('code'):
                    cur_code = m.group('code')
                cur = m.group('name')
                if pending:
                    warns.append((pno, 'trailing-entry', pending['raw']))
                    pending = None
                continue
            if kind == 'entry':
                if pending:
                    warns.append((pno, 'entry-without-page', pending['raw']))
                pending = {'code2': m.group('code') or '', 'given': m.group('name'),
                           'surname': cur, 'code': cur_code, 'book_page': pno,
                           'raw': t}
                continue
            if kind == 'page':
                if pending is None:
                    warns.append((pno, 'page-without-entry', t))
                    continue
                recs.append({
                    'surname': pending['surname'] or '',
                    'given': pending['given'],
                    'name': (pending['surname'] or '') + pending['given'],
                    'juan': int(m.group('juan')),
                    'page': int(m.group('page')),
                    'code': pending['code'] or '',
                    'code2': pending['code2'],
                    'book_page': pending['book_page'],
                    'raw': pending['raw'] + ' ' + t,
                })
                pending = None
    if pending:
        warns.append((len(pages), 'final-entry-without-page', pending['raw']))
    return recs, warns


def main():
    d = Path(sys.argv[1] if len(sys.argv) > 1 else 'work/ocr_spike')
    files = sorted(d.glob('page_*.md'))
    pages = [f.read_text(encoding='utf-8') for f in files]
    recs, warns = build_records(pages)
    print(f'pages={len(pages)}  records={len(recs)}  warnings={len(warns)}')
    for w in warns[:40]:
        print('  WARN', w)
    print('surnames:', Counter(r['surname'] for r in recs).most_common(15))
    out = d / 'records.jsonl'
    with out.open('w', encoding='utf-8') as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    print('wrote', out)


if __name__ == '__main__':
    main()
