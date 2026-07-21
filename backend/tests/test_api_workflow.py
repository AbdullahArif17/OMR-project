from __future__ import annotations

import json
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from config import settings
from routers import scanner as scanner_router


def _create_exam(client, *, name: str = "Biology Midterm") -> dict[str, object]:
    response = client.post(
        "/exams",
        json={
            "name": name,
            "subject": "Biology",
            "total_questions": 10,
            "options_per_question": 4,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _answer_map() -> dict[str, str]:
    return {
        str(question): "ABCD"[(question - 1) % 4]
        for question in range(1, 11)
    }


def test_complete_exam_scan_results_export_and_delete_workflow(
    client, make_sheet
) -> None:
    exam = _create_exam(client)
    exam_id = exam["id"]
    key_response = client.post(
        f"/exams/{exam_id}/answer-key/manual",
        json={"answers": _answer_map()},
    )
    assert key_response.status_code == 200

    selected = [0, 1, 2, 3, 0, 1, 2, 3, 0, 0]
    sheet_path: Path = make_sheet(selected)
    metadata = json.dumps(
        [{"name": "Ada Lovelace", "roll_number": "BIO-001", "class": "10-A"}]
    )
    with sheet_path.open("rb") as sheet:
        scan_response = client.post(
            f"/exams/{exam_id}/scan",
            files={"files": ("ada.png", sheet, "image/png")},
            data={"metadata": metadata},
        )
    assert scan_response.status_code == 200, scan_response.text
    scan_data = scan_response.json()["data"]
    assert scan_data["processed_count"] == 1
    assert scan_data["failed_count"] == 0
    result = scan_data["results"][0]
    assert result["score"] == 9
    assert result["percentage"] == 90.0
    assert result["student"]["name"] == "Ada Lovelace"
    assert result["student"]["class_name"] == "10-A"
    assert result["filename"] == "ada.png"
    stored_scan = settings.upload_dir / result["source_file"]
    assert stored_scan.is_file()

    list_response = client.get(f"/exams/{exam_id}/results")
    assert list_response.status_code == 200
    result_data = list_response.json()["data"]
    assert result_data["summary"] == {
        "average_score": 9.0,
        "highest_score": 9,
        "lowest_score": 9,
        "pass_rate": 100.0,
        "total_scans": 1,
    }

    detail_response = client.get(f"/results/{result['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["data"]["exam"]["id"] == exam_id

    export_response = client.get(f"/exams/{exam_id}/results/export")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    assert "BIO-001,Ada Lovelace,10-A,9,10,90.00,A,ada.png" in export_response.text

    delete_response = client.delete(f"/exams/{exam_id}")
    assert delete_response.status_code == 200
    assert not stored_scan.exists()
    assert client.get(f"/exams/{exam_id}").status_code == 404
    assert client.get(f"/results/{result['id']}").status_code == 404


def test_batch_scan_processes_valid_files_and_reports_invalid_files(
    client, make_sheet
) -> None:
    exam = _create_exam(client, name="Batch Exam")
    exam_id = exam["id"]
    client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    )
    valid_sheet = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1])
    with valid_sheet.open("rb") as valid:
        response = client.post(
            f"/exams/{exam_id}/scan",
            files=[
                ("files", ("valid.png", valid, "image/png")),
                ("files", ("broken.png", b"not-an-image", "image/png")),
            ],
            data={
                "student_metadata": json.dumps(
                    [
                        {"name": "Valid Student", "roll_number": "B-1"},
                        {"name": "Broken Student", "roll_number": "B-2"},
                    ]
                )
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["processed_count"] == 1
    assert data["failed_count"] == 1
    assert data["status"] == "partial"
    assert data["errors"][0]["filename"] == "broken.png"
    assert data["errors"][0] == {
        "filename": "broken.png",
        "message": "broken.png does not contain a recognized .png file",
        "stage": "upload",
        "status_code": 422,
        "retryable": False,
    }


def test_json_errors_always_use_the_envelope(client) -> None:
    response = client.post(
        "/exams",
        json={
            "name": "",
            "total_questions": 2,
            "options_per_question": 7,
        },
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["success"] is False
    assert payload["data"]["errors"]
    assert isinstance(payload["message"], str)


def test_scanned_master_answer_key_uses_the_omr_engine(client, make_sheet) -> None:
    exam = _create_exam(client, name="Scanned Key")
    master = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="master.png")
    with master.open("rb") as image:
        response = client.post(
            f"/exams/{exam['id']}/answer-key/scan",
            files={"file": ("master.png", image, "image/png")},
        )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["answers"] == _answer_map()


def test_zip_upload_expands_and_grades_each_sheet(client, make_sheet, tmp_path) -> None:
    exam = _create_exam(client, name="ZIP Batch")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    first = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="one.png")
    second = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="two.png")
    archive_path = tmp_path / "sheets.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("one.png", first.read_bytes())
        archive.writestr("folder/two.png", second.read_bytes())
    with archive_path.open("rb") as archive:
        response = client.post(
            f"/exams/{exam_id}/scan",
            files={"file": ("sheets.zip", archive, "application/zip")},
            data={
                "metadata": json.dumps(
                    [{"name": "ZIP Student", "roll_number": "ZIP-1"}]
                )
            },
        )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["processed_count"] == 2
    assert data["errors"] == []
    assert {item["student"]["roll_number"] for item in data["results"]} == {
        "ZIP-1",
        "ZIP-1-2",
    }


