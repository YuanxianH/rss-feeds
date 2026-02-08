#!/usr/bin/env python3
"""RSS Creator - 主程序入口"""

import yaml
import logging
import argparse
import time
import schedule
from pathlib import Path

from src.feed_creator import FeedCreator


def setup_logging(verbose: bool = False):
    """配置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def load_config(config_path: str = "config.yaml") -> dict:
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_once(config: dict, feeds_dir: str):
    """运行一次 RSS 生成"""
    creator = FeedCreator(feeds_dir=feeds_dir)
    feeds_config = config.get("feeds", [])

    if not feeds_config:
        logging.warning("配置文件中没有定义任何 feeds")
        return

    logging.info(f"开始生成 {len(feeds_config)} 个 RSS feeds")
    creator.create_all_feeds(feeds_config)


def run_scheduler(config: dict, feeds_dir: str):
    """运行定时任务"""
    update_config = config.get("update", {})
    interval = update_config.get("interval", 3600)

    logging.info(f"定时任务已启动，每 {interval} 秒更新一次")

    # 立即执行一次
    run_once(config, feeds_dir)

    # 设置定时任务
    schedule.every(interval).seconds.do(run_once, config, feeds_dir)

    # 运行循环
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("定时任务已停止")


def main():
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

    args = parser.parse_args()

    # 配置日志
    setup_logging(args.verbose)

    # 加载配置
    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logging.error(f"配置文件不存在: {args.config}")
        return
    except yaml.YAMLError as e:
        logging.error(f"配置文件格式错误: {e}")
        return

    # 运行
    if args.schedule or config.get("update", {}).get("enabled", False):
        run_scheduler(config, args.output)
    else:
        run_once(config, args.output)


if __name__ == "__main__":
    main()
