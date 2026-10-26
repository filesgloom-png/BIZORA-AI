from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from app.config import settings


def _database_url():
    url = settings.database_url.strip() or "sqlite:///./bizora.db"
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and "+psycopg" not in url:
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _database_url()
engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"
    telegram_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    conversations: Mapped[list["ConversationRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "telegram_id", "updated_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160), default="Новый диалог")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    user: Mapped[UserRecord] = relationship(back_populates="conversations")
    messages: Mapped[list["MessageRecord"]] = relationship(back_populates="conversation", cascade="all, delete-orphan", order_by="MessageRecord.id")


class MessageRecord(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    conversation: Mapped[ConversationRecord] = relationship(back_populates="messages")


class UsageEvent(Base):
    __tablename__ = "usage_events"
    __table_args__ = (Index("ix_usage_user_created", "telegram_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(ForeignKey("users.telegram_id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def initialize_database():
    Base.metadata.create_all(bind=engine)


def get_db():
    with SessionLocal() as session:
        yield session


def ensure_user(db: Session, user: dict):
    record = db.get(UserRecord, user["id"])
    now = datetime.now(timezone.utc)
    if record is None:
        record = UserRecord(telegram_id=user["id"], first_name=user.get("first_name", ""),
            username=user.get("username"), role=user.get("role", "user"), created_at=now, updated_at=now)
        db.add(record)
    else:
        record.first_name = user.get("first_name", "")
        record.username = user.get("username")
        record.role = user.get("role", "user")
        record.updated_at = now
    db.flush()
    return record


def check_and_record_usage(db: Session, user: dict, limit: int):
    now = datetime.now(timezone.utc)
    cutoff = datetime.fromtimestamp(now.timestamp() - 3600, tz=timezone.utc)
    count = db.scalar(select(func.count(UsageEvent.id)).where(
        UsageEvent.telegram_id == user["id"], UsageEvent.created_at >= cutoff
    )) or 0
    if count >= max(1, limit):
        from fastapi import HTTPException
        raise HTTPException(status_code=429, detail="Hourly AI request limit reached. Try again later.")
    db.add(UsageEvent(telegram_id=user["id"], created_at=now))
    db.flush()


initialize_database()
