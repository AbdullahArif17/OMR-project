from __future__ import annotations

import asyncio
import io
import stat
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import UploadFile
from PIL import Image

import services.file_processing as file_processing
from config import settings
from services.file_processing import (
    FileProcessingError,
    FileTooLargeError,
    StoredUpload,
    UnsupportedFileError,
    discard_scan_uploads,
    discard_upload,
    normalize_upload,
    processing_workspace,
    store_upload,
)


def _png_bytes(*, width: int = 64, height: int = 64) -> bytes:
    output = io.BytesIO()
    Image.new("L", (width, height), color=255).save(output, format="PNG")
    return output.getvalue()


def _stored(path: Path, original_name: str | None = None) -> StoredUpload:
    return StoredUpload(
        path=path,
        original_name=original_name or path.name,
        relative_path=f"scans/{path.name}",
    )


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.png", b"not-an-image")
    stored = StoredUpload(
        path=archive_path,
        original_name="unsafe.zip",
        relative_path="scans/generated.zip",
    )

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="unsafe path"):
            normalize_upload(stored, workspace=workspace, allow_zip=True)


def test_pdf_page_limit_is_checked_before_conversion(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "master.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic-pdf-bytes")
    conversion_called = False

    def fake_convert(*args, **kwargs):
        nonlocal conversion_called
        conversion_called = True
        return []

    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 2}
    )
    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    stored = StoredUpload(
        path=pdf_path,
        original_name="master.pdf",
        relative_path="answer-keys/generated.pdf",
    )
    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="sheet limit is 1"):
            normalize_upload(
                stored,
                workspace=workspace,
                allow_zip=False,
                max_sheets=1,
            )
    assert conversion_called is False


def test_upload_magic_must_match_extension_and_failed_store_is_cleaned(
    tmp_path: Path,
) -> None:
    configured = replace(settings, upload_dir=tmp_path / "uploads")
    upload = UploadFile(
        io.BytesIO(b"%PDF-1.7\nnot-a-png"),
        filename="../../student.png",
    )

    with pytest.raises(UnsupportedFileError, match="does not match"):
        asyncio.run(store_upload(upload, category="scans", configured=configured))

    scans_dir = configured.upload_dir / "scans"
    assert list(scans_dir.glob("*")) == []


def test_store_sanitizes_browser_path_and_keeps_generated_destination(
    tmp_path: Path,
) -> None:
    configured = replace(settings, upload_dir=tmp_path / "uploads")
    upload = UploadFile(
        io.BytesIO(_png_bytes()),
        filename=r"C:\fakepath\student.png",
    )

    stored = asyncio.run(store_upload(upload, category="scans", configured=configured))

    assert stored.original_name == "student.png"
    assert stored.path.parent == (configured.upload_dir / "scans").resolve()
    assert stored.path.name != stored.original_name
    discard_upload(stored)


@pytest.mark.parametrize(
    "filename",
    ["bad\x00.png", "bad\nname.png", "CON.png", f"{'a' * 256}.png"],
)
def test_unsafe_client_filenames_are_rejected(filename: str, tmp_path: Path) -> None:
    configured = replace(settings, upload_dir=tmp_path / "uploads")
    upload = UploadFile(io.BytesIO(_png_bytes()), filename=filename)

    with pytest.raises(UnsupportedFileError, match="filename"):
        asyncio.run(store_upload(upload, category="scans", configured=configured))


def test_image_pixel_limit_is_enforced_before_opencv_processing(tmp_path: Path) -> None:
    image_path = tmp_path / "oversized.png"
    image_path.write_bytes(_png_bytes(width=20, height=20))
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_image_pixels=399,
    )

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileProcessingError, match="unsafe image dimensions"):
            normalize_upload(
                _stored(image_path),
                workspace=workspace,
                allow_zip=False,
                configured=configured,
            )


def test_invalid_pdf_magic_is_rejected_before_poppler(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "fake.pdf"
    pdf_path.write_bytes(b"not-a-pdf")
    inspected = False

    def fake_info(*args, **kwargs):
        nonlocal inspected
        inspected = True
        return {"Pages": 1}

    monkeypatch.setattr(file_processing, "pdfinfo_from_path", fake_info)
    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="recognized .pdf"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
            )
    assert inspected is False


def test_encrypted_pdf_is_rejected_before_rendering(tmp_path: Path, monkeypatch) -> None:
    pdf_path = tmp_path / "encrypted.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    rendered = False

    monkeypatch.setattr(
        file_processing,
        "pdfinfo_from_path",
        lambda *_, **__: {"Pages": 1, "Encrypted": "yes"},
    )

    def fake_convert(*args, **kwargs):
        nonlocal rendered
        rendered = True
        return []

    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="encrypted"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
            )
    assert rendered is False


