from flask import Flask, render_template

from config import Config
from source.backend.controllers.auth_controller import auth_bp
from source.backend.middleware.auth_middleware import login_required, role_required


def create_app():
    app = Flask(__name__, template_folder="../frontend")
    app.register_blueprint(auth_bp)

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

    # demo the shared role_required guard (R-02) that will reuse
    @app.get("/api/admin/users")
    @role_required("admin")
    def list_users():
        return {"note": "Full User & Access management (US-13) ships in Iteration 6."}

    # real server-side gate for the User & Access nav
    @app.get("/api/admin/access-check")
    @role_required("admin")
    def access_check():
        return {"authorized": True}

    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)