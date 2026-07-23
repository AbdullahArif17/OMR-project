from __future__ import annotations

from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import pytest

from services.omr_engine import (
    AmbiguousMarkError,
    IncompleteSheetError,
    NoBubblesDetectedError,
    UnansweredQuestionError,
    detect_answers,
    grade_answers,
)


ImageTransform = Callable[[np.ndarray], np.ndarray]


def _rotate_with_full_canvas(image: np.ndarray, angle: float) -> np.ndarray:
    height, width = image.shape[:2]
    transform = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    cosine = abs(transform[0, 0])
    sine = abs(transform[0, 1])
    output_width = int(round(height * sine + width * cosine))
    output_height = int(round(height * cosine + width * sine))
    transform[0, 2] += output_width / 2 - width / 2
    transform[1, 2] += output_height / 2 - height / 2
    return cv2.warpAffine(
        image,
        transform,
        (output_width, output_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _moderate_perspective(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    source = np.float32(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
    )
    destination = np.float32(
        [
            [55, 25],
            [width + 20, 0],
            [width - 10, height + 30],
            [15, height + 55],
        ]
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(
        image,
        transform,
        (width + 80, height + 80),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(205, 205, 205),
    )


def _affine_skew(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    transform = np.float32([[1.0, 0.10, 12], [0.035, 1.0, 6]])
    return cv2.warpAffine(
        image,
        transform,
        (width + 90, height + 50),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _uneven_illumination_with_jpeg_noise(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    row_coordinates, column_coordinates = np.mgrid[0:height, 0:width]
    illumination = 0.42 + 0.58 * (
        0.65 * column_coordinates / max(width - 1, 1)
        + 0.35 * row_coordinates / max(height - 1, 1)
    )
    shaded = np.clip(
        image.astype(np.float32) * illumination[..., None], 0, 255
    ).astype(np.uint8)
    noise = np.random.default_rng(20260719).normal(0, 3, shaded.shape)
    noisy = np.clip(shaded.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    encoded, jpeg = cv2.imencode(
        ".jpg", noisy, [cv2.IMWRITE_JPEG_QUALITY, 38]
    )
    assert encoded
    decoded = cv2.imdecode(jpeg, cv2.IMREAD_COLOR)
    assert decoded is not None
    return decoded


def _downscale(image: np.ndarray) -> np.ndarray:
    return cv2.resize(
        image,
        None,
        fx=0.42,
        fy=0.42,
        interpolation=cv2.INTER_AREA,
    )


def _combined_capture_degradation(image: np.ndarray) -> np.ndarray:
    return _uneven_illumination_with_jpeg_noise(
        _rotate_with_full_canvas(image, 7.0)
    )


def _write_transformed(
    source: Path,
    tmp_path: Path,
    name: str,
    transform: ImageTransform,
) -> Path:
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    assert image is not None
    transformed = transform(image)
    output = tmp_path / f"{name}.png"
    assert cv2.imwrite(str(output), transformed)
    return output


def test_grade_answers_includes_missing_and_incorrect_answers() -> None:
    grading = grade_answers(
        {1: "a", 2: "D", 4: "D"},
        {1: "A", 2: "B", 3: "C", 4: "D"},
    )

    assert grading["score"] == 2
    assert grading["total"] == 4
    assert grading["percentage"] == 50.0
    assert grading["breakdown"][1] == {
        "student": "A",
        "correct": "A",
        "result": True,
    }
    assert grading["breakdown"][3] == {
        "student": None,
        "correct": "C",
        "result": False,
    }


@pytest.mark.parametrize("option_count", [4, 5])
def test_detect_answers_from_real_contours(
    make_sheet, option_count: int
) -> None:
    selected = [index % option_count for index in range(10)]
    sheet = make_sheet(selected, option_count=option_count)

    detected = detect_answers(sheet, 10, option_count)

    assert detected.answers == {
        question: "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[answer]
        for question, answer in enumerate(selected, start=1)
    }


@pytest.mark.parametrize(
    ("name", "option_count", "transform"),
    [
        ("rotated-clockwise", 4, lambda image: _rotate_with_full_canvas(image, 8)),
        (
            "rotated-counterclockwise",
            5,
            lambda image: _rotate_with_full_canvas(image, -11),
        ),
        ("perspective", 4, _moderate_perspective),
        ("affine-skew", 5, _affine_skew),
        ("uneven-light-jpeg", 4, _uneven_illumination_with_jpeg_noise),
        ("downscaled", 4, _downscale),
        ("combined-capture", 5, _combined_capture_degradation),
    ],
)
def test_detect_answers_survives_moderate_capture_transformations(
    make_sheet,
    tmp_path: Path,
    name: str,
    option_count: int,
    transform: ImageTransform,
) -> None:
    selected = [index % option_count for index in range(10)]
    source = make_sheet(
        selected,
        option_count=option_count,
        filename=f"{name}-source.png",
    )
    transformed = _write_transformed(source, tmp_path, name, transform)

    detected = detect_answers(transformed, 10, option_count)

    assert detected.answers == {
        question: "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[answer]
        for question, answer in enumerate(selected, start=1)
    }


def test_detect_answers_rejects_unanswered_question(make_sheet) -> None:
    sheet = make_sheet([0, 1, None, 3, 0, 1, 2, 3, 0, 1])

    with pytest.raises(UnansweredQuestionError, match="Question 3"):
        detect_answers(sheet, 10, 4)


def test_detect_answers_rejects_multiple_marks(make_sheet) -> None:
    sheet = make_sheet([0, 1, (1, 2), 3, 0, 1, 2, 3, 0, 1])

    with pytest.raises(AmbiguousMarkError, match="Question 3"):
        detect_answers(sheet, 10, 4)


@pytest.mark.parametrize(
    ("answers", "expected_error", "message"),
    [
        (
            [0, 1, None, 3, 0, 1, 2, 3, 0, 1],
            UnansweredQuestionError,
            "Question 3",
        ),
        (
            [0, 1, (1, 2), 3, 0, 1, 2, 3, 0, 1],
            AmbiguousMarkError,
            "Question 3",
        ),
    ],
)
def test_transformed_uncertain_marks_are_rejected(
    make_sheet,
    tmp_path: Path,
    answers,
    expected_error,
    message: str,
) -> None:
    source = make_sheet(answers, filename="uncertain-source.png")
    transformed = _write_transformed(
        source,
        tmp_path,
        "uncertain-transformed",
        _combined_capture_degradation,
    )

    with pytest.raises(expected_error, match=message):
        detect_answers(transformed, 10, 4)


def test_missing_bubble_geometry_is_rejected(make_sheet, tmp_path: Path) -> None:
    source = make_sheet([0, 1, 2, 3, 0, 1, 2, 3, 0, 1])
    image = cv2.imread(str(source), cv2.IMREAD_COLOR)
    assert image is not None
    cv2.rectangle(image, (48, 129), (92, 177), (255, 255, 255), -1)
    damaged = tmp_path / "missing-bubble.png"
    assert cv2.imwrite(str(damaged), image)

    with pytest.raises(IncompleteSheetError):
        detect_answers(damaged, 10, 4)


def test_detect_answers_rejects_blank_image(tmp_path: Path) -> None:
    blank_path = tmp_path / "blank.png"
    assert cv2.imwrite(
        str(blank_path), np.full((600, 600, 3), 255, dtype=np.uint8)
    )

    with pytest.raises(NoBubblesDetectedError):
        detect_answers(blank_path, 10, 4)
