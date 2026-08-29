# CI 失败自动修复（Cursor Automations）

Cloud Agent **无法代你创建** Automation。Cursor 没有仓库内配置文件，也没有创建 Automation 的 API。
请在 Cursor 控制台启用一条 Automation：CI 失败后自动排查，修到通过后再开 PR。

官方文档：[Automations](https://cursor.com/docs/cloud-agent/automations)
创建入口：[cursor.com/automations/new](https://cursor.com/automations/new)
模板：[Fix CI failures](https://cursor.com/marketplace/automations/fix-ci-failures)

## 前置条件

1. 已安装 Cursor GitHub App，并且能访问本仓库（[GitHub 集成](https://cursor.com/docs/integrations/github)）。
2. App 具备 Checks / Actions 读取权限，否则 `CI completed` 收不到事件。
3. 本仓库已有 Cloud Agent 环境；根目录 `AGENTS.md` 和 `.cursor/environment.json` 供 Automation 复现测试。

## 推荐配置

| 项 | 值 |
|---|---|
| 名称 | CI Autofix |
| 仓库 | `yuanxianh/rss-feeds`，默认分支 `main` |
| **触发器** | GitHub → **CI completed**（界面里也可能叫 **Checks completed**） |
| 结论 | **On failure** |
| 范围 | 本仓库；包含 `main` / `master` |
| 触发者 | **Anyone**（不要选 “by Me”，否则会漏掉 `github-actions[bot]`） |
| 工具 | Pull request creation（默认开启）；Memories（默认开启，用于去重） |

**不要用 Workflow run completed 作为唯一触发器。**
Cursor 对这个触发器只处理 **push** 启动的 workflow。本仓库主 CI 主要是每小时 `schedule`，以及手动 `workflow_dispatch`，这两种失败都不会启动 Automation。

[相关说明](https://forum.cursor.com/t/github-workflow-trigger-is-unreliable/167362)

## 创建步骤

### 方式 A：市场模板（最快）

1. 打开 [Fix CI failures](https://cursor.com/marketplace/automations/fix-ci-failures)。
2. 应用到本仓库。
3. 确认触发器是 **Checks completed / CI completed**、**On failure**、**Anyone**、包含 `main`。
4. 把模板自带 prompt 换成下面的「持续排查」版本（模板默认在没把握时直接停）。
5. 保存并激活。

### 方式 B：空白 Automation

1. 打开 [cursor.com/automations/new](https://cursor.com/automations/new)。
2. 选单一仓库 `yuanxianh/rss-feeds`。
3. 加上面的触发器。
4. 粘贴下面的 prompt。
5. 保存并激活。

### 方式 C：本地 `/automate`

在 **本地** Cursor Agent（不是 Cloud Agent）里输入 `/automate`，并说明：

> 当本仓库 GitHub CI 失败时（包括每小时定时的 Update RSS Feeds / update-rss.yml），读取失败日志，持续排查直到真正修好，验证后再开 PR。触发器必须用 CI completed / Checks completed，不要用 Workflow run completed，因为大多数 run 是 schedule 或 workflow_dispatch。

激活前检查触发器，避免被配成 Workflow run completed。

## 粘贴用 Prompt

```text
Your task is to fix CI failures in yuanxianh/rss-feeds until the failure is actually solved, then open a pull request.

The main CI is `.github/workflows/update-rss.yml` (display name "Update RSS Feeds"). It runs on schedule (hourly), workflow_dispatch, and push to main/master. All of those failures are in scope.

Read `AGENTS.md` and `.cursor/skills/debug-ci-failure/SKILL.md` first.

# Deduplication

To avoid racing against other agents, before any investigation:
1. Collect the names of ALL failing CI jobs/checks from the CI Status Report.
2. Calculate your memory filename: sort the failing jobs alphabetically, join with "_", then remove any characters that are not letters, digits, hyphens, underscores, or dots. Prepend "ci-fail-" and truncate to 64 characters total.
3. Read the memory file with this filename.
   - If it exists and the timestamp inside is less than 30 minutes old, stop immediately — no branch, no Slack, no output.
4. Else, write the memory file with the current unix timestamp.
   - If the write SUCCEEDS: you claimed this failure. Proceed.
   - If the write FAILS (version conflict): another agent claimed it first. Stop immediately.

Also stop (no new PR) if an open PR already exists whose title or branch clearly addresses this same CI failure.

# Investigate

1. Start from the trigger payload (repo, conclusion, head SHA, check/workflow names).
2. Fetch logs with `gh run list --workflow=update-rss.yml` and `gh run view <id> --log-failed`.
3. Classify: unit-test regression, parser/config/upstream-site change, dependency, deploy/permissions, or external outage.
4. Reproduce with the same commands the workflow uses:
   - `python -m pip install -r requirements.txt`
   - `python -m unittest discover -s tests -p "test_*.py"`
   - `python main.py --allow-partial` only when the failed step was feed generation

# Keep going until solved

- Do not stop at a diagnosis. Implement a minimal fix and re-run the same verification.
- If the first fix fails, iterate: new hypothesis, new change, re-verify.
- Repeat until the failure is gone, or you have exhausted reasonable code-side fixes.
- Prefer config.yaml selector / path_prefix / JSON mapping updates for upstream site changes. Add a dedicated job only when the source needs a special API.
- Add or update offline fixtures and unit tests when the page structure changed.
- Do not skip tests to make CI green unless you can justify a genuine flake skip.
- Do not commit generated feeds XML or feeds/index.html.
- Do not push to main. Do not merge.

# When not to open a PR

If the failure is a true external outage, rate limit, or GitHub Pages permission issue with no safe code change, stop and report that. Do not open a cosmetic PR.

# When to open a PR

Open a PR only when you have a verified fix. Pull request creation is enabled. Title and body must include root cause, what changed, and the verification commands.

# Output

**CI Autofix Automation**
**Failure logs**: <link>
**Reason**: <1-2 sentences>
**Fixed by**: <1-2 sentences>
**Verification**: <commands and result>
Do not include a PR link — the system will generate that.
```

## 可选：Webhook 兜底（保证定时任务失败也会触发）

若你发现 `CI completed` 仍漏掉 hourly `schedule` 失败，给**同一条** Automation 再加一个 **Webhook** 触发器（先保存 Automation，才会生成 URL 和 API key）。然后在 `update-rss.yml` 里加一个仅 `failure()` 时 POST 到该 webhook 的 step。

这仍然是 Cursor Automations（CI 调用 Automation webhook），不是 `POST /v1/agents`。
把 Automation 从 Private 提升为 Team Owned 后，必须重新生成 webhook key。

## 激活后如何验收

1. 打开 Automation 的 Run History，确认是开启状态。
2. 等下一次 `Update RSS Feeds` 失败，或在 Actions 里手动 `workflow_dispatch` 复现一次失败。
3. 应出现一次新的 Cloud Agent run；修好后应有修复 PR。
4. 若 Run History 为空：检查 GitHub App 的 Checks 权限，以及触发者是否误选了 “by Me”。
