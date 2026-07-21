from __future__ import annotations

import re
import shutil
import stat
import tempfile
import time
import unicodedata
import uuid
import warnings
import zipfile
from collections.abc import Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterator

import cv2
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

try:
    from pdf2image import convert_from_path, pdfinfo_from_path
    from pdf2image.exceptions import (
        PDFInfoNotInstalledError,
        PDFPageCountError,
        PDFPopplerTimeoutError,
        PDFSyntaxError,
    )
except ModuleNotFoundError:
    convert_from_path = None
    pdfinfo_from_path = None

    class PDFInfoNotInstalledError(Exception):
        """Fallback error used when the optional PDF package is absent."""

    class PDFPageCountError(Exception):
        """Fallback error used when the optional PDF package is absent."""

    class PDFPopplerTimeoutError(Exception):
        """Fallback error used when the optional PDF package is absent."""

    class PDFSyntaxError(Exception):
        """Fallback error used when the optional PDF package is absent."""

from config import Settings, settings
from errors import ApplicationError


IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
PDF_SUFFIXES = frozenset({".pdf"})
ZIP_SUFFIXES = frozenset({".zip"})
SCAN_SUFFIXES = IMAGE_SUFFIXES | PDF_SUFFIXES | ZIP_SUFFIXES
MAX_IMAGE_DIMENSION = 12_000
MAX_BATCH_TOTAL_PIXELS = 300_000_000
MAX_FILENAME_BYTES = 255
MAX_ARCHIVE_PATH_BYTES = 1024
MAX_JPEG_PNG_FRAMES = 1
PDF_RENDER_MAX_DIMENSION = 2500
SIGNATURE_READ_SIZE = 1024
COPY_CHUNK_SIZE = 1024 * 1024
ALLOWED_ZIP_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class FileProcessingError(ApplicationError):
    """Raised for a safe, user-facing upload or conversion failure."""


class UnsupportedFileError(FileProcessingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=415)


class FileTooLargeError(FileProcessingError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=413)


@dataclass(frozen=True, slots=True)
class StoredUpload:
    path: Path
    original_name: str
    relative_path: str


@dataclass(frozen=True, slots=True)
class NormalizedSheet:
    path: Path
    filename: str
    source_relative_path: str


def _contains_unsafe_characters(value: str) -> bool:
    return any(unicodedata.category(character) in {"Cc", "Cf", "Cs"} for character in value)


def _is_reserved_windows_name(value: str) -> bool:
    stem = value.rstrip(" .").split(".", 1)[0].upper()
    return stem in WINDOWS_RESERVED_NAMES


def _safe_client_filename(filename: str | None) -> str:
    if not isinstance(filename, str) or not filename.strip():
        raise UnsupportedFileError("Every upload must include a filename")
    normalized = unicodedata.normalize("NFC", filename).replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].strip()
    if (
        not basename
        or basename in {".", ".."}
        or _contains_unsafe_characters(basename)
        or basename.endswith((" ", "."))
        or _is_reserved_windows_name(basename)
    ):
        raise UnsupportedFileError("The upload filename is unsafe")
    try:
        encoded_length = len(basename.encode("utf-8", "strict"))
    except UnicodeEncodeError as exc:
        raise UnsupportedFileError("The upload filename is invalid") from exc
    if encoded_length > MAX_FILENAME_BYTES:
        raise UnsupportedFileError(
            f"The upload filename exceeds {MAX_FILENAME_BYTES} UTF-8 bytes"
        )
    return basename


def _safe_suffix(filename: str | None) -> str:
    safe_name = _safe_client_filename(filename)
    suffix = PurePosixPath(safe_name).suffix.lower()
    if not suffix:
        raise UnsupportedFileError(f"File {safe_name!r} has no extension")
    return suffix


def _detected_content_type(signature: bytes) -> str | None:
    if signature.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if signature.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if signature.startswith(b"%PDF-"):
        return "application/pdf"
    if signature.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "application/zip"
    return None


def _expected_content_type(suffix: str) -> str | None:
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".zip":
        return "application/zip"
    return None


