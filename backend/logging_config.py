import logging.config
import os
import sys
from datetime import datetime


def apply(level=os.environ.get("LOGLEVEL", "INFO")) -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "loggers": {
                "": {"level": "INFO", "handlers": ["default"]},
                "youmood": {"level": level, "handlers": ["default"], "propagate": False},
            },
            "handlers": {
                "default": {"class": "logging.StreamHandler", "formatter": "default", "stream": sys.stdout},
            },
            "formatters": {
                "default": {
                    "class": "logging_config.MultiLineFormatter",
                    "format": f"%(asctime)s %(levelname)s %(name)s %(message)s",
                },
            },
        }
    )


class MultiLineFormatter(logging.Formatter):
    def format(self, record):
        return super().format(record).lstrip().replace("\n", "\n\t")

    def formatTime(self, record, datefmt=None):
        dt = datetime.utcfromtimestamp(record.created)
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.{int(record.msecs):03d}Z")
