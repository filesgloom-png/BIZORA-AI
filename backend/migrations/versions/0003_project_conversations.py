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
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_conversations_project_id_projects",
            "projects",
            ["project_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])


def downgrade():
    op.drop_index("ix_conversations_project_id", table_name="conversations")
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_constraint("fk_conversations_project_id_projects", type_="foreignkey")
        batch_op.drop_column("project_id")
