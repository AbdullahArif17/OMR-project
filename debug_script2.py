
from backend.services.omr_engine import detect_answers
try:
    detect_answers('sample_omr_sheet_full.png', 10, 4)
except Exception as e:
    import traceback
    traceback.print_exc()
