from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app import auth as auth_lib
from app.config import get_settings
from app.extensions import get_session
from app.schemas import LoginIn, RegisterIn, validate
from app.serializers import user_json
from app.services import users

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register() -> ResponseReturnValue:
    data = validate(RegisterIn, request.get_json(silent=True))
    user = users.register_user(get_session(), data.email, data.password, data.full_name)
    token = auth_lib.create_token(user, get_settings().jwt_secret)
    return jsonify({"token": token, "user": user_json(user)}), 201


@bp.post("/login")
def login() -> ResponseReturnValue:
    data = validate(LoginIn, request.get_json(silent=True))
    user = users.authenticate(get_session(), data.email, data.password)
    token = auth_lib.create_token(user, get_settings().jwt_secret)
    return jsonify({"token": token, "user": user_json(user)})
