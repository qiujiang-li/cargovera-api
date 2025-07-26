import os
from cryptography.fernet import Fernet

class EncryptionHelper:
    """
    Production-ready helper to encrypt/decrypt sensitive tokens.
    Uses Fernet (AES 128 in CBC mode + HMAC) which is secure, authenticated encryption.
    """

    def __init__(self, key: str):
        """
        :param key: Base64-encoded 32-byte key. Must be securely stored (e.g., AWS Secrets Manager).
        """
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypts plaintext (e.g., refresh_token) and returns Base64-encoded ciphertext.
        """
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypts Base64-encoded ciphertext and returns plaintext.
        """
        return self.fernet.decrypt(ciphertext.encode()).decode()


# Usage example:
if __name__ == "__main__":
    # IMPORTANT: in production, load key securely (not hardcoded!)
    # Generate once: Fernet.generate_key()
    encryption_key = os.environ.get("REFRESH_TOKEN_ENCRYPTION_KEY")
    helper = EncryptionHelper(encryption_key)

    token = "my_amazon_refresh_token_123"
    encrypted = helper.encrypt(token)
    print(f"Encrypted: {encrypted}")

    decrypted = helper.decrypt(encrypted)
    print(f"Decrypted: {decrypted}")