def _validate_signature_bytes(signature: bytes, *, suffix: str, display_name: str) -> None:
    expected = _expected_content_type(suffix)
    if expected is None:
        return
    detected = _detected_content_type(signature)
    if detected is None:
        raise FileProcessingError(
            f"{display_name} does not contain a recognized {suffix} file",
            status_code=422,
        )
    if detected != expected:
        raise UnsupportedFileError(
            f"{display_name} content does not match its {suffix} extension"
        )


def _validate_file_signature(path: Path, *, suffix: str, display_name: str) -> None:
    try:
        with path.open("rb") as source:
            signature = source.read(SIGNATURE_READ_SIZE)
    except OSError as exc:
        raise FileProcessingError(
            f"{display_name} could not be read safely", status_code=422
        ) from exc
    _validate_signature_bytes(signature, suffix=suffix, display_name=display_name)


def _category_path(category: str, configured: Settings) -> Path:
    if category not in {"scans", "answer-keys"}:
        raise ValueError("Unsupported upload category")
    root = configured.upload_dir.resolve()
    category_path = (root / category).resolve()
    if category_path.parent != root:
        raise ValueError("Upload category escaped the configured upload directory")
    category_path.mkdir(parents=True, exist_ok=True)
    return category_path


async def store_upload(
    upload: UploadFile,
    *,
    category: str,
    allowed_suffixes: frozenset[str] = SCAN_SUFFIXES,
    configured: Settings = settings,
) -> StoredUpload:
    try:
        original_name = _safe_client_filename(upload.filename)
        suffix = _safe_suffix(original_name)
    except Exception:
        await upload.close()
        raise
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        await upload.close()
        raise UnsupportedFileError(
            f"Unsupported file type {suffix}; allowed types are {allowed}"
        )
    try:
        destination_dir = _category_path(category, configured)
    except Exception:
        await upload.close()
        raise
    destination = destination_dir / f"{uuid.uuid4().hex}{suffix}"
    total_bytes = 0
    try:
        with destination.open("xb") as output:
            while chunk := await upload.read(COPY_CHUNK_SIZE):
                total_bytes += len(chunk)
                if total_bytes > configured.max_file_size_bytes:
                    raise FileTooLargeError(
                        f"{original_name} exceeds the "
                        f"{configured.max_file_size_mb} MB upload limit"
                    )
                output.write(chunk)
        if total_bytes == 0:
            raise FileProcessingError("The uploaded file is empty", status_code=400)
        _validate_file_signature(
            destination,
            suffix=suffix,
            display_name=original_name,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()
    # `destination` derives from the resolved category dir, so compute the
    # relative path against the resolved root too. Using the unresolved
    # `configured.upload_dir` raises ValueError when the path traverses a
    # symlink (e.g. macOS /tmp -> /private/tmp), turning a valid upload into 500.
    relative_path = destination.relative_to(
        configured.upload_dir.resolve()
    ).as_posix()
    return StoredUpload(
        path=destination,
        original_name=original_name,
        relative_path=relative_path,
    )


async def read_limited_upload(
    upload: UploadFile,
    *,
    allowed_suffixes: frozenset[str],
    configured: Settings = settings,
) -> bytes:
    try:
        original_name = _safe_client_filename(upload.filename)
        suffix = _safe_suffix(original_name)
    except Exception:
        await upload.close()
        raise
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        await upload.close()
        raise UnsupportedFileError(
            f"Unsupported file type {suffix}; allowed types are {allowed}"
        )
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        while chunk := await upload.read(COPY_CHUNK_SIZE):
            total_bytes += len(chunk)
            if total_bytes > configured.max_file_size_bytes:
                raise FileTooLargeError(
                    f"{original_name} exceeds the "
                    f"{configured.max_file_size_mb} MB upload limit"
                )
            chunks.append(chunk)
    finally:
        await upload.close()
    if total_bytes == 0:
        raise FileProcessingError("The uploaded file is empty", status_code=400)
    content = b"".join(chunks)
    if suffix == ".csv" and b"\x00" in content:
        raise FileProcessingError(
            f"{original_name} contains invalid binary data", status_code=400
        )
    _validate_signature_bytes(
        content[:SIGNATURE_READ_SIZE],
        suffix=suffix,
        display_name=original_name,
    )
    return content


@contextmanager
def processing_workspace(configured: Settings = settings) -> Iterator[Path]:
    upload_root = configured.upload_dir.resolve()
    processing_root = (upload_root / ".processing").resolve()
    if processing_root.parent != upload_root:
        raise RuntimeError("Processing workspace escaped the upload directory")
    processing_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix="job-", dir=processing_root))
    try:
        yield workspace
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _validate_image(
    path: Path, display_name: str, *, configured: Settings = settings
) -> int:
    suffix = path.suffix.lower()
    _validate_file_signature(path, suffix=suffix, display_name=display_name)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                expected_format = "PNG" if suffix == ".png" else "JPEG"
                if image.format != expected_format:
                    raise UnsupportedFileError(
                        f"{display_name} is not a valid {expected_format} image"
                    )
                width, height = image.size
                if width <= 0 or height <= 0:
                    raise FileProcessingError(
                        f"{display_name} has invalid image dimensions", status_code=422
                    )
                if (
                    width > MAX_IMAGE_DIMENSION
                    or height > MAX_IMAGE_DIMENSION
                    or width * height > configured.max_image_pixels
                ):
                    raise FileProcessingError(
                        f"{display_name} has unsafe image dimensions", status_code=422
                    )
                if getattr(image, "n_frames", 1) > MAX_JPEG_PNG_FRAMES:
                    raise FileProcessingError(
                        f"{display_name} contains multiple image frames", status_code=422
                    )
                image.verify()
            with Image.open(path) as decoded_image:
                decoded_image.load()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise FileProcessingError(
            f"{display_name} is corrupt or is not a valid image", status_code=422
        ) from exc
    decoded = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if decoded is None or decoded.shape[:2] != (height, width):
        raise FileProcessingError(
            f"{display_name} could not be decoded as an image", status_code=422
        )
    return width * height


