import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="[%(asctime)s] %(levelname)s <%(module)s:%(funcName)s:%(lineno)d> %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
