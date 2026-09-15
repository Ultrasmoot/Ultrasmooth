import re
import bcrypt
import mysql.connector

from config import Config
from database.db import get_connection

# SRS-11 / URS-9: self-registration is limited to students. Professor and
# Admin accounts are created by an Admin only (SRS-13, Iteration 6).
STUDENT_ROLES = {"phd_student", "undergrad_student"}
ALL_ROLES = {"phd_student", "undergrad_student", "professor", "admin"}

class ValidationError(Exception):
    pass

class UserModel:
    # password helpers
    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

# check password
@staticmethod
def _check_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

# lookups
@staticmethod
def find_by_email(email: str):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return cur.fetchone()
    finally:
        conn.close()

@staticmethod
def find_by_google_sub(sub: str):
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM users WHERE google_sub = %s", (sub,))
        return cur.fetchone()
    finally:
        conn.close()