def _image_pixel_count(path: Path) -> int:
    try:
        with Image.open(path) as image:
            width, height = image.size
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise FileProcessingError(
            "A normalized image could not be inspected safely", status_code=422
        ) from exc
    return width * height


def _normalize_pdf(
    path: Path,
    *,
    display_name: str,
    source_relative_path: str,
    workspace: Path,
    configured: Settings,
    max_pages: int | None = None,
    max_rendered_bytes: int | None = None,
    max_rendered_pixels: int | None = None,
) -> list[NormalizedSheet]:
    _validate_file_signature(path, suffix=".pdf", display_name=display_name)
    if convert_from_path is None or pdfinfo_from_path is None:
        raise FileProcessingError(
            "PDF support requires the pdf2image package and Poppler",
            status_code=503,
        )
    page_limit = min(
        configured.max_files_per_request,
        configured.max_pdf_pages,
        max_pages if max_pages is not None else configured.max_files_per_request,
    )
    if page_limit <= 0:
        raise FileProcessingError(
            "The expanded sheet limit has been reached", status_code=422
        )
    try:
        information = pdfinfo_from_path(
            str(path), timeout=configured.pdf_info_timeout_seconds
        )
        if not isinstance(information, dict):
            raise ValueError("PDF metadata is malformed")
        encrypted = str(information.get("Encrypted", "no")).strip().lower()
        if encrypted not in {"", "no", "false", "0", "none"}:
            raise FileProcessingError(
                f"{display_name} is encrypted and cannot be processed",
                status_code=422,
            )
        raw_page_count = information.get("Pages", 0)
        if isinstance(raw_page_count, bool):
            raise ValueError("PDF page count is malformed")
        page_count = int(raw_page_count)
        if page_count <= 0:
            raise FileProcessingError(
                f"{display_name} contains no pages", status_code=422
            )
        if page_count > page_limit:
            raise FileProcessingError(
                f"{display_name} contains {page_count} pages; the remaining "
                f"sheet limit is {page_limit}",
                status_code=422,
            )
    except PDFInfoNotInstalledError as exc:
        raise FileProcessingError(
            "PDF conversion requires Poppler to be installed and available on PATH",
            status_code=503,
        ) from exc
    except (PDFPageCountError, PDFSyntaxError, PDFPopplerTimeoutError, ValueError) as exc:
        raise FileProcessingError(
            f"{display_name} is not a valid processable PDF", status_code=422
        ) from exc

    configured_byte_limit = min(
        configured.max_archive_uncompressed_bytes,
        configured.max_batch_size_bytes,
    )
    rendered_byte_limit = min(
        configured_byte_limit,
        max_rendered_bytes
        if max_rendered_bytes is not None
        else configured_byte_limit,
    )
    rendered_pixel_limit = min(
        MAX_BATCH_TOTAL_PIXELS,
        max_rendered_pixels
        if max_rendered_pixels is not None
        else MAX_BATCH_TOTAL_PIXELS,
    )
    if rendered_byte_limit <= 0:
        raise FileTooLargeError(
            f"{display_name} renders beyond the configured expansion limit"
        )
    if rendered_pixel_limit <= 0:
        raise FileProcessingError(
            f"{display_name} renders to unsafe image dimensions", status_code=422
        )

    output_dir = workspace / f"pdf-{uuid.uuid4().hex}"
    output_dir.mkdir()
    output_root = output_dir.resolve()
    sheets: list[NormalizedSheet] = []
    seen_paths: set[Path] = set()
    total_rendered_bytes = 0
    total_rendered_pixels = 0
    conversion_timeout_remaining = float(configured.pdf_conversion_timeout_seconds)
    try:
        for page_number in range(1, page_count + 1):
            if conversion_timeout_remaining <= 0:
                raise FileProcessingError(
                    f"{display_name} is not a valid processable PDF",
                    status_code=422,
                )
            conversion_started = time.monotonic()
            try:
                converted_paths = convert_from_path(
                    str(path),
                    output_folder=str(output_dir),
                    fmt="png",
                    paths_only=True,
                    thread_count=1,
                    dpi=configured.pdf_dpi,
                    size=PDF_RENDER_MAX_DIMENSION,
                    first_page=page_number,
                    last_page=page_number,
                    timeout=conversion_timeout_remaining,
                )
            except PDFInfoNotInstalledError as exc:
                raise FileProcessingError(
                    "PDF conversion requires Poppler to be installed and available on PATH",
                    status_code=503,
                ) from exc
            except (
                PDFPageCountError,
                PDFSyntaxError,
                PDFPopplerTimeoutError,
                ValueError,
            ) as exc:
                raise FileProcessingError(
                    f"{display_name} is not a valid processable PDF",
                    status_code=422,
                ) from exc
            finally:
                conversion_timeout_remaining -= max(
                    0.0, time.monotonic() - conversion_started
                )

            try:
                converted_paths = list(converted_paths)
            except (TypeError, ValueError) as exc:
                raise FileProcessingError(
                    f"{display_name} returned invalid rendered pages", status_code=422
                ) from exc
            if len(converted_paths) != 1:
                raise FileProcessingError(
                    f"{display_name} did not render the expected number of pages",
                    status_code=422,
                )

            converted_path = converted_paths[0]
            try:
                image_path = Path(converted_path).resolve()
            except (OSError, TypeError, ValueError) as exc:
                raise FileProcessingError(
                    f"{display_name} produced an invalid rendered page",
                    status_code=422,
                ) from exc
            if (
                image_path.parent != output_root
                or image_path in seen_paths
                or not image_path.is_file()
                or image_path.suffix.lower() != ".png"
            ):
                raise FileProcessingError(
                    f"{display_name} produced an unsafe rendered page", status_code=422
                )
            seen_paths.add(image_path)
            page_name = f"{display_name}#page-{page_number}"
            try:
                rendered_size = image_path.stat().st_size
            except OSError as exc:
                raise FileProcessingError(
                    f"{page_name} could not be inspected safely", status_code=422
                ) from exc
            if total_rendered_bytes + rendered_size > rendered_byte_limit:
                raise FileTooLargeError(
                    f"{display_name} renders beyond the configured expansion limit"
                )

            rendered_pixels = _image_pixel_count(image_path)
            if total_rendered_pixels + rendered_pixels > rendered_pixel_limit:
                raise FileProcessingError(
                    f"{display_name} renders to unsafe image dimensions",
                    status_code=422,
                )
            validated_pixels = _validate_image(
                image_path, page_name, configured=configured
            )
            if validated_pixels != rendered_pixels:
                raise FileProcessingError(
                    f"{page_name} changed while it was being validated",
                    status_code=422,
                )

            total_rendered_bytes += rendered_size
            total_rendered_pixels += rendered_pixels
            sheets.append(
                NormalizedSheet(
                    path=image_path,
                    filename=page_name,
                    source_relative_path=source_relative_path,
                )
            )
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise

    return sheets


