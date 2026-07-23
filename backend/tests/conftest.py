from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient


TEST_UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="omr-api-tests-"))
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["AUTH_REQUIRED"] = "false"
os.environ["AUTH_JWT_SECRET"] = ""
os.environ["UPLOAD_DIR"] = str(TEST_UPLOAD_DIR)
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def make_sheet(tmp_path: Path):
    def _make_sheet(
        answers: list[int | None | tuple[int, int]],
        *,
        option_count: int = 4,
        filename: str = "sheet.png",
    ) -> Path:
        row_spacing = 54
        column_spacing = 58
        image_height = 80 + row_spacing * len(answers)
        image_width = 140 + column_spacing * option_count
        image = np.full((image_height, image_width, 3), 255, dtype=np.uint8)
        for row_index, selected in enumerate(answers):
            selected_options = (
                set(selected) if isinstance(selected, tuple) else {selected}
            )
            center_y = 45 + row_index * row_spacing
            for option_index in range(option_count):
                center = (70 + option_index * column_spacing, center_y)
                cv2.circle(image, center, 15, (0, 0, 0), 2)
                if option_index in selected_options:
                    cv2.circle(image, center, 11, (0, 0, 0), -1)
        output_path = tmp_path / filename
        assert cv2.imwrite(str(output_path), image)
        return output_path

    return _make_sheet


def pytest_sessionfinish() -> None:
    shutil.rmtree(TEST_UPLOAD_DIR, ignore_errors=True)
