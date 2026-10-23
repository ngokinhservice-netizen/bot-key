import urllib.parse
from typing import Optional, Dict, Any
import aiohttp
import pymupdf
from app.config.settings import settings
from app.utils.logger import logger


class SePayGateway:
    @staticmethod
    def generate_vietqr_url(
        amount: int,
        content: str,
        bank_name: Optional[str] = None,
        account_number: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> str:
        """
        Generate a VietQR payment QR code image URL compatible with SePay / VietQR.
        """
        bank = bank_name or settings.SEPAY_BANK_NAME
        acc = account_number or settings.SEPAY_BANK_ACCOUNT
        acc_name = account_name or settings.SEPAY_ACCOUNT_NAME

        # URL encode parameters
        encoded_content = urllib.parse.quote(content)
        encoded_name = urllib.parse.quote(acc_name)

        # Standard VietQR image URL with bank, account, amount, and content
        # VietQR template 'compact2' is modern and clear
        url = (
            f"https://img.vietqr.io/image/{bank}-{acc}-compact2.png"
            f"?amount={int(amount)}&addInfo={encoded_content}&accountName={encoded_name}"
        )
        return url

    @staticmethod
    async def get_vietqr_image_bytes(
        amount: int,
        content: str,
        bank_name: Optional[str] = None,
        account_number: Optional[str] = None,
        account_name: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Fetch VietQR image and convert to PNG bytes for direct Telegram photo rendering.
        img.vietqr.io returns SVG which Telegram photo API rejects, so we rasterize SVG -> PNG.
        """
        url = SePayGateway.generate_vietqr_url(
            amount=amount,
            content=content,
            bank_name=bank_name,
            account_number=account_number,
            account_name=account_name,
        )
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if data.startswith(b"\x89PNG"):
                            return data
                        # Rasterize SVG to PNG using pymupdf
                        doc = pymupdf.open(stream=data, filetype="svg")
                        pix = doc[0].get_pixmap(dpi=150)
                        return pix.tobytes("png")
                    else:
                        logger.error(f"VietQR service returned HTTP {resp.status}")
        except Exception as e:
            logger.error(f"Error fetching/converting VietQR image: {e}")
        return None

    @staticmethod
    def verify_webhook_auth(auth_header: Optional[str], query_api_key: Optional[str] = None) -> bool:
        """
        Authenticate incoming webhook request.
        SePay typically sends header: `Authorization: Apikey <SEPAY_API_KEY>`
        or query parameter api_key.
        """
        if not settings.SEPAY_API_KEY:
            logger.warning("SEPAY_API_KEY is not configured in environment!")
            return False

        # 1. Check Authorization header
        if auth_header:
            parts = auth_header.strip().split()
            if len(parts) == 2 and parts[0].lower() in ["apikey", "bearer"]:
                token = parts[1]
                if token == settings.SEPAY_API_KEY:
                    return True
            elif auth_header.strip() == settings.SEPAY_API_KEY:
                return True

        # 2. Check query parameter fallback
        if query_api_key and query_api_key == settings.SEPAY_API_KEY:
            return True

        return False
