# -*- coding: utf-8 -*-
"""全量分栏 OCR 驱动器：切图 -> 分块 PDF -> 并发提交 PaddleOCR-VL -> 解析。

例：
  python run_ocr.py --pages 19-156 --out work/cols_full --chunk 10 --jobs 5
可反复运行，已完成的块会跳过（断点续跑）。
"""
import argparse, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
# PaddleOCR 脚本路径：优先取环境变量 PADDLEOCR_SCRIPT，默认放在当前用户目录下
OCR_SCRIPT = os.environ.get("PADDLEOCR_SCRIPT") or os.path.join(
    os.path.expanduser("~"), ".claude", "skills", "paddleocr", "paddleocr_ocr.py")

def get_token():
    tok = os.environ.get("PADDLEOCR_TOKEN")
    if tok:
        return tok
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "[Environment]::GetEnvironmentVariable('PADDLEOCR_TOKEN','User')"],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.strip()
    except Exception:
        return ""

def slice_pages(pdf, pages, out, chunk, quiet=True):
    meta_path = os.path.join(out, "meta.json")
    if os.path.exists(meta_path):
        print(f"[skip] 切图已存在: {meta_path}")
        return json.load(open(meta_path, encoding="utf-8"))
    cmd = [sys.executable, os.path.join(HERE, "slice_columns.py"),
           "--pdf", pdf, "--pages", pages, "--out", out,
           "--chunks", "--chunk", str(chunk), "--nopng"]
    print("[slice]", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout[-2000:] or r.stderr[-2000:])
    return json.load(open(meta_path, encoding="utf-8"))

def ocr_one(pdf_path, outdir, token, log):
    os.makedirs(outdir, exist_ok=True)
    if os.path.exists(os.path.join(outdir, "page_001.md")):
        return "skip", pdf_path
    env = dict(os.environ); env["PADDLEOCR_TOKEN"] = token
    t0 = time.time()
    r = subprocess.run([sys.executable, OCR_SCRIPT, pdf_path, "--output", outdir],
                       capture_output=True, text=True, env=env, timeout=7200)
    dt = time.time() - t0
    ok = r.returncode == 0 and os.path.exists(os.path.join(outdir, "page_001.md"))
    msg = f"{'OK ' if ok else 'ERR'} {os.path.basename(outdir)} {dt:.0f}s"
    print(msg, flush=True)
    with open(log, "a", encoding="utf-8") as f:
        f.write(msg + "\n" + ("" if ok else (r.stdout[-800:] + r.stderr[-800:])) + "\n")
    return ("ok" if ok else "err"), pdf_path

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True)
    ap.add_argument("--out", default="work/cols_full")
    ap.add_argument("--chunk", type=int, default=10)
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--parse", action="store_true", help="OCR 完成后自动解析")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    slice_pages(a.pdf, a.pages, a.out, a.chunk)
    index = json.load(open(os.path.join(a.out, "index.json"), encoding="utf-8"))
    jobs = []
    for side in ("L", "R"):
        for it in index[side]:
            jobs.append((os.path.join(a.out, it["stem"] + ".pdf"),
                         os.path.join(a.out, "ocr_" + side, it["stem"])))
    print(f"共 {len(jobs)} 个分块")
    token = get_token()
    if not token:
        sys.exit("PADDLEOCR_TOKEN 未获取到")
    log = os.path.join(a.out, "run.log")
    done = 0; errs = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(ocr_one, p, d, token, log): p for p, d in jobs}
        for f in as_completed(futs):
            st, p = f.result()
            if st in ("ok", "skip"):
                done += 1
            else:
                errs.append(p)
    print(f"\n完成 {done}/{len(jobs)}，失败 {len(errs)}")
    for p in errs:
        print("  失败:", p)
    if a.parse and not errs:
        r = subprocess.run([sys.executable, os.path.join(HERE, "parse_columns.py"),
                            "--dir", a.out, "--out", os.path.join(a.out, "records.jsonl")],
                           capture_output=True, text=True)
        print(r.stdout[-3000:] or r.stderr[-3000:])

if __name__ == "__main__":
    main()
