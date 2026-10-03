import os

_INSECURE_SECRET_KEYS = {"", "dev-secret-change-me", "change-me"}

def _load_secret_key(app_env: str) -> str:
    """Require a real SECRET_KEY in production; allow a temporary key only in development."""
    key = os.getenv("SECRET_KEY", "")
    if key not in _INSECURE_SECRET_KEYS:
        return key
    if app_env == "development":
        return "dev-secret-change-me"
    raise RuntimeError(
        "SECRET_KEY is missing or still set to a placeholder value. "
        "Set a long random SECRET_KEY in the environment "
        "(or set APP_ENV=development for local testing only)."
    )

class Config:
    # Defaults to "production" (the safe choice) when APP_ENV is not set.
    APP_ENV = os.getenv("APP_ENV", "production").strip().lower()
    SECRET_KEY = _load_secret_key(APP_ENV)
    # Flask debug mode is only ever honoured in development.
    DEBUG = APP_ENV == "development" and os.getenv("FLASK_DEBUG", "0") == "1"
    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "12"))

    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "vase_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "vase_pass")
    DB_NAME = os.getenv("DB_NAME", "vase_lab")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    # restrict account creation to the email
    ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "ku.th")
    
    # forgot password settings
    APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5000")
    RESET_TOKEN_EXPIRES_MINUTES = int(os.getenv("RESET_TOKEN_EXPIRES_MINUTES", "30"))

    # email settings
    # SMTP_HOST is empty, print the reset link in the console instead of sending an email
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", "no-reply@vase-lab.local")
