import sys
import re
from loguru import logger
from app.config.settings import settings

# Filter out sensitive information from logs
SENSITIVE_PATTERNS = [
    r'(token=)[^&\s]+',
    r'(password=)[^&\s]+',
    r'(api_key=)[^&\s]+',
    r'(\b\d{9,10}:[A-Za-z0-9_-]{35}\b)',  # Telegram Bot Token format
]

def mask_sensitive(record):
    msg = record["message"]
    for pattern in SENSITIVE_PATTERNS:
        msg = re.sub(pattern, r'\1***MASKED***' if '=' in pattern else '***TOKEN_MASKED***', msg)
    record["message"] = msg
    return True

logger.remove()
log_level = "DEBUG" if settings.DEBUG else "INFO"

logger.add(
    sys.stdout,
    level=log_level,
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    filter=mask_sensitive
)

logger.add(
    "logs/mtk_bot_{time:YYYY-MM-DD}.log",
    rotation="50 MB",
    retention="30 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    filter=mask_sensitive
)

__all__ = ["logger"]
