"""Generate printable OMR sheet templates with proper grid separation.

This module produces scanner-compatible OMR bubble sheets as PNG images.
It is used by the ``/exams/{exam_id}/sheet`` API endpoint to create
printable sheets tailored to each exam's question count and option count.
"""

from __future__ import annotations

import io
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
    # ── canvas ──────────────────────────────────────────────────────
    bed_w, bed_h = 1700, 2400
    paper_w, paper_h = 1400, 2100
    mx = (bed_w - paper_w) // 2
    my = (bed_h - paper_h) // 2

    img = np.full((bed_h, bed_w, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (mx, my), (mx + paper_w, my + paper_h), (255, 255, 255), -1)

    # ── bubble parameters ───────────────────────────────────────────
    R = 16
    cs = 42
    rs = 42

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_s = 0.45
    font_c = (0, 0, 0)
    label_off = 35

    # ── title ───────────────────────────────────────────────────────
    title_y = my + 80
    title_text = exam_title[:60]  # Truncate long titles
    # Center the title
    (text_w, _), _ = cv2.getTextSize(title_text, cv2.FONT_HERSHEY_SIMPLEX, 1.4, 3)
    title_x = mx + (paper_w - text_w) // 2
    cv2.putText(img, title_text, (title_x, title_y), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 0), 3)

    # Track the bottom of the header grids
    header_bottom = title_y + 40

    # ── NAME grid (26 rows × 15 cols) ──────────────────────────────
    if include_name_grid:
        name_x0 = mx + 80
        name_y0 = title_y + 80
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
    else:
        name_grid_right = mx + 80

    # ── ROLL NUMBER grid (10 rows × 6 cols) ────────────────────────
    if include_roll_grid:
        x_gap = 200
        roll_x0 = name_grid_right + x_gap if include_name_grid else mx + 80
        roll_y0 = title_y + 80
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

    # ── ANSWERS grid (total_questions rows × options cols) ──────────
    y_gap = 180
    q_y0 = header_bottom + y_gap
    q_grid_w = (options_per_question - 1) * cs
    q_x0 = mx + (paper_w - q_grid_w) // 2

    cv2.putText(img, "ANSWERS", (q_x0, q_y0 - 30), font, 0.7, font_c, 2)
    for c in range(options_per_question):
        cv2.putText(
            img, chr(ord("A") + c), (q_x0 + c * cs - 5, q_y0 - 8), font, font_s, font_c, 1
        )
    for r in range(total_questions):
        cv2.putText(
            img, f"{r + 1}", (q_x0 - 45, q_y0 + r * rs + 5), font, font_s, font_c, 1
        )
        for c in range(options_per_question):
            cv2.circle(img, (q_x0 + c * cs, q_y0 + r * rs), R, (0, 0, 0), 2)

    # Check if the answer grid fits on the page and extend if needed
    q_grid_bottom = q_y0 + (total_questions - 1) * rs + R
    if q_grid_bottom > bed_h - 50:
        # Extend the canvas height
        extra = q_grid_bottom - bed_h + 100
        extension = np.full((extra, bed_w, 3), 40, dtype=np.uint8)
        # Fill the paper area white
        cv2.rectangle(extension, (mx, 0), (mx + paper_w, extra), (255, 255, 255), -1)
        img = np.vstack([img, extension])

    # ── encode to PNG ───────────────────────────────────────────────
    success, buffer = cv2.imencode(".png", img)
    if not success:
        raise RuntimeError("Failed to encode OMR sheet image")
    return buffer.tobytes()
