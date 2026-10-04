"""normalize default media path"""
from alembic import op

revision = "0004_camera_path_casa"
down_revision = "0003_camera_stream_path"
branch_labels = None
depends_on = None

def upgrade():
    op.execute("UPDATE cameras SET stream_path='casa' WHERE stream_path='camera_casa'")

def downgrade():
    op.execute("UPDATE cameras SET stream_path='camera_casa' WHERE stream_path='casa'")
