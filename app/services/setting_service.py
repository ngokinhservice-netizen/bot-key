from typing import Optional, Dict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.models import SystemSetting
from app.services.audit_service import AuditService
from app.utils.logger import logger


class SettingService:
    @staticmethod
    async def get_setting(session: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()
        if item and item.value is not None:
            return item.value
        return default

    @staticmethod
    async def set_setting(
        session: AsyncSession,
        key: str,
        value: str,
        description: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> SystemSetting:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        res = await session.execute(stmt)
        item = res.scalar_one_or_none()

        if item:
            item.value = value
            if description:
                item.description = description
        else:
            item = SystemSetting(key=key, value=value, description=description)
            session.add(item)

        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="UPDATE_SETTING",
                admin_id=admin_id,
                target_type="setting",
                target_id=key,
                details=f"key={key} | value={value}",
            )

        logger.info(f"Updated setting: {key} = {value}")
        return item

    @staticmethod
    async def get_bank_info(session: AsyncSession) -> Dict[str, str]:
        """
        Get current Bank Account configuration for payments.
        Checks database first, falls back to .env settings.
        """
        bank_name = await SettingService.get_setting(session, "BANK_NAME", settings.SEPAY_BANK_NAME)
        bank_account = await SettingService.get_setting(session, "BANK_ACCOUNT", settings.SEPAY_BANK_ACCOUNT)
        account_name = await SettingService.get_setting(session, "ACCOUNT_NAME", settings.SEPAY_ACCOUNT_NAME)
        sepay_api_key = await SettingService.get_setting(session, "SEPAY_API_KEY", settings.SEPAY_API_KEY)

        return {
            "bank_name": bank_name,
            "bank_account": bank_account,
            "account_name": account_name,
            "sepay_api_key": sepay_api_key,
        }

    @staticmethod
    async def update_bank_info(
        session: AsyncSession,
        bank_name: str,
        bank_account: str,
        account_name: str,
        sepay_api_key: Optional[str] = None,
        admin_id: Optional[int] = None,
    ):
        await SettingService.set_setting(session, "BANK_NAME", bank_name.strip(), "Tên ngân hàng thụ hưởng", admin_id)
        await SettingService.set_setting(session, "BANK_ACCOUNT", bank_account.strip(), "Số tài khoản ngân hàng", admin_id)
        await SettingService.set_setting(session, "ACCOUNT_NAME", account_name.strip().upper(), "Tên chủ tài khoản", admin_id)
        if sepay_api_key:
            await SettingService.set_setting(session, "SEPAY_API_KEY", sepay_api_key.strip(), "API Key SePay", admin_id)
