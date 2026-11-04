# -*- coding: utf-8 -*-
"""生成单文件检索网页（繁體），供 build_output.py 调用。

特点：
  1. 繁簡／異體通檢：单字级 opencc s2t + 手工异体表，逐字归一（长度不变，
     故高亮下标可直接映射回原字）；不改动任何数据。
  2. 检索后进入独立结果面板，按姓氏分组列出命中者（姓名、册—页、字、原书页），
     命中处高亮；点结果跳回全表并闪烁定位。
  3. 支持 册-页 倒查（如 3-143）、姓氏拼音检索（如 liao）。
"""
import html
import json
from collections import defaultdict

from pypinyin import lazy_pinyin

# 手工异体表：opencc 不处理、或需要二次收束的链（如 为→爲→為）
# 归一目标为「简体」。opencc t2s 已能处理绝大多数繁简与常见异体，
# 这里补它不收敛的少数（如 寗 不归 宁、譛 不归 谮）。
MANUAL = {
    "寗": "宁",
    "譛": "谮",
}


def build_variant_map(rows):
    """返回 {异体/简体字: 规范字}，只含确实需要转换的字。"""
    chars = set()
    for e in rows:
        chars |= set(e["full"]) | set(e["note"])
    try:
        from opencc import OpenCC
        cc = OpenCC("t2s").convert         # 归一方向：简体
        back = OpenCC("s2t").convert       # 反向，用于把「数据里没有的繁体写法」也收进字表
    except Exception:
        cc = lambda c: c
        back = lambda c: c

    def canon(c):
        n = cc(c)
        if len(n) != 1:
            n = c
        return MANUAL.get(n, n)

    m = {}
    for c in chars:
        k = canon(c)
        if k != c:
            m[c] = k
        t = back(k)                        # 灯 -> 燈、灏 -> 灝：让繁体输入也能命中
        if len(t) == 1 and t != k:
            m[t] = k
    for a, b in MANUAL.items():            # 手工异体（含 opencc 不收敛的）
        m[a] = b
    return m


