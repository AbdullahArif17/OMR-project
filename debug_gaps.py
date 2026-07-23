"""Analyze gaps between rows after rectification to design better clustering."""
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

print(f"Total bubbles: {len(bubbles)}")
print(f"Total rows: {len(rows)}")
print()

# Print y-center and column count for each row
row_centers = []
for i, row in enumerate(rows):
    cy = np.mean([b.position_y for b in row])
    cx_min = min(b.position_x for b in row)
    cx_max = max(b.position_x for b in row)
    row_centers.append(cy)
    print(f"Row {i:2d}: y={cy:6.1f}, cols={len(row):2d}, x=[{cx_min:.0f}, {cx_max:.0f}]")

print()
# Print gaps between consecutive rows
print("Gaps between rows:")
for i in range(len(row_centers) - 1):
    gap = row_centers[i+1] - row_centers[i]
    print(f"  Row {i:2d} -> {i+1:2d}: gap = {gap:.1f}")
