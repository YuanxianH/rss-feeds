"""HTML 解析模块"""

from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import timezone
from dateutil import parser as date_parser
from urllib.parse import urljoin
import logging

logger = logging.getLogger(__name__)


class HTMLParser:
    """HTML 解析器"""

    def __init__(self, html: str, base_url: str = ""):
        """
        初始化解析器

        Args:
            html: HTML 内容
            base_url: 基础 URL，用于处理相对链接
        """
        self.soup = BeautifulSoup(html, "lxml")
        self.base_url = base_url.rstrip("/")

    def parse_items(self, selectors: Dict[str, str], max_items: int = 20) -> List[Dict[str, str]]:
        """
        解析网页内容为结构化数据

        Args:
            selectors: CSS 选择器配置
            max_items: 最多返回条目数

        Returns:
            解析后的条目列表
        """
        items = []
        seen_links = set()

        # 查找所有条目容器
        items_selector = selectors.get("items")
        if not items_selector:
            logger.warning("未配置 items 选择器")
            return items

        containers = self.soup.select(items_selector)

        if not containers:
            logger.warning(f"未找到匹配的条目，选择器: {items_selector}")
            return items

        logger.info(f"找到 {len(containers)} 个条目")

        for container in containers[:max_items]:
            try:
                item = self._parse_item(container, selectors)
                if item and item.get("title") and item.get("link"):
                    if item["link"] in seen_links:
                        continue
                    seen_links.add(item["link"])
                    items.append(item)
            except Exception as e:
                logger.debug(f"解析条目失败: {e}")
                continue

        logger.info(f"成功解析 {len(items)} 个有效条目")
        return items

    def _parse_item(self, container, selectors: Dict[str, str]) -> Dict[str, str]:
        """解析单个条目"""
        item = {}

        # 标题
        if title_selector := selectors.get("title"):
            if title_elem := container.select_one(title_selector):
                item["title"] = title_elem.get_text(strip=True)

        # 链接
        link_selector = selectors.get("link")
        if link_selector:
            # 如果提供了选择器，使用选择器
            if link_elem := container.select_one(link_selector):
                item["link"] = self._normalize_url(link_elem.get("href", ""))
        elif container.name == "a":
            # 如果 container 本身就是 <a> 标签，直接获取 href
            item["link"] = self._normalize_url(container.get("href", ""))
        else:
            # 尝试在 container 中查找第一个 <a> 标签
            if link_elem := container.find("a"):
                item["link"] = self._normalize_url(link_elem.get("href", ""))

        # 描述
        if desc_selector := selectors.get("description"):
            if desc_elem := container.select_one(desc_selector):
                item["description"] = desc_elem.get_text(strip=True)

        # 日期
        if date_selector := selectors.get("date"):
            if date_elem := container.select_one(date_selector):
                date_text = date_elem.get("datetime") or date_elem.get_text(strip=True)
                item["pubDate"] = self._parse_date(date_text)

        # 作者
        if author_selector := selectors.get("author"):
            if author_elem := container.select_one(author_selector):
                item["author"] = author_elem.get_text(strip=True)

        return item

    def _normalize_url(self, url: str) -> str:
        """规范化 URL，处理相对链接"""
        if not url:
            return ""

        if not self.base_url:
            return url

        # 使用标准 URL 规则处理 /、./、../、查询参数等场景
        return urljoin(f"{self.base_url}/", url)

    def _parse_date(self, date_string: str) -> Optional[str]:
        """解析日期字符串为 RSS 格式"""
        try:
            dt = date_parser.parse(date_string)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            # 日期解析失败时返回 None，避免把旧内容伪装成最新内容
            return None
