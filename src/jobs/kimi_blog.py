"""Backward-compatible Kimi job backed by the generic dynamic-site crawler."""

from __future__ import annotations

from .dynamic_site import DynamicSiteJob
from .registry import register_job

KIMI_BLOG_URL = "https://www.kimi.ai/blog/"


@register_job
class KimiBlogJob(DynamicSiteJob):
    """Compatibility adapter for existing ``type: kimi_blog`` configs."""

    job_type = "kimi_blog"

    def __init__(self, config: dict):
        merged = {
            "url": KIMI_BLOG_URL,
            "link": KIMI_BLOG_URL,
            "path_prefix": "/blog",
            "allowed_hosts": ["kimi.ai"],
            "output": "kimi_blog.xml",
            **config,
        }
        super().__init__(merged)
