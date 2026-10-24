from datetime import timedelta

import jwt
import pytest
from flask.testing import FlaskClient

from app import auth as auth_lib
from app.models import User
from tests.conftest import FIXED_NOW, JWT_SECRET, PASSWORD, auth_headers

REGISTER = {"email": "New.User@Example.com", "password": "longenough", "full_name": "New User"}


def test_register_creates_a_guest_and_returns_a_token(client: FlaskClient) -> None:
    res = client.post("/api/auth/register", json=REGISTER)
    assert res.status_code == 201
    body = res.get_json()
    assert body["user"] == {
        "id": body["user"]["id"],
        "email": "new.user@example.com",
        "full_name": "New User",
        "role": "guest",
    }
    claims = jwt.decode(
        body["token"],
        JWT_SECRET,
        algorithms=["HS256"],
        options={"verify_exp": False, "verify_iat": False},
    )
    assert claims["sub"] == str(body["user"]["id"]) and claims["role"] == "guest"
    assert claims["exp"] - claims["iat"] == 3600


def test_register_ignores_a_requested_role(client: FlaskClient) -> None:
    res = client.post("/api/auth/register", json={**REGISTER, "role": "staff"})
    assert res.get_json()["user"]["role"] == "guest"


def test_duplicate_email_is_a_409_regardless_of_case(client: FlaskClient) -> None:
    assert client.post("/api/auth/register", json=REGISTER).status_code == 201
    res = client.post("/api/auth/register", json={**REGISTER, "email": "new.user@example.COM"})
    assert res.status_code == 409
    assert res.get_json()["error"] == "email_taken"


@pytest.mark.parametrize(
    "payload",
    [
        {**REGISTER, "password": "short"},
        {**REGISTER, "email": "not-an-email"},
        {**REGISTER, "full_name": "  "},
        {"email": "a@b.co"},
        {},
    ],
)
def test_register_validation(client: FlaskClient, payload: dict[str, str]) -> None:
    res = client.post("/api/auth/register", json=payload)
    assert res.status_code == 422
    body = res.get_json()
    assert body["error"] == "validation_error" and body["details"]["fields"]


def test_malformed_json_is_a_400(client: FlaskClient) -> None:
    res = client.post("/api/auth/register", data="{nope", content_type="application/json")
    assert res.status_code == 400
    assert res.get_json()["error"] == "validation_error"
    res = client.post("/api/auth/register", json=["a list"])
    assert res.status_code == 400


def test_login_success_and_failures(client: FlaskClient, guest: User) -> None:
    ok = client.post("/api/auth/login", json={"email": "GUEST@example.com", "password": PASSWORD})
    assert ok.status_code == 200 and ok.get_json()["user"]["email"] == "guest@example.com"
    for creds in (
        {"email": "guest@example.com", "password": "wrong-password"},
        {"email": "nobody@example.com", "password": PASSWORD},
    ):
        bad = client.post("/api/auth/login", json=creds)
        assert bad.status_code == 401
        assert bad.get_json()["error"] == "unauthorized"


def test_protected_endpoint_requires_a_valid_token(client: FlaskClient, guest: User) -> None:
    assert client.get("/api/bookings").status_code == 401
    for header in ("Bearer", "Basic abc", "Bearer not.a.jwt", f"Bearer {'x' * 20}"):
        res = client.get("/api/bookings", headers={"Authorization": header})
        assert res.status_code == 401, header
        assert res.get_json()["error"] == "unauthorized"


def test_expired_and_forged_tokens_are_rejected(client: FlaskClient, guest: User) -> None:
    expired = auth_lib.create_token(guest, JWT_SECRET, now=FIXED_NOW - timedelta(minutes=61))
    forged = auth_lib.create_token(guest, "another-secret-another-secret-123456")
    for token in (expired, forged):
        res = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


def test_token_with_wrong_algorithm_or_missing_claims_is_rejected(
    client: FlaskClient, guest: User
) -> None:
    none_alg = jwt.encode({"sub": "1", "role": "staff"}, key="", algorithm="none")
    no_role = jwt.encode({"sub": "1", "exp": FIXED_NOW.timestamp() + 9e9}, JWT_SECRET)
    bad_sub = jwt.encode({"sub": "abc", "role": "guest", "exp": 9999999999}, JWT_SECRET)
    for token in (none_alg, no_role, bad_sub):
        res = client.get("/api/bookings", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401


def test_token_for_a_deleted_user_is_rejected(client: FlaskClient, guest: User) -> None:
    headers = auth_headers(guest)
    from sqlalchemy import text

    from app.extensions import db

    db.session.execute(text("DELETE FROM users"))
    db.session.commit()
    assert client.get("/api/bookings", headers=headers).status_code == 401


def test_role_comes_from_the_database_not_from_the_token(client: FlaskClient, guest: User) -> None:
    forged = jwt.encode(
        {"sub": str(guest.id), "role": "staff", "exp": FIXED_NOW.timestamp() + 3600}, JWT_SECRET
    )
    res = client.get("/api/rooms", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 403
