from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy import text

from app.errors import error_response
from app.extensions import get_session

bp = Blueprint("health", __name__, url_prefix="/api")


@bp.get("/health")
def health() -> ResponseReturnValue:
    try:
        get_session().execute(text("SELECT 1"))
    except Exception:
        get_session().rollback()
        return error_response(503, "service_unavailable", "Database is unreachable")
    return jsonify({"status": "ok"})
