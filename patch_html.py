# -*- coding: utf-8 -*-
"""把 build_output.py 里的 write_html 替换为委托 html_build.write_html 的薄壳。

用法: python patch_html.py
"""
import re

p = "build_output.py"
src = open(p, encoding="utf-8").read()

start = src.index("def write_html(rows, path, title):")
end = src.index("def main():")

stub = '''def write_html(rows, path, title):
    """实际实现在 html_build.py（繁简/异体通检 + 结果面板）。"""
    from html_build import write_html as _impl
    _impl(rows, path, title)


'''

src = src[:start] + stub + src[end:]
open(p, "w", encoding="utf-8").write(src)
print("patched build_output.py")
