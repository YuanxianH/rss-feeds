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
        resp = session.get(url, timeout=15)
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

    blog_url = "https://www.minimax.io/blog"
    output_dir = Path("feeds")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "minimax_blog.xml"

    logger.info("正在从 MiniMax Tech Blog 获取文章...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    session = requests.Session()
    session.headers.update(headers)

    # 获取博客页面
    resp = session.get(blog_url, timeout=15)
    soup = BeautifulSoup(resp.text, 'html.parser')

    # 找到所有文章链接
    articles = []
    seen_urls = set()

    # 查找 li 元素中的链接 - 更精确的选择
    lis = soup.find_all('li')
    for li in lis:
        links = li.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if '/news/' in href and href not in seen_urls:
                # 清理 URL
                if href.startswith('/'):
                    href = f"https://www.minimax.io{href}"
                if href not in seen_urls and 'minimax.io/news/' in href:
                    seen_urls.add(href)
                    # 获取更干净的标题 - 在 li 中查找非 "Learn More" 的文本
                    title = link.get_text(strip=True)
                    # 如果标题是 "Learn More"，尝试从父元素获取
                    if title == "Learn More" or not title:
                        # 查找同级的图片或标题元素
                        parent = link.find_parent('li')
                        if parent:
                            # 获取标题文本（排除按钮文字）
                            texts = parent.find_all(string=True)
                            for t in texts:
                                text = t.strip()
                                if text and text != "Learn More" and len(text) > 3:
                                    title = text
                                    break
                    if title and len(title) > 2 and title != "Learn More":
                        articles.append({'url': href, 'title': title})

    logger.info(f"找到 {len(articles)} 篇文章")

    # 获取每篇文章的日期
    items = []
    for i, article in enumerate(articles[:20]):  # 限制数量
        logger.info(f"获取文章 {i+1}/{min(len(articles), 20)}: {article['title'][:30]}")
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
        title="MiniMax Tech Blog",
        link="https://www.minimax.io/blog",
        description="Latest updates and announcements from MiniMax AI",
    )
    generator.add_items(items)

    if generator.generate(str(output_path)):
        logger.info(f"成功生成 {len(items)} 篇文章到 {output_path}")
    else:
        logger.error("RSS 生成失败")


if __name__ == "__main__":
    main()
