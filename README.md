# DSH 知识图谱网站

DeepSeek Harness 知识图谱网站源码，线上地址：**https://kg.agidsh.com**

## 内容

- **知识图谱首页**（`/`）：9,350 实体 / 15,153 关系 / 11 架构层 / 16 步导览。Canvas 交互面板，支持搜索、分层过滤、节点详情、官方文档悬浮展开。
- **官方参考文档站**（`/deepseek-harness/reference/`）：官方 VitePress 站点的完整镜像，含入门（guide）、开发（develop）、参考（reference）三大部分，中英双语，原生语言切换。
- **对齐报告**：`docs/docs-sync-report.md`，记录与官方文档的逐轮对齐、补全与上线过程。

## 目录结构

```
scripts/   构建脚本
  build_layout.py          图布局（代码岛/文档岛分离）
  build_dashboard.py       单文件面板组装
  build_doc_payload.py     官方文档落地与链接改写
  build_site.py            站点组装（首页导航、旧文档站）
  mirror_official_docs.py  官方 VitePress 站点镜像（中英双语）
  apply_reference_sync.py  图谱知识实体同步
  dashboard_app.js         面板前端逻辑
  dashboard_template.html  面板模板
data/
  doc-payload.json         69 页文档结构化正文（2.2 MB）
docs/
  docs-sync-report.md      对齐报告
site/                      可直接部署的静态站点（35 MB）
  index.html               图谱首页
  deepseek-harness/        官方 VitePress 镜像（中英双语）
  docs/                    旧自建文档站（兼容保留）
  assets/                  站点样式
```

## 重建

脚本依赖 `.ua/intermediate/layout-file-level.json` 与 `.ua/knowledge-graph.json`（由 understand-anything 生成，不随本站仓库分发）。已有产物的增量重建：

```bash
python scripts/build_dashboard.py   # 需 .ua/intermediate + knowledge-graph.json
python scripts/build_site.py        # 组装首页与旧文档站
python scripts/mirror_official_docs.py  # 从官网重新镜像文档（需联网）
```

## 部署

静态站点，直接把 `site/` 内容发布到 Web 根目录即可。线上使用 Windows + Nginx：

- 站点目录：`C:\wwwroot\kg`
- 域名：`kg.agidsh.com`（HTTPS，证书有效期至 2027-02-25）
- Nginx 关键路由：

```nginx
location = /deepseek-harness/guide/    { return 301 /deepseek-harness/guide/quickstart; }
location = /deepseek-harness/develop/  { return 301 /deepseek-harness/develop/basic/; }
location /deepseek-harness/ { try_files $uri $uri/index.html =404; expires 7d; }
```

`location /deepseek-harness/` 必须允许目录 index，否则 VitePress SPA 会渲染 404。

## 数据来源

- 代码图谱：deepseek-ai/deepseek-harness 仓库（by understand-anything skill）
- 文档：https://deepseek-harness.github.io/deepseek-harness/ （官方镜像）
- 对齐记录见 `docs/docs-sync-report.md`
