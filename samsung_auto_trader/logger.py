import logging
import sys


def setup_logger() -> None:
    logger = logging.getLogger("samsung_auto_trader")
    if logger.handlers:
        return

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(handler)
    logger.propagate = False


def get_logger() -> logging.Logger:
    logger = logging.getLogger("samsung_auto_trader")
    if not logger.handlers:
        setup_logger()
    return logger
