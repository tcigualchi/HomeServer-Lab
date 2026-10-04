import getpass
from sqlalchemy import select
from backend.app.core.config import get_settings
from backend.app.db import SessionLocal
from backend.app.models import User
from backend.app.security import hash_password

settings = get_settings()
password = getpass.getpass("Nova senha do admin: ")
confirm = getpass.getpass("Repita a senha: ")
if password != confirm or len(password) < 12:
    raise SystemExit("As senhas devem coincidir e ter pelo menos 12 caracteres.")

with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == settings.admin_username))
    if user:
        user.password_hash = hash_password(password)
        user.role = "Admin"
        user.is_active = True
    else:
        user = User(username=settings.admin_username, password_hash=hash_password(password), role="Admin", is_active=True)
        db.add(user)
    db.commit()
print(f"Usuário '{settings.admin_username}' atualizado no banco.")
