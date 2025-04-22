import sqlite3
import os
from cryptography.fernet import Fernet

class EncryptedSQLiteDB:
    """
    A wrapper around sqlite3 that transparently encrypts and decrypts
    specified fields using Fernet symmetric encryption.

    Usage:
        db = EncryptedSQLiteDB(db_path='secure.db', key_path='secret.key')
        # Use SQL functions `encrypt(?)` and `decrypt(column)` in your queries.

    """
    def __init__(self, db_path: str, key_path: str):
        # Load or create encryption key
        self.key = self._load_or_create_key(key_path)
        self.fernet = Fernet(self.key)

        # Connect to SQLite database
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Register custom SQL functions for encryption/decryption
        self._register_functions()

    def _load_or_create_key(self, key_path: str) -> bytes:
        """
        Load existing encryption key from file, or generate a new one.
        """
        if os.path.exists(key_path):
            return open(key_path, 'rb').read()
        key = Fernet.generate_key()
        with open(key_path, 'wb') as f:
            f.write(key)
        return key

    def _encrypt(self, data: bytes) -> bytes:
        """
        Encrypt raw bytes. Returns encrypted token.
        """
        return self.fernet.encrypt(data)

    def _decrypt(self, token: bytes) -> bytes:
        """
        Decrypt token to raw bytes. """
        return self.fernet.decrypt(token)

    def _encrypt_func(self, plain_text):
        """
        SQL function: encrypt(TEXT) -> BLOB
        Automatically called in SQL when using `encrypt(?)`.
        """
        if plain_text is None:
            return None
        if isinstance(plain_text, str):
            plain_text = plain_text.encode('utf-8')
        return self._encrypt(plain_text)

    def _decrypt_func(self, token):
        """
        SQL function: decrypt(BLOB) -> TEXT
        Automatically called in SQL when using `decrypt(column)`.
        """
        if token is None:
            return None
        # token may be stored as bytes or buffer
        return self._decrypt(token).decode('utf-8')

    def _register_functions(self):
        """
        Register the SQL functions for encrypt/decrypt.
        """
        self.conn.create_function('encrypt', 1, self._encrypt_func)
        self.conn.create_function('decrypt', 1, self._decrypt_func)

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        """
        Execute a write operation (INSERT, UPDATE, DELETE).
        """
        cur = self.conn.cursor()
        cur.execute(query, params)
        self.conn.commit()
        return cur

    def query(self, query: str, params: tuple = ()) -> list:
        """
        Execute a read operation (SELECT) and fetch all rows.
        Use `decrypt(column)` in SELECT to get plaintext values.
        """
        cur = self.conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()

    def close(self):
        """Close the database connection."""
        self.conn.close()