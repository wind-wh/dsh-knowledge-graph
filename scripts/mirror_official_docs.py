#!/usr/bin/env python3
"""镜像官方 VitePress reference 站点到本地文档站，UI 与官方完全一致。

- 下载 69 页 HTML（保留原路径 /deepseek-harness/reference/...）
- 下载首页引用的全部 assets（CSS/JS/字体/图标）
- 在每页注入「返回图谱」浮动入口
- 产物写入 .ua/site/deepseek-harness/
"""
import re
import shutil
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

UA = Path(__file__).resolve().parent
SITE = UA / "site"
MIRROR = SITE / "deepseek-harness"
BASE = "https://deepseek-harness.github.io"
PREFIX = "/deepseek-harness"


def fetch(url: str, dest: Path) -> bool:
    if dest.parent.exists() and not dest.parent.is_dir():
        return True  # 路径已被资源文件占用，跳过
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"FAIL {url}: {e}")
        return False


def main():
    MIRROR.mkdir(parents=True, exist_ok=True)

    # 1) 首页 HTML + 提取资源
    index_url = f"{BASE}{PREFIX}/reference/"
    html = urllib.request.urlopen(index_url, timeout=60).read().decode("utf-8")
    assets = sorted(set(re.findall(r'(?:href|src)="(' + PREFIX + r'/assets/[^"]+)"', html)))
    assets += [f"{PREFIX}/vp-icons.css", f"{PREFIX}/favicon.svg"]
    # CSS 里的字体引用：URL 形如 url(/assets/xxx.woff2)，需补 PREFIX
    css = urllib.request.urlopen(f"{BASE}{PREFIX}/assets/style.6heebdof.css", timeout=60).read().decode("utf-8")
    for f in sorted(set(re.findall(r'url\((/assets/[^)]+\.woff2)\)', css))):
        assets.append(PREFIX + f)
    assets = sorted(set(assets))
    print(f"assets: {len(assets)}")

    def dl_asset(a):
        # a 形如 /deepseek-harness/assets/xxx；MIRROR 已经是 .../deepseek-harness，去掉前缀
        rel = a[len(PREFIX):].lstrip("/") if a.startswith(PREFIX) else a.lstrip("/")
        return fetch(BASE + a, MIRROR / rel), a

    ok = 0
    with ThreadPoolExecutor(8) as ex:
        for f in as_completed([ex.submit(dl_asset, a) for a in assets]):
            success, a = f.result()
            ok += success
    print(f"assets downloaded: {ok}/{len(assets)}")

    # 2) 69 页 HTML（从 payload 的 route 生成）
    import json
    payload = json.loads((UA / "doc-payload.json").read_text(encoding="utf-8"))
    routes = ["/reference/"] + [f"/reference/{r.replace('reference/', '', 1)}"
                                for r in payload if r != "reference/index"]
    # 入门（guide）与开发（develop）页面，从 website/docs.ts 的路由表提取
    docs_ts = (UA.parent / "website" / "docs.ts").read_text(encoding="utf-8")
    for r in re.findall(r"route: '((?:guide|develop)/[^']+)\.md'", docs_ts):
        routes.append("/" + r)
    # 英文版（/en/...）：官网自带语言切换，需镜像整套英文页面
    en_routes = ["/en/reference/"]
    for r in list(routes):
        if r.startswith("/guide/") or r.startswith("/develop/"):
            en_routes.append("/en" + r)
    for r in ["/reference/"] + [f"/reference/{x.replace('reference/', '', 1)}"
                                for x in payload if x != "reference/index"]:
        en_routes.append("/en" + r)
    routes = sorted(set(routes + en_routes))

    page_chunks = set()
    discovered = set()

    def dl_page(route):
        url = f"{BASE}{PREFIX}{route}"
        rel = route.strip("/") or "reference"
        # .md 页面按原始文件名保存，其余按目录 index.html
        if route.endswith(".md"):
            dest = MIRROR / rel.lstrip("/")
        else:
            dest = MIRROR / rel / "index.html"
        success = fetch(url, dest)
        if success:
            t = dest.read_text(encoding="utf-8", errors="replace")
            # VitePress 每页的内容 chunk
            for c in re.findall(r'(' + PREFIX + r'/assets/[^"\']+\.lean\.js)', t):
                page_chunks.add(c)
            # 递归发现站内链接（排除 assets / 锚点 / query）
            for h in re.findall(r'href="(' + PREFIX + r'/[^"#?]+)"', t):
                if "/assets/" in h or re.search(r'\.(svg|png|jpg|ico|woff2?|css|js)$', h):
                    continue
                r = h[len(PREFIX):]
                if r not in routes and r not in discovered:
                    discovered.add(r)
        return success, route

    done = set()
    todo = list(routes)
    total_ok = 0
    round_no = 0
    while todo:
        round_no += 1
        batch = [r for r in todo if r not in done]
        if not batch:
            break
        with ThreadPoolExecutor(8) as ex:
            for f in as_completed([ex.submit(dl_page, r) for r in batch]):
                success, r = f.result()
                total_ok += success
                done.add(r)
        new = [r for r in sorted(discovered) if r not in done]
        print(f"  round {round_no}: attempted {len(batch)}, total ok {total_ok}, discovered {len(new)} new")
        todo = new
    print(f"pages downloaded: {total_ok}/{len(done)}")

    # 下载每页的内容 chunk（SPA 路由必需）
    print(f"page chunks: {len(page_chunks)}")
    with ThreadPoolExecutor(8) as ex:
        results = [ex.submit(fetch, BASE + c, MIRROR / c[len(PREFIX):].lstrip("/"))
                   for c in page_chunks]
        chunk_ok = sum(f.result() for f in as_completed(results))
    print(f"chunks downloaded: {chunk_ok}/{len(page_chunks)}")

    # 关键：VitePress 客户端点击跳转加载「非 lean」chunk（xxx.md.<hash>.js），
    # 而首屏 HTML 加载的是 lean 版（xxx.md.<hash>.lean.js）。两者都必须镜像，
    # 否则点击导航会 404（刷新正常、点击 404 的根因）。
    hash_map_url = f"{BASE}{PREFIX}/assets/hashmap.json"
    # 从首页 HTML 内联的 __VP_HASH_MAP__ 提取全部 key.hash
    sample_html = MIRROR / "reference/index.html"
    full_chunks = set()
    if sample_html.exists():
        import json as _json
        ht = sample_html.read_text(encoding="utf-8", errors="replace")
        k = ht.find('window.__VP_HASH_MAP__=JSON.parse("')
        if k >= 0:
            start = k + len('window.__VP_HASH_MAP__=JSON.parse("')
            j = start
            esc = False
            while j < len(ht):
                ch = ht[j]
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    break
                j += 1
            hm = _json.loads(_json.loads('"' + ht[start:j] + '"'))
            for key, hashv in hm.items():
                full_chunks.add(f"{PREFIX}/assets/{key}.{hashv}.js")
    print(f"full chunks (non-lean): {len(full_chunks)}")
    with ThreadPoolExecutor(8) as ex:
        results = [ex.submit(fetch, BASE + c, MIRROR / c[len(PREFIX):].lstrip("/"))
                   for c in full_chunks]
        full_ok = sum(f.result() for f in as_completed(results))
    print(f"full chunks downloaded: {full_ok}/{len(full_chunks)}")

    # 2b) 改写 CSS 里的字体 URL：/assets/xxx → /deepseek-harness/assets/xxx
    css_path = MIRROR / "assets/style.6heebdof.css"
    if css_path.exists():
        t = css_path.read_text(encoding="utf-8")
        t = t.replace("url(/assets/", f"url({PREFIX}/assets/")
        css_path.write_text(t, encoding="utf-8")
        print("css font urls rewritten")

    badge = """\
<style>
.kg-back{position:fixed;right:16px;bottom:16px;z-index:999;background:#1f6feb;color:#fff;
  padding:9px 14px;border-radius:8px;text-decoration:none;font-size:12px;font-weight:600;
  box-shadow:0 8px 24px rgba(0,0,0,.35)}
.kg-back:hover{background:#388bfd;color:#fff}
</style><a class="kg-back" href="/">← 返回知识图谱</a>"""

    # 2c) 官网 404 的 cookbook/contributing-system-messages：用自建文档页兜底
    missing = MIRROR / "deepseek-harness/reference/cookbook/contributing-system-messages/index.html"
    if not missing.exists():
        fallback = SITE / "docs/cookbook/contributing-system-messages.html"
        if fallback.exists():
            missing.parent.mkdir(parents=True, exist_ok=True)
            t = fallback.read_text(encoding="utf-8")
            missing.write_text(t.replace("</body>", badge + "</body>") if "kg-back" in t else t, encoding="utf-8")
            print("fallback page created")

    # 2d) landing 页：/guide/ 与 /develop/ 用首篇内容承载（官网无目录 index）
    for landing, source in [
        ("guide/index.html", "guide/quickstart/index.html"),
        ("develop/index.html", "develop/basic/index/index.html"),
    ]:
        dst = MIRROR / landing
        src = MIRROR / source
        if not dst.exists() and src.exists():
            dst.write_bytes(src.read_bytes())
            print("landing:", landing)

    # 3) 注入「返回图谱」浮动入口（所有页面）
    n = 0
    for p in MIRROR.rglob("index.html"):
        t = p.read_text(encoding="utf-8", errors="replace")
        if "kg-back" not in t:
            p.write_text(t.replace("</body>", badge + "</body>"), encoding="utf-8")
            n += 1
    print(f"badge injected: {n}")

    total = sum(f.stat().st_size for f in MIRROR.rglob("*") if f.is_file())
    print(f"mirror -> {MIRROR} ({total/1048576:.2f} MB, {len(list(MIRROR.rglob('*')))} files)")


if __name__ == "__main__":
    main()
