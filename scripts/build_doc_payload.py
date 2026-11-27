#!/usr/bin/env python3
"""把官方 reference 站点的 69 页文档落地到本地目录，并生成可内嵌的 payload。

- 复制 docs/<stem>.zh.md（缺失时回退 docs/<stem>.md）到 .ua/docs-local/<route>.md
- 生成 .ua/doc-payload.json：route -> { title, group, md, file, url }
  供 dashboard 悬浮展开使用，完全离线。
"""
import ast
import json
import os
import re
import shutil
from pathlib import Path

UA = Path(__file__).resolve().parent
ROOT = UA.parent
DOCS = ROOT / "docs"
LOCAL = UA / "docs-local"
SITE = "https://deepseek-harness.github.io/deepseek-harness"
GITHUB = "https://github.com/deepseek-ai/deepseek-harness/blob/master/"
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
ANGLE_LINK = re.compile(r"<(\.\./[^>]+)>")


def gh_url(text: str, href: str, src: Path):
    """把文档内的相对链接改写为 GitHub blob 绝对 URL；返回 None 表示保持原样。"""
    if href.startswith("#") or re.match(r"^[a-z]+:", href):
        return None
    raw = href.split("#", 1)[0].strip("<>")
    frag = href.split("#", 1)[1] if "#" in href else ""
    if not raw:
        return None
    target = (src.parent / raw).resolve()
    try:
        rel = os.path.relpath(target, ROOT).replace(os.sep, "/")
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    path = rel.replace(" ", "%20")
    url = GITHUB + path
    # 行号优先取链接文本末尾的 :N（如 packages/x.ts:41），其次取 href 锚点
    m = re.search(r":(\d+)(?:-(\d+))?$", text.strip().strip("`"))
    if m:
        url += f"#L{m.group(1)}" + (f"-L{m.group(2)}" if m.group(2) else "")
    elif re.match(r"^L?\d+(?:-\d+)?$", frag):
        url += "#" + frag
    return url


def rewrite_links(md: str, src: Path):
    """改写 Markdown 内联链接与尖括号链接，使离线副本中的跳转可用。"""
    def repl(m):
        text, href = m.group(1), m.group(2)
        u = gh_url(text, href, src)
        return f"[{text}]({u})" if u else m.group(0)
    md = MD_LINK.sub(repl, md)

    def repl_angle(m):
        href = m.group(1)
        u = gh_url("", href, src)
        return f"<{u}>" if u else m.group(0)
    return ANGLE_LINK.sub(repl_angle, md)


def load_pages():
    """从 apply_reference_sync.py 提取 PAGES 与 SUBSYSTEM_GROUPS（避免执行副作用）。"""
    tree = ast.parse((UA / "apply_reference_sync.py").read_text(encoding="utf-8"))
    pages, subs = [], []
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        names = [getattr(t, "id", "") for t in node.targets]
        if "PAGES" in names:
            pages = ast.literal_eval(node.value)
        elif "SUBSYSTEM_GROUPS" in names:
            subs = ast.literal_eval(node.value)
    for group, files in subs:
        for f in files:
            route = "reference/subsystems/index" if f == "README" else f"reference/subsystems/{f}"
            pages.append((f"subsystems/{f}", route, group))
    return pages


def clean_title(text, fallback):
    """取首个标题行，跳过代码块内内容。"""
    fence = False
    for ln in text.splitlines():
        if ln.startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        m = re.match(r"^#\s+(.+?)\s*$", ln)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return fallback


def main():
    if LOCAL.exists():
        shutil.rmtree(LOCAL)
    LOCAL.mkdir(parents=True)

    payload, missing = {}, []
    for stem, route, group in load_pages():
        zh = DOCS / f"{stem}.zh.md"
        en = DOCS / f"{stem}.md"
        src = zh if zh.exists() else en
        if not src.exists():
            missing.append((stem, route))
            continue
        rel = route.replace("reference/", "", 1) + ".md"
        if rel.startswith("index"):
            rel = "index.md"
        dest = LOCAL / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

        raw_text = src.read_text(encoding="utf-8")
        text = rewrite_links(raw_text, src)
        # 本地副本同步改写，保证直接打开 .ua/docs-local/*.md 时链接同样可用
        dest.write_text(text, encoding="utf-8")
        title = clean_title(text, stem.split("/")[-1])
        url = f"{SITE}/{route}"
        if route == "reference/cookbook/contributing-system-messages":
            url = ("https://github.com/deepseek-ai/deepseek-harness/blob/master/"
                   "docs/cookbook/contributing-system-messages.zh.md")
        payload[route] = {
            "title": title,
            "group": group,
            "md": text,
            "file": f".ua/docs-local/{rel}",
            "url": url,
        }

    out = UA / "doc-payload.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"docs-local: {len(payload)} pages, missing={missing}")
    print(f"payload: {out} ({out.stat().st_size / 1048576:.2f} MB)")


if __name__ == "__main__":
    main()
