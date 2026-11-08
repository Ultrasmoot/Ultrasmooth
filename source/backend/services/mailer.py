# Send check-in codes by e-mail (us-10)
# Print to log if SMTP is not configured
import logging
import smtplib
import ssl
import threading
from email.mime.text import MIMEText

from config import Config

logger = logging.getLogger(__name__)


def send_email(to_email: str, subject: str, body: str, dev_log_line: str = None):
    if not Config.SMTP_HOST:
        print(f"[DEV] {dev_log_line or subject} -> {to_email}", flush=True)
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = Config.SMTP_FROM
    msg["To"] = to_email

    # Verify the server certificate and set a timeout
    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=Config.SMTP_TIMEOUT_SECONDS) as server:
        server.starttls(context=ssl.create_default_context())
        if Config.SMTP_USER:
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_FROM, [to_email], msg.as_string())


def send_email_in_background(to_email: str, subject: str, body: str, dev_log_line: str = None):
    # Send e-mail in the background and log any errors

    def _run():
        try:
            send_email(to_email, subject, body, dev_log_line=dev_log_line)
        except Exception:
            logger.exception("Background e-mail to %s failed", to_email)

    thread = threading.Thread(target=_run, name="vase-mail", daemon=True)
    thread.start()
    return thread


def send_checkin_code(to_email: str, resource_name: str, code: str, ttl_minutes: int):
    body = (
        f"Your code to check in to {resource_name} is:\n\n    {code}\n\n"
        f"It expires in {ttl_minutes} minutes and can be used only once. "
        "If you didn't request this, you can ignore this email."
    )
    send_email(
        to_email,
        "[VASE] Your check-in code",
        body,
        dev_log_line=f"Check-in code for {resource_name} is {code}",
    )