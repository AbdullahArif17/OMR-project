from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

import auth
from database import SessionLocal
from models import User


SECRET = "test-secret-that-is-long-enough-for-production-use"
ADMIN_PASSWORD = "admin-console-password"


@pytest.fixture()
def secured(monkeypatch):
    """Turn on real authentication with a signing secret for a test."""
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            auth_jwt_secret=SECRET,
            admin_password=ADMIN_PASSWORD,
        ),
    )
    yield


def _create_user(email: str, *, role: str = "teacher", password: str = "sup3r-secret-pw") -> User:
    session = SessionLocal()
    try:
        user = User(
            email=email.strip().lower(),
            password_hash=auth.hash_password(password),
            name=email.split("@")[0],
            role=role,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user
    finally:
        session.close()


def _headers(user: User) -> dict[str, str]:
    token, _ = auth.create_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _admin_headers() -> dict[str, str]:
    token, _ = auth.create_admin_access_token()
    return {"Authorization": f"Bearer {token}"}


# --- Answer-key behaviour (auth bypass in default test config) --------------


def _exam(client) -> str:
    response = client.post(
        "/exams",
        json={
            "name": "CSV Exam",
            "total_questions": 10,
            "options_per_question": 4,
        },
    )
    return response.json()["data"]["id"]


def test_csv_answer_key_is_validated_and_retrievable(client) -> None:
    exam_id = _exam(client)
    csv_body = "question,answer\n" + "\n".join(
        f"{question},{'ABCD'[(question - 1) % 4]}" for question in range(1, 11)
    )
    response = client.post(
        f"/exams/{exam_id}/answer-key/csv",
        files={"file": ("key.csv", csv_body.encode(), "text/csv")},
    )
    assert response.status_code == 200, response.text
    get_response = client.get(f"/exams/{exam_id}/answer-key")
    assert get_response.status_code == 200
    assert len(get_response.json()["data"]["answers"]) == 10

    duplicate_csv = "question,answer\n1,A\n1,B\n"
    duplicate_response = client.post(
        f"/exams/{exam_id}/answer-key/csv",
        files={"file": ("key.csv", duplicate_csv.encode(), "text/csv")},
    )
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["success"] is False


def test_manual_answer_key_must_be_complete_and_use_valid_options(client) -> None:
    exam_id = _exam(client)
    incomplete = client.post(
        f"/exams/{exam_id}/answer-key/manual",
        json={"answers": {"1": "A"}},
    )
    assert incomplete.status_code == 422
    assert "missing questions" in incomplete.json()["message"]

    answers = {str(question): "A" for question in range(1, 11)}
    answers["10"] = "E"
    invalid = client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": answers}
    )
    assert invalid.status_code == 422
    assert "Question 10" in invalid.json()["message"]


# --- Authentication ---------------------------------------------------------


def test_password_hash_roundtrip_and_length_guard() -> None:
    stored = auth.hash_password("correct horse battery staple")
    assert stored != "correct horse battery staple"
    assert auth.verify_password("correct horse battery staple", stored)
    assert not auth.verify_password("wrong password", stored)
    assert not auth.verify_password("x" * 100, stored)


def test_missing_token_is_rejected_when_auth_required(client, secured) -> None:
    response = client.get("/exams")
    assert response.status_code == 401
    assert response.json()["success"] is False


def test_login_issues_tokens_and_authorizes_requests(client, secured) -> None:
    _create_user("teacher@example.com", password="sup3r-secret-pw")
    login = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "sup3r-secret-pw"},
    )
    assert login.status_code == 200, login.text
    data = login.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "teacher"
    access = data["access_token"]

    authorized = client.get(
        "/exams", headers={"Authorization": f"Bearer {access}"}
    )
    assert authorized.status_code == 200

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["data"]["email"] == "teacher@example.com"


def test_login_rejects_wrong_password(client, secured) -> None:
    _create_user("teacher@example.com", password="sup3r-secret-pw")
    response = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert "Incorrect" in response.json()["message"]


def test_expired_access_token_is_rejected(client, secured) -> None:
    user = _create_user("teacher@example.com")
    expired = jwt.encode(
        {
            "sub": str(user.id),
            "role": "teacher",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        SECRET,
        algorithm="HS256",
    )
    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401


def test_refresh_token_is_a_non_access_token(client, secured) -> None:
    # A token missing type=access must not be usable as a bearer credential.
    user = _create_user("teacher@example.com")
    wrong_type = jwt.encode(
        {
            "sub": str(user.id),
            "role": "teacher",
            "type": "refresh",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {wrong_type}"}
    )
    assert response.status_code == 401


def test_refresh_rotates_and_old_token_is_revoked(client, secured) -> None:
    _create_user("teacher@example.com", password="sup3r-secret-pw")
    login = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "sup3r-secret-pw"},
    ).json()["data"]
    first_refresh = login["refresh_token"]

    rotated = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert rotated.status_code == 200, rotated.text
    new_refresh = rotated.json()["data"]["refresh_token"]
    assert new_refresh != first_refresh

    # The rotated-away token can no longer be used.
    reused = client.post("/auth/refresh", json={"refresh_token": first_refresh})
    assert reused.status_code == 401


def test_logout_revokes_the_refresh_token(client, secured) -> None:
    _create_user("teacher@example.com", password="sup3r-secret-pw")
    login = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "sup3r-secret-pw"},
    ).json()["data"]
    refresh_token = login["refresh_token"]

    assert client.post(
        "/auth/logout", json={"refresh_token": refresh_token}
    ).status_code == 200
    assert client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    ).status_code == 401