def _archive_member_label(member: zipfile.ZipInfo) -> str:
    return repr(member.filename[:120])


def _validate_archive_member_type(member: zipfile.ZipInfo) -> None:
    label = _archive_member_label(member)
    if member.flag_bits & 0x1:
        raise FileProcessingError(
            f"Encrypted archive entry is not supported: {label}", status_code=422
        )
    if member.compress_type not in ALLOWED_ZIP_COMPRESSION:
        raise FileProcessingError(
            f"Archive entry uses an unsupported compression method: {label}",
            status_code=422,
        )
    if member.create_system not in {0, 3}:
        raise FileProcessingError(
            f"Archive entry uses unsupported platform metadata: {label}",
            status_code=422,
        )

    if member.create_system == 3:
        unix_mode = (member.external_attr >> 16) & 0xFFFF
        file_type = stat.S_IFMT(unix_mode)
        expected_types = {0, stat.S_IFDIR} if member.is_dir() else {0, stat.S_IFREG}
        if stat.S_ISLNK(unix_mode) or file_type not in expected_types:
            raise FileProcessingError(
                f"Archive contains a link or special-file entry: {label}",
                status_code=422,
            )
    else:
        dos_attributes = member.external_attr & 0xFFFF
        if dos_attributes & 0x400:
            raise FileProcessingError(
                f"Archive contains a reparse-point entry: {label}", status_code=422
            )
        if not member.is_dir() and dos_attributes & 0x10:
            raise FileProcessingError(
                f"Archive entry has inconsistent file attributes: {label}",
                status_code=422,
            )


