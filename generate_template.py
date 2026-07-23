"""Generate printable OMR sheet templates with proper grid separation.

Layout
------
The sheet is designed for flatbed / ADF scanning at ≥200 dpi.
Three bubble-grid sections are placed with clear physical gaps so the
OMR engine can reliably cluster them even after perspective correction.

Grid layout (left to right, top to bottom):
    ┌────────────────────────────────────────────┐
    │  Title                                     │
    ├──────────────────┬──── gap ──┬─────────────┤
    │  STUDENT NAME    │           │ ROLL NUMBER │
    │  26 rows × 15 col│           │ 10 rows × 6 │
    │                  │           │             │
    │                  │           ├─────────────┤
    │                  │           │             │
    │                  │           │             │
    │                  │           │             │
    ├──────────────────┴───────────┴─────────────┤
    │                   gap                      │
    ├────────────────────────────────────────────┤
    │  ANSWERS                                   │
    │  N rows × 4 cols  (centered)               │
    └────────────────────────────────────────────┘
"""

import cv2
import numpy as np


def create_omr_template(
    output_path: str = "sample_sheet_printable.png",
    total_questions: int = 10,
    options: int = 4,
) -> None:
    # ── canvas ──────────────────────────────────────────────────────
    bed_w, bed_h = 1700, 2400          # scanner bed (dark border)
    paper_w, paper_h = 1400, 2100      # white paper area
    mx = (bed_w - paper_w) // 2        # paper margin-x
    my = (bed_h - paper_h) // 2        # paper margin-y

    img = np.full((bed_h, bed_w, 3), 40, dtype=np.uint8)
    cv2.rectangle(img, (mx, my), (mx + paper_w, my + paper_h),
                  (255, 255, 255), -1)

    # ── bubble parameters ───────────────────────────────────────────
    R = 16                             # bubble radius
    cs = 42                            # column spacing (within a grid)
    rs = 42                            # row spacing    (within a grid)

    font      = cv2.FONT_HERSHEY_SIMPLEX
    font_s    = 0.45
    font_c    = (0, 0, 0)
    label_off = 35                     # label offset left of first col

    # ── title ───────────────────────────────────────────────────────
    title_y = my + 80
    cv2.putText(img, "OMR EXAMINATION SHEET",
                (mx + 300, title_y), cv2.FONT_HERSHEY_SIMPLEX, 1.6, (0, 0, 0), 3)

    # ── NAME grid (26 rows × 15 cols) ──────────────────────────────
    name_x0  = mx + 80
    name_y0  = title_y + 80
    name_rows, name_cols = 26, 15

    cv2.putText(img, "STUDENT NAME",
                (name_x0, name_y0 - 25), font, 0.7, font_c, 2)
    for r in range(name_rows):
        lbl = chr(ord('A') + r)
        cv2.putText(img, lbl,
                    (name_x0 - label_off, name_y0 + r * rs + 5),
                    font, font_s, font_c, 1)
        for c in range(name_cols):
            cv2.circle(img,
                       (name_x0 + c * cs, name_y0 + r * rs),
                       R, (0, 0, 0), 2)

    name_grid_right  = name_x0 + (name_cols - 1) * cs + R
    name_grid_bottom = name_y0 + (name_rows - 1) * rs + R

    # ── ROLL NUMBER grid (10 rows × 6 cols) ────────────────────────
    # Placed to the RIGHT with a large physical gap
    x_gap = 200                        # ← big gap so clustering works
    roll_x0  = name_grid_right + x_gap
    roll_y0  = name_y0
    roll_rows, roll_cols = 10, 6

    cv2.putText(img, "ROLL NUMBER",
                (roll_x0, roll_y0 - 25), font, 0.7, font_c, 2)
    for r in range(roll_rows):
        cv2.putText(img, str(r),
                    (roll_x0 - label_off, roll_y0 + r * rs + 5),
                    font, font_s, font_c, 1)
        for c in range(roll_cols):
            cv2.circle(img,
                       (roll_x0 + c * cs, roll_y0 + r * rs),
                       R, (0, 0, 0), 2)

    roll_grid_bottom = roll_y0 + (roll_rows - 1) * rs + R

    # ── ANSWERS grid (total_questions rows × options cols) ──────────
    # Placed BELOW both grids with a large vertical gap
    y_gap = 180                        # ← big gap so clustering works
    q_y0 = max(name_grid_bottom, roll_grid_bottom) + y_gap
    # Center horizontally on the paper
    q_grid_w = (options - 1) * cs
    q_x0 = mx + (paper_w - q_grid_w) // 2

    cv2.putText(img, "ANSWERS",
                (q_x0, q_y0 - 30), font, 0.7, font_c, 2)
    for c in range(options):
        cv2.putText(img, chr(ord('A') + c),
                    (q_x0 + c * cs - 5, q_y0 - 8),
                    font, font_s, font_c, 1)
    for r in range(total_questions):
        cv2.putText(img, f"{r + 1}",
                    (q_x0 - 45, q_y0 + r * rs + 5),
                    font, font_s, font_c, 1)
        for c in range(options):
            cv2.circle(img,
                       (q_x0 + c * cs, q_y0 + r * rs),
                       R, (0, 0, 0), 2)

    cv2.imwrite(output_path, img)
    print(f"[OK] Clean template  -> {output_path}")

    # ── filled copy for backend testing ─────────────────────────────
    test_name = "JOHN"
    test_roll = "123456"

    for r in range(name_rows):
        for c in range(name_cols):
            if c < len(test_name) and ord(test_name[c]) - ord('A') == r:
                cv2.circle(img,
                           (name_x0 + c * cs, name_y0 + r * rs),
                           R - 4, (0, 0, 0), -1)

    for r in range(roll_rows):
        for c in range(roll_cols):
            if c < len(test_roll) and int(test_roll[c]) == r:
                cv2.circle(img,
                           (roll_x0 + c * cs, roll_y0 + r * rs),
                           R - 4, (0, 0, 0), -1)

    for r in range(total_questions):
        filled_opt = r % options
        cv2.circle(img,
                   (q_x0 + filled_opt * cs, q_y0 + r * rs),
                   R - 4, (0, 0, 0), -1)

    filled_path = "sample_sheet_filled.png"
    cv2.imwrite(filled_path, img)
    print(f"[OK] Filled template -> {filled_path}")


if __name__ == "__main__":
    create_omr_template()
