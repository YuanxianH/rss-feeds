"""RSS 生成模块"""

from feedgen.feed import FeedGenerator
from typing import List, Dict, Optional
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
        self._seen_entry_ids = set()

    def add_items(self, items: List[Dict[str, str]]):
        """
        添加条目到 RSS

        Args:
            items: 条目列表
        """
        for item_data in items:
            try:
                entry_id = self._get_entry_id(item_data)
                if entry_id in self._seen_entry_ids:
                    continue
                self._seen_entry_ids.add(entry_id)

                fe = self.fg.add_entry()

                # 必需字段
                title = item_data.get("title", "").strip() or "无标题"
                link = item_data.get("link", "").strip()
                if not link:
                    raise ValueError("条目缺少 link")

                fe.title(title)
                fe.link(href=link)
                guid = item_data.get("guid", "").strip() or link
                fe.guid(guid, permalink=(guid == link))

                # 可选字段
                if description := item_data.get("description"):
                    fe.description(description)

                if pub_date := item_data.get("pubDate"):
                    dt = self._to_datetime(pub_date)
                    if dt is not None:
                        fe.pubDate(dt)

                if author := item_data.get("author"):
                    fe.author({"name": author})

            except Exception as e:
                logger.warning(f"添加条目失败: {e}")
                continue

    def _get_entry_id(self, item_data: Dict[str, str]) -> str:
        """优先使用稳定链接作为幂等键，缺失时回退到标题。"""
        link = item_data.get("link", "").strip()
        if link:
            return link
        return item_data.get("title", "").strip()

    def _to_datetime(self, value) -> Optional[datetime]:
        """将字符串或 datetime 统一转换成带时区的 datetime。"""
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                dt = date_parser.parse(str(value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

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
