"""SQLAlchemy 模型基类"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有模型的基类"""
    pass
