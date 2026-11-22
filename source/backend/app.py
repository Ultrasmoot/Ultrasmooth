import secrets

from flask import Flask, g, jsonify, render_template, request
from config import Config
from controllers.auth.controller import auth_bp
from controllers.resource.controller import resource_bp
from controllers.booking.controller import booking_bp
from controllers.announcement.controller import announcement_bp
from controllers.maintenance.controller import maintenance_bp  
from controllers.checkin.controller import checkin_bp 
from controllers.activity.controller import activity_bp 
from controllers.appointment.controller import appointment_bp  
from controllers.dashboard.controller import dashboard_bp 
from controllers.notification.controller import notification_bp 
from controllers.user_admin.controller import user_admin_bp 
from controllers.history.controller import history_bp 
from controllers.calendar.controller import calendar_bp 
from middleware.auth_middleware import login_required, role_required
from web.errors import register_error_handlers
from web.headers import register_security_headers


def create_app():
    app = Flask(__name__, template_folder="../frontend", static_folder="../frontend/static", static_url_path="/static")
    app.register_blueprint(auth_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(maintenance_bp) 
    app.register_blueprint(checkin_bp) 
    app.register_blueprint(activity_bp)
    app.register_blueprint(appointment_bp) 
    app.register_blueprint(dashboard_bp) 
    app.register_blueprint(notification_bp)  
    app.register_blueprint(user_admin_bp)  
    app.register_blueprint(history_bp) 
    app.register_blueprint(calendar_bp) 

    @app.before_request
    def require_json_object():
        if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH"}:
            body = request.get_json(silent=True)
            if body is not None and not isinstance(body, dict):
                return jsonify({"error": "Request body must be a JSON object."}), 400

    register_error_handlers(app)

    @app.get("/")
    def index():
        # One-time value that lets the single inline <script> in index.html run under the CSP.
        g.csp_nonce = secrets.token_urlsafe(16)
        return render_template("index.html", google_client_id=Config.GOOGLE_CLIENT_ID, csp_nonce=g.csp_nonce)

    register_security_headers(app)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/me/ping")
    @login_required
    def ping():
        return {"status": "authenticated"}

    # Real server-side gate for the "User & Access" nav item 
    # The frontend calls this before switching into that view, so access is
    # enforced by the backend guard, not just by hiding the nav button.
    @app.get("/api/admin/access-check")
    @role_required("admin")
    def access_check():
        return {"authorized": True}

    return app


app = create_app()

if __name__ == "__main__":
    # Background jobs (auto check-out, old-row cleanup). With the debug reloader the code runs
    # twice; only the child process that serves requests starts the worker.
    import os
    from services.housekeeping.service import start_background_worker

    if not Config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_background_worker()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
