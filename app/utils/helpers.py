import re
import secrets
import string
from datetime import datetime
from typing import Optional


def format_vnd(amount: int | float) -> str:
    """Format integer amount to VND format: 100000 -> 100.000 đ"""
    try:
        val = int(amount)
        return f"{val:,}".replace(",", ".") + " đ"
    except Exception:
        return f"{amount} đ"


def generate_order_code() -> str:
    """Generate unique readable order code, e.g., DH2610-8A7B"""
    chars = string.ascii_uppercase + string.digits
    rand = ''.join(secrets.choice(chars) for _ in range(5))
    timestamp = datetime.now().strftime("%d%H%M")
    return f"DH{timestamp}{rand}"


def generate_deposit_code(telegram_id: int) -> str:
    """Generate deposit transfer code e.g. NAP123456ABC"""
    chars = string.ascii_uppercase + string.digits
    rand = ''.join(secrets.choice(chars) for _ in range(3))
    return f"NAP{telegram_id}{rand}"


def parse_order_code_from_content(content: str) -> Optional[str]:
    """
    Search for order code in transfer content string.
    Patterns matched: DH123456789 or DH[A-Z0-9]+
    """
    if not content:
        return None
    # Look for DH followed by letters/digits, uppercase or lowercase
    match = re.search(r'\b(DH[A-Za-z0-9_]{6,16})\b', content, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def parse_deposit_code_from_content(content: str) -> Optional[tuple[int, str]]:
    """
    Search for deposit code in transfer content string.
    Pattern: NAP<telegram_id><random_suffix>
    Returns (telegram_id, full_code) or None.
    """
    if not content:
        return None
    match = re.search(r'\bNAP(\d{6,14})([A-Za-z0-9]{2,5})?\b', content, re.IGNORECASE)
    if match:
        telegram_id = int(match.group(1))
        full_code = match.group(0).upper()
        return (telegram_id, full_code)
    return None


def mask_key(key: str, visible_chars: int = 4) -> str:
    """Mask key for safe preview, e.g. ABCD-****-****-WXYZ"""
    if len(key) <= visible_chars * 2:
        return "****"
    return f"{key[:visible_chars]}...{key[-visible_chars:]}"
