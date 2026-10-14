from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class Favorite(Base):
    __tablename__ = "favorite"

    __table_args__ = (
        UniqueConstraint('user_id', 'news_id', name = 'user_news_unique'),
        Index('fk_favorite_user_idx', 'user_id'),
        Index('fk_favorite_news_idx', 'news_id')
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="Favorite ID")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="User ID")
    news_id: Mapped[int] = mapped_column(Integer,nullable=False, comment="News ID")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, comment="Creation timestamp")

    def __repr__(self):
        return f"<Favorite id={self.id} user_id={self.user_id} news_id={self.news_id} created_at={self.created_at}>"