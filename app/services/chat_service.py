"""对话服务：会话管理、消息记录

Phase 3 Agent 接入后，send_message 会调用 Agent 生成回复。
目前先做好会话创建和历史查询的基础设施。
"""

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.user import User


def create_conversation(db: Session, user: User) -> Conversation:
    """为用户创建一个新的客服对话会话"""
    conversation = Conversation(user_id=user.id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def add_message(db: Session, conversation: Conversation, role: str, content: str) -> Message:
    """往会话中添加一条消息（user 或 agent），同时刷新会话的 updated_at"""
    message = Message(conversation_id=conversation.id, role=role, content=content)
    db.add(message)
    # 手动触碰会话使其 updated_at 刷新 -- onupdate 只在 ORM 对象上生效
    conversation.status = conversation.status  # 无实际变更，但触发 onupdate
    db.commit()
    db.refresh(message)
    return message


def get_conversation(db: Session, conversation_id: int, user_id: int) -> Conversation:
    """获取会话，校验归属"""
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == user_id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在")
    return conversation


def get_conversation_messages(db: Session, conversation_id: int, user_id: int) -> list[Message]:
    """获取会话的所有消息记录（按时间正序），先校验会话归属"""
    # 先确认会话属于当前用户
    get_conversation(db, conversation_id, user_id)
    return (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
        .all()
    )
