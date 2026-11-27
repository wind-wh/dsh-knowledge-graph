#!/usr/bin/env python3
"""把站点内所有外链替换为 kg.agidsh.com 本站链接。

处理对象：site/ 下的 HTML（首页图谱 + 官方镜像文档 + 旧文档站）
替换规则：
  1. deepseek-harness.github.io/deepseek-harness/{reference,guide,develop,...}
     → /deepseek-harness/...（本站镜像）
  2. github.com/deepseek-ai/deepseek-harness/blob/master/<path>#L<n>
     → /src/<path>#L<n>（本站源码查看器）
  3. github.com/deepseek-ai/deepseek-harness（裸仓库链接）→ 本站 GitHub 仓库说明
  4. 文档内其它 http(s) 链接：保留（json-schema.org 等规范链接属正常外链）
"""
import json
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent / "site"
KG = "https://kg.agidsh.com"
OFFICIAL = "https://deepseek-harness.github.io/deepseek-harness"
GH_BLOB = re.compile(r"https://github\.com/deepseek-ai/deepseek-harness/blob/master/([^\s\"'<>)\]]+)")
GH_PLAIN = "https://github.com/deepseek-ai/deepseek-harness"
OUR_REPO = "https://github.com/wind-wh/dsh-knowledge-graph"


def localize(text: str):
    n = 0
    # 1) GitHub blob → 本站源码查看器
    def blob(m):
        nonlocal n
        n += 1
        raw = m.group(1)
        return "/src/" + raw
    text = GH_BLOB.sub(blob, text)

    # 2) 官网绝对 URL → 本站（含 http 与 https）
    for scheme in ("https://", "http://"):
        text = text.replace(scheme + "deepseek-harness.github.io/deepseek-harness", "/deepseek-harness")
        n += text.count("/deepseek-harness")

    # 3) 裸 GitHub 仓库链接 → 我们的仓库（保留一个外链入口，指向源码仓库）
    text = text.replace(GH_PLAIN, OUR_REPO)

    # 4) 首页导航 GitHub 按钮也指向我们的仓库
    text = text.replace('href="https://github.com/deepseek-ai/deepseek-harness"',
                        f'href="{OUR_REPO}"')
    return text, n


def main():
    changed = 0
    total = 0
    for p in list(SITE.rglob("*.html")) + list(SITE.rglob("*.md")):
        if "src" in p.relative_to(SITE).parts:  # 源码查看器由 mirror_source 单独生成
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        new, n = localize(t)
        if new != t:
            p.write_text(new, encoding="utf-8")
            changed += 1
            total += n
    print(f"localized {changed} html files, {total} replacements")

    # docs.json（懒加载的文档数据）同样需要本地化
    docs_json = SITE / "data" / "docs.json"
    if docs_json.exists():
        raw = docs_json.read_text(encoding="utf-8")
        new, n = localize(raw)
        if new != raw:
            docs_json.write_text(new, encoding="utf-8")
            print(f"localized data/docs.json ({n} replacements)")

    # 验证：统计剩余外链
    remain = {}
    for p in SITE.rglob("*.html"):
        t = p.read_text(encoding="utf-8", errors="replace")
        for u in re.findall(r'https?://[^\s"\'<>)\]]+', t):
            host = re.match(r"https?://([^/]+)", u).group(1)
            remain[host] = remain.get(host, 0) + 1
    for host, cnt in sorted(remain.items(), key=lambda x: -x[1])[:12]:
        print(f"  remaining {host}: {cnt}")


if __name__ == "__main__":
    main()
