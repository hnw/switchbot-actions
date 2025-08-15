import logging
import sys

from .config import LoggingSettings

logger = logging.getLogger(__name__)


def setup_logging(settings: LoggingSettings):
    """Configures logging based on LoggingSettings."""
    log_format = settings.format
    stream = sys.stdout

    level = settings.level

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=log_format,
        stream=stream,
    )

    # Apply specific logger levels from config
    for logger_name, logger_level in settings.loggers.items():
        logging.getLogger(logger_name).setLevel(
            getattr(logging, logger_level.upper(), logging.INFO)
        )

    logger.info(f"Logging configured with level {level} from config.")


def get_logger(name: str) -> logging.Logger:
    """Returns a logger with the specified name."""
    return logging.getLogger(name)
