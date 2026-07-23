
from backend.services.omr_engine import detect_answers, _cluster_bubbles, _candidate_bubbles, _prepare_thresholds, _resize_for_analysis, _group_rows, _filter_dominant_bubble_size, _align_grid_coordinates, _select_question_rows
import cv2
image = cv2.imread('sample_omr_sheet_full.png')
image = _resize_for_analysis(image)
_, candidate_binary, _ = _prepare_thresholds(image)
bubbles = _candidate_bubbles(candidate_binary)
bubbles = _filter_dominant_bubble_size(bubbles, 40)
bubbles = _align_grid_coordinates(bubbles)
clusters = _cluster_bubbles(bubbles)
for cluster in clusters:
    rows = _group_rows(cluster)
    if len(rows) == 10 and all(len(row) >= 5 for row in rows):
        print('Roll')
        continue
    if len(rows) == 26 and all(len(row) >= 15 for row in rows):
        print('Name')
        continue
    usable = [row for row in rows if len(row) >= 4]
    if len(usable) >= 10:
        print('Questions: len(usable) =', len(usable))
        try:
            res = _select_question_rows(rows, 10, 4)
            print('Success!', len(res))
        except Exception as e:
            print('Failed!', repr(e))
