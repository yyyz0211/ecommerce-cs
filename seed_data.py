"""种子数据脚本 -- 使用独立同步引擎，不影响主 async engine"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from passlib.context import CryptContext

from app.config import settings
from app.models.base import Base
from app.models.user import User
from app.models.order import Order, OrderItem, Logistics
from app.models.after_sale import AfterSale

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def seed():
    # 使用同步引擎（种子数据是一次性脚本，不需要异步）
    sync_url = settings.DATABASE_URL.replace("mysql+aiomysql://", "mysql+pymysql://")
    engine = create_engine(sync_url)
    Base.metadata.create_all(bind=engine)

    # 清空旧数据，避免重复插入报错
    with engine.connect() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        conn.commit()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    test_user = User(
        username="buyer1",
        password_hash=pwd_context.hash("123456"),
        phone="13800001111",
        default_address="北京市朝阳区 xx 路 100 号",
    )
    db.add(test_user)
    db.flush()

    orders_data = [
        {
            "order_no": "202605280001",
            "status": "delivered",
            "total_amount": 299.00,
            "items": [("iPhone 手机壳", 2, 49.00), ("USB-C 数据线", 1, 29.00)],
            "logistics": ("顺丰快递", "SF1234567890", "已签收"),
        },
        {
            "order_no": "202605280002",
            "status": "shipped",
            "total_amount": 1599.00,
            "items": [("蓝牙耳机 Pro", 1, 1599.00)],
            "logistics": ("中通快递", "ZT9876543210", "运输中"),
        },
        {
            "order_no": "202605280003",
            "status": "paid",
            "total_amount": 88.50,
            "items": [("不锈钢保温杯", 1, 59.00), ("杯刷", 1, 29.50)],
            "logistics": (None, None, "待发货"),
        },
        {
            "order_no": "202605280004",
            "status": "pending",
            "total_amount": 4999.00,
            "items": [("机械键盘 Cherry 轴", 1, 4999.00)],
            "logistics": (None, None, "待发货"),
        },
    ]

    first_order_id = None
    for od in orders_data:
        order = Order(
            user_id=test_user.id,
            order_no=od["order_no"],
            status=od["status"],
            total_amount=od["total_amount"],
        )
        db.add(order)
        db.flush()

        if first_order_id is None:
            first_order_id = order.id

        for name, qty, price in od["items"]:
            db.add(OrderItem(order_id=order.id, product_name=name, quantity=qty, price=price))

        db.add(Logistics(
            order_id=order.id,
            company=od["logistics"][0],
            tracking_no=od["logistics"][1],
            status=od["logistics"][2],
        ))

    db.add(AfterSale(
        order_id=first_order_id,
        user_id=test_user.id,
        type="return",
        reason="手机壳尺寸不匹配，申请退货",
        status="pending",
    ))

    db.commit()
    db.close()
    print("种子数据插入完成！")
    print("  用户: buyer1 / 123456")
    print("  订单: 4 条（各种状态）")
    print("  售后: 1 条（待处理退货）")


if __name__ == "__main__":
    seed()
