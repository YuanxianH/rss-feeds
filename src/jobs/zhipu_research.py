"""Backward-compatible Zhipu job backed by the generic dynamic-site crawler."""

from __future__ import annotations

from .dynamic_site import DynamicSiteJob
from .registry import register_job

ZHIPU_RESEARCH_URL = "https://www.zhipuai.cn/zh/research"
ZHIPU_API_URL = "https://www.zhipuai.cn/api/articles"
DEFAULT_ARTICLE_BASE_URL = ZHIPU_RESEARCH_URL


@register_job
class ZhipuResearchJob(DynamicSiteJob):
    """Compatibility adapter for existing ``type: zhipu_research`` configs."""

    job_type = "zhipu_research"

    def __init__(self, config: dict):
        incoming_options = dict(config.get("options") or {})
        merged = {
            "url": ZHIPU_RESEARCH_URL,
            "link": ZHIPU_RESEARCH_URL,
            "path_prefix": "/zh/research",
            "allowed_hosts": ["zhipuai.cn"],
            "api_urls": [str(config.get("api_url") or ZHIPU_API_URL)],
            "article_base_url": ZHIPU_RESEARCH_URL,
            "category": "blog",
            "locale": "zh",
            "output": "zhipu_research.xml",
            **config,
        }
        if not merged.get("api_urls"):
            merged["api_urls"] = [ZHIPU_API_URL]
        merged["options"] = {
            "require_active": True,
            "minimum_items": 1,
            **incoming_options,
        }
        super().__init__(merged)
