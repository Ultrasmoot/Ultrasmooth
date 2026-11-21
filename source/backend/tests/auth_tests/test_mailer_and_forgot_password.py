from auth_tests.base import (
    Config,
    UserModel,
    create_app,
    mailer,
    mock,
    reset_rate_limits,
)  
import time
import unittest

# password-reset mail timeout + never blocks the response
class MailerTests(unittest.TestCase):
    def test_smtp_connection_gets_the_configured_timeout_and_verified_tls(self):
        with mock.patch.object(Config, "SMTP_HOST", "smtp.example.com"), \
             mock.patch.object(Config, "SMTP_USER", "u"), mock.patch.object(Config, "SMTP_PASSWORD", "p"), \
             mock.patch.object(Config, "SMTP_TIMEOUT_SECONDS", 7), \
             mock.patch("services.mailer.service.smtplib.SMTP") as smtp:
            mailer.send_email("a@ku.th", "Subject", "Body")
        args, kwargs = smtp.call_args
        self.assertEqual(args, ("smtp.example.com", Config.SMTP_PORT))
        self.assertEqual(kwargs["timeout"], 7)
        server = smtp.return_value.__enter__.return_value
        self.assertIn("context", server.starttls.call_args.kwargs) # certificate is verified
        server.login.assert_called_once_with("u", "p")
        server.sendmail.assert_called_once()

    def test_without_smtp_host_the_message_is_only_logged(self):
        with mock.patch.object(Config, "SMTP_HOST", ""), mock.patch("services.mailer.service.smtplib.SMTP") as smtp, \
             mock.patch("builtins.print") as pr:
            mailer.send_email("a@ku.th", "S", "B", dev_log_line="link here")
        smtp.assert_not_called()
        self.assertIn("link here", pr.call_args[0][0])

    def test_background_send_returns_immediately_even_if_the_mail_server_hangs(self):
        release = []

        def slow(*a, **k):
            while not release:
                time.sleep(0.01)

        with mock.patch.object(mailer, "send_email", side_effect=slow):
            started = time.monotonic()
            thread = mailer.send_email_in_background("a@ku.th", "S", "B")
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, 0.5)
            self.assertTrue(thread.daemon)
            release.append(1)
            thread.join(2)
        self.assertFalse(thread.is_alive())

    def test_background_failure_is_logged_and_never_raised(self):
        with mock.patch.object(mailer, "send_email", side_effect=OSError("smtp down")), \
             self.assertLogs("services.mailer.service", level="ERROR"):
            mailer.send_email_in_background("a@ku.th", "S", "B").join(2)

    def test_forgot_password_answers_the_same_and_fast_whether_or_not_the_account_exists(self):
        reset_rate_limits()
        client = create_app().test_client()
        gate = []

        def hanging_send(*a, **k):
            while not gate:
                time.sleep(0.01)

        with mock.patch.object(mailer, "send_email", side_effect=hanging_send):
            for token in ("T0K", None):    # account exists / does not exist
                with mock.patch.object(UserModel, "create_reset_token", return_value=token):
                    reset_rate_limits()
                    started = time.monotonic()
                    r = client.post("/api/auth/forgot-password", json={"email": "alice@ku.th"})
                    self.assertLess(time.monotonic() - started, 1.0)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn("If an account exists", r.get_json()["message"])
            gate.append(1)
            time.sleep(0.1)
