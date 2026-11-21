import bcrypt
import models.user.model as _m

def _check_password_rules(password):
    if not isinstance(password, str) or len(password) < _m.MIN_PASSWORD_LENGTH:
        raise _m.ValidationError(f"Password must be at least {_m.MIN_PASSWORD_LENGTH} characters.")
    if len(password.encode("utf-8")) > _m.MAX_PASSWORD_BYTES:
        raise _m.ValidationError(f"Password must be at most {_m.MAX_PASSWORD_BYTES} bytes long.")

class UserModelCheckPasswordRulesHashPassword:
    # hash password
    @staticmethod
    def _hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # check password
    @staticmethod
    def _check_password(password: str, password_hash: str) -> bool:
        if not password_hash or not isinstance(password, str):
            return False
        raw = password.encode("utf-8")
        if len(raw) > _m.MAX_PASSWORD_BYTES:
            return False
        try:
            return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
        except ValueError:
            return False  # malformed stored hash

    # lookups
    @staticmethod
    def find_by_email(email: str):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def find_by_google_sub(sub: str):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE google_sub = %s", (sub,))
            return cur.fetchone()
        finally:
            conn.close()

    # used in middleware
    @staticmethod
    def find_by_id(user_id: int):
        conn = _m.get_connection()
        try:
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
            return cur.fetchone()
        finally:
            conn.close()
