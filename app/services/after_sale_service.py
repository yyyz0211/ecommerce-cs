"""售后服务：提交申请、查询售后记录"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.after_sale import AfterSale
from app.models.order import Order


def create_after_sale(
    db: Session, user_id: int, order_id: int, type_: str, reason: str
) -> AfterSale:
    """提交售后申请 -- 校验订单是否属于当前用户"""
    # 确认订单存在且属于当前用户
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user_id).first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    after_sale = AfterSale(
        order_id=order_id,
        user_id=user_id,
        type=type_,
        reason=reason,
    )
    db.add(after_sale)
    db.commit()
    db.refresh(after_sale)
    return after_sale


def get_user_after_sales(db: Session, user_id: int) -> list[AfterSale]:
    """获取用户所有售后记录，按时间倒序"""
    return (
        db.query(AfterSale)
        .filter(AfterSale.user_id == user_id)
        .order_by(AfterSale.created_at.desc())
        .all()
    )


def get_after_sale_detail(db: Session, after_sale_id: int, user_id: int) -> AfterSale:
    """获取单条售后详情，仅限本人"""
    record = db.query(AfterSale).filter(
        AfterSale.id == after_sale_id,
        AfterSale.user_id == user_id,
    ).first()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="售后记录不存在")
    return record
