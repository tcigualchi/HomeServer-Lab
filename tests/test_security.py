from backend.app.security import hash_password, verify_password

def test_password_hashing():
    hashed = hash_password("uma senha de teste forte")
    assert hashed != "uma senha de teste forte"
    assert verify_password("uma senha de teste forte", hashed)
    assert not verify_password("senha errada", hashed)