def test_deactivated_account_cannot_use_a_live_access_token(client, secured) -> None:
    user = _create_user("teacher@example.com")
    headers = _headers(user)
    assert client.get("/exams", headers=headers).status_code == 200

    session = SessionLocal()
    try:
        db_user = session.get(User, user.id)
        db_user.is_active = False
        session.commit()
    finally:
        session.close()

    assert client.get("/exams", headers=headers).status_code == 401


def test_admin_login_requires_the_configured_password(client, secured) -> None:
    ok = client.post("/auth/admin/login", json={"password": ADMIN_PASSWORD})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["user"]["role"] == "admin"
    assert ok.json()["data"]["access_token"]

    wrong = client.post("/auth/admin/login", json={"password": "nope-nope-nope"})
    assert wrong.status_code == 401


def test_admin_login_disabled_without_admin_password(client, monkeypatch) -> None:
    monkeypatch.setattr(
        auth,
        "settings",
        replace(auth.settings, auth_required=True, auth_jwt_secret=SECRET, admin_password=None),
    )
    response = client.post("/auth/admin/login", json={"password": "anything-long"})
    assert response.status_code == 401


def test_only_admin_token_can_create_accounts(client, secured) -> None:
    teacher = _create_user("teacher@example.com", role="teacher")

    denied = client.post(
        "/auth/users",
        headers=_headers(teacher),
        json={"email": "new@example.com", "password": "another-strong-pw"},
    )
    assert denied.status_code == 403

    created = client.post(
        "/auth/users",
        headers=_admin_headers(),
        json={"email": "new@example.com", "password": "another-strong-pw"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["data"]["email"] == "new@example.com"
    assert created.json()["data"]["role"] == "teacher"

    duplicate = client.post(
        "/auth/users",
        headers=_admin_headers(),
        json={"email": "new@example.com", "password": "another-strong-pw"},
    )
    assert duplicate.status_code == 409


def test_api_cannot_create_an_admin_account(client, secured) -> None:
    response = client.post(
        "/auth/users",
        headers=_admin_headers(),
        json={
            "email": "second-admin@example.com",
            "password": "another-strong-pw",
            "role": "admin",
        },
    )
    # The role literal only accepts "teacher"; an admin role is rejected.
    assert response.status_code == 422, response.text


def test_admin_lists_only_teacher_accounts(client, secured) -> None:
    _create_user("teacher-a@example.com", role="teacher")
    _create_user("teacher-b@example.com", role="teacher")

    response = client.get("/auth/users", headers=_admin_headers())
    assert response.status_code == 200, response.text
    emails = {row["email"] for row in response.json()["data"]}
    assert emails == {"teacher-a@example.com", "teacher-b@example.com"}


def test_admin_deactivates_teacher_and_revokes_sessions(client, secured) -> None:
    teacher = _create_user("teacher@example.com", role="teacher")

    login = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "sup3r-secret-pw"},
    )
    assert login.status_code == 200, login.text
    refresh_token = login.json()["data"]["refresh_token"]

    updated = client.patch(
        f"/auth/users/{teacher.id}",
        headers=_admin_headers(),
        json={"is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["is_active"] is False

    # The teacher's outstanding refresh token was revoked on deactivation.
    refreshed = client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refreshed.status_code == 401
    # And they can no longer sign in.
    relogin = client.post(
        "/auth/login",
        json={"email": "teacher@example.com", "password": "sup3r-secret-pw"},
    )
    assert relogin.status_code == 401


def test_admin_session_refreshes_and_survives_without_a_db_row(client, secured) -> None:
    login = client.post(
        "/auth/admin/login", json={"password": ADMIN_PASSWORD}
    ).json()["data"]
    refreshed = client.post(
        "/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    new_access = refreshed.json()["data"]["access_token"]
    # The refreshed admin token still authorizes admin-only routes.
    assert client.get(
        "/auth/users", headers={"Authorization": f"Bearer {new_access}"}
    ).status_code == 200


def test_teacher_cannot_manage_accounts(client, secured) -> None:
    teacher = _create_user("teacher@example.com", role="teacher")
    target = _create_user("target@example.com", role="teacher")

    assert client.get("/auth/users", headers=_headers(teacher)).status_code == 403
    assert client.patch(
        f"/auth/users/{target.id}",
        headers=_headers(teacher),
        json={"is_active": False},
    ).status_code == 403


def test_teacher_exam_ownership_and_admin_override(client, secured) -> None:
    teacher_a = _headers(_create_user("a@example.com", role="teacher"))
    teacher_b = _headers(_create_user("b@example.com", role="teacher"))
    admin = _admin_headers()

    created = client.post(
        "/exams",
        headers=teacher_a,
        json={
            "name": "Private Exam",
            "total_questions": 10,
            "options_per_question": 4,
        },
    )
    assert created.status_code == 201
    exam_id = created.json()["data"]["id"]

    assert client.get("/exams", headers=teacher_b).json()["data"] == []
    assert client.get(f"/exams/{exam_id}", headers=teacher_b).status_code == 404
    answers = {str(question): "A" for question in range(1, 11)}
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual",
        headers=teacher_a,
        json={"answers": answers},
    ).status_code == 200
    assert client.get(
        f"/exams/{exam_id}/answer-key", headers=teacher_b
    ).status_code == 404
    assert client.get(f"/exams/{exam_id}", headers=admin).status_code == 200
    assert client.delete(f"/exams/{exam_id}", headers=admin).status_code == 200
