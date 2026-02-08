"""RSS 生成模块"""

from feedgen.feed import FeedGenerator
from typing import List, Dict
from datetime import datetime, timezone
from dateutil import parser as date_parser
import logging

logger = logging.getLogger(__name__)


class RSSGenerator:
    """RSS 生成器"""

    def __init__(self, title: str, link: str, description: str):
        """
        初始化 RSS 生成器

        Args:
            title: Feed 标题
            link: Feed 链接
            description: Feed 描述
        """
        self.fg = FeedGenerator()
        self.fg.title(title)
        self.fg.link(href=link, rel="alternate")
        self.fg.description(description)
        self.fg.language("zh-CN")
        self.fg.generator("RSS Creator")

    def add_items(self, items: List[Dict[str, str]]):
        """
        添加条目到 RSS

        Args:
            items: 条目列表
        """
        for item_data in items:
            try:
                fe = self.fg.add_entry()

                # 必需字段
                fe.title(item_data.get("title", "无标题"))
                fe.link(href=item_data.get("link", ""))

                # 可选字段
                if description := item_data.get("description"):
                    fe.description(description)

                if pub_date := item_data.get("pubDate"):
                    # 将字符串转换为带时区的 datetime 对象
                    try:
                        if isinstance(pub_date, str):
                            dt = date_parser.parse(pub_date)
                            # 如果没有时区信息，添加 UTC
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            fe.pubDate(dt)
                        else:
                            fe.pubDate(pub_date)
                    except Exception:
                        # 如果解析失败，使用当前时间
                        fe.pubDate(datetime.now(timezone.utc))
                else:
                    # 默认使用当前时间
                    fe.pubDate(datetime.now(timezone.utc))

                if author := item_data.get("author"):
                    fe.author({"name": author})

            except Exception as e:
                logger.warning(f"添加条目失败: {e}")
                continue

    def generate(self, output_path: str) -> bool:
        """
        生成 RSS 文件

        Args:
            output_path: 输出文件路径

        Returns:
            是否成功生成
        """
        try:
            self.fg.rss_file(output_path, pretty=True)
            logger.info(f"成功生成 RSS: {output_path}")
            return True
        except Exception as e:
            logger.error(f"生成 RSS 失败: {e}")
            return False
