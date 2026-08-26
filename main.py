#!/usr/bin/env python3
"""RSS Creator - 主程序入口"""

import argparse
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import sys
import time
from typing import Sequence

import schedule
import yaml

from src.jobs import JobRunner
from src.jobs.base import JobRunReport
from src.runtime import setup_logging
from src.site_index import generate_site_index


@dataclass(frozen=True)
class RunReport:
    """Result of generating jobs and the static directory page."""

    jobs: JobRunReport
    index_generated: bool
    index_error: str = ""

    def is_success(self, *, allow_partial: bool = False) -> bool:
        if not self.index_generated:
            return False
        if allow_partial:
            return self.jobs.any_succeeded
        return self.jobs.all_succeeded

    def __bool__(self) -> bool:
        return self.is_success()


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _run_jobs(config: dict, feeds_dir: str) -> JobRunReport:
    jobs_config = config.get("jobs", [])
    if not jobs_config:
        return JobRunReport(results={})

    enabled_jobs = [job for job in jobs_config if job.get("enabled", True)]
    if not enabled_jobs:
        logging.info("配置中的 jobs 均为禁用状态")
        return JobRunReport(results={})

    logging.info(f"开始执行 {len(enabled_jobs)} 个 jobs")
    runner = JobRunner(feeds_dir=feeds_dir)
    return runner.run_jobs(enabled_jobs)


def run_once(config: dict, feeds_dir: str) -> RunReport:
    """运行一次 RSS 生成"""
    jobs = _run_jobs(config, feeds_dir)
    index_generated = True
    index_error = ""
    try:
        generate_site_index(config, feeds_dir)
    except Exception as exc:
        index_generated = False
        index_error = str(exc)
        logging.error("生成部署首页失败: %s", exc)

    if not jobs.total:
        logging.warning("配置文件中没有定义任何可执行任务")
    elif jobs.failed:
        logging.error("以下任务失败: %s", ", ".join(result.name for result in jobs.failed))

    return RunReport(
        jobs=jobs,
        index_generated=index_generated,
        index_error=index_error,
    )


def _write_github_summary(report: RunReport, config: dict, feeds_dir: str) -> None:
    """Write a concise per-feed report when running in GitHub Actions."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    outputs = {
        str(job.get("name") or job.get("type") or ""): str(job.get("output") or "")
        for job in config.get("jobs", [])
        if job.get("enabled", True)
    }
    rows = [
        "## RSS update",
        "",
        "| Feed | Update | Published output | Details |",
        "| --- | --- | --- | --- |",
    ]
    feeds_path = Path(feeds_dir)
    for result in report.jobs.results.values():
        output = outputs.get(result.name, "")
        output_exists = bool(output and (feeds_path / output).exists())
        update = "Updated" if result.success else "Failed"
        published = "Current" if result.success else ("Previous kept" if output_exists else "Unavailable")
        details = result.details or "—"
        cells = (result.name, update, published, details)
        escaped = [str(cell).replace("|", "\\|").replace("\n", " ") for cell in cells]
        rows.append("| " + " | ".join(escaped) + " |")

    overall = (
        "complete"
        if report.is_success()
        else "partial"
        if report.is_success(allow_partial=True)
        else "failed"
    )
    rows.extend(
        [
            "",
            f"Result: **{overall}** · {len(report.jobs.succeeded)}/{report.jobs.total} feeds updated.",
        ]
    )
    if report.index_error:
        rows.append(f"Landing page failed: `{report.index_error}`")

    with open(summary_path, "a", encoding="utf-8") as summary:
        summary.write("\n".join(rows) + "\n")


def run_scheduler(config: dict, feeds_dir: str) -> int:
    """运行定时任务"""
    update_config = config.get("update", {})
    interval = update_config.get("interval", 3600)

    logging.info(f"定时任务已启动，每 {interval} 秒更新一次")

    # 立即执行一次
    if not run_once(config, feeds_dir).is_success():
        logging.error("首次执行存在失败，调度器将继续运行并在下次重试")

    # 设置定时任务
    schedule.every(interval).seconds.do(run_once, config, feeds_dir)

    # 运行循环
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("定时任务已停止")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """主函数"""
    parser = argparse.ArgumentParser(description="RSS Creator - 为任何网站生成 RSS feed")
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="配置文件路径 (默认: config.yaml)"
    )
    parser.add_argument(
        "-o", "--output",
        default="feeds",
        help="RSS 文件输出目录 (默认: feeds)"
    )
    parser.add_argument(
        "-s", "--schedule",
        action="store_true",
        help="启用定时更新"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细日志"
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="至少一个 feed 更新成功时返回成功（用于保留旧 feed 的自动发布）",
    )

    args = parser.parse_args(argv)

    setup_logging(args.verbose)

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logging.error(f"配置文件不存在: {args.config}")
        return 2
    except yaml.YAMLError as exc:
        logging.error(f"配置文件格式错误: {exc}")
        return 2

    if args.schedule or config.get("update", {}).get("enabled", False):
        return run_scheduler(config, args.output)

    report = run_once(config, args.output)
    _write_github_summary(report, config, args.output)
    return 0 if report.is_success(allow_partial=args.allow_partial) else 1


if __name__ == "__main__":
    sys.exit(main())
