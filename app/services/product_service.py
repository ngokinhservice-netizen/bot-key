from typing import Optional, List, Tuple
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models import Product, KeyInventory, KeyStatus
from app.services.audit_service import AuditService
from app.utils.logger import logger


class ProductService:
    @staticmethod
    async def list_active_products(session: AsyncSession) -> List[Tuple[Product, int]]:
        """
        List all active products together with their available stock count
        """
        # Subquery for available key counts
        stock_subq = (
            select(
                KeyInventory.product_id,
                func.count(KeyInventory.id).label("stock_count")
            )
            .where(KeyInventory.status == KeyStatus.AVAILABLE)
            .group_by(KeyInventory.product_id)
            .subquery()
        )

        stmt = (
            select(Product, func.coalesce(stock_subq.c.stock_count, 0).label("stock"))
            .outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
            .where(Product.is_active == True)
            .order_by(Product.price.asc())
        )
        res = await session.execute(stmt)
        return [(row[0], int(row[1])) for row in res.all()]

    @staticmethod
    async def get_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        stmt = select(Product).where(Product.id == product_id)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_by_slug(session: AsyncSession, slug: str) -> Optional[Product]:
        stmt = select(Product).where(Product.slug == slug)
        res = await session.execute(stmt)
        return res.scalar_one_or_none()

    @staticmethod
    async def get_stock_count(session: AsyncSession, product_id: int) -> int:
        stmt = select(func.count(KeyInventory.id)).where(
            and_(
                KeyInventory.product_id == product_id,
                KeyInventory.status == KeyStatus.AVAILABLE,
            )
        )
        res = await session.execute(stmt)
        return res.scalar() or 0

    @staticmethod
    async def create_product(
        session: AsyncSession,
        name: str,
        slug: str,
        description: str,
        price: int,
        duration_days: int = 30,
        image_url: Optional[str] = None,
        activation_guide: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> Product:
        # Check slug unique
        existing = await ProductService.get_by_slug(session, slug)
        if existing:
            raise ValueError(f"Mã định danh slug '{slug}' đã tồn tại.")

        product = Product(
            name=name,
            slug=slug,
            description=description,
            price=price,
            duration_days=duration_days,
            is_active=True,
            image_url=image_url,
            activation_guide=activation_guide or "Nhập mã key vào phần mềm MTK để kích hoạt bản quyền.",
        )
        session.add(product)
        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="CREATE_PRODUCT",
                admin_id=admin_id,
                target_type="product",
                target_id=str(product.id),
                details=f"name={name} | price={price} | duration={duration_days}",
            )
        return product

    @staticmethod
    async def update_product(
        session: AsyncSession,
        product_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[int] = None,
        duration_days: Optional[int] = None,
        is_active: Optional[bool] = None,
        image_url: Optional[str] = None,
        activation_guide: Optional[str] = None,
        admin_id: Optional[int] = None,
    ) -> Product:
        product = await ProductService.get_by_id(session, product_id)
        if not product:
            raise ValueError(f"Không tìm thấy sản phẩm #{product_id}")

        if name is not None:
            product.name = name
        if description is not None:
            product.description = description
        if price is not None:
            product.price = price
        if duration_days is not None:
            product.duration_days = duration_days
        if is_active is not None:
            product.is_active = is_active
        if image_url is not None:
            product.image_url = image_url
        if activation_guide is not None:
            product.activation_guide = activation_guide

        await session.flush()

        if admin_id:
            await AuditService.log_action(
                session=session,
                action="UPDATE_PRODUCT",
                admin_id=admin_id,
                target_type="product",
                target_id=str(product_id),
                details=f"price={price} | active={is_active}",
            )
        return product

    @staticmethod
    async def list_all_for_admin(session: AsyncSession) -> List[Tuple[Product, int]]:
        stock_subq = (
            select(
                KeyInventory.product_id,
                func.count(KeyInventory.id).label("stock_count")
            )
            .where(KeyInventory.status == KeyStatus.AVAILABLE)
            .group_by(KeyInventory.product_id)
            .subquery()
        )

        stmt = (
            select(Product, func.coalesce(stock_subq.c.stock_count, 0).label("stock"))
            .outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
            .order_by(Product.id.asc())
        )
        res = await session.execute(stmt)
        return [(row[0], int(row[1])) for row in res.all()]
