"""API error types and the JSON error handlers (one consistent error format)."""

from __future__ import annotations

import logging
from typing import Any

from flask import Flask, jsonify
from flask.typing import ResponseReturnValue
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class ApiError(Exception):
    """Base class for errors that map to a JSON response."""

    status = 500
    code = "internal_error"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = details or {}


class ValidationFailed(ApiError):
    status = 422
    code = "validation_error"


class MalformedRequest(ApiError):
    status = 400
    code = "validation_error"


class Unauthorized(ApiError):
    status = 401
    code = "unauthorized"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class NotFound(ApiError):
    status = 404
    code = "not_found"


class NoAvailability(ApiError):
    status = 409
    code = "no_availability"


class InvalidState(ApiError):
    status = 409
    code = "invalid_state"


class EmailTaken(ApiError):
    status = 409
    code = "email_taken"


_HTTP_CODES = {
    400: "validation_error",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
    415: "unsupported_media_type",
}


def error_response(
    status: int, code: str, message: str, details: dict[str, Any] | None = None
) -> ResponseReturnValue:
    return jsonify({"error": code, "message": message, "details": details or {}}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(exc: ApiError) -> ResponseReturnValue:
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.errorhandler(HTTPException)
    def _http_error(exc: HTTPException) -> ResponseReturnValue:
        status = exc.code or 500
        code = _HTTP_CODES.get(status, "http_error")
        return error_response(status, code, exc.description or exc.name)

    @app.errorhandler(Exception)
    def _unexpected(exc: Exception) -> ResponseReturnValue:
        log.exception("Unhandled error", exc_info=exc)
        return error_response(500, "internal_error", "Internal server error")
