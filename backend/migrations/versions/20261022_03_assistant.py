"""Assistant conversations, turns and curated knowledge; no banking rows changed.

Revision ID: 20261022_03
Revises: 20261022_02
"""
import sqlalchemy as sa
from alembic import op

revision = "20261022_03"
down_revision = "20261022_02"
branch_labels = None
depends_on = None


def upgrade():
    # Keep the schema frozen in the revision; do not import future application models.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "assistant_conversations" not in existing:
        op.create_table("assistant_conversations",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
            sa.Column("audience", sa.String(10), nullable=False),
            sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id")),
            sa.Column("application_id", sa.Integer, sa.ForeignKey("applications.id")),
            sa.Column("title", sa.String(120), nullable=False),
            sa.Column("lease_token", sa.String(36)),
            sa.Column("lease_until", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    if "assistant_documents" not in existing:
        op.create_table("assistant_documents",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("body", sa.Text, nullable=False),
            sa.Column("audience", sa.String(10), nullable=False),
            sa.Column("kind", sa.String(12), nullable=False),
            sa.Column("source_url", sa.String(2000)),
            sa.Column("published_at", sa.DateTime(timezone=True)),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False))
    if "assistant_turns" not in existing:
        op.create_table("assistant_turns",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("conversation_id", sa.String(36), sa.ForeignKey("assistant_conversations.id"), nullable=False),
            sa.Column("request_id", sa.String(36), nullable=False),
            sa.Column("status", sa.String(12), nullable=False),
            sa.Column("intent", sa.String(30), nullable=False),
            sa.Column("user_content", sa.Text, nullable=False),
            sa.Column("assistant_content", sa.Text),
            sa.Column("sources", sa.JSON, nullable=False),
            sa.Column("tool_calls", sa.JSON, nullable=False),
            sa.Column("usage", sa.JSON, nullable=False),
            sa.Column("model", sa.String(120), nullable=False),
            sa.Column("error_code", sa.String(50)),
            sa.Column("latency_ms", sa.Integer),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True)),
            sa.UniqueConstraint("conversation_id", "request_id", name="uq_assistant_turn_request"))
    indexes = [
        ("assistant_conversations", "ix_assistant_conversations_owner_id", ["owner_id"]),
        ("assistant_conversations", "ix_assistant_conversations_owner_updated", ["owner_id", "updated_at"]),
        ("assistant_documents", "ix_assistant_documents_audience", ["audience"]),
        ("assistant_documents", "ix_assistant_documents_kind", ["kind"]),
        ("assistant_turns", "ix_assistant_turns_conversation_id", ["conversation_id"]),
        ("assistant_turns", "ix_assistant_turns_conversation_created", ["conversation_id", "created_at"]),
    ]
    for table, name, columns in indexes:
        if name not in {i["name"] for i in sa.inspect(op.get_bind()).get_indexes(table)}:
            op.create_index(name, table, columns)


def downgrade():
    # Explicit rollback discards assistant history only, not applications or scoring.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for name in ("assistant_turns", "assistant_documents", "assistant_conversations"):
        if name in existing:
            op.drop_table(name)
