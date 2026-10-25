from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from config import Config
from controllers.auth_controller import auth_bp
from controllers.resource_controller import resource_bp
from controllers.booking_controller import booking_bp
from controllers.announcement_controller import announcement_bp
from controllers.maintenance_controller import maintenance_bp
from controllers.checkin_controller import checkin_bp
from middleware.auth_middleware import login_required, role_required


def create_app():
    app = Flask(__name__, template_folder="../frontend")
    app.register_blueprint(auth_bp)
    app.register_blueprint(resource_bp)
    app.register_blueprint(booking_bp)
    app.register_blueprint(announcement_bp)
    app.register_blueprint(maintenance_bp)
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

    # Demonstrates the shared role_required guard (R-02) that every future
    # controller (Resource, Booking, Maintenance, History & Dashboard,
    # User & Access) will reuse instead of duplicating permission checks.
    @app.get("/api/admin/users")
    @role_required("admin")
    def list_users():
        return {"note": "Full User & Access management (US-13) ships in Iteration 6."}

    # Real server-side gate for the "User & Access" nav item (SRS-12).
    # The frontend calls this before switching into that view, so access is
    # enforced by the backend guard, not just by hiding the nav button.
    @app.get("/api/admin/access-check")
    @role_required("admin")
    def access_check():
        return {"authorized": True}

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)