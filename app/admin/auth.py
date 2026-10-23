import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from fastapi import Request, HTTPException, status, Depends
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.config.settings import settings
from app.database.session import get_db
from app.database.models import AdminUser, AdminRole
from app.utils.logger import logger


# Simple and robust SHA256 + salt password hashing (zero binary wheels issues)
def hash_password(password: str) -> str:
    salt = settings.APP_SECRET_KEY[:16]
    return hashlib.sha256(f"{salt}{password}".encode("utf-8")).hexdigest()


def verify_password(plain_password: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_password(plain_password), hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.APP_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_admin(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> AdminUser:
    """Extract admin user from cookie token or Authorization header"""
    token = request.cookies.get("admin_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập quản trị",
            headers={"Location": "/admin/login"},
        )

    try:
        payload = jwt.decode(token, settings.APP_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        admin_id = payload.get("sub")
        if not admin_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập hết hạn")

    stmt = select(AdminUser).where(AdminUser.id == int(admin_id))
    res = await session.execute(stmt)
    admin = res.scalar_one_or_none()

    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản bị vô hiệu hóa")

    return admin


def require_roles(allowed_roles: List[AdminRole]):
    """RBAC Dependency to protect endpoints by role"""
    async def role_checker(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
        if admin.role not in allowed_roles and admin.role != AdminRole.SUPER_ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Bạn không có quyền thực hiện chức năng này. Yêu cầu: {[r.value for r in allowed_roles]}",
            )
        return admin
    return role_checker
