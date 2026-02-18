"""MiniMax Releases RSS 任务 - 整合 HuggingFace 模型发布与 GitHub 仓库."""

import logging
from typing import Optional

import requests

from src.http_client import create_retry_session
from src.path_utils import resolve_output_path
from src.rss_generator import RSSGenerator

from .base import FeedJob, JobContext, JobResult
from .registry import register_job

HF_API_BASE = "https://huggingface.co/api"
HF_ORG = "MiniMaxAI"
HF_ORG_URL = f"https://huggingface.co/{HF_ORG}"

GITHUB_API_BASE = "https://api.github.com"
GITHUB_ORG = "MiniMax-AI"
GITHUB_ORG_URL = f"https://github.com/{GITHUB_ORG}"

DEFAULT_OUTPUT = "minimax_releases.xml"
REQUEST_TIMEOUT = 20


# ---------------------------------------------------------------------------
# HuggingFace helpers
# ---------------------------------------------------------------------------

def _hf_session(retries: int, backoff_factor: float) -> requests.Session:
    return create_retry_session(
        accept="application/json",
        retries=retries,
        backoff_factor=backoff_factor,
    )


def _fetch_hf_resources(
    session: requests.Session,
    resource_type: str,
    max_items: int,
    logger: logging.Logger,
) -> list[dict]:
    url = f"{HF_API_BASE}/{resource_type}"
    params = {
        "author": HF_ORG,
        "sort": "createdAt",
        "direction": -1,
        "limit": max_items,
    }
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning(f"获取 HuggingFace {resource_type} 失败: {exc}")
        return []
    except ValueError as exc:
        logger.warning(f"解析 HuggingFace {resource_type} JSON 失败: {exc}")
        return []


def _hf_resource_to_item(resource: dict, resource_type: str) -> Optional[dict]:
    resource_id = resource.get("id", "")
    if not resource_id:
        return None

    name = resource_id.split("/")[-1] if "/" in resource_id else resource_id
    link = f"https://huggingface.co/{resource_id}"

    parts = [f"[HuggingFace {resource_type.rstrip('s').capitalize()}]"]
    if pipeline_tag := resource.get("pipeline_tag"):
        parts.append(pipeline_tag)
    if likes := resource.get("likes"):
        parts.append(f"Likes: {likes}")
    tags = resource.get("tags", [])
    if tags:
        parts.append(f"Tags: {', '.join(tags[:5])}")

    return {
        "title": name,
        "link": link,
        "guid": link,
        "pubDate": resource.get("createdAt"),
        "description": " | ".join(parts),
    }


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def _github_session(retries: int, backoff_factor: float) -> requests.Session:
    return create_retry_session(
        accept="application/vnd.github+json",
        retries=retries,
        backoff_factor=backoff_factor,
    )


def _fetch_github_repos(
    session: requests.Session,
    max_items: int,
    logger: logging.Logger,
) -> list[dict]:
    url = f"{GITHUB_API_BASE}/orgs/{GITHUB_ORG}/repos"
    params = {
        "sort": "created",
        "direction": "desc",
        "per_page": min(max_items, 100),
        "type": "public",
    }
    try:
        resp = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        logger.warning(f"获取 GitHub 仓库列表失败: {exc}")
        return []
    except ValueError as exc:
        logger.warning(f"解析 GitHub 仓库 JSON 失败: {exc}")
        return []


def _repo_to_item(repo: dict) -> Optional[dict]:
    name = repo.get("name", "")
    html_url = repo.get("html_url", "")
    if not name or not html_url:
        return None

    parts = ["[GitHub Repo]"]
    if desc := repo.get("description"):
        parts.append(desc)
    if language := repo.get("language"):
        parts.append(f"Language: {language}")
    if stars := repo.get("stargazers_count"):
        parts.append(f"Stars: {stars}")
    topics = repo.get("topics", [])
    if topics:
        parts.append(f"Topics: {', '.join(topics)}")

    return {
        "title": name,
        "link": html_url,
        "guid": html_url,
        "pubDate": repo.get("created_at"),
        "description": " | ".join(parts),
    }


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

@register_job
class MiniMaxReleasesJob(FeedJob):
    job_type = "minimax_releases"

    def run(self, context: JobContext) -> JobResult:
        output_file = self.config.get("output", DEFAULT_OUTPUT)
        output_path = resolve_output_path(context.feeds_dir, output_file)
        logger = logging.getLogger(__name__)

        options = self.config.get("options", {})
        max_items = int(options.get("max_items", 50))
        resource_types = options.get("resource_types", ["models"])
        retries = int(options.get("retries", 2))
        backoff_factor = float(options.get("backoff_factor", 0.5))

        items: list[dict] = []

        # --- HuggingFace ---
        hf_session = _hf_session(retries, backoff_factor)
        for resource_type in resource_types:
            logger.info(f"从 HuggingFace 获取 {HF_ORG} 的 {resource_type}...")
            resources = _fetch_hf_resources(hf_session, resource_type, max_items, logger)
            logger.info(f"  获取到 {len(resources)} 条 {resource_type}")
            for resource in resources:
                item = _hf_resource_to_item(resource, resource_type)
                if item:
                    items.append(item)

        # --- GitHub ---
        gh_session = _github_session(retries, backoff_factor)
        logger.info(f"从 GitHub 获取 {GITHUB_ORG} 的公开仓库...")
        repos = _fetch_github_repos(gh_session, max_items, logger)
        logger.info(f"获取到 {len(repos)} 个仓库")
        for repo in repos:
            item = _repo_to_item(repo)
            if item:
                items.append(item)

        if not items:
            return JobResult(
                name=self.name,
                success=False,
                details="未获取到任何 MiniMax 发布内容",
            )

        # Sort all items by pubDate descending, items without date go last
        items.sort(key=lambda x: x.get("pubDate") or "", reverse=True)
        items = items[:max_items]

        generator = RSSGenerator(
            title=self.config.get("title", "MiniMax Releases"),
            link=self.config.get("link", HF_ORG_URL),
            description=self.config.get(
                "description",
                "MiniMax model releases on HuggingFace and new GitHub repositories",
            ),
        )
        generator.add_items(items)

        success = generator.generate(str(output_path))
        if not success:
            return JobResult(name=self.name, success=False, details="RSS 生成失败")

        logger.info(f"成功生成 {len(items)} 条 MiniMax Releases 到 {output_path}")
        return JobResult(name=self.name, success=True, details=f"输出: {output_path}")
