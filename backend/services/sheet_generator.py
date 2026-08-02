"""Generate printable OMR sheet templates with proper grid separation.

This module produces scanner-compatible OMR bubble sheets as PNG images.
It is used by the ``/exams/{exam_id}/sheet`` API endpoint to create
printable sheets tailored to each exam's question count and option count.
"""

from __future__ import annotations

import io
import math
from typing import Literal

import cv2
import numpy as np


def generate_omr_sheet(
    *,
    total_questions: int = 20,
    options_per_question: int = 4,
    exam_title: str = "OMR EXAMINATION SHEET",
    include_name_grid: bool = True,
    include_roll_grid: bool = True,
) -> bytes:
    """Return a PNG image of a blank, printable OMR bubble sheet.

    Parameters
    ----------
    total_questions:
        Number of question rows in the answer grid (10–40).
    options_per_question:
        Number of bubble columns per question row (4 or 5).
    exam_title:
        Title printed at the top of the sheet.
    include_name_grid:
        Whether to include the alphabetical STUDENT NAME grid.
    include_roll_grid:
        Whether to include the numeric ROLL NUMBER grid.

    Returns
    -------
    bytes
        The PNG-encoded image data.
    """
    # ── layout constants ────────────────────────────────────────────
    R = 16          # bubble radius
    cs = 42         # column spacing (bubble centre to centre)
    rs = 42         # row spacing
    MARGIN = 80     # page margin on all sides
    PAPER_W = 1400  # printable area width

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_s = 0.45
    font_c = (0, 0, 0)
    label_off = 35

    # ── pre-calculate total height ──────────────────────────────────
    # Title area
    title_h = 80  # space from top to title baseline
    title_gap = 80  # gap between title and grids

    # Header grids height
    header_grid_h = 0
    if include_name_grid:
        name_rows = 26
        header_grid_h = max(header_grid_h, 25 + name_rows * rs + R)
    if include_roll_grid:
        roll_rows = 10
        header_grid_h = max(header_grid_h, 25 + roll_rows * rs + R)

    # Answer grid — use 2 columns for > 20 questions to keep it compact
    num_answer_cols = 2 if total_questions > 20 else 1
    rows_per_col = math.ceil(total_questions / num_answer_cols)
    answer_header_h = 50  # space for "ANSWERS" label + column headers
    answer_grid_h = rows_per_col * rs + R
    answer_gap = 100  # gap between header grids and answer section

    total_content_h = (
        title_h
        + title_gap
        + header_grid_h
        + answer_gap
        + answer_header_h
        + answer_grid_h
        + MARGIN  # bottom margin
    )

    paper_h = max(total_content_h + MARGIN, 2100)

    # ── create clean white canvas (no dark border) ──────────────────
    img = np.full((paper_h, PAPER_W, 3), 255, dtype=np.uint8)

    # ── thin border around the entire sheet ─────────────────────────
    cv2.rectangle(img, (2, 2), (PAPER_W - 3, paper_h - 3), (0, 0, 0), 2)

    # ── title ───────────────────────────────────────────────────────
    title_y = MARGIN
    title_text = exam_title[:60]
    (text_w, _), _ = cv2.getTextSize(title_text, font, 1.4, 3)
    title_x = (PAPER_W - text_w) // 2
    cv2.putText(img, title_text, (title_x, title_y), font, 1.4, (0, 0, 0), 3)

    # Horizontal rule under title
    rule_y = title_y + 20
    cv2.line(img, (MARGIN, rule_y), (PAPER_W - MARGIN, rule_y), (0, 0, 0), 2)

    # Track the bottom of header grids
    header_bottom = rule_y + 10

    # ── NAME grid (26 rows × 15 cols) ──────────────────────────────
    name_grid_right = MARGIN
    if include_name_grid:
        name_x0 = MARGIN + 40
        name_y0 = rule_y + title_gap
        name_rows, name_cols = 26, 15

        cv2.putText(img, "STUDENT NAME", (name_x0, name_y0 - 25), font, 0.7, font_c, 2)
        for r in range(name_rows):
            lbl = chr(ord("A") + r)
            cv2.putText(
                img, lbl, (name_x0 - label_off, name_y0 + r * rs + 5), font, font_s, font_c, 1
            )
            for c in range(name_cols):
                cv2.circle(img, (name_x0 + c * cs, name_y0 + r * rs), R, (0, 0, 0), 2)

        name_grid_right = name_x0 + (name_cols - 1) * cs + R
        name_grid_bottom = name_y0 + (name_rows - 1) * rs + R
        header_bottom = max(header_bottom, name_grid_bottom)

    # ── ROLL NUMBER grid (10 rows × 6 cols) ────────────────────────
    if include_roll_grid:
        x_gap = 120
        roll_x0 = name_grid_right + x_gap if include_name_grid else MARGIN + 40
        roll_y0 = rule_y + title_gap
        roll_rows, roll_cols = 10, 6

        cv2.putText(img, "ROLL NUMBER", (roll_x0, roll_y0 - 25), font, 0.7, font_c, 2)
        for r in range(roll_rows):
            cv2.putText(
                img, str(r), (roll_x0 - label_off, roll_y0 + r * rs + 5), font, font_s, font_c, 1
            )
            for c in range(roll_cols):
                cv2.circle(img, (roll_x0 + c * cs, roll_y0 + r * rs), R, (0, 0, 0), 2)

        roll_grid_bottom = roll_y0 + (roll_rows - 1) * rs + R
        header_bottom = max(header_bottom, roll_grid_bottom)

    # ── separator line between header and answers ───────────────────
    sep_y = header_bottom + 40
    cv2.line(img, (MARGIN, sep_y), (PAPER_W - MARGIN, sep_y), (180, 180, 180), 1)

    # ── ANSWERS grid (multi-column layout) ──────────────────────────
    q_y0 = sep_y + answer_gap - 40

    # Calculate column width: label + options bubbles
    single_col_w = 50 + options_per_question * cs  # 50px for question number label

    if num_answer_cols == 1:
        # Center a single column
        q_x0 = (PAPER_W - single_col_w) // 2 + 50  # +50 to offset past label
        _draw_answer_column(
            img, q_x0, q_y0, 0, total_questions,
            options_per_question, cs, rs, R, font, font_s, font_c, show_header=True,
        )
    else:
        # Two columns with a gap between them
        col_gap = 80
        total_grid_w = 2 * single_col_w + col_gap
        col1_x = (PAPER_W - total_grid_w) // 2 + 50
        col2_x = col1_x + single_col_w + col_gap

        col1_count = rows_per_col
        col2_count = total_questions - rows_per_col

        _draw_answer_column(
            img, col1_x, q_y0, 0, col1_count,
            options_per_question, cs, rs, R, font, font_s, font_c, show_header=True,
        )
        _draw_answer_column(
            img, col2_x, q_y0, col1_count, col2_count,
            options_per_question, cs, rs, R, font, font_s, font_c, show_header=True,
        )

    # ── encode to PNG ───────────────────────────────────────────────
    success, buffer = cv2.imencode(".png", img)
    if not success:
        raise RuntimeError("Failed to encode OMR sheet image")
    return buffer.tobytes()


def _draw_answer_column(
    img: np.ndarray,
    x0: int,
    y0: int,
    start_q: int,
    count: int,
    options: int,
    cs: int,
    rs: int,
    R: int,
    font: int,
    font_s: float,
    font_c: tuple,
    *,
    show_header: bool = True,
) -> None:
    """Draw a single column of the answer bubble grid."""
    if show_header:
        cv2.putText(img, "ANSWERS", (x0, y0 - 30), font, 0.7, font_c, 2)
        for c in range(options):
            cv2.putText(
                img, chr(ord("A") + c), (x0 + c * cs - 5, y0 - 8), font, font_s, font_c, 1
            )

    for r in range(count):
        q_num = start_q + r + 1
        cv2.putText(
            img, f"{q_num}", (x0 - 45, y0 + r * rs + 5), font, font_s, font_c, 1
        )
        for c in range(options):
            cv2.circle(img, (x0 + c * cs, y0 + r * rs), R, (0, 0, 0), 2)
