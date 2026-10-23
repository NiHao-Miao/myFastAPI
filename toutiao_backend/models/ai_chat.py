from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AiChat(Base):
    __tablename__ = "ai_chat"

    __table_args__ = (
        Index("fk_ai_chat_user_idx", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="聊天ID")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="用户ID")
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="用户提问")
    response: Mapped[str] = mapped_column(Text, nullable=False, comment="AI回答")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="创建时间",
    )

    def __repr__(self):
        return f"<AiChat id={self.id} user_id={self.user_id}>"
