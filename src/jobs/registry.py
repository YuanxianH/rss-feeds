"""Registry for config-driven feed jobs."""

from typing import Type

from .base import FeedJob

_REGISTRY: dict[str, Type[FeedJob]] = {}


def register_job(job_cls: Type[FeedJob]) -> Type[FeedJob]:
    job_type = getattr(job_cls, "job_type", "")
    if not job_type:
        raise ValueError(f"{job_cls.__name__} 必须定义 job_type")
    _REGISTRY[job_type] = job_cls
    return job_cls


def create_job(config: dict) -> FeedJob:
    job_type = config.get("type")
    if not job_type:
        raise ValueError("job 配置缺少 type")

    job_cls = _REGISTRY.get(job_type)
    if not job_cls:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(f"未知 job type: {job_type}（可选: {available or '无'}）")
    return job_cls(config)


def list_job_types() -> list[str]:
    return sorted(_REGISTRY.keys())
