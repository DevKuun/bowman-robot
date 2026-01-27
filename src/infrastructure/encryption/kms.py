"""
Encryption for API keys.
Supports AWS KMS or local Fernet encryption.
"""
import base64
import hashlib
import os
from typing import Optional

from src.config.settings import settings


class BaseEncryption:
    """Base encryption interface."""
    
    def encrypt(self, plaintext: str) -> str:
        raise NotImplementedError
    
    def decrypt(self, encrypted_data: str) -> str:
        raise NotImplementedError


class KMSEncryption(BaseEncryption):
    """AWS KMS encryption/decryption service."""
    
    def __init__(self):
        import boto3
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            self._client = boto3.client(
                'kms',
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
                region_name=settings.aws_region
            )
        else:
            self._client = boto3.client('kms', region_name=settings.aws_region)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt using AWS KMS."""
        from botocore.exceptions import ClientError
        try:
            response = self._client.encrypt(
                KeyId=settings.kms_key_id,
                Plaintext=plaintext.encode('utf-8'),
                EncryptionAlgorithm=settings.kms_encrypt_algorithm
            )
            return base64.b64encode(response['CiphertextBlob']).decode('utf-8')
        except ClientError as e:
            raise RuntimeError(f"KMS encryption failed: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt using AWS KMS."""
        from botocore.exceptions import ClientError
        try:
            response = self._client.decrypt(
                KeyId=settings.kms_key_id,
                EncryptionAlgorithm=settings.kms_encrypt_algorithm,
                CiphertextBlob=base64.b64decode(encrypted_data)
            )
            return response['Plaintext'].decode('utf-8')
        except ClientError as e:
            raise RuntimeError(f"KMS decryption failed: {e}")


class LocalEncryption(BaseEncryption):
    """
    Local Fernet encryption for development/simple deployments.
    Uses ENCRYPTION_KEY from settings or generates from a secret.
    """
    
    def __init__(self):
        from cryptography.fernet import Fernet
        
        # Use provided key or derive from secret
        if settings.encryption_key:
            key = settings.encryption_key.encode()
        else:
            # Derive key from a secret (or use default for dev)
            secret = settings.encryption_secret or "bowman-robot-default-secret"
            key = base64.urlsafe_b64encode(
                hashlib.sha256(secret.encode()).digest()
            )
        
        self._fernet = Fernet(key)
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt using Fernet."""
        return self._fernet.encrypt(plaintext.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt using Fernet."""
        return self._fernet.decrypt(encrypted_data.encode()).decode()


class PlainTextEncryption(BaseEncryption):
    """
    No encryption - just base64 encoding.
    WARNING: Only for development/testing!
    """
    
    def encrypt(self, plaintext: str) -> str:
        return base64.b64encode(plaintext.encode()).decode()
    
    def decrypt(self, encrypted_data: str) -> str:
        return base64.b64decode(encrypted_data.encode()).decode()


class EncryptionService:
    """
    Encryption service factory.
    Automatically selects the appropriate encryption method.
    """
    
    _instance = None
    _encryption = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._encryption is None:
            self._initialize()
    
    def _initialize(self):
        """Initialize the appropriate encryption service."""
        encryption_type = settings.encryption_type.lower()
        
        if encryption_type == "kms":
            self._encryption = KMSEncryption()
        elif encryption_type == "local":
            self._encryption = LocalEncryption()
        elif encryption_type == "none":
            self._encryption = PlainTextEncryption()
        else:
            # Auto-detect: use KMS if configured, otherwise local
            if settings.kms_key_id:
                self._encryption = KMSEncryption()
            else:
                self._encryption = LocalEncryption()
    
    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string."""
        return self._encryption.encrypt(plaintext)
    
    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt a string."""
        return self._encryption.decrypt(encrypted_data)


# Global instance (backward compatible)
kms_encryption = EncryptionService()


def get_encryptor() -> EncryptionService:
    """Return a shared encryption service instance."""
    return kms_encryption
