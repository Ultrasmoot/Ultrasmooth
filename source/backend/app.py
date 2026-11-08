from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import Config
from controllers.auth_controller import auth_bp
from controllers.resource_controller import resource_bp
from controllers.booking_controller import booking_bp
from controllers.announcement_controller import announcement_bp
from controllers.maintenance_controller import maintenance_bp
from controllers.checkin_controller import checkin_bp

from controllers.activity_controller import activity_bp 
from controllers.appointment_controller import appointment_bp 
from controllers.dashboard_controller import dashboard_bp 
from controllers.notification_controller import notification_bp 
from controllers.user_admin_controller import user_admin_bp 
from middleware.auth_middleware import login_required, role_required


def create_app():
    app = Flask(__name__, template_folder="../frontend")
    app.register_blueprint(auth_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(maintenance_bp)
    app.register_blueprint(checkin_bp)
    # Panisara
    app.register_blueprint(activity_bp) 
    app.register_blueprint(appointment_bp) 
    app.register_blueprint(dashboard_bp) 
    app.register_blueprint(notification_bp) 
    app.register_blueprint(user_admin_bp) 

    @app.before_request
    def require_json_object():
        if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH"}:
            body = request.get_json(silent=True)
            if body is not None and not isinstance(body, dict):
                return jsonify({"error": "Request body must be a JSON object."}), 400

    # unexpected server error on an /api route frontend can show a message 
    @app.errorhandler(Exception)
    def api_error(e):
        if not request.path.startswith("/api/"):
            if isinstance(e, HTTPException):
                return e
            raise e
        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code
        app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({"error": "Something went wrong on the server. Please try again."}), 500

    @app.get("/")
    def index():
        return render_template("index.html", google_client_id=Config.GOOGLE_CLIENT_ID)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/me/ping")
    @login_required
    def ping():
        return {"status": "authenticated"}
    
    # user access , frontend calls this (server-side)
    @app.get("/api/admin/access-check")
    @role_required("admin")
    def access_check():
        return {"authorized": True}

    return app


app = create_app()

if __name__ == "__main__":
    # Background jobs (auto check-out, old-row cleanup)
    import os
    from services.housekeeping import start_background_worker

    if not Config.DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_background_worker()
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
