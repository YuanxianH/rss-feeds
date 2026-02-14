# 维护指南

适用对象：需要维护代码、排查故障、扩展新站点的开发者。

## 目录与职责

```text
rss_creator/
├── src/                 # 核心库（抓取/解析/RSS 生成）
├── scripts/feed_jobs/   # 独立来源任务脚本（不走 config.yaml）
├── scripts/ops/         # 运维脚本实现（更新/部署/发布）
├── tests/               # 单元测试
├── .github/workflows/   # CI/CD 工作流
└── feeds/               # RSS 产物目录
```

根目录 `deploy.sh` / `publish.sh` / `update_feeds.sh` / `push_to_github.sh` 是兼容入口，实际逻辑在 `scripts/ops/`。

## 核心执行链路

1. `main.py`
- 读取 `config.yaml`
- 调用 `src/feed_creator.py` 处理每个 feed
- 在非调度模式下，任一 feed 失败返回退出码 `1`

2. `scripts/ops/update_feeds.sh`
- 依次执行：
  - `python main.py`
  - `scripts/feed_jobs/filter_openai_research.py`
  - `scripts/feed_jobs/fetch_waymo_blog.py`
  - `scripts/feed_jobs/fetch_minimax_blog.py`
- 聚合失败并在最后返回非零

3. `.github/workflows/update-rss.yml`
- 安装依赖
- 运行单元测试
- 调用 `./update_feeds.sh`
- 将 `feeds/` 发布到 `gh-pages`

## 失败语义约定

- 任务成功：退出码 `0`
- 业务失败（抓取失败/无有效内容/生成失败）：退出码 `1`
- 配置或参数错误：退出码 `2`（例如主配置文件不存在）

新增脚本时请保持同样约定，避免 CI 假成功。

## 如何新增一个 feed

### 路径 A：可配置站点（优先）

1. 在 `config.yaml` 追加 `feeds[]` 配置
2. 先本地验证：

```bash
python main.py -v
```

3. 确认产物和订阅器行为（标题、链接、日期、去重）

### 路径 B：独立任务脚本

适用于需要 API 调用或复杂解析逻辑的来源。

1. 在 `scripts/feed_jobs/` 新增脚本
2. 确保返回规范退出码
3. 在 `scripts/ops/update_feeds.sh` 增加 `run_step`
4. 补对应单元测试（必要时 mock 网络层）

## 测试与检查

```bash
# 单元测试
python -m unittest discover -s tests -p "test_*.py"

# 语法检查（示例）
python -m compileall main.py src scripts/feed_jobs tests

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
- 开启 `-v` 查看解析日志

2. CI 失败但本地成功
- 检查网络与目标站点限流策略
- 检查 CI 运行时依赖版本是否一致

3. 本地 sandbox 网络失败（在受限环境）
- 这通常是执行环境限制，不代表脚本逻辑错误
- 在可联网环境再次验证抓取结果
