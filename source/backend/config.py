import os


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    JWT_EXPIRES_HOURS = int(os.getenv("JWT_EXPIRES_HOURS", "12"))

    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = int(os.getenv("DB_PORT", "3306"))
    DB_USER = os.getenv("DB_USER", "vase_user")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "vase_pass")
    DB_NAME = os.getenv("DB_NAME", "vase_lab")

    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    # restrict account creation to the email
    ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "ku.th")
