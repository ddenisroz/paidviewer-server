#!/usr/bin/env python3
"""
Helpers for token encryption and decryption.
Uses Fernet for symmetric encryption.

Encrypted tokens are marked with the `ENC:` prefix for quick inspection
without trying to decrypt them first.
"""
import logging
import sys
from cryptography.fernet import Fernet
from typing import Optional
from core.config import settings
logger = logging.getLogger(__name__)
ENCRYPTED_PREFIX = 'ENC:'

class TokenEncryptionError(Exception):
    """Raised when token encryption/decryption fails."""
    pass
ENCRYPTION_KEY = settings.token_encryption_key
if not ENCRYPTION_KEY or ENCRYPTION_KEY.startswith('your-'):
    logger.critical('[SECURITY] TOKEN_ENCRYPTION_KEY is not configured. Generate a key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" and add it to your .env file as TOKEN_ENCRYPTION_KEY=<key>')
    if not settings.is_development:
        sys.exit(1)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    logger.warning('[SECURITY] Using temporary encryption key for development. Tokens will NOT survive restart.')
try:
    cipher_suite = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)
except Exception as e:
    logger.critical(f'[SECURITY] Failed to initialize encryption: {e}')
    if not settings.is_development:
        sys.exit(1)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    cipher_suite = Fernet(ENCRYPTION_KEY.encode())
    logger.warning('[SECURITY] Using fallback temporary encryption key for development.')

def encrypt_token(token: str) -> str:
    """
    Encrypt a token and prefix it with `ENC:`.

    Args:
        token: Token value to encrypt

    Returns:
        Encrypted token with the `ENC:` prefix

    Raises:
        TokenEncryptionError: Raised when encryption fails
    """
    if not token:
        return token
    if is_token_encrypted(token):
        return token
    try:
        encrypted = cipher_suite.encrypt(token.encode())
        return ENCRYPTED_PREFIX + encrypted.decode()
    except Exception as e:
        raise TokenEncryptionError(f'Failed to encrypt token: {e}') from e

def decrypt_token(encrypted_token: str) -> Optional[str]:
    """
    Decrypt a token.

    Args:
        encrypted_token: Encrypted token value, with or without the `ENC:` prefix

    Returns:
        Decrypted token value

    Raises:
        TokenEncryptionError: Raised when decryption fails
    """
    if not encrypted_token:
        return encrypted_token
    if encrypted_token.startswith(ENCRYPTED_PREFIX):
        raw = encrypted_token[len(ENCRYPTED_PREFIX):]
        try:
            decrypted = cipher_suite.decrypt(raw.encode())
            return decrypted.decode()
        except Exception as e:
            raise TokenEncryptionError(f'Failed to decrypt token: {e}') from e
    try:
        decrypted = cipher_suite.decrypt(encrypted_token.encode())
        return decrypted.decode()
    except Exception:
        return encrypted_token

def is_token_encrypted(token: str) -> bool:
    """
    Check whether a token is encrypted by looking for the `ENC:` prefix.

    Args:
        token: Token value to inspect

    Returns:
        True if the token is encrypted, otherwise False
    """
    if not token:
        return False
    return token.startswith(ENCRYPTED_PREFIX)