_TPL = r"""<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#1f2328;--mute:#6b7280;--line:#e5e7eb;--accent:#8a5a2b;--hl:#fde68a}
*{box-sizing:border-box}
body{margin:0;font:15px/1.7 "Songti SC","SimSun",serif;color:var(--ink);background:#faf8f4}
header{position:sticky;top:0;z-index:9;background:#fffdf9;border-bottom:1px solid var(--line);padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
h1{font-size:17px;margin:0;font-weight:600;letter-spacing:.02em}
.sbox{flex:1;min-width:260px;display:flex;align-items:center;position:relative}
#q{width:100%;padding:9px 34px 9px 12px;border:1px solid var(--line);border-radius:6px;font:inherit;background:#fff}
#q:focus{outline:2px solid #d9c7a8;border-color:#d9c7a8}
#clr{position:absolute;right:6px;border:0;background:transparent;font-size:18px;line-height:1;color:var(--mute);cursor:pointer;padding:4px 6px;border-radius:4px;display:none}
#clr:hover{background:#f0e9dd}
#cnt{color:var(--mute);font-size:13px;white-space:nowrap}
main{display:flex;align-items:flex-start}
nav{position:sticky;top:64px;max-height:calc(100vh - 64px);overflow:auto;width:132px;flex:none;padding:10px 6px;border-right:1px solid var(--line);background:#fffdf9}
nav a{display:flex;justify-content:space-between;padding:3px 8px;color:var(--ink);text-decoration:none;border-radius:4px;font-size:14px}
nav a:hover{background:#f0e9dd}
nav a i{color:var(--mute);font-style:normal;font-size:12px}
#list{flex:1;padding:18px 26px 80px;column-width:340px;column-gap:34px}
.g{break-inside:avoid;margin:0 0 18px}
.g h2{font-size:20px;margin:0 0 6px;padding-bottom:4px;border-bottom:1.5px solid var(--accent);font-weight:600}
.g h2 em{font-style:normal;font-size:12px;color:#fff;background:var(--accent);border-radius:9px;padding:1px 7px;margin-left:6px;vertical-align:2px}
.g h2 small{float:right;font-weight:400;color:var(--mute);font-size:12px;letter-spacing:.05em}
.g ul{list-style:none;margin:0;padding:0}
.g li{display:flex;gap:8px;padding:1.5px 0;border-bottom:1px dotted #eee;border-radius:3px}
.g li b{font-weight:500;min-width:4.2em}
.loc{color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:12.5px}
.note{color:var(--mute);font-size:12.5px}
.src{margin-left:auto;color:#c8c2b6;font-size:11px;font-family:ui-monospace,monospace}
#res{flex:1;padding:16px 26px 80px;max-width:940px}
.resbar{display:flex;justify-content:space-between;align-items:baseline;gap:12px;border-bottom:2px solid var(--accent);padding-bottom:6px;margin-bottom:10px}
.resbar b{font-size:16px}
#resinfo{color:var(--mute);font-size:13px}
.rg{margin:14px 0 4px}
.rg h3{margin:0 0 4px;font-size:16px;color:var(--accent);font-weight:600}
.rg h3 em{font-style:normal;font-size:12px;color:#fff;background:var(--accent);border-radius:9px;padding:0 7px;margin-left:6px;vertical-align:2px}
.rg ul{list-style:none;margin:0;padding:0}
.rg li{display:flex;align-items:baseline;gap:10px;padding:5px 8px;border-bottom:1px dotted #eee;border-radius:4px;cursor:pointer}
.rg li:hover{background:#f3ece1}
.rn{font-weight:600;min-width:7.5em;font-size:15.5px}
.rloc{color:var(--accent);font-family:ui-monospace,Menlo,monospace;font-size:13px}
.rnote{color:var(--mute);font-size:12.5px}
.rsrc{margin-left:auto;color:#c8c2b6;font-size:11px;font-family:ui-monospace,monospace}
mark{background:var(--hl);padding:0 1px;border-radius:2px}
.empty{color:var(--mute);padding:26px 4px;font-size:14px;line-height:2}
.empty b{color:var(--ink)}
.flash{animation:fl 2.2s ease}
@keyframes fl{0%,25%{background:var(--hl)}100%{background:transparent}}
@media(max-width:720px){nav{display:none}#list{column-width:auto}}
</style>
<header><h1>__TITLE__</h1>
<div class="sbox"><input id="q" placeholder="輸入姓名／姓氏（簡繁、異體通檢），或冊-頁如 3-143" autocomplete="off"><button id="clr" title="清空">×</button></div>
<span id="cnt">共 __NSUR__ 姓 / __TOTAL__ 條</span></header>
<main>
<nav id="nav">__NAV__</nav>
<div id="list">__PARTS__</div>
<section id="res" hidden>
  <div class="resbar"><b>檢索結果</b><span id="resinfo"></span></div>
  <div id="resbody"></div>
</section>
</main>
<script id="vm" type="application/json">__VMJSON__</script>
<script>
(function(){
"use strict";
var VM = JSON.parse(document.getElementById('vm').textContent);
var q = document.getElementById('q'), clr = document.getElementById('clr');
var cnt = document.getElementById('cnt'), nav = document.getElementById('nav');
var listWrap = document.getElementById('list'), res = document.getElementById('res');
var resInfo = document.getElementById('resinfo'), resBody = document.getElementById('resbody');
var LOC = /^(\d{1,3})\s*[\u2014\u2013-]\s*(\d{1,4})$/;
var TOTAL = __TOTAL__, NSUR = __NSUR__;

/* 逐字归一：长度不变，高亮下标可直接映射回原字 */
function norm(s){ var o = '', i = 0, n = s.length; for (; i < n; i++) o += (VM[s[i]] || s[i]); return o; }
function esc(s){ return String(s).replace(/[&<>"]/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]; }); }

var R = [];
var secs = document.querySelectorAll('#list .g');
for (var i = 0; i < secs.length; i++){
  var sec = secs[i], sn = sec.dataset.s, py = sec.dataset.py || '';
  var sm = sec.querySelector('h2 small'), code = sm ? sm.textContent : '';
  var lis = sec.querySelectorAll('li');
  for (var j = 0; j < lis.length; j++){
    var li = lis[j], b = li.querySelector('b'), nt = li.querySelector('.note');
    var sr = li.querySelector('.src');
    R.push({
      el: li, sn: sn, nSn: norm(sn), py: py, code: code,
      name: b.textContent, nName: norm(b.textContent),
      note: nt ? nt.textContent : '', nNote: nt ? norm(nt.textContent) : '',
      juan: li.dataset.j, page: li.dataset.p, src: sr ? sr.textContent : ''
    });
  }
}

function markIn(text, nText, qn){
  var k = qn ? nText.indexOf(qn) : -1;
  if (k < 0 || k + qn.length > text.length) return esc(text);
  return esc(text.slice(0, k)) + '<mark>' + esc(text.slice(k, k + qn.length)) + '</mark>' + esc(text.slice(k + qn.length));
}

/* 排序：全名全等 > 全名前缀 > 姓氏全等 > 字号命中 > 册页序 */
function rank(r, qn){
  if (r.nName === qn) return 0;
  if (r.nName.indexOf(qn) === 0) return 1;
  if (r.nSn === qn) return 2;
  if (r.nNote && r.nNote.indexOf(qn) >= 0) return 3;
  return 4;
}

function reset(){
  q.value = ''; clr.style.display = 'none';
  listWrap.hidden = false; nav.style.display = ''; res.hidden = true;
  cnt.textContent = '共 ' + NSUR + ' 姓 / ' + TOTAL + ' 條';
  resBody.innerHTML = '';
}

function run(){
  var raw = q.value.trim();
  clr.style.display = raw ? 'block' : 'none';
  if (!raw){ reset(); return; }
  var qn = norm(raw.toLowerCase());
  var m = raw.match(LOC);
  var hits = [];
  for (var i = 0; i < R.length; i++){
    var r = R[i], ok = false, where = '';
    if (m){
      ok = (String(+r.juan) === String(+m[1]) && String(+r.page) === String(+m[2]));
      where = 'loc';
    } else if (r.nName.indexOf(qn) >= 0){ ok = true; where = 'name'; }
    else if (r.nNote && r.nNote.indexOf(qn) >= 0){ ok = true; where = 'note'; }
    else if (r.nSn.indexOf(qn) >= 0 || (r.py && r.py.indexOf(qn) >= 0)){ ok = true; where = 'sn'; }
    if (ok) hits.push({ r: r, where: where, k: rank(r, qn), i: i });
  }
  hits.sort(function(a, b){
    return a.k - b.k || (+a.r.juan - +b.r.juan) || (+a.r.page - +b.r.page) || String(a.r.name).localeCompare(b.r.name);
  });

  listWrap.hidden = true; nav.style.display = 'none'; res.hidden = false;

  if (!hits.length){
    resInfo.textContent = '';
    resBody.innerHTML = '<div class="empty">未找到 <b>' + esc(raw) + '</b>。<br>' +
      '可試：只輸入姓氏、輸入簡體字（如「陈」找陳）、異體字（如「恒」找恆），或倒查冊-頁（如 <b>3-143</b>）。</div>';
    cnt.textContent = '0 條';
    return;
  }

  var CAP = 400, shown = Math.min(hits.length, CAP), groups = new Map();
  for (var k2 = 0; k2 < shown; k2++){
    var s = hits[k2].r.sn;
    if (!groups.has(s)) groups.set(s, []);
    groups.get(s).push(hits[k2]);
  }
  var buf = '';
  groups.forEach(function(arr, s){
    buf += '<section class="rg"><h3>' + esc(s) + '<em>' + arr.length + '</em></h3><ul>';
    arr.forEach(function(h){
      var r = h.r;
      var nameHtml = (h.where === 'name') ? markIn(r.name, r.nName, qn) : esc(r.name);
      var noteHtml = (h.where === 'note') ? markIn(r.note, r.nNote, qn) : esc(r.note);
      buf += '<li data-idx="' + h.i + '"><span class="rn">' + nameHtml + '</span>' +
             '<span class="rloc">' + esc(r.juan + '—' + r.page) + '</span>' +
             (r.note ? '<span class="rnote">字' + noteHtml + '</span>' : '') +
             '<span class="rsrc">' + esc(r.src) + '</span></li>';
    });
    buf += '</ul></section>';
  });
  if (hits.length > CAP) buf += '<div class="empty">僅顯示前 ' + CAP + ' 條，請輸入更精確的關鍵詞。</div>';
  resBody.innerHTML = buf;
  resInfo.textContent = '命中 ' + hits.length + ' 條，涉及 ' + groups.size + ' 姓';
  cnt.textContent = hits.length + ' 條';
}

function focusRow(idx){
  var r = R[idx]; if (!r) return;
  reset();
  r.el.classList.add('flash');
  r.el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(function(){ r.el.classList.remove('flash'); }, 2300);
}

resBody.addEventListener('click', function(e){
  var li = e.target.closest ? e.target.closest('li[data-idx]') : null;
  if (li) focusRow(+li.getAttribute('data-idx'));
});
q.addEventListener('input', run);
q.addEventListener('keydown', function(e){
  if (e.key === 'Escape') reset();
  if (e.key === 'Enter'){
    var first = resBody.querySelector('li[data-idx]');
    if (first) focusRow(+first.getAttribute('data-idx'));
  }
});
clr.addEventListener('click', function(){ reset(); q.focus(); });

nav.addEventListener('click', function(e){
  var a = e.target.closest ? e.target.closest('a[data-s]') : null;
  if (!a) return;
  e.preventDefault(); reset();
  var t = document.getElementById('s-' + a.getAttribute('data-s'));
  if (t) t.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
run();
})();
</script></html>"""


