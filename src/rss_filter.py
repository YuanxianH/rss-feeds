"""RSS 过滤模块 - 从现有 RSS 中过滤特定分类"""

import requests
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


class RSSFilter:
    """RSS 过滤器"""

    def __init__(self, source_url: str):
        """
        初始化过滤器

        Args:
            source_url: 源 RSS feed URL
        """
        self.source_url = source_url

    def fetch_rss(self) -> Optional[str]:
        """获取源 RSS 内容"""
        try:
            logger.info(f"正在获取 RSS: {self.source_url}")
            response = requests.get(self.source_url, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.error(f"获取 RSS 失败: {e}")
            return None

    def filter_by_category(
        self,
        categories: List[str],
        output_path: str,
        title: Optional[str] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        按分类过滤 RSS

        Args:
            categories: 要保留的分类列表（不区分大小写）
            output_path: 输出文件路径
            title: 新 RSS 的标题（可选）
            description: 新 RSS 的描述（可选）

        Returns:
            是否成功生成
        """
        rss_content = self.fetch_rss()
        if not rss_content:
            return False

        try:
            soup = BeautifulSoup(rss_content, "xml")

            # 获取源 RSS 信息
            channel = soup.find("channel")
            if not channel:
                logger.error("RSS 格式无效")
                return False

            source_title = channel.find("title").get_text() if channel.find("title") else "RSS Feed"
            source_link = channel.find("link").get_text() if channel.find("link") else ""
            source_desc = channel.find("description").get_text() if channel.find("description") else ""

            # 创建新的 RSS
            fg = FeedGenerator()
            fg.title(title or f"{source_title} - 已过滤")
            fg.link(href=source_link, rel="alternate")
            fg.description(description or f"{source_desc} (仅包含: {', '.join(categories)})")
            fg.language("zh-CN")
            fg.generator("RSS Creator - RSS Filter")

            # 过滤条目
            items = soup.find_all("item")
            filtered_count = 0
            categories_lower = [c.lower() for c in categories]

            logger.info(f"源 RSS 包含 {len(items)} 个条目")

            for item in items:
                # 获取分类
                item_categories = item.find_all("category")
                item_category_texts = [cat.get_text().lower() for cat in item_categories]

                # 检查是否匹配
                if any(cat in item_category_texts for cat in categories_lower):
                    fe = fg.add_entry()

                    # 标题
                    if item_title := item.find("title"):
                        fe.title(item_title.get_text())

                    # 链接
                    if item_link := item.find("link"):
                        fe.link(href=item_link.get_text())

                    # 描述
                    if item_desc := item.find("description"):
                        fe.description(item_desc.get_text())

                    # GUID
                    if item_guid := item.find("guid"):
                        fe.guid(item_guid.get_text())

                    # 发布日期
                    if item_date := item.find("pubDate"):
                        fe.pubDate(item_date.get_text())

                    # 分类
                    for cat in item_categories:
                        fe.category(term=cat.get_text())

                    filtered_count += 1

            # 生成文件
            fg.rss_file(output_path, pretty=True)
            logger.info(f"成功过滤 RSS: {output_path}")
            logger.info(f"保留了 {filtered_count}/{len(items)} 个条目")

            return True

        except Exception as e:
            logger.error(f"过滤 RSS 失败: {e}")
            return False
