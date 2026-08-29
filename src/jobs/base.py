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


@dataclass(frozen=True)
class JobRunReport:
    """Aggregate result for one pass over the configured jobs."""

    results: dict[str, JobResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> tuple[JobResult, ...]:
        return tuple(result for result in self.results.values() if result.success)

    @property
    def failed(self) -> tuple[JobResult, ...]:
        return tuple(result for result in self.results.values() if not result.success)

    @property
    def any_succeeded(self) -> bool:
        return bool(self.succeeded)

    @property
    def all_succeeded(self) -> bool:
        return self.total > 0 and not self.failed


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
