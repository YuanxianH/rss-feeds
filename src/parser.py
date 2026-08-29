"""HTML 解析模块"""

from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from datetime import datetime, timezone
from dateutil import parser as date_parser
from urllib.parse import urljoin
import logging
import re

logger = logging.getLogger(__name__)

_SLASH_DATE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b")
_YEAR_DATE = re.compile(r"\b((?:18|19|20)\d{2})\b")
_CONTEXT_PARENTS = {"li", "small", "span", "p", "td"}
_CONTEXT_PARENT_MAX_CHARS = 200


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

    def parse_items(
        self,
        selectors: Dict[str, str],
        max_items: int = 20,
        infer_dates_from_context: bool = False,
    ) -> List[Dict[str, str]]:
        """
        解析网页内容为结构化数据

        Args:
            selectors: CSS 选择器配置
            max_items: 最多返回条目数
            infer_dates_from_context: 从链接旁文本推断日期

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
                item = self._parse_item(
                    container,
                    selectors,
                    infer_dates_from_context=infer_dates_from_context,
                )
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

    def _parse_item(
        self,
        container,
        selectors: Dict[str, str],
        infer_dates_from_context: bool = False,
    ) -> Dict[str, str]:
        """解析单个条目"""
        item = {}

        # 标题
        if title_selector := selectors.get("title"):
            if title_elem := container.select_one(title_selector):
                item["title"] = self._element_text(title_elem)
        if not item.get("title") and container.name == "a":
            # 条目容器本身就是 <a> 时，select_one 找不到后代标题，回退到自身文本
            item["title"] = self._element_text(container)

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

        if infer_dates_from_context and not item.get("pubDate"):
            if pub_date := self._infer_date_from_context(container):
                item["pubDate"] = pub_date

        return item

    def _infer_date_from_context(self, container) -> Optional[str]:
        """从链接后文本、短父节点或标题里提取日期。"""
        for text in self._context_date_texts(container):
            if pub_date := self._first_date_in_text(text):
                return pub_date
        return None

    def _context_date_texts(self, container) -> List[str]:
        texts = [self._sibling_text(container)]
        parent = container.parent
        if (
            parent is not None
            and parent.name in _CONTEXT_PARENTS
        ):
            parent_text = " ".join(parent.get_text(" ", strip=True).split())
            if parent_text and len(parent_text) <= _CONTEXT_PARENT_MAX_CHARS:
                texts.append(parent_text)
        texts.append(self._element_text(container))
        return texts

    def _sibling_text(self, container) -> str:
        bits = []
        sibling = container.next_sibling
        while sibling is not None:
            name = getattr(sibling, "name", None)
            if name in {"a", "li", "ul", "ol"}:
                break
            if hasattr(sibling, "get_text"):
                bits.append(sibling.get_text(" ", strip=True))
            else:
                bits.append(str(sibling))
            sibling = sibling.next_sibling
        return " ".join(bit for bit in bits if bit)

    def _first_date_in_text(self, text: str) -> Optional[str]:
        if not text:
            return None
        if match := _SLASH_DATE.search(text):
            return self._parse_date(match.group(1))
        if match := _YEAR_DATE.search(text):
            year = int(match.group(1))
            dt = datetime(year, 1, 1, tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        return None

    def _element_text(self, elem) -> str:
        """读取元素可见文本，并折叠 HTML 换行造成的多余空白。"""
        return " ".join((elem.get("title") or elem.get_text() or "").split())

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
            dt = date_parser.parse(date_string, dayfirst=False)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S %z")
        except Exception:
            # 日期解析失败时返回 None，避免把旧内容伪装成最新内容
            return None
