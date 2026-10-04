import getpass
from pathlib import Path
from argon2 import PasswordHasher

password = getpass.getpass("Nova senha do admin: ")
confirm = getpass.getpass("Repita a senha: ")
if password != confirm or len(password) < 12:
    raise SystemExit("As senhas devem coincidir e ter pelo menos 12 caracteres.")
env = Path(".env")
text = env.read_text(encoding="utf-8") if env.exists() else ""
line = f"ADMIN_PASSWORD_HASH={PasswordHasher().hash(password)}"
lines = [x for x in text.splitlines() if not x.startswith("ADMIN_PASSWORD_HASH=")]
env.write_text("\n".join(lines + [line, ""]), encoding="utf-8")
try:
    env.chmod(0o600)
except OSError:
    pass
print("Hash Argon2 gravado em .env. Proteja o arquivo e nunca o comite.")
