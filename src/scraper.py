"""网页抓取模块"""

import time
import requests
from typing import Optional
import logging

from .http_client import create_retry_session

logger = logging.getLogger(__name__)


def impersonated_get(url: str, *, impersonate: str, timeout: int):
    """GET a URL with curl_cffi browser impersonation.

    x.ai and similar Cloudflare sites reject the TLS fingerprint of plain
    ``requests``. Chrome impersonation matches the hourly workflow, which only
    installs ``requirements.txt`` and does not run a browser.
    """
    from curl_cffi import requests as curl_requests

    return curl_requests.get(url, impersonate=impersonate, timeout=timeout)


class WebScraper:
    """网页抓取器"""

    def __init__(
        self,
        timeout: int = 10,
        user_agent: Optional[str] = None,
        retries: int = 2,
        backoff_factor: float = 0.5,
        impersonate: Optional[str] = None,
    ):
        """
        初始化抓取器

        Args:
            timeout: 请求超时时间（秒）
            user_agent: 自定义 User-Agent
            retries: 网络失败重试次数
            backoff_factor: 退避系数
            impersonate: curl_cffi 浏览器模拟标识，例如 ``chrome``。
                设置后不再使用 requests。
        """
        self.timeout = timeout
        self.retries = retries
        self.backoff_factor = backoff_factor
        self.impersonate = impersonate or None
        self.session = create_retry_session(
            user_agent=user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            retries=retries,
            backoff_factor=backoff_factor,
        )
        self.headers = dict(self.session.headers)

    def fetch(self, url: str, encoding: Optional[str] = None) -> Optional[str]:
        """
        抓取网页内容

        Args:
            url: 目标 URL
            encoding: 页面编码

        Returns:
            网页 HTML 内容，失败返回 None
        """
        if self.impersonate:
            return self._fetch_impersonated(url, encoding)

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

    def _fetch_impersonated(self, url: str, encoding: Optional[str]) -> Optional[str]:
        attempts = max(int(self.retries), 0) + 1
        for attempt in range(1, attempts + 1):
            try:
                logger.info(f"正在抓取: {url} (impersonate={self.impersonate})")
                response = impersonated_get(
                    url,
                    impersonate=str(self.impersonate),
                    timeout=self.timeout,
                )
                response.raise_for_status()
                if encoding:
                    response.encoding = encoding
                logger.info(f"成功抓取: {url} (状态码: {response.status_code})")
                return response.text
            except ImportError:
                logger.error("curl_cffi 未安装，无法模拟浏览器抓取 %s", url)
                return None
            except Exception as exc:
                logger.warning(
                    "抓取失败 %s (第 %s/%s 次): %s",
                    url,
                    attempt,
                    attempts,
                    exc,
                )
                if attempt >= attempts:
                    logger.error(f"抓取失败 {url}: {exc}")
                    return None
                delay = self.backoff_factor * (2 ** (attempt - 1))
                if delay > 0:
                    time.sleep(delay)
        return None
