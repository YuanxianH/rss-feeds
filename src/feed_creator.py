"""Feed 创建主逻辑"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
import logging

from .scraper import WebScraper
from .parser import HTMLParser
from .path_utils import resolve_output_path
from .rss_generator import RSSGenerator

logger = logging.getLogger(__name__)
_NAIVE_MIN = datetime.min.replace(tzinfo=timezone.utc)


class FeedCreator:
    """Feed 创建器"""

    def __init__(self, feeds_dir: str = "feeds"):
        """
        初始化 Feed 创建器

        Args:
            feeds_dir: RSS 文件输出目录
        """
        self.feeds_dir = Path(feeds_dir)
        self.feeds_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_output_path(self, output: str) -> Path:
        """确保输出文件在 feeds 目录内，避免路径逃逸。"""
        return resolve_output_path(self.feeds_dir, output)

    def _persist_pubdates(self, items: list[dict], output_path: Path) -> list[dict]:
        """无页面日期的条目沿用上次 feed 的 pubDate，新条目才用当前时间。"""
        previous = self._read_existing_pubdates(output_path)
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")
        for item in items:
            if item.get("pubDate"):
                continue
            item["pubDate"] = previous.get(item.get("link", "")) or now
        return items

    def _read_existing_pubdates(self, xml_path: Path) -> dict[str, str]:
        if not xml_path.exists():
            return {}
        try:
            root = ET.parse(xml_path).getroot()
        except (ET.ParseError, OSError) as exc:
            logger.warning("读取已有 feed 日期失败 %s: %s", xml_path, exc)
            return {}
        dates: dict[str, str] = {}
        for item in root.findall("./channel/item"):
            link = (item.findtext("guid") or item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if link and pub_date:
                dates[link] = pub_date
        return dates

    def _order_items_for_rss(self, items: list[dict]) -> list[dict]:
        """feedgen 会反转写入顺序，因此先按时间升序，使 XML 中最新条目在前。"""
        return sorted(items, key=self._item_sort_datetime)

    @staticmethod
    def _item_sort_datetime(item: dict) -> datetime:
        value = item.get("pubDate") or ""
        try:
            parsed = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return _NAIVE_MIN
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def create_feed(self, config: Dict) -> bool:
        """
        根据配置创建单个 RSS feed

        Args:
            config: Feed 配置

        Returns:
            是否成功创建
        """
        name = config.get("name", "未命名")
        logger.info(f"开始处理: {name}")

        try:
            # 1. 获取配置
            url = config.get("url")
            if not url:
                logger.error(f"{name}: 缺少 url 配置")
                return False

            output = config.get("output", f"{name}.xml")
            selectors = config.get("selectors", {})
            options = config.get("options", {})

            # 2. 抓取网页
            scraper = WebScraper(
                timeout=options.get("timeout", 10),
                user_agent=options.get("user_agent"),
                retries=options.get("retries", 2),
                backoff_factor=options.get("backoff_factor", 0.5),
            )
            html = scraper.fetch(url, encoding=options.get("encoding"))

            if not html:
                logger.error(f"{name}: 抓取失败")
                return False

            # 3. 解析内容
            # 提取 base_url 用于处理相对链接
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

            parser = HTMLParser(html, base_url=base_url)
            items = parser.parse_items(
                selectors,
                max_items=options.get("max_items", 20),
                infer_dates_from_context=bool(options.get("infer_dates_from_context")),
            )

            if not items:
                logger.warning(f"{name}: 未解析到任何条目")
                return False

            output_path = self._resolve_output_path(output)
            if options.get("persist_pubdates"):
                items = self._persist_pubdates(items, output_path)
            if options.get("infer_dates_from_context") or options.get("persist_pubdates"):
                items = self._order_items_for_rss(items)

            # 4. 生成 RSS
            generator = RSSGenerator(
                title=config.get("title", name),
                link=config.get("link", url),
                description=config.get("description", f"{name} RSS Feed")
            )
            generator.add_items(items)

            success = generator.generate(str(output_path))

            if success:
                logger.info(f"{name}: 成功生成，包含 {len(items)} 个条目")

            return success

        except Exception as e:
            logger.error(f"{name}: 处理失败 - {e}")
            return False

    def create_all_feeds(self, configs: list) -> Dict[str, bool]:
        """
        创建所有配置的 feeds

        Args:
            configs: Feed 配置列表

        Returns:
            每个 feed 的创建结果
        """
        results = {}

        for config in configs:
            name = config.get("name", "未命名")
            results[name] = self.create_feed(config)

        # 统计
        success_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        logger.info(f"完成: {success_count}/{total_count} 个 feeds 创建成功")

        return results
