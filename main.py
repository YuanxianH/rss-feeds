#!/usr/bin/env python3
"""RSS Creator - 主程序入口"""

import argparse
import logging
import sys
import time
from typing import Sequence

import schedule
import yaml

from src.jobs import JobRunner
from src.runtime import setup_logging


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def _run_jobs(config: dict, feeds_dir: str) -> dict[str, bool]:
    jobs_config = config.get("jobs", [])
    if not jobs_config:
        return {}

    enabled_jobs = [job for job in jobs_config if job.get("enabled", True)]
    if not enabled_jobs:
        logging.info("配置中的 jobs 均为禁用状态")
        return {}

    logging.info(f"开始执行 {len(enabled_jobs)} 个 jobs")
    runner = JobRunner(feeds_dir=feeds_dir)
    return runner.run_jobs(enabled_jobs)


def run_once(config: dict, feeds_dir: str) -> bool:
    """运行一次 RSS 生成"""
    results = _run_jobs(config, feeds_dir)

    if not results:
        logging.warning("配置文件中没有定义任何可执行任务")
        return False

    failed_tasks = [name for name, success in results.items() if not success]
    if failed_tasks:
        logging.error(f"以下任务失败: {', '.join(failed_tasks)}")
        return False

    return True


def run_scheduler(config: dict, feeds_dir: str) -> int:
    """运行定时任务"""
    update_config = config.get("update", {})
    interval = update_config.get("interval", 3600)

    logging.info(f"定时任务已启动，每 {interval} 秒更新一次")

    # 立即执行一次
    if not run_once(config, feeds_dir):
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

    return 0 if run_once(config, args.output) else 1


if __name__ == "__main__":
    sys.exit(main())
