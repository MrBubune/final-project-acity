import sqlite3
import pytest
import config.settings as settings

def test_db_at_rest_is_encrypted(test_env):
    # raw bytes should not begin with SQLite header
    data = open(settings.DB_PATH, "rb").read(16)
    assert not data.startswith(b"SQLite format 3")
