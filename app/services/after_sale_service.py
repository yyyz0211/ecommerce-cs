"""售后服务：提交申请、查询售后记录"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ORDER_NOT_FOUND, AFTER_SALE_NOT_FOUND
from app.models.after_sale import AfterSale
from app.models.order import Order


async def create_after_sale(
    db: AsyncSession, user_id: int, order_id: int, type_: str, reason: str
) -> AfterSale:
    """提交售后申请 -- 校验订单是否属于当前用户"""
    result = await db.execute(
        select(Order).where(Order.id == order_id, Order.user_id == user_id)
    )
    order = result.scalar_one_or_none()
    if not order:
        raise ORDER_NOT_FOUND

    after_sale = AfterSale(
        order_id=order_id,
        user_id=user_id,
        type=type_,
        reason=reason,
    )
    db.add(after_sale)
    await db.commit()
    await db.refresh(after_sale)
    return after_sale


async def get_user_after_sales(db: AsyncSession, user_id: int) -> list[AfterSale]:
    """获取用户所有售后记录，按时间倒序"""
    result = await db.execute(
        select(AfterSale)
        .where(AfterSale.user_id == user_id)
        .order_by(AfterSale.created_at.desc())
    )
    return result.scalars().all()


async def get_after_sale_detail(
    db: AsyncSession, after_sale_id: int, user_id: int
) -> AfterSale:
    """获取单条售后详情，仅限本人"""
    result = await db.execute(
        select(AfterSale).where(
            AfterSale.id == after_sale_id,
            AfterSale.user_id == user_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise AFTER_SALE_NOT_FOUND
    return record
