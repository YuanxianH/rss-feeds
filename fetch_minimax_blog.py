#!/usr/bin/env python3
"""从 MiniMax Tech Blog 获取文章并生成 RSS"""

import logging
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
from src.rss_generator import RSSGenerator

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_article_date(url, session):
    """从文章页面提取日期"""
    try:
        resp = session.get(url, timeout=30)
        soup = BeautifulSoup(resp.text, 'html.parser')

        # 方法1: 查找包含日期的 div (class 包含 text-brand-1)
        date_divs = soup.find_all('div', class_=lambda x: x and 'text-brand-1' in x if x else False)
        for div in date_divs:
            text = div.get_text(strip=True)
            # 检查是否是日期格式 (2026.2.12)
            if re.match(r'\d{4}\.\d{1,2}\.\d{1,2}', text):
                return text

        # 方法2: 在文本中查找日期模式
        text = soup.get_text()
        dates = re.findall(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
        if dates:
            return dates[0]

        return None
    except Exception as e:
        logging.warning(f"获取文章日期失败 {url}: {e}")
        return None


def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    # 从多个页面抓取文章
    pages = [
        "https://www.minimax.io/",
        "https://www.minimax.io/news",
        "https://www.minimax.io/blog",
    ]

    output_dir = Path("feeds")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "minimax_blog.xml"

    logger.info("正在从 MiniMax 网站获取所有文章...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    session = requests.Session()
    session.headers.update(headers)

    # 从所有页面收集文章链接 - 先收集所有 URL
    all_urls = set()

    for page_url in pages:
        logger.info(f"正在抓取页面: {page_url}")
        try:
            resp = session.get(page_url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')

            # 查找所有包含 /news/ 的链接
            links = soup.find_all('a', href=True)
            for link in links:
                href = link.get('href', '')
                if '/news/' in href:
                    # 清理 URL
                    if href.startswith('/'):
                        href = f"https://www.minimax.io{href}"
                    if 'minimax.io/news/' in href:
                        all_urls.add(href)
        except Exception as e:
            logger.warning(f"抓取页面失败 {page_url}: {e}")

    # 从 URL 提取标题
    articles = []
    for url in all_urls:
        # 从 URL 提取产品名作为标题
        import re
        match = re.search(r'news/([^/]+)$', url)
        if match:
            slug = match.group(1)
            title = slug.replace('-', ' ').title()
            # 修复一些常见的产品名
            title = title.replace('M21', 'M2.1')
            title = title.replace('M25', 'M2.5')
            title = title.replace('M20', 'M2.0')
            title = title.replace('M2 Her', 'M2-her')
            title = title.replace('Speech 26', 'Speech 2.6')
            title = title.replace('Hailuo 23', 'Hailuo 2.3')
            title = title.replace('Music 25', 'Music 2.5')
            title = title.replace('Music 20', 'Music 2.0')
            title = title.replace('Mcp', 'MCP')
            articles.append({'url': url, 'title': title})

    logger.info(f"找到 {len(articles)} 篇文章")

    # 获取每篇文章的日期
    items = []
    for i, article in enumerate(articles[:20]):  # 限制数量
        logger.info(f"获取文章 {i+1}/{min(len(articles), 20)}: {article['title'][:40]}")
        date = get_article_date(article['url'], session)
        if date:
            # 转换日期格式
            try:
                from datetime import datetime
                dt = datetime.strptime(date, '%Y.%m.%d')
                pub_date = dt.strftime('%a, %d %b %Y %H:%M:%S GMT')
            except:
                pub_date = date
        else:
            pub_date = None

        items.append({
            'title': article['title'],
            'link': article['url'],
            'description': '',
            'pubDate': pub_date,
        })

    if not items:
        logger.warning("未找到任何文章")
        return

    generator = RSSGenerator(
        title="MiniMax News",
        link="https://www.minimax.io/news",
        description="Latest news and updates from MiniMax AI",
    )
    generator.add_items(items)

    if generator.generate(str(output_path)):
        logger.info(f"成功生成 {len(items)} 篇文章到 {output_path}")
    else:
        logger.error("RSS 生成失败")


if __name__ == "__main__":
    main()
