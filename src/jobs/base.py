"""Base definitions for feed jobs."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class JobContext:
    feeds_dir: Path


@dataclass
class JobResult:
    name: str
    success: bool
    details: str = ""


class FeedJob:
    """Config-driven job interface."""

    job_type = ""

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @property
    def name(self) -> str:
        return str(self.config.get("name") or self.job_type)

    def run(self, context: JobContext) -> JobResult:
        raise NotImplementedError
