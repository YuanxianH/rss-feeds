# Agent 指南

这个仓库把没有 RSS 的 AI 实验室 / 公司网站做成 Feed，由
`.github/workflows/update-rss.yml`（显示名 **Update RSS Feeds**）每小时抓取并发布到 `gh-pages`。

Feed XML、`feeds/index.html` 和 `feeds/assets/` 是生成产物，不要手工编辑或提交。

## 常用命令

在仓库根目录执行：

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py"
python -m compileall main.py src tests
bash -n scripts/ops/*.sh
python main.py -v
python main.py --allow-partial
```

CI 与本地验证命令必须一致。单元测试应脱网可过；`python main.py` 会访问上游站点。

## 失败语义

- 退出码 `0`：成功
- 退出码 `1`：业务失败（抓取失败 / 无有效内容 / 生成失败）
- 退出码 `2`：配置或参数错误
- `--allow-partial`：至少一个 Feed 更新成功且首页生成成功时返回 `0`；失败 Feed 的旧 XML 由发布流程保留

新增脚本时保持同样约定，避免 CI 假成功。

## Cursor Cloud specific instructions

本仓库的 Cloud Agent / Automation 主要用于 **CI 失败后排查并提修复 PR**。

1. 先读失败的 GitHub Actions run 日志，不要凭猜测改代码。
   ```bash
   gh run list --workflow=update-rss.yml --limit 5
   gh run view <run-id> --log-failed
   ```
2. 用与 workflow 相同的命令复现：先单测，再按需要跑 `python main.py --allow-partial`。
3. 上游站点改版时，优先改 `config.yaml` 选择器 / `path_prefix` / JSON 字段映射；只有专用 API 才新增 `src/jobs/` job。
4. 为页面结构保存最小 HTML/JSON fixture，并补脱网单元测试。参考 `.claude/skills/add-rss-feed/SKILL.md`。
5. 确认修复后再开 PR。不要推 `main`，不要合并，不要改无关文件。
6. 纯外部站点宕机、限流、或没有安全代码改动能修的问题：不要开装饰性 PR，写清原因即可。
7. 不要为了让 CI 变绿而跳过测试，除非能证明是 flake 且跳过是正确产品决策。

更完整的 CI Autofix Automation 配置见 `docs/CI_AUTOFIX_AUTOMATION.md`。
维护约定见 `docs/MAINTAINER_GUIDE.md`。
