import logging
import sys

from .config import AppSettings

logger = logging.getLogger(__name__)


def setup_logging(settings: AppSettings):
    """Configures logging based on AppSettings."""
    if settings.debug:
        # Debug mode: hardcode levels, ignore config
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=sys.stdout,
        )
        # Set bleak to INFO to reduce noise
        logging.getLogger("bleak").setLevel(logging.INFO)
        logger.info("Debug mode enabled. Root logger set to DEBUG, bleak set to INFO.")
        return

    # Normal mode: use config file
    log_settings = settings.logging
    level = log_settings.level
    fmt = log_settings.format

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format=fmt,
        stream=sys.stdout,
    )

    # Apply specific logger levels from config
    for logger_name, logger_level in log_settings.loggers.items():
        logging.getLogger(logger_name).setLevel(
            getattr(logging, logger_level.upper(), logging.INFO)
        )

    logger.info(f"Logging configured with level {level}")
