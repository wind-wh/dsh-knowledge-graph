#!/usr/bin/env python3
"""把文档正文引用的源码文件镜像到本站 /src/，并生成本站源码查看器。

- 从 doc-payload.json 提取所有 GitHub blob 链接对应的源码路径
- 复制仓库文件到 site/src/<path>（保留目录结构）
- 生成 site/src/index.html：通用查看器，?f=<path> 加载纯文本，#L<n> 行号高亮
"""
import html
import json
import re
import shutil
from pathlib import Path

UA = Path(__file__).resolve().parent
ROOT = UA.parent
SITE = UA / "site"
SRC = SITE / "src"
GITHUB = "https://github.com/deepseek-ai/deepseek-harness/blob/master/"

VIEWER = """<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>源码 · DSH 知识图谱</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#0d1117;color:#c9d1d9;font:12.5px/1.6 "SFMono-Regular",Consolas,"Liberation Mono",monospace}
header{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:14px;padding:10px 16px;background:#161b22;border-bottom:1px solid #30363d}
header a{color:#58a6ff;text-decoration:none}header a:hover{text-decoration:underline}
.hd-path{font-weight:600;color:#e6edf3;word-break:break-all;flex:1}
.hd-act{font-size:11px;color:#8b949e}
#code{padding:10px 0 40px;white-space:pre;overflow-x:auto}
.ln{display:flex;padding:0 16px}
.ln:hover{background:#161b22}
.ln.hit{background:#3b2f00;box-shadow:inset 3px 0 #e3b341}
.n{width:52px;flex:0 0 52px;text-align:right;padding-right:16px;color:#484f58;user-select:none}
.t{flex:1}
</style></head><body>
<header><a href="/">← 图谱</a><span class="hd-path" id="path"></span>
<span class="hd-act">本站源码镜像</span></header>
<div id="code">加载中…</div>
<script>
const q=new URLSearchParams(location.search);
const f=q.get('f')||'';
document.getElementById('path').textContent=f;
const hit=parseInt((location.hash.match(/L(\\d+)/)||[])[1]||'0',10);
fetch('/src/'+f).then(r=>{if(!r.ok)throw new Error(r.status);return r.text()}).then(t=>{
  const box=document.getElementById('code'); box.innerHTML='';
  t.replace(/\\r\\n/g,'\\n').split('\\n').forEach((line,i)=>{
    const n=i+1, row=document.createElement('div');
    row.className='ln'+(n===hit?' hit':''); row.id='L'+n;
    row.innerHTML='<span class="n">'+n+'</span><span class="t"></span>';
    row.querySelector('.t').textContent=line;
    box.appendChild(row);
  });
  if(hit) setTimeout(()=>{const el=document.getElementById('L'+hit);if(el)el.scrollIntoView({block:'center'})},50);
}).catch(e=>{document.getElementById('code').textContent='加载失败：'+e.message});
</script>
</body></html>"""


def main():
    payload = json.loads((UA / "doc-payload.json").read_text(encoding="utf-8"))
    paths = set()
    for v in payload.values():
        for u in re.findall(r"https://github\.com/deepseek-ai/deepseek-harness/blob/master/([^\s\"'<>)\]]+)", v["md"]):
            paths.add(u.split("#")[0])

    n = 0
    missing = []
    for rel in sorted(paths):
        src = ROOT / rel
        # 目录链接 → 映射到 README（GitHub blob 目录的实际行为）
        if not src.is_file() and src.is_dir():
            for candidate in ("README.md", "README.zh.md", "index.ts", "index.md"):
                if (src / candidate).is_file():
                    src = src / candidate
                    break
        if not src.is_file():
            missing.append(rel)
            continue
        dst = SRC / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    (SRC / "index.html").write_text(VIEWER, encoding="utf-8")
    print(f"source files: {n}, missing: {len(missing)}")
    if missing:
        print("  ", missing[:6])
    total = sum(f.stat().st_size for f in SRC.rglob("*") if f.is_file())
    print(f"mirror -> {SRC} ({total/1048576:.2f} MB)")


if __name__ == "__main__":
    main()
