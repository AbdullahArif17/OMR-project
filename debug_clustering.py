"""Debug why clustering fails after _rectify_page."""
from backend.services.omr_engine import (
    _cluster_bubbles, _candidate_bubbles, _prepare_thresholds,
    _resize_for_analysis, _rectify_page, _filter_dominant_bubble_size,
    _align_grid_coordinates, _group_rows,
)
import cv2
import numpy as np

image = cv2.imread('sample_omr_sheet_full.png')
image = _resize_for_analysis(image)

# Without rectify
_, cb1, _ = _prepare_thresholds(image)
b1 = _candidate_bubbles(cb1)
b1 = _filter_dominant_bubble_size(b1, 40)
b1 = _align_grid_coordinates(b1)
c1 = _cluster_bubbles(b1)
print("WITHOUT rectify:")
print(f"  Bubbles: {len(b1)}, Clusters: {len(c1)}, Sizes: {[len(c) for c in c1]}")
for i, cl in enumerate(c1):
    rows = _group_rows(cl)
    print(f"  Cluster {i}: {len(rows)} rows, cols per row: {[len(r) for r in rows[:3]]}...")

# With rectify (same path as detect_answers)
rectified = _rectify_page(image)
image2 = _resize_for_analysis(rectified)
_, cb2, _ = _prepare_thresholds(image2)
b2 = _candidate_bubbles(cb2)
b2 = _filter_dominant_bubble_size(b2, 40)
b2 = _align_grid_coordinates(b2)
c2 = _cluster_bubbles(b2)
print("\nWITH rectify:")
print(f"  Bubbles: {len(b2)}, Clusters: {len(c2)}, Sizes: {[len(c) for c in c2]}")

# Check distances between grid groups
all_xs = [b.position_x for b in b2]
all_ys = [b.position_y for b in b2]
diameters = [b.diameter for b in b2]
med_d = np.median(diameters)
print(f"  Median diameter: {med_d}")
print(f"  X range: {min(all_xs):.0f} - {max(all_xs):.0f}")
print(f"  Y range: {min(all_ys):.0f} - {max(all_ys):.0f}")

# Check what threshold would separate them
for i, cl in enumerate(c2):
    rows = _group_rows(cl)
    xs = [b.position_x for b in cl]
    ys = [b.position_y for b in cl]
    print(f"  Cluster {i}: {len(rows)} rows, x=[{min(xs):.0f},{max(xs):.0f}], y=[{min(ys):.0f},{max(ys):.0f}]")