def _safe_archive_member(member: zipfile.ZipInfo) -> PurePosixPath:
    _validate_archive_member_type(member)
    normalized_name = unicodedata.normalize("NFC", member.filename).replace("\\", "/")
    candidate_name = normalized_name[:-1] if member.is_dir() else normalized_name
    parts = candidate_name.split("/")
    if (
        not candidate_name
        or normalized_name.startswith("/")
        or len(normalized_name.encode("utf-8", "surrogatepass")) > MAX_ARCHIVE_PATH_BYTES
        or any(
            not part
            or part in {".", ".."}
            or ":" in part
            or part.endswith((" ", "."))
            or _contains_unsafe_characters(part)
            or _is_reserved_windows_name(part)
            or len(part.encode("utf-8", "surrogatepass")) > MAX_FILENAME_BYTES
            for part in parts
        )
    ):
        raise FileProcessingError(
            f"Archive contains an unsafe path: {_archive_member_label(member)}",
            status_code=422,
        )
    return PurePosixPath(*parts)


def _copy_archive_member(
    source: BinaryIO,
    destination: Path,
    *,
    maximum_bytes: int,
    display_name: str,
) -> int:
    written = 0
    with destination.open("xb") as output:
        while chunk := source.read(COPY_CHUNK_SIZE):
            written += len(chunk)
            if written > maximum_bytes:
                raise FileTooLargeError(
                    f"Archive entry {display_name} exceeds the per-file upload limit"
                )
            output.write(chunk)
    return written


