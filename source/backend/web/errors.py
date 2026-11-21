# Any unexpected server error on an /api route is answered with JSON, so the
# frontend can show a message instead of failing to parse an HTML error page.
from flask import jsonify, request
from werkzeug.exceptions import HTTPException


def register_error_handlers(app):
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