def test_scan_retry_with_idempotency_key_returns_original_batch_once(
    client, make_sheet
) -> None:
    exam = _create_exam(client, name="Idempotent Batch")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    sheet_path = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="retry.png"
    )
    headers = {"Idempotency-Key": "scan-retry-0001"}
    scans_dir = settings.upload_dir / "scans"
    before = set(scans_dir.glob("*")) if scans_dir.exists() else set()

    def submit():
        with sheet_path.open("rb") as sheet:
            return client.post(
                f"/exams/{exam_id}/scan",
                headers=headers,
                files={"files": ("retry.png", sheet, "image/png")},
                data={"metadata": json.dumps([{"roll_number": "RETRY-1"}])},
            )

    first = submit()
    assert first.status_code == 200, first.text
    after_first = set(scans_dir.glob("*"))
    assert len(after_first - before) == 1

    second = submit()
    assert second.status_code == 200, second.text
    assert second.json() == first.json()
    assert set(scans_dir.glob("*")) == after_first
    listed = client.get(f"/exams/{exam_id}/results").json()["data"]
    assert listed["summary"]["total_scans"] == 1


def test_reused_idempotency_key_with_different_payload_is_rejected(
    client, make_sheet
) -> None:
    exam = _create_exam(client, name="Idempotent Mismatch")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    headers = {"Idempotency-Key": "scan-reuse-0001"}
    scans_dir = settings.upload_dir / "scans"

    first_sheet = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="reuse-a.png"
    )
    with first_sheet.open("rb") as sheet:
        first = client.post(
            f"/exams/{exam_id}/scan",
            headers=headers,
            files={"files": ("reuse-a.png", sheet, "image/png")},
            data={"metadata": json.dumps([{"roll_number": "REUSE-1"}])},
        )
    assert first.status_code == 200, first.text
    after_first = set(scans_dir.glob("*"))

    # Same key, different metadata: reusing the token for a new submission must
    # not silently drop the new upload.
    with first_sheet.open("rb") as sheet:
        conflict = client.post(
            f"/exams/{exam_id}/scan",
            headers=headers,
            files={"files": ("reuse-a.png", sheet, "image/png")},
            data={"metadata": json.dumps([{"roll_number": "REUSE-2"}])},
        )
    assert conflict.status_code == 409, conflict.text
    assert set(scans_dir.glob("*")) == after_first
    listed = client.get(f"/exams/{exam_id}/results").json()["data"]
    assert listed["summary"]["total_scans"] == 1