def test_pdf_limits_and_timeouts_are_passed_to_poppler(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "bounded.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        pdf_info_timeout_seconds=7,
        pdf_conversion_timeout_seconds=11,
        pdf_dpi=144,
        max_pdf_pages=3,
    )
    observed: dict[str, int] = {}

    def fake_info(*args, **kwargs):
        observed["info_timeout"] = kwargs["timeout"]
        return {"Pages": 1, "Encrypted": "no"}

    def fake_convert(*args, **kwargs):
        observed["conversion_timeout"] = kwargs["timeout"]
        observed["dpi"] = kwargs["dpi"]
        observed["first_page"] = kwargs["first_page"]
        observed["last_page"] = kwargs["last_page"]
        rendered = Path(kwargs["output_folder"]) / "page-1.png"
        rendered.write_bytes(_png_bytes())
        return [str(rendered)]

    monkeypatch.setattr(file_processing, "pdfinfo_from_path", fake_info)
    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    with processing_workspace(configured) as workspace:
        sheets = normalize_upload(
            _stored(pdf_path),
            workspace=workspace,
            allow_zip=False,
            configured=configured,
        )

    assert len(sheets) == 1
    assert observed == {
        "info_timeout": 7,
        "conversion_timeout": 11,
        "dpi": 144,
        "first_page": 1,
        "last_page": 1,
    }


def test_pdf_render_count_must_equal_declared_page_count(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "short-render.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 2}
    )
    monkeypatch.setattr(file_processing, "convert_from_path", lambda *_, **__: [])

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="expected number of pages"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
            )


def test_pdf_renderer_cannot_return_a_path_outside_its_output_directory(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "escaped-render.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    outside_page = tmp_path / "outside.png"
    outside_page.write_bytes(_png_bytes())
    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 1}
    )
    monkeypatch.setattr(
        file_processing,
        "convert_from_path",
        lambda *_, **__: [str(outside_page)],
    )

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="unsafe rendered page"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
            )


def test_pdf_render_byte_limit_stops_before_later_pages_accumulate(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "byte-amplification.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_archive_uncompressed_mb=1,
    )
    rendered_pages: list[int] = []

    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 3}
    )

    def fake_convert(*args, **kwargs):
        paths: list[str] = []
        for page_number in range(kwargs["first_page"], kwargs["last_page"] + 1):
            rendered_pages.append(page_number)
            rendered = Path(kwargs["output_folder"]) / f"page-{page_number}.png"
            rendered.write_bytes(b"x" * 600_000)
            paths.append(str(rendered))
        return paths

    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    monkeypatch.setattr(file_processing, "_image_pixel_count", lambda *_: 1)
    monkeypatch.setattr(file_processing, "_validate_image", lambda *_, **__: 1)

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileTooLargeError, match="configured expansion limit"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
                configured=configured,
            )
        assert list(workspace.glob("pdf-*")) == []

    assert rendered_pages == [1, 2]


def test_pdf_render_pixel_limit_stops_before_later_pages_accumulate(
    tmp_path: Path, monkeypatch
) -> None:
    pdf_path = tmp_path / "pixel-amplification.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\nsynthetic")
    rendered_pages: list[int] = []

    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 3}
    )

    def fake_convert(*args, **kwargs):
        paths: list[str] = []
        for page_number in range(kwargs["first_page"], kwargs["last_page"] + 1):
            rendered_pages.append(page_number)
            rendered = Path(kwargs["output_folder"]) / f"page-{page_number}.png"
            rendered.write_bytes(b"rendered-page")
            paths.append(str(rendered))
        return paths

    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    monkeypatch.setattr(
        file_processing, "_image_pixel_count", lambda *_: 160_000_000
    )
    monkeypatch.setattr(
        file_processing, "_validate_image", lambda *_, **__: 160_000_000
    )

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="unsafe image dimensions"):
            normalize_upload(
                _stored(pdf_path),
                workspace=workspace,
                allow_zip=False,
            )
        assert list(workspace.glob("pdf-*")) == []

    assert rendered_pages == [1, 2]


def test_zip_pdf_rendering_uses_the_archives_remaining_byte_budget(
    tmp_path: Path, monkeypatch
) -> None:
    archive_path = tmp_path / "mixed.zip"
    first_image = b"\x89PNG\r\n\x1a\n" + b"x" * (600_000 - 8)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("first.png", first_image)
        archive.writestr("remaining.pdf", b"%PDF-1.7\nsynthetic")

    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_archive_uncompressed_mb=1,
    )
    rendered_pages: list[int] = []
    monkeypatch.setattr(
        file_processing, "pdfinfo_from_path", lambda *_, **__: {"Pages": 3}
    )

    def fake_convert(*args, **kwargs):
        paths: list[str] = []
        for page_number in range(kwargs["first_page"], kwargs["last_page"] + 1):
            rendered_pages.append(page_number)
            rendered = Path(kwargs["output_folder"]) / f"page-{page_number}.png"
            rendered.write_bytes(b"x" * 300_000)
            paths.append(str(rendered))
        return paths

    monkeypatch.setattr(file_processing, "convert_from_path", fake_convert)
    monkeypatch.setattr(file_processing, "_image_pixel_count", lambda *_: 1)
    monkeypatch.setattr(file_processing, "_validate_image", lambda *_, **__: 1)

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileTooLargeError, match="configured expansion limit"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
                configured=configured,
            )
        assert list(workspace.glob("pdf-*")) == []

    assert rendered_pages == [1, 2]


