import models.user.model as _m

class UserModelAuthenticateFindOrCreateGoogleUser:
    # email / password login 
    @classmethod
    def authenticate(cls, email: str, password: str):
        if not isinstance(email, str) or not isinstance(password, str):
            return None
        user = cls.find_by_email(email.strip().lower())
        if not user or not user["is_active"]:
            return None
        if not cls._check_password(password, user["password_hash"]):
            return None
        return user

    # Google OAuth
    @classmethod
    def find_or_create_google_user(cls, google_sub: str, email: str, full_name: str):
        # returns the user and whether it's a new account 
        # existing accounts are linked by email only if not already linked to another Google account
        user = cls.find_by_google_sub(google_sub)
        if user:
            return user, False

        user = cls.find_by_email(email)
        if user:
            # a deactivated account must not be touched by a Google
            # sign-in attempt (no linking, no password wipe)
            if not user["is_active"]:
                return user, False
            # Already linked to another Google identity: never re-link it
            if user.get("google_sub") and user["google_sub"] != google_sub:
                raise _m.ValidationError(
                    "This email is already linked to a different Google account."
                )
            conn = _m.get_connection()
            try:
                cur = conn.cursor()
                # Google verifies the email owner, so the old password is cleared
                # the account is linked only if no other request has linked it first
                cur.execute(
                    "UPDATE users SET google_sub = %s, password_hash = NULL, email_verified = 1 "
                    "WHERE id = %s AND is_active = 1 AND (google_sub IS NULL OR google_sub = %s)",
                    (google_sub, user["id"], google_sub),
                )
                linked = cur.rowcount
                conn.commit()
            finally:
                conn.close()
            fresh = cls.find_by_id(user["id"])
            if not linked:
                if fresh and not fresh["is_active"]:
                    return fresh, False  # deactivated while we were linking: caller answers 403
                if not (fresh and fresh.get("google_sub") == google_sub):
                    raise _m.ValidationError(
                        "This email is already linked to a different Google account."
                    )
            return fresh, False

        return None, True
