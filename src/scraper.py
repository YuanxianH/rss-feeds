"""网页抓取模块"""

import requests
from typing import Optional
import logging
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class WebScraper:
    """网页抓取器"""

    def __init__(
        self,
        timeout: int = 10,
        user_agent: Optional[str] = None,
        retries: int = 2,
        backoff_factor: float = 0.5,
    ):
        """
        初始化抓取器

        Args:
            timeout: 请求超时时间（秒）
            user_agent: 自定义 User-Agent
            retries: 网络失败重试次数
            backoff_factor: 退避系数
        """
        self.timeout = timeout
        self.headers = {
            "User-Agent": user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        retry_policy = Retry(
            total=retries,
            connect=retries,
            read=retries,
            status=retries,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "HEAD"]),
            backoff_factor=backoff_factor,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry_policy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def fetch(self, url: str, encoding: Optional[str] = None) -> Optional[str]:
        """
        抓取网页内容

        Args:
            url: 目标 URL
            encoding: 页面编码

        Returns:
            网页 HTML 内容，失败返回 None
        """
        try:
            logger.info(f"正在抓取: {url}")
            response = self.session.get(
                url,
                timeout=self.timeout
            )
            response.raise_for_status()

            if encoding:
                response.encoding = encoding

            logger.info(f"成功抓取: {url} (状态码: {response.status_code})")
            return response.text

        except requests.RequestException as e:
            logger.error(f"抓取失败 {url}: {e}")
            return None
