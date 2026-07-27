from datetime import datetime, timedelta, timezone

from jose import jwt

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from tests.conftest import TEST_PASSWORD


def register_payload(email: str = "new@example.com", **extra) -> dict:
    return {"email": email, "password": "somepassword123", **extra}


# --- register ---


def test_register_returns_created_user(client):
    response = client.post("/auth/register", json=register_payload())
    assert response.status_code == 201

    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == UserRole.USER.value
    # The response schema must never leak the password back out
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_rejects_duplicate_email(client, user):
    response = client.post("/auth/register", json=register_payload(email=user.email))
    assert response.status_code == 400


def test_register_rejects_invalid_email(client):
    response = client.post("/auth/register", json=register_payload(email="not-an-email"))
    assert response.status_code == 422


def test_register_ignores_a_role_sent_by_the_client(client):
    """Privilege escalation attempt: the router builds the User object
    field by field and never reads `role` from the body, so this extra
    key must be dropped rather than honoured."""
    response = client.post("/auth/register", json=register_payload(role="admin"))
    assert response.status_code == 201
    assert response.json()["role"] == UserRole.USER.value


def test_registered_user_can_log_in(client):
    client.post("/auth/register", json=register_payload())
    response = client.post(
        "/auth/login", data={"username": "new@example.com", "password": "somepassword123"}
    )
    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


# --- login ---


def test_login_returns_a_token(client, user):
    response = client.post(
        "/auth/login", data={"username": user.email, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_rejects_wrong_password(client, user):
    response = client.post(
        "/auth/login", data={"username": user.email, "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_login_rejects_unknown_email(client):
    response = client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": TEST_PASSWORD}
    )
    assert response.status_code == 401


def test_login_error_does_not_reveal_whether_the_email_exists(client, user):
    """Both failures must look identical, otherwise the endpoint becomes a
    way to enumerate which emails are registered."""
    wrong_password = client.post(
        "/auth/login", data={"username": user.email, "password": "wrong-password"}
    )
    unknown_email = client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": TEST_PASSWORD}
    )
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


# --- /auth/me and token validation ---


def test_me_returns_the_token_owner(user_client, user):
    response = user_client.get("/auth/me")
    assert response.status_code == 200
    assert response.json()["id"] == user.id


def test_me_requires_a_token(client):
    assert client.get("/auth/me").status_code == 401


def test_me_rejects_a_malformed_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401


def test_me_rejects_a_token_signed_with_another_key(client, user):
    """A well-formed JWT is not enough - it has to be signed with our
    SECRET_KEY, or anyone could mint their own."""
    forged = jwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(minutes=30)},
        "some-other-secret",
        algorithm=settings.algorithm,
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_me_rejects_an_expired_token(client, user, monkeypatch):
    # create_access_token reads the expiry from settings at call time, so
    # a negative value produces an already-expired token.
    monkeypatch.setattr(settings, "access_token_expire_minutes", -1)
    expired = create_access_token(subject=str(user.id))
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401


def test_me_rejects_a_token_for_a_user_that_no_longer_exists(client, db_session, user):
    token = create_access_token(subject=str(user.id))
    db_session.delete(user)
    db_session.commit()

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
