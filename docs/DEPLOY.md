# 部署指南（GitHub Pages）

适用对象：使用者。开发细节请看 `docs/MAINTAINER_GUIDE.md`。

## 部署方式

- 推荐：`deploy.sh` 推送代码，触发 GitHub Actions 自动生成并发布
- 可选：`publish.sh` 直接把本地 `feeds/*.xml` 发布到 `gh-pages`

## 前置条件

- 已安装 `git`、`python`
- 拥有 GitHub 仓库权限
- 仓库根目录已包含本项目

## 方式一：自动化部署（推荐）

### 1. 首次推送

```bash
cd /path/to/rss_creator
./deploy.sh --remote-url https://github.com/YOUR_USERNAME/rss-feeds.git
```

说明：

- 会先执行单元测试
- 默认要求工作区干净（避免误推未确认改动）

### 2. 后续更新

```bash
./deploy.sh
```

可选参数：

- `--no-tests` 跳过测试
- `--auto-commit` 自动提交当前改动
- `--allow-dirty` 允许未提交改动继续推送

### 3. 开启 GitHub Pages

1. 打开仓库 `Settings -> Pages`
2. Source 选择 `Deploy from a branch`
3. Branch 选择 `gh-pages`，目录选 `/ (root)`

### 4. 查看结果

1. 打开 `Actions` 查看 `Update RSS Feeds`
2. 成功后通过如下地址访问（替换用户名与仓库名）：

```text
https://YOUR_USERNAME.github.io/rss-feeds/openai_research_only.xml
https://YOUR_USERNAME.github.io/rss-feeds/deepmind_blog.xml
```

## 方式二：手动发布到 gh-pages

```bash
./publish.sh
```

常见参数：

```bash
# 使用已有 XML，不重新抓取
./publish.sh --skip-generate

# 指定发布分支
./publish.sh --branch gh-pages
```

## 常见问题

### 1) `deploy.sh` 提示 dirty working tree

默认安全策略。可选处理：

- 先手动提交再部署
- 或使用 `--auto-commit`
- 或使用 `--allow-dirty`

### 2) Actions 无法推送 `gh-pages`

检查仓库设置：

- `Settings -> Actions -> General -> Workflow permissions`
- 选择 `Read and write permissions`

### 3) Pages 404

- 等待 5-10 分钟
- 确认 Pages Source 指向 `gh-pages`
- 确认 workflow 最新一次执行成功
