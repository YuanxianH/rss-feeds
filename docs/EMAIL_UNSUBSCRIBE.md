# 邮件服务清理

这个仓库只做 RSS，不向外发信。PR 合并后，用下面清单在自己的邮箱里退订对应通讯。

## 本仓库有没有发信服务

没有。查过这些位置：

- 源码、配置、文档、脚本里没有 SMTP / SendGrid / Mailgun / Resend / SES / Mailchimp / Buttondown / Substack 等发信集成
- 仓库 Secrets 为空
- 唯一 workflow 是 `.github/workflows/update-rss.yml`，只抓取、测、发布 `gh-pages`
- workflow 里的 `user_email: github-actions[bot]@users.noreply.github.com` 只是 Pages 提交的 git author，不会发邮件

因此这里没有可以“关掉”的发信服务。

## 来源站上的邮件通讯

只统计 `config.yaml` 里正在跟踪的站点。退订需要你邮箱里那封信底部的链接，这边不能代点。

| 来源 | RSS | 邮件通讯 | 合并后怎么退订 |
|---|---|---|---|
| Google DeepMind Blog | `deepmind_blog.xml` | 有。页脚 “Sign up for updates on our latest innovations”，表单提交到 `https://services.google.com/fb/submissions/deepmindgoogle/`，字段 `DeepmindGcmNewsletter` | 搜 DeepMind / Google 更新信，点 Unsubscribe，或打开 [Google 账号通讯偏好](https://myaccount.google.com/) |
| Waymo Blog / Research | `waymo_blog_tech.xml`、`waymo_research.xml` | 有。城市更新页 [waymo.com/updates](https://waymo.com/updates/) 勾选 “Send me regular updates”，提交到 `https://services.google.com/fb/submissions/waymo-newsletter-v1/`（`WaymoNewsletterUpdates`）。Waymo One 乘车账号另有营销信 | 搜 Waymo 信，点 “Unsubscribe here”。乘车营销信见 [Waymo One 邮件说明](https://support.google.com/waymo/answer/9190806)。不要为了退营销信删账号 |
| OpenAI Research | `openai_research_only.xml`（官方 RSS 过滤） | 官方会发营销信，常见发件人 `noreply@email.openai.com`。审计时 openai.com 返回 403，页脚表单未抓到 | 搜 openai.com，点信里的 Unsubscribe；登录后也可改账号通知设置 |
| Meta AI Research | `meta_ai_research.xml` | 研究页没有通讯表单。Meta 账号 / Horizon 营销信是账号级，不是这篇研究 RSS | 只有收到 Meta 营销信时，才去账号通知设置关 |
| DeepSeek / MiniMax / Kimi / Seed / 智谱研究 / 混元 / Physical Intelligence / Incomplete Ideas / Codex Releases | 已有对应 XML | 跟踪页上没有邮件通讯表单。智谱页里的“订阅”是 GLM Coding Plan 套餐，不是邮件列表 | 不用为这些源发退订信 |

## 这边没法代取消的

- 你邮箱里已经在收的 DeepMind / Waymo / OpenAI 信：要你点信里的退订链接
- GitHub 自己的 Actions / Watching / Security 通知：这是 GitHub 账号设置，仓库 token 读不到，也改不了
- 和这些 RSS 源无关的其它通讯（The Batch、Import AI 等）：这个仓库里没有记录

## 合并后建议动作

1. 在邮箱搜 `DeepMind`、`Waymo`、`OpenAI` / `noreply@email.openai.com`
2. 只对营销 / 更新信点 Unsubscribe
3. 研究、博客、发布继续用 [订阅目录](https://yuanxianh.github.io/rss-feeds/)
