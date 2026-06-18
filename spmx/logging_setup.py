"""Logging setup for spmx."""

import logging
import sys


class Colors:
    """ANSI color codes for terminal output."""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colored log levels."""

    COLORS = {
        'DEBUG': Colors.BLUE,
        'INFO': Colors.GREEN,
        'WARNING': Colors.YELLOW,
        'ERROR': Colors.RED,
        'CRITICAL': Colors.RED,
    }

    def format(self, record):
        """Format log record with colors."""
        levelname = record.levelname
        color = self.COLORS.get(levelname, Colors.END)
        record.levelname = f'{color}{levelname}{Colors.END}'
        return super().format(record)


def setup_logging(debug: bool = False) -> logging.Logger:
    """Configure and return the root logger for the pipeline.

    Parameters
    ----------
    debug : bool
        If True, set level to DEBUG; otherwise INFO.

    Returns
    -------
    logging.Logger
    """
    level = logging.DEBUG if debug else logging.INFO
    fmt = '[%(levelname)-7s] %(name)s | %(message)s'

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ColoredFormatter(fmt))

    logger = logging.getLogger('spmx')
    logger.setLevel(level)
    if not logger.handlers:
        logger.addHandler(handler)

    return logger


def get_file_handler(log_path):
    """Return a file handler that captures all output (DEBUG level).

    Parameters
    ----------
    log_path : pathlib.Path
        Path to the log file.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(log_path, mode='w')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter('%(asctime)s [%(levelname)-7s] %(name)s | %(message)s')
    )
    return fh
