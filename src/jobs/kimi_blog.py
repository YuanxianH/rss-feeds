"""Kimi Blog RSS 任务 - 从 VitePress 站点提取文章."""

import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

BASE_URL = "https://www.kimi.com"
BLOG_URL = f"{BASE_URL}/blog"
DEFAULT_OUTPUT = "kimi_blog.xml"
REQUEST_TIMEOUT = 20


def create_session() -> requests.Session:
    return create_retry_session(
        accept="text/html,application/xhtml+xml",
        retries=2,
        backoff_factor=0.5,
    )


def extract_article_urls_from_index(html: str, base_url: str = BLOG_URL) -> list[str]:
    """从 index 页面提取所有文章链接。"""
    # 从 __VP_HASH_MAP__ JavaScript 变量中提取页面列表
    # HTML 中是转义的 JSON: __VP_HASH_MAP__=JSON.parse("{\"key\":\"value\"}")
    # 使用非贪婪匹配
    pattern = r'__VP_HASH_MAP__\s*=\s*JSON\.parse\("(.+?)"\)'
    match = re.search(pattern, html)
    if not match:
        return []

    # JSON 字符串是转义的，需要解码
    json_str = match.group(1)
    # 解码 Unicode 转义
    json_str = json_str.encode().decode('unicode_escape')
    try:
        pages = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    urls = []
    for page_name in pages.keys():
        if page_name == "index.md":
            continue
        # 转换 .md 为 .html
        article_path = page_name.replace(".md", ".html")
        url = urljoin(base_url + "/", article_path)
        urls.append(url)

    return urls


def extract_article_item(url: str, html: str) -> Optional[dict]:
    """从文章页面提取 RSS 条目。"""
    soup = BeautifulSoup(html, "html.parser")

    # 获取标题
    title = None
    if title_tag := soup.find("title"):
        title = title_tag.get_text(strip=True)

    if not title:
        return None

    # 获取描述
    description = None
    if meta_desc := soup.find("meta", attrs={"name": "description"}):
        description = meta_desc.get("content", "").strip()

    # 尝试从内容中提取第一段作为描述
    if not description:
        # 查找第一个段落
        for p in soup.select("div.markdown p"):
            text = p.get_text(strip=True)
            if text and len(text) > 50:
                description = text[:500]  # 截取前500字符
                break

    item = {
        "title": title,
        "link": url,
    }

    if description:
        item["description"] = description

    return item


@register_job
class KimiBlogJob(FeedJob):
    job_type = "kimi_blog"

    def run(self, context: JobContext) -> JobResult:
        output_file = self.config.get("output", DEFAULT_OUTPUT)
        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger = logging.getLogger(__name__)

        session = create_session()
        logger.info(f"正在从 {BLOG_URL} 获取文章列表...")

        # 获取 index 页面
        try:
            response = session.get(BLOG_URL, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            return JobResult(name=self.name, success=False, details=f"抓取失败: {exc}")

        # 提取文章链接
        article_urls = extract_article_urls_from_index(response.text, BLOG_URL)
        if not article_urls:
            return JobResult(name=self.name, success=False, details="未找到任何文章链接")

        logger.info(f"找到 {len(article_urls)} 篇文章")

        # 抓取每篇文章
        items = []
        for idx, article_url in enumerate(article_urls, start=1):
            logger.info(f"解析文章 {idx}/{len(article_urls)}: {article_url}")
            try:
                resp = session.get(article_url, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
            except requests.RequestException as exc:
                logger.warning(f"抓取文章失败 {article_url}: {exc}")
                continue

            item = extract_article_item(article_url, resp.text)
            if item:
                items.append(item)
                logger.info(f"  - {item.get('title', 'N/A')[:50]}")

        if not items:
            return JobResult(name=self.name, success=False, details="未能解析任何文章")

        # 反转顺序，最新的在前
        items = list(reversed(items))

        generator = RSSGenerator(
            title=self.config.get("title", "Kimi Blog"),
            link=self.config.get("link", BLOG_URL),
            description=self.config.get("description", "Kimi Research Articles & Technical Blogs"),
        )
        generator.add_items(items)

        success = generator.generate(str(output_path))
        if not success:
            return JobResult(name=self.name, success=False, details="RSS 生成失败")

        logger.info(f"成功生成 {len(items)} 篇 Kimi Blog 到 {output_path}")
        return JobResult(name=self.name, success=True, details=f"输出: {output_path}")
