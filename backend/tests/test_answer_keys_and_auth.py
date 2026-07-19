from __future__ import annotations

import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from jose import jwt

import auth


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    auth._clear_jwks_cache()
    yield
    auth._clear_jwks_cache()


def _base64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _rsa_signing_material(kid: str) -> tuple[bytes, dict[str, object]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_numbers = private_key.public_key().public_numbers()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_jwk: dict[str, object] = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "RS256",
        "n": _base64url_uint(public_numbers.n),
        "e": _base64url_uint(public_numbers.e),
    }
    return private_pem, public_jwk


def _ec_signing_material(kid: str) -> tuple[bytes, dict[str, object]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_numbers = private_key.public_key().public_numbers()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_jwk: dict[str, object] = {
        "kty": "EC",
        "kid": kid,
        "use": "sig",
        "key_ops": ["verify"],
        "alg": "ES256",
        "crv": "P-256",
        "x": _base64url_uint(public_numbers.x),
        "y": _base64url_uint(public_numbers.y),
    }
    return private_pem, public_jwk


def _asymmetric_token(
    private_pem: bytes,
    *,
    kid: str,
    issuer: str,
    algorithm: str = "RS256",
) -> str:
    return jwt.encode(
        {
            "sub": "asymmetric-teacher",
            "iss": issuer,
            "app_metadata": {"role": "teacher"},
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        private_pem,
        algorithm=algorithm,
        headers={"kid": kid},
    )


def test_admin_role_takes_precedence_over_teacher_role() -> None:
    assert auth._authorized_role(["teacher", "admin"]) == "admin"


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


def test_authentication_enforces_token_and_teacher_admin_role(client, monkeypatch) -> None:
    secret = "test-secret-that-is-long-enough"
    secured_settings = replace(
        auth.settings,
        auth_required=True,
        supabase_jwks_url="https://project.supabase.co/auth/v1/.well-known/jwks.json",
        supabase_jwt_secret=secret,
        supabase_jwt_audience=None,
        supabase_jwt_issuer=None,
    )
    monkeypatch.setattr(auth, "settings", secured_settings)
    monkeypatch.setattr(
        auth,
        "_fetch_jwks",
        lambda _: pytest.fail("HS256 fallback must not fetch JWKS"),
    )

    missing = client.get("/exams")
    assert missing.status_code == 401
    assert missing.json()["success"] is False

    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)
    student_token = jwt.encode(
        {"sub": "student-id", "role": "student", "exp": expiry},
        secret,
        algorithm="HS256",
    )
    forbidden = client.get(
        "/exams", headers={"Authorization": f"Bearer {student_token}"}
    )
    assert forbidden.status_code == 403

    teacher_token = jwt.encode(
        {
            "sub": "teacher-id",
            "app_metadata": {"role": "teacher"},
            "exp": expiry,
        },
        secret,
        algorithm="HS256",
    )
    authorized = client.get(
        "/exams", headers={"Authorization": f"Bearer {teacher_token}"}
    )
    assert authorized.status_code == 200


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_asymmetric_jwks_verification_uses_cached_key(
    client, monkeypatch, algorithm: str
) -> None:
    issuer = "https://project.supabase.co/auth/v1"
    jwks_url = f"{issuer}/.well-known/jwks.json"
    material_factory = (
        _ec_signing_material if algorithm == "ES256" else _rsa_signing_material
    )
    private_pem, public_jwk = material_factory("active-key")
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_url="https://project.supabase.co",
            supabase_jwks_url=jwks_url,
            supabase_jwt_secret=None,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=issuer,
        ),
    )
    fetch_count = 0

    def fetch_jwks(_: str):
        nonlocal fetch_count
        fetch_count += 1
        return (public_jwk,)

    monkeypatch.setattr(auth, "_fetch_jwks", fetch_jwks)
    token = _asymmetric_token(
        private_pem,
        kid="active-key",
        issuer=issuer,
        algorithm=algorithm,
    )
    headers = {"Authorization": f"Bearer {token}"}

    assert client.get("/exams", headers=headers).status_code == 200
    assert client.get("/exams", headers=headers).status_code == 200
    assert fetch_count == 1


def test_asymmetric_token_with_unknown_kid_is_rejected(client, monkeypatch) -> None:
    issuer = "https://project.supabase.co/auth/v1"
    private_pem, public_jwk = _rsa_signing_material("published-key")
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwks_url=f"{issuer}/.well-known/jwks.json",
            supabase_jwt_secret=None,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=issuer,
        ),
    )
    monkeypatch.setattr(auth, "_fetch_jwks", lambda _: (public_jwk,))
    token = _asymmetric_token(
        private_pem,
        kid="unpublished-key",
        issuer=issuer,
    )

    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert "not recognized" in response.json()["message"]


def test_asymmetric_key_fetch_failure_returns_503(client, monkeypatch) -> None:
    issuer = "https://project.supabase.co/auth/v1"
    jwks_url = f"{issuer}/.well-known/jwks.json"
    private_pem, _ = _rsa_signing_material("active-key")
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwks_url=jwks_url,
            supabase_jwt_secret=None,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=issuer,
        ),
    )

    original_get = httpx.Client.get

    def fail_fetch(self, url, **kwargs):
        if str(url) == jwks_url:
            raise httpx.ConnectError(
                "JWKS endpoint unavailable",
                request=httpx.Request("GET", url),
            )
        return original_get(self, url, **kwargs)

    monkeypatch.setattr(httpx.Client, "get", fail_fetch)
    token = _asymmetric_token(
        private_pem,
        kid="active-key",
        issuer=issuer,
    )

    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 503
    assert response.json()["success"] is False
    assert "unavailable" in response.json()["message"]


