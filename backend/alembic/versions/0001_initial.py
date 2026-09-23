"""0001 — initial schema: users, agents, agent_voices, tools, agent_tools,
calls, conversation_messages, call_events.

Revision ID: 0001
Revises: None
Create Date: 2026-09-22
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "agents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="auto"),
        sa.Column("voice_gender", sa.String(16), nullable=False),
        sa.Column("voice_id", sa.String(128), nullable=False),
        sa.Column("tts_provider", sa.String(32), nullable=False, server_default="piper"),
        sa.Column("llm_model", sa.String(128), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("greeting", sa.Text(), nullable=True),
        sa.Column("max_duration_sec", sa.Integer(), nullable=False, server_default="600"),
        sa.Column("silence_timeout_sec", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agents_user_id", "agents", ["user_id"])

    op.create_table(
        "agent_voices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("voice_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="piper"),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("gender", sa.String(16), nullable=False),
        sa.Column("sample_rate", sa.Integer(), nullable=False, server_default="22050"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_agent_voices_voice_id", "agent_voices", ["voice_id"], unique=True)

    op.create_table(
        "tools",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tools_name", "tools", ["name"], unique=True)

    op.create_table(
        "agent_tools",
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tool_id",
            sa.String(36),
            sa.ForeignKey("tools.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("duration_sec", sa.Float(), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("facts", sa.JSON(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_calls_user_id", "calls", ["user_id"])
    op.create_index("ix_calls_agent_id", "calls", ["agent_id"])

    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "call_id",
            sa.String(36),
            sa.ForeignKey("calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("intent", sa.String(128), nullable=True),
        sa.Column("entities", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_conversation_messages_call_id", "conversation_messages", ["call_id"]
    )

    op.create_table(
        "call_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "call_id",
            sa.String(36),
            sa.ForeignKey("calls.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_call_events_call_id", "call_events", ["call_id"])
    op.create_index("ix_call_events_event_type", "call_events", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_call_events_event_type", table_name="call_events")
    op.drop_index("ix_call_events_call_id", table_name="call_events")
    op.drop_table("call_events")
    op.drop_index("ix_conversation_messages_call_id", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_calls_agent_id", table_name="calls")
    op.drop_index("ix_calls_user_id", table_name="calls")
    op.drop_table("calls")
    op.drop_table("agent_tools")
    op.drop_index("ix_tools_name", table_name="tools")
    op.drop_table("tools")
    op.drop_index("ix_agent_voices_voice_id", table_name="agent_voices")
    op.drop_table("agent_voices")
    op.drop_index("ix_agents_user_id", table_name="agents")
    op.drop_table("agents")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
