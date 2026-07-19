from __future__ import annotations

import math
import string
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

import cv2
import numpy as np


class OMRProcessingError(ValueError):
    """Raised when a sheet cannot be interpreted reliably."""


class NoBubblesDetectedError(OMRProcessingError):
    """Raised when no usable circular bubble contours are present."""


class IncompleteSheetError(OMRProcessingError):
    """Raised when the expected question grid is incomplete."""


class UnansweredQuestionError(OMRProcessingError):
    """Raised when no option is sufficiently filled for a question."""


class AmbiguousMarkError(OMRProcessingError):
    """Raised when multiple options appear selected for a question."""


@dataclass(frozen=True, slots=True)
class Bubble:
    x: int
    y: int
    width: int
    height: int
    grid_x: float | None = None
    grid_y: float | None = None

    @property
    def center_x(self) -> float:
        return self.x + self.width / 2

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2

    @property
    def position_x(self) -> float:
        return self.grid_x if self.grid_x is not None else self.center_x

    @property
    def position_y(self) -> float:
        return self.grid_y if self.grid_y is not None else self.center_y

    @property
    def diameter(self) -> float:
        return math.sqrt(self.width * self.height)


def _resize_for_analysis(image: np.ndarray) -> np.ndarray:
    height, width = image.shape[:2]
    longest_side = max(height, width)
    if longest_side < 900:
        scale = 900 / longest_side
        interpolation = cv2.INTER_CUBIC
    elif longest_side > 2200:
        scale = 1800 / longest_side
        interpolation = cv2.INTER_AREA
    else:
        return image
    return cv2.resize(
        image,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=interpolation,
    )


def _order_quad(points: np.ndarray) -> np.ndarray:
    points = points.astype(np.float32)
    ordered = np.zeros((4, 2), dtype=np.float32)
    coordinate_sum = points.sum(axis=1)
    coordinate_difference = np.diff(points, axis=1).reshape(-1)
    ordered[0] = points[np.argmin(coordinate_sum)]
    ordered[2] = points[np.argmax(coordinate_sum)]
    ordered[1] = points[np.argmin(coordinate_difference)]
    ordered[3] = points[np.argmax(coordinate_difference)]
    return ordered


