#!/usr/bin/env python3
"""过滤 OpenAI RSS，只保留研究内容"""

import logging
from pathlib import Path
from src.rss_filter import RSSFilter


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main():
    """主函数"""
    setup_logging()

    # 创建输出目录
    output_dir = Path("feeds")
    output_dir.mkdir(exist_ok=True)

    # 过滤器配置
    source_url = "https://openai.com/news/rss.xml"
    output_path = output_dir / "openai_research_only.xml"

    # 要保留的分类
    research_categories = [
        "Research",           # 研究
        "research",
        "Science",           # 科学
        "science",
    ]

    # 创建过滤器
    logger = logging.getLogger(__name__)
    logger.info("开始过滤 OpenAI RSS，只保留研究内容...")

    filter_tool = RSSFilter(source_url)

    success = filter_tool.filter_by_category(
        categories=research_categories,
        output_path=str(output_path),
        title="OpenAI Research Only",
        description="OpenAI 官方 RSS - 仅研究内容"
    )

    if success:
        logger.info(f"✅ 成功！RSS 已保存到: {output_path}")
        logger.info(f"📡 在 RSS 阅读器中订阅: file://{output_path.absolute()}")
        logger.info("\n或者启动本地服务器：")
        logger.info(f"  cd {output_dir}")
        logger.info("  python -m http.server 8000")
        logger.info(f"  然后订阅: http://localhost:8000/{output_path.name}")
    else:
        logger.error("❌ 过滤失败")


if __name__ == "__main__":
    main()
