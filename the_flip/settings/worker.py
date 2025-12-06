"""Worker service production settings."""

from .prod_base import *  # noqa
from decouple import config  # noqa: F401
from .base import LOGGING, APP_LOG_LEVEL, DJANGO_LOG_LEVEL, LOG_LEVEL  # noqa: F401

# Worker-specific logging levels (overrides APP_LOG_LEVEL/LOG_LEVEL)
LOGGING["loggers"]["the_flip"]["level"] = config(  # type: ignore[name-defined, index]
    "WORKER_LOG_LEVEL",
    default=APP_LOG_LEVEL,  # noqa: F405
).upper()
LOGGING["root"]["level"] = config("WORKER_ROOT_LOG_LEVEL", default=LOG_LEVEL).upper()  # type: ignore[name-defined, index]  # noqa: F405
LOGGING["loggers"]["django_q"]["level"] = config(  # type: ignore[name-defined, index]
    "WORKER_DJANGO_Q_LOG_LEVEL",
    default=DJANGO_LOG_LEVEL,  # noqa: F405
).upper()
