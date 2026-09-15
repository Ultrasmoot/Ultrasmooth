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