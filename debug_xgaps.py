"""Analyze X-gaps within rows to find column clusters."""
from backend.services.omr_engine import (
    _candidate_bubbles, _prepare_thresholds,
    _resize_for_analysis, _rectify_page, _filter_dominant_bubble_size,
    _align_grid_coordinates, _group_rows,
)
import cv2
import numpy as np

image = cv2.imread('sample_omr_sheet_full.png')
image = _resize_for_analysis(image)
rectified = _rectify_page(image)
image2 = _resize_for_analysis(rectified)
_, cb, _ = _prepare_thresholds(image2)
bubbles = _candidate_bubbles(cb)
bubbles = _filter_dominant_bubble_size(bubbles, 40)
bubbles = _align_grid_coordinates(bubbles)
rows = _group_rows(bubbles)

# Show X positions for the first few rows to see gaps
for i in range(min(12, len(rows))):
    row = rows[i]
    xs = sorted([b.position_x for b in row])
    gaps = [xs[j+1] - xs[j] for j in range(len(xs)-1)]
    max_gap_idx = max(range(len(gaps)), key=lambda g: gaps[g]) if gaps else -1
    big_gaps = [(j, gaps[j]) for j in range(len(gaps)) if gaps[j] > 50]
    print(f"Row {i:2d} ({len(row)} cols): xs={[f'{x:.0f}' for x in xs]}")
    print(f"  Gaps: {[f'{g:.0f}' for g in gaps]}")
    if big_gaps:
        print(f"  BIG gaps at indices: {big_gaps}")
    print()
