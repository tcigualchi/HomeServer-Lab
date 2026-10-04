"""add local media path to cameras"""
from alembic import op
import sqlalchemy as sa

revision = "0003_camera_stream_path"
down_revision = "0002_operations"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("cameras", sa.Column("stream_path", sa.String(120), nullable=False, server_default="camera_casa"))

def downgrade():
    op.drop_column("cameras", "stream_path")
