"""End-to-end test: generate filled sheet -> detect_answers -> verify."""
from backend.services.omr_engine import (
    detect_answers, _cluster_bubbles, _candidate_bubbles, _prepare_thresholds,
    _resize_for_analysis, _rectify_page, _filter_dominant_bubble_size,
    _align_grid_coordinates, _group_rows,
)
import cv2
import numpy as np

print("=== Testing with new filled template ===")
image = cv2.imread('sample_sheet_filled.png')
image = _resize_for_analysis(image)

# 1. Test without rectify
_, cb1, _ = _prepare_thresholds(image)
b1 = _candidate_bubbles(cb1)
b1 = _filter_dominant_bubble_size(b1, 40)
b1 = _align_grid_coordinates(b1)
c1 = _cluster_bubbles(b1)
print(f"WITHOUT rectify: {len(b1)} bubbles, {len(c1)} clusters, sizes={[len(c) for c in c1]}")
for i, cl in enumerate(c1):
    rows = _group_rows(cl)
    print(f"  Cluster {i}: {len(rows)} rows, cols={[len(r) for r in rows[:3]]}...")

# 2. Test with rectify (actual detect_answers path)
rectified = _rectify_page(image)
image2 = _resize_for_analysis(rectified)
_, cb2, _ = _prepare_thresholds(image2)
b2 = _candidate_bubbles(cb2)
b2 = _filter_dominant_bubble_size(b2, 40)
b2 = _align_grid_coordinates(b2)
c2 = _cluster_bubbles(b2)
print(f"\nWITH rectify: {len(b2)} bubbles, {len(c2)} clusters, sizes={[len(c) for c in c2]}")
for i, cl in enumerate(c2):
    rows = _group_rows(cl)
    print(f"  Cluster {i}: {len(rows)} rows, cols={[len(r) for r in rows[:3]]}...")

# 3. Full detect_answers call
print("\n=== Full detect_answers ===")
try:
    data = detect_answers('sample_sheet_filled.png', 10, 4)
    print(f"SUCCESS!")
    print(f"  Answers: {data.answers}")
    print(f"  Roll:    {data.roll_number}")
    print(f"  Name:    {data.student_name}")
except Exception as e:
    import traceback
    print(f"FAILED: {e}")
    traceback.print_exc()
