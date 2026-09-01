---
name: debug-ci-failure
description: >
  Debug a failed Update RSS Feeds GitHub Actions run, reproduce it, iterate
  until the failure is actually fixed, and open a pull request. Use when CI
  fails, a check is red, or a Cursor Automation asks to autofix CI.
---

# Debug CI Failure

本仓库主 CI 是 `.github/workflows/update-rss.yml`（显示名 **Update RSS Feeds**）。
它在 `schedule`（每小时）、`workflow_dispatch` 和 push 到 `main`/`master` 时运行。

## 1. 读失败日志

```bash
gh run list --workflow=update-rss.yml --limit 10
gh run view <run-id> --log-failed
```

先定位失败的 job / step，再改代码。常见步骤：

| Step | 含义 |
|---|---|
| Install dependencies | `requirements.txt` / Python 版本 |
| Run unit tests | 脱网单测失败，几乎一定是代码或 fixture 回归 |
| Generate RSS feeds | `python main.py --allow-partial`；全失败或首页生成失败才会让 job 失败 |
| Deploy to GitHub Pages | 发布权限 / `gh-pages` 问题，通常不是抓取逻辑

## 2. 本地复现

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
python main.py --allow-partial
```

单测必须脱网可通过。不要用 hop 过测试来“修”CI。

## 3. 按根因修

- **单测 / 解析回归**：改 `src/` 或对应 fixture，补最小测试。
- **上游改版**：先改 `config.yaml` 的选择器、`path_prefix`、`allowed_hosts`、JSON 字段映射；必要时用 `python .claude/skills/add-rss-feed/scripts/analyze_page.py <URL>`。
- **专用 API 变了**：只在现有 job 无法表达时才新增 `src/jobs/` 并注册 `job_type`。
- **部分上游临时失败**：`--allow-partial` 已允许部分成功。不要把整体失败改成吞掉所有错误。
- **外部宕机 / 限流且无安全代码修复**：不要开 PR，说明原因后停止。

生成产物（`feeds/*.xml`、`feeds/index.html`、`feeds/assets/`）不要提交。

## 4. 迭代到真正修好

1. 提出假设并做最小改动。
2. 再跑与 CI 相同的验证命令。
3. 失败则换假设，继续改，直到失败消失或确认没有安全的代码修复。
4. 有验证过的修复再开 PR。标题和正文写清根因、改动和验证命令。
5. 不要推 `main`，不要合并。

失败语义与维护约定见 `AGENTS.md` 和 `docs/MAINTAINER_GUIDE.md`。
