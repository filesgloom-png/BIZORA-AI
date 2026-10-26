"""Create the initial BIZORA AI schema.

This baseline is intentionally explicit so future model changes do not rewrite
the schema represented by this revision. Existing MVP tables are preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _table_names():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name):
    return {item["name"] for item in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade():
    tables = _table_names()
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
            sa.Column("first_name", sa.String(length=128), nullable=False, server_default=""),
            sa.Column("username", sa.String(length=128), nullable=True),
            sa.Column("role", sa.String(length=16), nullable=False, server_default="user"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "conversations" not in tables:
        op.create_table(
            "conversations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
            sa.Column("title", sa.String(length=160), nullable=False, server_default="Новый диалог"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "messages" not in tables:
        op.create_table(
            "messages",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("conversation_id", sa.Integer(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
            sa.Column("role", sa.String(length=16), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "usage_events" not in tables:
        op.create_table(
            "usage_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("telegram_id", sa.BigInteger(), sa.ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    for table_name, index_name, columns in [
        ("conversations", "ix_conversations_telegram_id", ["telegram_id"]),
        ("conversations", "ix_conversations_user_updated", ["telegram_id", "updated_at"]),
        ("messages", "ix_messages_conversation_id", ["conversation_id"]),
        ("usage_events", "ix_usage_events_telegram_id", ["telegram_id"]),
        ("usage_events", "ix_usage_user_created", ["telegram_id", "created_at"]),
    ]:
        if index_name not in _indexes(table_name):
            op.create_index(index_name, table_name, columns)


def downgrade():
    tables = _table_names()
    if "usage_events" in tables:
        op.drop_table("usage_events")
    if "messages" in tables:
        op.drop_table("messages")
    if "conversations" in tables:
        op.drop_table("conversations")
    if "users" in tables:
        op.drop_table("users")