def test_expired_token_is_rejected(client, monkeypatch) -> None:
    secret = "test-secret-that-is-long-enough"
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwt_secret=secret,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=None,
        ),
    )
    expired = jwt.encode(
        {
            "sub": "teacher-id",
            "role": "teacher",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        secret,
        algorithm="HS256",
    )
    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {expired}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["message"].lower()


def test_user_metadata_cannot_grant_a_privileged_role(client, monkeypatch) -> None:
    secret = "test-secret-that-is-long-enough"
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwt_secret=secret,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=None,
        ),
    )
    token = jwt.encode(
        {
            "sub": "unprivileged-user",
            "role": "authenticated",
            "user_metadata": {"role": "admin"},
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    response = client.get(
        "/exams", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


def test_teacher_exam_ownership_and_admin_override(client, monkeypatch) -> None:
    secret = "test-secret-that-is-long-enough"
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwt_secret=secret,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=None,
        ),
    )
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    def headers(subject: str, role: str) -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": subject,
                "app_metadata": {"role": role},
                "exp": expiry,
            },
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    teacher_a = headers("teacher-a", "teacher")
    teacher_b = headers("teacher-b", "teacher")
    admin = headers("admin-user", "admin")
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
    assert client.get(
        f"/exams/{exam_id}/results", headers=teacher_b
    ).status_code == 404
    assert client.get(
        f"/exams/{exam_id}/results/export", headers=teacher_b
    ).status_code == 404
    assert client.delete(f"/exams/{exam_id}", headers=teacher_b).status_code == 404
    assert client.get(f"/exams/{exam_id}", headers=admin).status_code == 200
    assert client.delete(f"/exams/{exam_id}", headers=admin).status_code == 200


def test_student_roll_numbers_are_tenant_scoped_and_results_are_snapshotted(
    client, make_sheet, monkeypatch
) -> None:
    secret = "test-secret-that-is-long-enough"
    monkeypatch.setattr(
        auth,
        "settings",
        replace(
            auth.settings,
            auth_required=True,
            supabase_jwt_secret=secret,
            supabase_jwt_audience=None,
            supabase_jwt_issuer=None,
        ),
    )
    expiry = datetime.now(timezone.utc) + timedelta(minutes=5)

    def headers(subject: str) -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": subject,
                "app_metadata": {"role": "teacher"},
                "exp": expiry,
            },
            secret,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    teacher_a = headers("tenant-a")
    teacher_b = headers("tenant-b")

    def create_exam(owner_headers: dict[str, str], name: str) -> str:
        created = client.post(
            "/exams",
            headers=owner_headers,
            json={
                "name": name,
                "total_questions": 10,
                "options_per_question": 4,
            },
        )
        assert created.status_code == 201
        exam_id = created.json()["data"]["id"]
        answers = {
            str(question): "ABCD"[(question - 1) % 4]
            for question in range(1, 11)
        }
        assert client.post(
            f"/exams/{exam_id}/answer-key/manual",
            headers=owner_headers,
            json={"answers": answers},
        ).status_code == 200
        return exam_id

    exam_a = create_exam(teacher_a, "Tenant A Exam")
    exam_b = create_exam(teacher_b, "Tenant B Exam")
    sheet = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1])

    def scan(
        exam_id: str,
        owner_headers: dict[str, str],
        *,
        name: str,
        class_name: str,
    ) -> dict[str, object]:
        with sheet.open("rb") as image:
            response = client.post(
                f"/exams/{exam_id}/scan",
                headers=owner_headers,
                files={"files": ("student.png", image, "image/png")},
                data={
                    "metadata": json.dumps(
                        [
                            {
                                "name": name,
                                "roll_number": "SHARED-001",
                                "class_name": class_name,
                            }
                        ]
                    )
                },
            )
        assert response.status_code == 200, response.text
        return response.json()["data"]["results"][0]

    first_a = scan(exam_a, teacher_a, name="Alice", class_name="A-Class")
    first_b = scan(exam_b, teacher_b, name="Bob", class_name="B-Class")
    assert first_a["student"]["name"] == "Alice"
    assert first_b["student"]["name"] == "Bob"
    assert first_a["student"]["id"] != first_b["student"]["id"]

    second_a = scan(
        exam_a,
        teacher_a,
        name="Alice Updated",
        class_name="A-Class-Updated",
    )
    assert second_a["student"]["name"] == "Alice Updated"
    historical_a = client.get(
        f"/results/{first_a['id']}", headers=teacher_a
    ).json()["data"]
    assert historical_a["student"]["name"] == "Alice"
    assert historical_a["student"]["class_name"] == "A-Class"

    tenant_b_results = client.get(
        f"/exams/{exam_b}/results", headers=teacher_b
    ).json()["data"]["results"]
    assert len(tenant_b_results) == 1
    assert tenant_b_results[0]["student"]["name"] == "Bob"
    assert client.get(
        f"/results/{first_b['id']}", headers=teacher_a
    ).status_code == 404