def test_unexpected_scan_failure_rolls_back_results_and_removes_uploads(
    client, make_sheet, monkeypatch
) -> None:
    exam = _create_exam(client, name="Atomic Batch")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    first_path = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="atomic-one.png"
    )
    second_path = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="atomic-two.png"
    )
    original_detect = scanner_router.detect_answers
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("simulated scanner outage")
        return original_detect(*args, **kwargs)

    monkeypatch.setattr(scanner_router, "detect_answers", fail_second)
    scans_dir = settings.upload_dir / "scans"
    before = set(scans_dir.glob("*")) if scans_dir.exists() else set()
    with pytest.raises(RuntimeError, match="simulated scanner outage"):
        with first_path.open("rb") as first, second_path.open("rb") as second:
            client.post(
                f"/exams/{exam_id}/scan",
                files=[
                    ("files", ("atomic-one.png", first, "image/png")),
                    ("files", ("atomic-two.png", second, "image/png")),
                ],
            )

    assert set(scans_dir.glob("*")) == before
    listed = client.get(f"/exams/{exam_id}/results").json()["data"]
    assert listed["summary"]["total_scans"] == 0


def test_commit_failure_rolls_back_results_and_removes_upload(
    client, make_sheet, monkeypatch
) -> None:
    exam = _create_exam(client, name="Commit Failure")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    sheet_path = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="commit.png"
    )

    def fail_commit(_db):
        raise RuntimeError("simulated database outage")

    monkeypatch.setattr(scanner_router, "_commit_transaction", fail_commit)
    scans_dir = settings.upload_dir / "scans"
    before = set(scans_dir.glob("*")) if scans_dir.exists() else set()
    with pytest.raises(RuntimeError, match="simulated database outage"):
        with sheet_path.open("rb") as sheet:
            client.post(
                f"/exams/{exam_id}/scan",
                files={"files": ("commit.png", sheet, "image/png")},
            )

    assert set(scans_dir.glob("*")) == before
    listed = client.get(f"/exams/{exam_id}/results").json()["data"]
    assert listed["summary"]["total_scans"] == 0


def test_expanded_sheet_limit_rejects_oversized_archive_without_partial_results(
    client, make_sheet, tmp_path, monkeypatch
) -> None:
    exam = _create_exam(client, name="Bounded ZIP")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    first = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="limit-one.png"
    )
    second = make_sheet(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="limit-two.png"
    )
    archive_path = tmp_path / "too-many.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("one.png", first.read_bytes())
        archive.writestr("two.png", second.read_bytes())
    monkeypatch.setattr(
        scanner_router,
        "settings",
        replace(scanner_router.settings, max_files_per_request=1),
    )
    with archive_path.open("rb") as archive:
        response = client.post(
            f"/exams/{exam_id}/scan",
            files={"files": ("too-many.zip", archive, "application/zip")},
        )

    assert response.status_code == 422
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["processed_count"] == 0
    assert data["errors"][0]["stage"] == "normalization"
    assert client.get(f"/exams/{exam_id}/results").json()["data"]["summary"][
        "total_scans"
    ] == 0


def test_unanswered_sheet_reports_a_clear_detection_failure(client, make_sheet) -> None:
    exam = _create_exam(client, name="Blank Answers")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    sheet_path = make_sheet(
        [None, 1, 2, 3, 0, 1, 2, 3, 0, 1], filename="blank.png"
    )
    with sheet_path.open("rb") as sheet:
        response = client.post(
            f"/exams/{exam_id}/scan",
            files={"files": ("blank.png", sheet, "image/png")},
        )

    assert response.status_code == 422
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["errors"][0]["stage"] == "detection"
    assert data["errors"][0]["message"] == "Question 1 appears unanswered"


def test_combined_upload_size_is_bounded_before_processing(
    client, monkeypatch
) -> None:
    exam = _create_exam(client, name="Batch Byte Limit")
    exam_id = exam["id"]
    assert client.post(
        f"/exams/{exam_id}/answer-key/manual", json={"answers": _answer_map()}
    ).status_code == 200
    monkeypatch.setattr(
        scanner_router,
        "settings",
        replace(scanner_router.settings, max_batch_size_mb=1),
    )
    response = client.post(
        f"/exams/{exam_id}/scan",
        files=[
            ("files", ("first.png", b"x" * 600_000, "image/png")),
            ("files", ("second.png", b"x" * 600_000, "image/png")),
        ],
    )

    assert response.status_code == 413
    data = response.json()["data"]
    assert data["status"] == "failed"
    assert data["errors"] == [
        {
            "filename": "batch",
            "message": "The combined uploads exceed the 1 MB batch limit",
            "stage": "upload",
            "status_code": 413,
            "retryable": False,
        }
    ]
