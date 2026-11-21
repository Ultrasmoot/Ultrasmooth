# Security headers on every response. The CSP lists exactly what the page loads: its own files,
# Google Sign-In (accounts.google.com/gsi) and Google Fonts. Inline STYLES are allowed because the
# UI sets style="" attributes; inline SCRIPTS are not (only the nonce'd one).
from flask import g, request


def register_security_headers(app):
    @app.after_request
    def security_headers(resp):
        nonce = g.get("csp_nonce")
        script_src = "'self' https://accounts.google.com/gsi/client" + (f" 'nonce-{nonce}'" if nonce else "")
        resp.headers.setdefault("Content-Security-Policy", "; ".join([
            "default-src 'self'",
            f"script-src {script_src}",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: https:",
            "connect-src 'self' https://accounts.google.com/gsi/",
            "frame-src https://accounts.google.com/gsi/",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]))
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")   # API answers carry personal data
        return resp