def _normalize_zip(
    stored: StoredUpload,
    *,
    workspace: Path,
    configured: Settings,
    max_sheets: int | None = None,
) -> list[NormalizedSheet]:
    archive_name = _safe_client_filename(stored.original_name)
    _validate_file_signature(
        stored.path,
        suffix=".zip",
        display_name=archive_name,
    )
    try:
        archive = zipfile.ZipFile(stored.path)
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError) as exc:
        raise FileProcessingError(
            f"{archive_name} is not a valid ZIP archive", status_code=422
        ) from exc

    with archive:
        sheet_limit = min(
            configured.max_files_per_request,
            max_sheets if max_sheets is not None else configured.max_files_per_request,
        )
        try:
            all_members = archive.infolist()
        except (zipfile.BadZipFile, OSError) as exc:
            raise FileProcessingError(
                f"{archive_name} has an invalid ZIP directory", status_code=422
            ) from exc
        if len(all_members) > configured.max_archive_entries:
            raise FileProcessingError(
                f"Archive contains {len(all_members)} entries; the limit is "
                f"{configured.max_archive_entries}",
                status_code=422,
            )

        members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
        seen_paths: set[str] = set()
        for member in all_members:
            member_path = _safe_archive_member(member)
            normalized_key = member_path.as_posix().casefold()
            if normalized_key in seen_paths:
                raise FileProcessingError(
                    f"Archive contains a duplicate path: {_archive_member_label(member)}",
                    status_code=422,
                )
            seen_paths.add(normalized_key)
            if not member.is_dir():
                members.append((member, member_path))

        if not members:
            raise FileProcessingError(
                f"{archive_name} contains no files", status_code=422
            )
        if any(
            member.file_size < 0 or member.compress_size < 0 for member, _ in members
        ):
            raise FileProcessingError(
                f"{archive_name} contains invalid entry sizes", status_code=422
            )
        total_uncompressed = sum(member.file_size for member, _ in members)
        archive_expansion_limit = min(
            configured.max_archive_uncompressed_bytes,
            configured.max_batch_size_bytes,
        )
        if total_uncompressed > archive_expansion_limit:
            raise FileTooLargeError(
                f"Archive expands beyond the "
                f"{configured.max_archive_uncompressed_mb} MB safety limit"
            )
        total_compressed = sum(member.compress_size for member, _ in members)
        if total_uncompressed and (
            total_compressed <= 0
            or total_uncompressed / total_compressed
            > configured.max_archive_compression_ratio
        ):
            raise FileProcessingError(
                "Archive has an unsafe aggregate compression ratio", status_code=422
            )

        sheets: list[NormalizedSheet] = []
        actual_expanded_bytes = 0
        normalized_output_bytes = 0
        normalized_pixels = 0
        for member, member_path in members:
            suffix = member_path.suffix.lower()
            if suffix in ZIP_SUFFIXES:
                raise UnsupportedFileError(
                    f"Nested archive entry {_archive_member_label(member)} is not supported"
                )
            if suffix not in IMAGE_SUFFIXES | PDF_SUFFIXES:
                raise UnsupportedFileError(
                    f"Archive entry {_archive_member_label(member)} is not a supported image or PDF"
                )
            if member.file_size > configured.max_file_size_bytes:
                raise FileTooLargeError(
                    f"Archive entry {_archive_member_label(member)} exceeds the per-file upload limit"
                )
            if member.file_size and member.compress_size == 0:
                raise FileProcessingError(
                    f"Archive entry {_archive_member_label(member)} has an unsafe compression ratio",
                    status_code=422,
                )
            if (
                member.compress_size
                and member.file_size / member.compress_size
                > configured.max_archive_compression_ratio
            ):
                raise FileProcessingError(
                    f"Archive entry {_archive_member_label(member)} has an unsafe compression ratio",
                    status_code=422,
                )
            extracted_path = workspace / f"entry-{uuid.uuid4().hex}{suffix}"
            try:
                remaining_expansion = (
                    archive_expansion_limit - actual_expanded_bytes
                )
                maximum_entry_bytes = min(
                    configured.max_file_size_bytes,
                    remaining_expansion,
                )
                if maximum_entry_bytes < member.file_size:
                    raise FileTooLargeError(
                        "Archive expands beyond the configured safety limit"
                    )
                with archive.open(member, "r") as source:
                    written = _copy_archive_member(
                        source,
                        extracted_path,
                        maximum_bytes=maximum_entry_bytes,
                        display_name=_archive_member_label(member),
                    )
                if written != member.file_size:
                    raise FileProcessingError(
                        f"Archive entry {_archive_member_label(member)} has inconsistent size metadata",
                        status_code=422,
                    )
                actual_expanded_bytes += written
                _validate_file_signature(
                    extracted_path,
                    suffix=suffix,
                    display_name=_archive_member_label(member),
                )
                entry_display_name = f"{archive_name}:{member_path.as_posix()}"
                if suffix in IMAGE_SUFFIXES:
                    if len(sheets) >= sheet_limit:
                        raise FileProcessingError(
                            f"Expanded archive exceeds the {sheet_limit} sheet limit",
                            status_code=422,
                        )
                    normalized_pixels += _validate_image(
                        extracted_path,
                        entry_display_name,
                        configured=configured,
                    )
                    normalized_output_bytes += written
                    sheets.append(
                        NormalizedSheet(
                            path=extracted_path,
                            filename=entry_display_name,
                            source_relative_path=stored.relative_path,
                        )
                    )
                else:
                    normalization_limit = min(
                        configured.max_archive_uncompressed_bytes,
                        configured.max_batch_size_bytes,
                    )
                    rendered_sheets = _normalize_pdf(
                        extracted_path,
                        display_name=entry_display_name,
                        source_relative_path=stored.relative_path,
                        workspace=workspace,
                        configured=configured,
                        max_pages=sheet_limit - len(sheets),
                        max_rendered_bytes=(
                            normalization_limit - normalized_output_bytes
                        ),
                        max_rendered_pixels=(
                            MAX_BATCH_TOTAL_PIXELS - normalized_pixels
                        ),
                    )
                    for rendered_sheet in rendered_sheets:
                        normalized_output_bytes += rendered_sheet.path.stat().st_size
                        normalized_pixels += _image_pixel_count(rendered_sheet.path)
                    sheets.extend(rendered_sheets)
                if normalized_output_bytes > min(
                    configured.max_archive_uncompressed_bytes,
                    configured.max_batch_size_bytes,
                ):
                    raise FileTooLargeError(
                        "Archive normalization exceeds the configured expansion limit"
                    )
                if normalized_pixels > MAX_BATCH_TOTAL_PIXELS:
                    raise FileProcessingError(
                        "Archive expands to unsafe image dimensions", status_code=422
                    )
            except FileProcessingError:
                extracted_path.unlink(missing_ok=True)
                raise
            except (
                zipfile.BadZipFile,
                RuntimeError,
                NotImplementedError,
                EOFError,
                OSError,
            ) as exc:
                extracted_path.unlink(missing_ok=True)
                raise FileProcessingError(
                    f"Archive entry {_archive_member_label(member)} could not be read safely",
                    status_code=422,
                ) from exc
        return sheets


