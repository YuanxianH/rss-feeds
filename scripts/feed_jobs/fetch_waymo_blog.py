#!/usr/bin/env python3
"""从 Waymo Blog API 获取 Technology 分类文章并生成 RSS"""

import logging
import requests
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.rss_generator import RSSGenerator


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    setup_logging()
    logger = logging.getLogger(__name__)

    api_url = "https://waymo.com/api/blog/posts"
    base_url = "https://waymo.com"
    tag = "Technology"
    max_items = 50

    output_dir = ROOT_DIR / "feeds"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "waymo_blog_tech.xml"

    logger.info(f"正在从 Waymo Blog API 获取文章...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
    }
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        logger.error(f"调用 Waymo API 失败: {exc}")
        return 1
    except ValueError as exc:
        logger.error(f"Waymo API 返回了非法 JSON: {exc}")
        return 1

    posts = data.get("posts", [])
    logger.info(f"API 返回 {len(posts)} 篇文章")

    # 过滤 Technology 标签，按日期倒序排列（最新在前）
    tech_posts = [p for p in posts if tag in p.get("tags", [])]
    tech_posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    logger.info(f"过滤后 {len(tech_posts)} 篇 Technology 文章")

    # 取最新的 max_items 篇，反转后输入 feedgen（feedgen 以栈顺序输出）
    latest = tech_posts[:max_items]
    latest.reverse()

    # 转换为 RSS 条目格式
    items = []
    for post in latest:
        url = post.get("url", "")
        if url and not url.startswith("http"):
            url = base_url + url

        items.append({
            "title": post.get("title", ""),
            "link": url,
            "description": post.get("summary", ""),
            "pubDate": post.get("date", ""),
            "author": post.get("author", ""),
        })

    if not items:
        logger.warning("未找到任何 Technology 文章")
        return 1

    generator = RSSGenerator(
        title="Waymo Blog - Technology",
        link="https://waymo.com/blog/search/?t=Technology",
        description="Waymo Blog Technology 分类文章",
    )
    generator.add_items(items)

    if generator.generate(str(output_path)):
        logger.info(f"成功生成 {len(items)} 篇文章到 {output_path}")
        return 0
    else:
        logger.error("RSS 生成失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
