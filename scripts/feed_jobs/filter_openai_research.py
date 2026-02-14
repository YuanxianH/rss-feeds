#!/usr/bin/env python3
"""过滤 OpenAI RSS，只保留研究内容"""

import logging
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rss_filter import RSSFilter


def setup_logging():
    """配置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main() -> int:
    """主函数"""
    setup_logging()

    # 创建输出目录
    output_dir = ROOT_DIR / "feeds"
    output_dir.mkdir(parents=True, exist_ok=True)

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
        return 0
    else:
        logger.error("❌ 过滤失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
