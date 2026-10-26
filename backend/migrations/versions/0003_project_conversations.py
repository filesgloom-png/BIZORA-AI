"""Attach conversations to projects.

Existing conversations remain unassigned so this migration preserves all chat history.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_project_conversations"
down_revision = "0002_workspaces_projects"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "conversations",
        sa.Column("project_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_project_id_projects",
        "conversations",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])


def downgrade():
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    op.drop_constraint("fk_conversations_project_id_projects", "conversations", type_="foreignkey")
    op.drop_column("conversations", "project_id")
