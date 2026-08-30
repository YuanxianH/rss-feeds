# 维护指南

适用对象：需要维护代码、排查故障、扩展新站点的开发者。

## 目录与职责

```text
rss_creator/
├── src/                 # 核心库（抓取/解析/RSS 生成）
├── src/jobs/            # 扩展任务实现（由 main.py 统一调度）
├── scripts/ops/         # 运维脚本实现（更新/部署/发布）
├── tests/               # 单元测试
├── .github/workflows/   # CI/CD 工作流
└── feeds/               # RSS 产物目录
```

## 核心执行链路

1. `main.py`
- 读取 `config.yaml`
- 调用 `src/jobs/runner.py` 处理 `jobs[]`
- 生成 RSS 后由 `src/site_index.py` 从模板和样式生成静态目录
- 默认严格模式下，任一任务失败返回退出码 `1`

2. `.github/workflows/update-rss.yml`
- 安装依赖
- 运行单元测试
- 恢复 `gh-pages` 上一次发布的 XML
- 调用 `python main.py --allow-partial`
- 将 `feeds/` 发布到 `gh-pages`

## 失败语义约定

- 任务成功：退出码 `0`
- 业务失败（抓取失败/无有效内容/生成失败）：退出码 `1`
- 配置或参数错误：退出码 `2`（例如主配置文件不存在）
- `--allow-partial`：至少一个 Feed 更新成功且首页生成成功时返回 `0`；失败
  Feed 的旧 XML 会由发布流程保留，并在 Actions summary 中标记

新增脚本时请保持同样约定，避免 CI 假成功。

## 如何新增一个 feed

### 统一方式：新增 job

1. 简单 SSR 网页：在 `config.yaml` 增加 `type: selector_scrape`。
2. Next.js 等页面若 HTML、内嵌数据或 collection API 含文章：使用
   `type: dynamic_site`，配置 `url`、`path_prefix`、`allowed_hosts`，以及可选的
   `sitemap_urls` / `api_urls`。小时任务会重新抓取页面，网页新增文章后 feed
   会自动更新。
3. 公开 JSON 列表接口（HTML 里没有可用文章链接）：使用 `type: json_list_api`，
   把 list/title/slug/date 和分页参数写进 `config.yaml`。同类站点（例如混元
   研究页）可以复用同一 job，网页持续发文时由小时级 Actions 自动更新 XML。
4. 只有专用 API 或特殊数据模型的来源：在 `src/jobs/` 新增 job 并注册
   `job_type`。
5. 本地验证：

```bash
python main.py -v
```

6. 为页面结构保存最小 HTML/JSON fixture，并补脱网单元测试。

`feeds/index.html`、`feeds/assets/` 和 XML 都是生成产物，不要手工编辑或提交。
首页源文件位于 `src/templates/` 与 `src/site_assets/`。

## 测试与检查

```bash
# 单元测试
python -m unittest discover -s tests -p "test_*.py"

# 语法检查（示例）
python -m compileall main.py src tests

# shell 脚本语法检查
bash -n scripts/ops/*.sh
```

## 发布与部署

- 使用者流程见 `docs/DEPLOY.md`
- 维护者重点关注：
  - workflow 是否全部通过
  - `gh-pages` 最新提交是否包含预期 XML
  - `GITHUB_TOKEN` 权限是否允许写入 Pages 分支

## 常见故障排查

1. 某站点突然无新内容
- 优先检查 `config.yaml` 里的 CSS 选择器
- 对 `dynamic_site` 检查文章链接是否仍符合 `path_prefix`，以及域名是否迁移
- 开启 `-v` 查看解析日志

2. CI 失败但本地成功
- 检查网络与目标站点限流策略
- 检查 CI 运行时依赖版本是否一致
- 查看 Actions summary，区分更新失败、保留旧 Feed 与整体部署失败

3. 本地 sandbox 网络失败（在受限环境）
- 这通常是执行环境限制，不代表脚本逻辑错误
- 在可联网环境再次验证抓取结果

## 邮件

这个项目不发信。不要加 SMTP、SendGrid、Mailgun 或其它投递服务。

来源站如果还有邮件通讯，退订步骤见 `docs/EMAIL_UNSUBSCRIBE.md`。RSS 目录是这些通讯的替代。
