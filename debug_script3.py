
from backend.services.omr_engine import detect_answers, _cluster_bubbles, _candidate_bubbles, _prepare_thresholds, _resize_for_analysis, _group_rows, _filter_dominant_bubble_size, _align_grid_coordinates, _select_question_rows
import cv2
image = cv2.imread('sample_omr_sheet_full.png')
image = _resize_for_analysis(image)
_, candidate_binary, _ = _prepare_thresholds(image)
bubbles = _candidate_bubbles(candidate_binary)
print('Before filter:', len(bubbles))
bubbles = _filter_dominant_bubble_size(bubbles, 40)
print('After filter 40:', len(bubbles))