def write_html(rows, path, title):
    groups = defaultdict(list)
    for e in rows:
        groups[e["surname"]].append(e)
    order = sorted(groups, key=lambda s: (lazy_pinyin(s), s))

    parts = []
    for sn in order:
        items = sorted(groups[sn], key=lambda e: (e["juan"] or 0, e["page"] or 0, e["name"]))
        py = " ".join(lazy_pinyin(sn))
        lis = "".join(
            f'<li data-j="{e["juan"]}" data-p="{e["page"]}"><b>{html.escape(e["full"])}</b>'
            f'<span class="loc">{e["juan"]}—{e["page"]}</span>'
            + (f'<span class="note">{html.escape(e["note"])}</span>' if e["note"] else "")
            + f'<span class="src">p{e["src_page"]}{e["src_col"]}</span></li>'
            for e in items)
        parts.append(
            f'<section class="g" id="s-{html.escape(sn)}" data-s="{html.escape(sn)}" data-py="{py}">'
            f'<h2>{html.escape(sn)} <em>{len(items)}</em>'
            f'<small>{py} · {groups[sn][0]["code"]}</small></h2>'
            f'<ul>{lis}</ul></section>')

    nav = "".join(
        f'<a href="#s-{html.escape(sn)}" data-s="{html.escape(sn)}">{html.escape(sn)}<i>{len(groups[sn])}</i></a>'
        for sn in order)

    vmap = build_variant_map(rows)
    doc = (_TPL
           .replace("__TITLE__", html.escape(title))
           .replace("__NAV__", nav)
           .replace("__PARTS__", "".join(parts))
           .replace("__VMJSON__", json.dumps(vmap, ensure_ascii=False, separators=(",", ":")))
           .replace("__TOTAL__", str(len(rows)))
           .replace("__NSUR__", str(len(groups))))
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"  HTML：检索字表 {len(vmap)} 条（繁简/异体归一）")
