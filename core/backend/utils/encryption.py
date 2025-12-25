from cryptography.fernet import Fernet
import os
from config import settings

# We'll use the JWT secret key as a base for the encryption key
# Fernet keys must be 32 signal-based bytes (base64 encoded)
# For now, we'll derive it or use a default if not set
def get_encryption_key():
    # In a real app, this should be a separate stable key
    # For MVP, we'll use a derived key from settings or a dedicated env var
    key = os.getenv("SECRET_ENCRYPTION_KEY")
    if not key:
        # Fallback to a derived key from jwt_secret_key (not ideal but works for MVP)
        import base64
        import hashlib
        m = hashlib.sha256()
        m.update(settings.jwt_secret_key.encode())
        key = base64.urlsafe_b64encode(m.digest())
    return key

def encrypt_string(plain_text: str) -> str:
    if not plain_text:
        return ""
    f = Fernet(get_encryption_key())
    return f.encrypt(plain_text.encode()).decode()

def decrypt_string(encrypted_text: str) -> str:
    if not encrypted_text:
        return ""
    try:
        f = Fernet(get_encryption_key())
        return f.decrypt(encrypted_text.encode()).decode()
    except Exception:
        return ""
