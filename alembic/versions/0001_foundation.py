"""foundation tables"""
from alembic import op
import sqlalchemy as sa

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("username", sa.String(100), nullable=False), sa.Column("password_hash", sa.String(255), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table("sessions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("token_hash", sa.String(64), nullable=False), sa.Column("csrf_token", sa.String(64), nullable=False), sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_sessions_token_hash", "sessions", ["token_hash"], unique=True); op.create_index("ix_sessions_user_id", "sessions", ["user_id"]); op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table("events", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("level", sa.String(20), nullable=False), sa.Column("event_type", sa.String(100), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("actor", sa.String(100)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_events_level", "events", ["level"]); op.create_index("ix_events_event_type", "events", ["event_type"]); op.create_index("ix_events_created_at", "events", ["created_at"])
    op.create_table("settings", sa.Column("key", sa.String(100), primary_key=True), sa.Column("value", sa.Text(), nullable=False))

def downgrade():
    op.drop_table("settings"); op.drop_index("ix_events_created_at", table_name="events"); op.drop_index("ix_events_event_type", table_name="events"); op.drop_index("ix_events_level", table_name="events"); op.drop_table("events"); op.drop_index("ix_sessions_expires_at", table_name="sessions"); op.drop_index("ix_sessions_user_id", table_name="sessions"); op.drop_index("ix_sessions_token_hash", table_name="sessions"); op.drop_table("sessions"); op.drop_index("ix_users_username", table_name="users"); op.drop_table("users")
