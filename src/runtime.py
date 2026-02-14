"""Runtime helpers shared by CLI entrypoints and jobs."""

import logging

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(verbose: bool = False):
    """Configure process-wide logging with a consistent format."""
    level = logging.DEBUG if verbose else logging.INFO
    root_logger = logging.getLogger()

    if root_logger.handlers:
        root_logger.setLevel(level)
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        for handler in root_logger.handlers:
            handler.setFormatter(formatter)
        return

    logging.basicConfig(level=level, format=LOG_FORMAT, datefmt=DATE_FORMAT)