def test_archive_entry_count_includes_directories(tmp_path: Path) -> None:
    archive_path = tmp_path / "many-entries.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("one/", b"")
        archive.writestr("two/", b"")
        archive.writestr("three/", b"")
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_archive_entries=2,
    )

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileProcessingError, match="3 entries"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
                configured=configured,
            )


def test_archive_symlink_entry_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    link = zipfile.ZipInfo("linked.png")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(link, b"target.png")

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="link or special-file"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )


def test_encrypted_archive_entry_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "encrypted.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sheet.png", _png_bytes())
    payload = bytearray(archive_path.read_bytes())
    local_header = payload.index(b"PK\x03\x04")
    central_header = payload.index(b"PK\x01\x02")
    payload[local_header + 6 : local_header + 8] = (1).to_bytes(2, "little")
    payload[central_header + 8 : central_header + 10] = (1).to_bytes(2, "little")
    archive_path.write_bytes(payload)

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="Encrypted archive entry"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )


def test_nested_archive_is_rejected(tmp_path: Path) -> None:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("sheet.png", _png_bytes())
    archive_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("inner.zip", inner.getvalue())

    with processing_workspace() as workspace:
        with pytest.raises(UnsupportedFileError, match="Nested archive"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )


def test_archive_duplicate_paths_are_rejected_case_insensitively(tmp_path: Path) -> None:
    archive_path = tmp_path / "duplicates.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("Sheet.png", _png_bytes())
        archive.writestr("sheet.PNG", _png_bytes())

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="duplicate path"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )


def test_archive_compression_ratio_is_bounded(tmp_path: Path) -> None:
    archive_path = tmp_path / "ratio.zip"
    with zipfile.ZipFile(
        archive_path, "w", compression=zipfile.ZIP_DEFLATED
    ) as archive:
        archive.writestr("sheet.png", b"A" * 100_000)
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_archive_compression_ratio=10.0,
    )

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileProcessingError, match="compression ratio"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
                configured=configured,
            )


def test_archive_expanded_byte_limit_is_checked_before_extraction(tmp_path: Path) -> None:
    archive_path = tmp_path / "expanded.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("one.png", b"1" * 600_000)
        archive.writestr("two.png", b"2" * 600_000)
    configured = replace(
        settings,
        upload_dir=tmp_path / "uploads",
        max_archive_uncompressed_mb=1,
    )

    with processing_workspace(configured) as workspace:
        with pytest.raises(FileTooLargeError, match="expands beyond"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
                configured=configured,
            )


def test_archive_member_magic_mismatch_is_rejected_and_cleaned(tmp_path: Path) -> None:
    archive_path = tmp_path / "mismatch.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sheet.png", b"%PDF-1.7\nwrong-content")

    with processing_workspace() as workspace:
        with pytest.raises(UnsupportedFileError, match="does not match"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )
        assert list(workspace.glob("entry-*")) == []


def test_corrupt_archive_member_is_rejected_and_partial_file_is_cleaned(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "bad-crc.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("sheet.png", _png_bytes())
    payload = bytearray(archive_path.read_bytes())
    local_header = payload.index(b"PK\x03\x04")
    filename_length = int.from_bytes(
        payload[local_header + 26 : local_header + 28], "little"
    )
    extra_length = int.from_bytes(
        payload[local_header + 28 : local_header + 30], "little"
    )
    content_start = local_header + 30 + filename_length + extra_length
    payload[content_start + 12] ^= 0x01
    archive_path.write_bytes(payload)

    with processing_workspace() as workspace:
        with pytest.raises(FileProcessingError, match="could not be read safely"):
            normalize_upload(
                _stored(archive_path),
                workspace=workspace,
                allow_zip=True,
            )
        assert list(workspace.glob("entry-*")) == []


def test_scan_cleanup_never_deletes_outside_upload_root(tmp_path: Path) -> None:
    configured = replace(settings, upload_dir=tmp_path / "uploads")
    configured.upload_dir.mkdir()
    outside = tmp_path / ("a" * 32 + ".png")
    outside.write_bytes(b"keep-me")

    deleted = discard_scan_uploads(
        [f"../{outside.name}"], configured=configured
    )

    assert deleted == 0
    assert outside.read_bytes() == b"keep-me"
