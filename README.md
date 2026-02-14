# RSS Creator

多来源 RSS 生成与发布工具。

## 文档导航

- 用户使用：[docs/USER_GUIDE.md](docs/USER_GUIDE.md)
- 部署说明：[docs/DEPLOY.md](docs/DEPLOY.md)
- 开发维护：[docs/MAINTAINER_GUIDE.md](docs/MAINTAINER_GUIDE.md)

## 一分钟上手

```bash
pip install -r requirements.txt
python main.py
```

生成文件位于 `feeds/`。
核心配置入口是 `config.yaml` 的 `jobs` 数组。

## 仓库结构

```text
rss_creator/
├── docs/
├── scripts/
│   └── ops/
├── src/
│   └── jobs/
├── tests/
├── main.py
├── config.yaml
└── feeds/
```