def normalize_upload(
    stored: StoredUpload,
    *,
    workspace: Path,
    allow_zip: bool,
    configured: Settings = settings,
    max_sheets: int | None = None,
) -> list[NormalizedSheet]:
    original_name = _safe_client_filename(stored.original_name)
    sheet_limit = min(
        configured.max_files_per_request,
        max_sheets if max_sheets is not None else configured.max_files_per_request,
    )
    if sheet_limit <= 0:
        raise FileProcessingError("The expanded sheet limit has been reached", status_code=422)
    suffix = stored.path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        _validate_image(stored.path, original_name, configured=configured)
        return [
            NormalizedSheet(
                path=stored.path,
                filename=original_name,
                source_relative_path=stored.relative_path,
            )
        ]
    if suffix in PDF_SUFFIXES:
        return _normalize_pdf(
            stored.path,
            display_name=original_name,
            source_relative_path=stored.relative_path,
            workspace=workspace,
            configured=configured,
            max_pages=sheet_limit,
        )
    if suffix in ZIP_SUFFIXES and allow_zip:
        return _normalize_zip(
            stored,
            workspace=workspace,
            configured=configured,
            max_sheets=sheet_limit,
        )
    raise UnsupportedFileError(f"Unsupported file type {suffix}")


def discard_upload(stored: StoredUpload) -> None:
    stored.path.unlink(missing_ok=True)


def discard_scan_uploads(
    relative_paths: Iterable[str], *, configured: Settings = settings
) -> int:
    upload_root = configured.upload_dir.resolve()
    scans_root = (upload_root / "scans").resolve()
    generated_name = re.compile(r"^[0-9a-f]{32}\.(?:jpe?g|png|pdf|zip)$")
    deleted = 0
    for relative_path in set(relative_paths):
        candidate = upload_root / relative_path
        try:
            resolved_candidate = candidate.resolve()
            if candidate.parent.resolve() != scans_root:
                continue
            if resolved_candidate.parent != scans_root:
                continue
            if not generated_name.fullmatch(candidate.name):
                continue
            if candidate.is_file() or candidate.is_symlink():
                candidate.unlink()
                deleted += 1
        except OSError:
            continue
    return deleted