def _rectify_page(image: np.ndarray) -> np.ndarray:
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    edges = cv2.Canny(blurred, 35, 110)
    edges = cv2.morphologyEx(
        edges,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=2,
    )
    contours, _ = cv2.findContours(
        edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    image_area = float(image.shape[0] * image.shape[1])
    page_quad: np.ndarray | None = None
    page_area = 0.0
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:12]:
        area = cv2.contourArea(contour)
        area_ratio = area / image_area
        if area_ratio < 0.22:
            break
        if area_ratio > 0.985:
            continue
        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue
        if area > page_area:
            page_quad = approximation.reshape(4, 2)
            page_area = area
    if page_quad is None:
        return image

    top_left, top_right, bottom_right, bottom_left = _order_quad(page_quad)
    target_width = int(
        round(
            max(
                np.linalg.norm(bottom_right - bottom_left),
                np.linalg.norm(top_right - top_left),
            )
        )
    )
    target_height = int(
        round(
            max(
                np.linalg.norm(top_right - bottom_right),
                np.linalg.norm(top_left - bottom_left),
            )
        )
    )
    if (
        target_width < image.shape[1] * 0.35
        or target_height < image.shape[0] * 0.35
        or min(target_width, target_height) < 180
    ):
        return image
    destination = np.array(
        [
            [0, 0],
            [target_width - 1, 0],
            [target_width - 1, target_height - 1],
            [0, target_height - 1],
        ],
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(
        _order_quad(page_quad), destination
    )
    return cv2.warpPerspective(
        image,
        transform,
        (target_width, target_height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )


def _prepare_thresholds(
    image: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    background_sigma = max(9.0, min(grayscale.shape) / 24.0)
    background = cv2.GaussianBlur(grayscale, (0, 0), background_sigma)
    background = np.maximum(background, 1)
    normalized = cv2.divide(grayscale, background, scale=255)
    normalized = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(
        normalized
    )
    blurred = cv2.GaussianBlur(normalized, (5, 5), 0)
    _, otsu = cv2.threshold(
        blurred, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
    )
    minimum_dimension = min(normalized.shape)
    adaptive_block_size = int(round(minimum_dimension * 0.055))
    adaptive_block_size = max(31, min(101, adaptive_block_size | 1))
    adaptive = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        adaptive_block_size,
        7,
    )
    candidates = cv2.bitwise_or(otsu, adaptive)
    candidates = cv2.morphologyEx(
        candidates,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    return normalized, candidates, otsu


def _candidate_bubbles(binary: np.ndarray) -> list[Bubble]:
    contours, _ = cv2.findContours(
        binary.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    image_height, image_width = binary.shape[:2]
    minimum_image_dimension = min(image_height, image_width)
    minimum_dimension = max(9, int(round(minimum_image_dimension * 0.010)))
    maximum_dimension = minimum_image_dimension * 0.16
    candidates: list[Bubble] = []

    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if width < minimum_dimension or height < minimum_dimension:
            continue
        if width > maximum_dimension or height > maximum_dimension:
            continue
        aspect_ratio = width / float(height)
        if not 0.60 <= aspect_ratio <= 1.67:
            continue
        area = cv2.contourArea(contour)
        perimeter = cv2.arcLength(contour, True)
        if perimeter <= 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        extent = area / float(width * height)
        if circularity < 0.40 or not 0.32 <= extent <= 0.96:
            continue
        candidates.append(Bubble(x=x, y=y, width=width, height=height))

    candidates.sort(key=lambda bubble: (bubble.center_y, bubble.center_x))
    deduplicated: list[Bubble] = []
    for candidate in candidates:
        duplicate_index = next(
            (
                index
                for index, existing in enumerate(deduplicated)
                if abs(candidate.center_x - existing.center_x)
                < min(candidate.width, existing.width) * 0.45
                and abs(candidate.center_y - existing.center_y)
                < min(candidate.height, existing.height) * 0.45
            ),
            None,
        )
        if duplicate_index is None:
            deduplicated.append(candidate)
        elif candidate.width * candidate.height > (
            deduplicated[duplicate_index].width
            * deduplicated[duplicate_index].height
        ):
            deduplicated[duplicate_index] = candidate
    return deduplicated


def _filter_dominant_bubble_size(
    bubbles: list[Bubble], expected_count: int
) -> list[Bubble]:
    if len(bubbles) <= expected_count:
        return bubbles
    sizes = np.array([bubble.diameter for bubble in bubbles], dtype=np.float64)
    best_subset = bubbles
    best_score = float("inf")
    for candidate_size in np.unique(np.quantile(sizes, np.linspace(0.1, 0.9, 17))):
        subset = [
            bubble
            for bubble in bubbles
            if candidate_size * 0.62 <= bubble.diameter <= candidate_size * 1.62
        ]
        if len(subset) < expected_count:
            continue
        subset_sizes = np.array(
            [bubble.diameter for bubble in subset], dtype=np.float64
        )
        dispersion = float(np.std(subset_sizes) / max(np.mean(subset_sizes), 1.0))
        count_excess = max(0, len(subset) - expected_count) / expected_count
        score = dispersion + count_excess * 0.08
        if score < best_score:
            best_score = score
            best_subset = subset
    return best_subset


def _estimate_grid_angle(bubbles: list[Bubble]) -> float:
    if len(bubbles) < 2:
        return 0.0
    median_diameter = float(np.median([bubble.diameter for bubble in bubbles]))
    angles: list[float] = []
    for left_index, left in enumerate(bubbles):
        for right in bubbles[left_index + 1 :]:
            delta_x = right.center_x - left.center_x
            delta_y = right.center_y - left.center_y
            if delta_x < 0:
                delta_x = -delta_x
                delta_y = -delta_y
            distance = math.hypot(delta_x, delta_y)
            if not median_diameter * 1.15 <= distance <= median_diameter * 3.8:
                continue
            if delta_x <= median_diameter * 0.75:
                continue
            angle = math.degrees(math.atan2(delta_y, delta_x))
            if -30 <= angle <= 30:
                angles.append(angle)
    if len(angles) < 3:
        return 0.0
    histogram, edges = np.histogram(angles, bins=31, range=(-31, 31))
    mode_index = int(np.argmax(histogram))
    mode_center = (edges[mode_index] + edges[mode_index + 1]) / 2
    near_mode = [angle for angle in angles if abs(angle - mode_center) <= 4]
    if len(near_mode) < 3:
        return 0.0
    estimated_angle = float(np.median(near_mode))
    return estimated_angle if abs(estimated_angle) <= 20 else 0.0


def _align_grid_coordinates(bubbles: list[Bubble]) -> list[Bubble]:
    angle = math.radians(_estimate_grid_angle(bubbles))
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return [
        replace(
            bubble,
            grid_x=cosine * bubble.center_x + sine * bubble.center_y,
            grid_y=-sine * bubble.center_x + cosine * bubble.center_y,
        )
        for bubble in bubbles
    ]


def _group_rows(bubbles: list[Bubble], tolerance: float | None = None) -> list[list[Bubble]]:
    if not bubbles:
        return []
    if tolerance is None:
        tolerance = max(8.0, float(np.median([bubble.diameter for bubble in bubbles])) * 0.58)
    rows: list[list[Bubble]] = []
    row_centers: list[float] = []
    for bubble in sorted(bubbles, key=lambda item: (item.position_y, item.position_x)):
        matching_row = None
        if rows:
            distances = [abs(bubble.position_y - center) for center in row_centers]
            closest_index = int(np.argmin(distances))
            if distances[closest_index] <= tolerance:
                matching_row = closest_index
        if matching_row is None:
            rows.append([bubble])
            row_centers.append(bubble.position_y)
        else:
            rows[matching_row].append(bubble)
            row_centers[matching_row] = sum(
                item.position_y for item in rows[matching_row]
            ) / len(rows[matching_row])
    for row in rows:
        row.sort(key=lambda item: item.position_x)
    return [
        row
        for _, row in sorted(
            zip(row_centers, rows, strict=True), key=lambda item: item[0]
        )
    ]


def _best_option_window(row: list[Bubble], option_count: int) -> list[Bubble]:
    scored_windows: list[tuple[float, list[Bubble]]] = []
    for start in range(len(row) - option_count + 1):
        window = row[start : start + option_count]
        gaps = [
            window[index + 1].position_x - window[index].position_x
            for index in range(option_count - 1)
        ]
        if any(gap <= 0 for gap in gaps):
            continue
        mean_gap = sum(gaps) / len(gaps) if gaps else 1.0
        gap_variance = (
            sum((gap - mean_gap) ** 2 for gap in gaps) / len(gaps)
            if gaps
            else 0.0
        )
        mean_width = sum(item.width for item in window) / option_count
        width_variance = sum(
            (item.width - mean_width) ** 2 for item in window
        ) / option_count
        score = gap_variance / max(mean_gap**2, 1.0) + width_variance / max(
            mean_width**2, 1.0
        )
        scored_windows.append((score, window))
    if not scored_windows:
        raise IncompleteSheetError("A question row does not contain enough bubbles")
    scored_windows.sort(key=lambda item: item[0])
    best_score, best_window = scored_windows[0]
    if best_score > 0.24:
        raise IncompleteSheetError("A question row has inconsistent bubble spacing")
    if len(scored_windows) > 1:
        second_score = scored_windows[1][0]
        if second_score <= best_score + 0.025:
            raise IncompleteSheetError(
                "A question row contains an ambiguous bubble sequence"
            )
    return best_window


def _select_question_rows(
    grouped_rows: list[list[Bubble]], total_questions: int, option_count: int
) -> list[list[Bubble]]:
    usable_rows = [row for row in grouped_rows if len(row) >= option_count]
    if len(usable_rows) < total_questions:
        raise IncompleteSheetError(
            f"Detected {len(usable_rows)} complete question rows; "
            f"expected {total_questions}"
        )
    if len(usable_rows) == total_questions:
        selected = [_best_option_window(row, option_count) for row in usable_rows]
        _validate_grid_geometry(selected)
        return selected

    best_score = float("inf")
    best_rows: list[list[Bubble]] | None = None
    for start in range(len(usable_rows) - total_questions + 1):
        window = usable_rows[start : start + total_questions]
        centers = [sum(item.position_y for item in row) / len(row) for row in window]
        gaps = [centers[index + 1] - centers[index] for index in range(len(centers) - 1)]
        mean_gap = sum(gaps) / len(gaps) if gaps else 1.0
        spacing_variance = (
            sum((gap - mean_gap) ** 2 for gap in gaps) / len(gaps)
            if gaps
            else 0.0
        )
        extra_bubbles = sum(abs(len(row) - option_count) for row in window)
        score = spacing_variance / max(mean_gap**2, 1.0) + extra_bubbles
        if score < best_score:
            best_score = score
            best_rows = window
    if best_rows is None:
        raise IncompleteSheetError("Could not identify the expected question grid")
    selected = [_best_option_window(row, option_count) for row in best_rows]
    _validate_grid_geometry(selected)
    return selected


def _coefficient_of_variation(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = float(np.mean(values))
    return float(np.std(values) / max(abs(mean), 1.0))


def _validate_grid_geometry(rows: list[list[Bubble]]) -> None:
    if not rows or not rows[0]:
        raise IncompleteSheetError("The answer grid is empty")
    option_count = len(rows[0])
    if any(len(row) != option_count for row in rows):
        raise IncompleteSheetError("The answer grid has inconsistent row lengths")

    diameters = [bubble.diameter for row in rows for bubble in row]
    median_diameter = float(np.median(diameters))
    if _coefficient_of_variation(diameters) > 0.30:
        raise IncompleteSheetError("Detected bubbles have inconsistent sizes")

    for row in rows:
        gaps = [
            row[index + 1].position_x - row[index].position_x
            for index in range(option_count - 1)
        ]
        if (
            any(gap < median_diameter * 0.65 for gap in gaps)
            or _coefficient_of_variation(gaps) > 0.28
        ):
            raise IncompleteSheetError(
                "Detected answer columns are geometrically inconsistent"
            )
    row_centers = [
        float(np.mean([bubble.position_y for bubble in row])) for row in rows
    ]
    row_gaps = [
        row_centers[index + 1] - row_centers[index]
        for index in range(len(row_centers) - 1)
    ]
    if row_gaps and (
        any(gap < median_diameter * 0.70 for gap in row_gaps)
        or _coefficient_of_variation(row_gaps) > 0.36
    ):
        raise IncompleteSheetError(
            "Detected question rows are geometrically inconsistent"
        )

    if len(rows) >= 3:
        row_positions = np.asarray(row_centers, dtype=np.float64)
        maximum_column_residual = median_diameter * 0.58
        for column_index in range(option_count):
            column_positions = np.asarray(
                [row[column_index].position_x for row in rows],
                dtype=np.float64,
            )
            coefficients = np.polyfit(row_positions, column_positions, 1)
            fitted = np.polyval(coefficients, row_positions)
            residual = float(np.max(np.abs(column_positions - fitted)))
            if residual > maximum_column_residual:
                raise IncompleteSheetError(
                    "Detected answer columns do not form a reliable grid"
                )


def _fill_ratio(binary: np.ndarray, bubble: Bubble) -> float:
    inset = max(2, int(round(min(bubble.width, bubble.height) * 0.22)))
    x1, x2 = bubble.x + inset, bubble.x + bubble.width - inset
    y1, y2 = bubble.y + inset, bubble.y + bubble.height - inset
    if x2 <= x1 or y2 <= y1:
        return 0.0
    region = binary[y1:y2, x1:x2]
    if region.size == 0:
        return 0.0
    mask = np.zeros(region.shape, dtype=np.uint8)
    cv2.ellipse(
        mask,
        (region.shape[1] // 2, region.shape[0] // 2),
        (max(1, region.shape[1] // 2 - 1), max(1, region.shape[0] // 2 - 1)),
        0,
        0,
        360,
        255,
        -1,
    )
    masked_pixels = cv2.countNonZero(mask)
    if masked_pixels == 0:
        return 0.0
    filled_pixels = cv2.countNonZero(cv2.bitwise_and(region, region, mask=mask))
    return filled_pixels / masked_pixels


def _mark_score(
    binary: np.ndarray, normalized_grayscale: np.ndarray, bubble: Bubble
) -> float:
    binary_ratio = _fill_ratio(binary, bubble)
    inset = max(2, int(round(min(bubble.width, bubble.height) * 0.22)))
    x1, x2 = bubble.x + inset, bubble.x + bubble.width - inset
    y1, y2 = bubble.y + inset, bubble.y + bubble.height - inset
    if x2 <= x1 or y2 <= y1:
        return binary_ratio
    grayscale_region = normalized_grayscale[y1:y2, x1:x2]
    if grayscale_region.size == 0:
        return binary_ratio
    mask = np.zeros(grayscale_region.shape, dtype=np.uint8)
    cv2.ellipse(
        mask,
        (grayscale_region.shape[1] // 2, grayscale_region.shape[0] // 2),
        (
            max(1, grayscale_region.shape[1] // 2 - 1),
            max(1, grayscale_region.shape[0] // 2 - 1),
        ),
        0,
        0,
        360,
        255,
        -1,
    )
    mean_intensity = cv2.mean(grayscale_region, mask=mask)[0]
    darkness = 1.0 - mean_intensity / 255.0
    return float(0.72 * binary_ratio + 0.28 * darkness)


def detect_answers(
    image_path: str | Path,
    total_questions: int,
    options_per_question: int,
) -> dict[int, str]:
    if total_questions <= 0:
        raise ValueError("total_questions must be greater than zero")
    if not 2 <= options_per_question <= len(string.ascii_uppercase):
        raise ValueError("options_per_question is outside the supported range")

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise OMRProcessingError("The uploaded image is invalid or unreadable")
    image = _resize_for_analysis(image)
    image = _resize_for_analysis(_rectify_page(image))
    normalized_grayscale, candidate_binary, mark_binary = _prepare_thresholds(image)

    bubbles = _candidate_bubbles(candidate_binary)
    if not bubbles:
        raise NoBubblesDetectedError(
            "No answer bubbles were detected; use a clear, upright sheet image"
        )
    expected_bubble_count = total_questions * options_per_question
    bubbles = _filter_dominant_bubble_size(bubbles, expected_bubble_count)
    maximum_candidate_count = max(
        expected_bubble_count + 80,
        int(math.ceil(expected_bubble_count * 2.5)),
    )
    if len(bubbles) > maximum_candidate_count:
        raise OMRProcessingError(
            "Too many bubble-like shapes were detected to identify a reliable grid"
        )
    if len(bubbles) < expected_bubble_count:
        raise IncompleteSheetError(
            f"Detected {len(bubbles)} answer bubbles; expected at least "
            f"{expected_bubble_count}"
        )
    bubbles = _align_grid_coordinates(bubbles)
    rows = _select_question_rows(
        _group_rows(bubbles), total_questions, options_per_question
    )

    labels = string.ascii_uppercase[:options_per_question]
    answers: dict[int, str] = {}
    score_rows = [
        [
            _mark_score(mark_binary, normalized_grayscale, bubble)
            for bubble in row
        ]
        for row in rows
    ]
    all_scores = np.asarray(
        [score for row_scores in score_rows for score in row_scores],
        dtype=np.float64,
    )
    empty_baseline = float(np.median(all_scores))
    median_absolute_deviation = float(
        np.median(np.abs(all_scores - empty_baseline))
    )
    minimum_fill = max(
        0.14,
        empty_baseline + max(0.09, median_absolute_deviation * 4.0),
    )
    if minimum_fill > 0.58:
        raise OMRProcessingError(
            "Sheet contrast is too uneven to distinguish filled bubbles safely"
        )

    for question_number, scores in enumerate(score_rows, start=1):
        ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
        selected_index, selected_score = ranked[0]
        mark_contrast = selected_score - empty_baseline
        if selected_score < minimum_fill or mark_contrast < 0.10:
            raise UnansweredQuestionError(
                f"Question {question_number} appears unanswered"
            )
        if len(ranked) > 1:
            second_index, second_score = ranked[1]
            required_margin = max(0.075, mark_contrast * 0.22)
            if (
                second_score >= minimum_fill
                and second_score >= selected_score * 0.55
            ) or selected_score - second_score < required_margin:
                raise AmbiguousMarkError(
                    f"Question {question_number} has ambiguous marks in "
                    f"options {labels[selected_index]} and {labels[second_index]}"
                )
        answers[question_number] = labels[selected_index]
    return answers


def _normalize_answers(answers: Mapping[int | str, str | None]) -> dict[int, str | None]:
    normalized: dict[int, str | None] = {}
    for raw_question, raw_answer in answers.items():
        try:
            question = int(raw_question)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid question number: {raw_question!r}") from exc
        if question <= 0:
            raise ValueError("Question numbers must be greater than zero")
        if raw_answer is None:
            normalized[question] = None
        else:
            answer = str(raw_answer).strip().upper()
            normalized[question] = answer or None
    return normalized


def grade_answers(
    student_answers: Mapping[int | str, str | None],
    answer_key: Mapping[int | str, str],
) -> dict[str, object]:
    normalized_key = _normalize_answers(answer_key)
    if not normalized_key:
        raise ValueError("The answer key cannot be empty")
    normalized_student = _normalize_answers(student_answers)

    breakdown: dict[int, dict[str, object]] = {}
    score = 0
    for question in sorted(normalized_key):
        correct_answer = normalized_key[question]
        if correct_answer is None:
            raise ValueError(f"Answer key question {question} has no answer")
        student_answer = normalized_student.get(question)
        is_correct = student_answer == correct_answer
        if is_correct:
            score += 1
        breakdown[question] = {
            "student": student_answer,
            "correct": correct_answer,
            "result": is_correct,
        }

    total = len(normalized_key)
    percentage = round((score / total) * 100, 2)
    return {
        "score": score,
        "total": total,
        "percentage": percentage,
        "breakdown": breakdown,
    }
