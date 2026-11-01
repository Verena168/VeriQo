"""File uploads (CVs, pitch decks) stored in MongoDB GridFS.

Uses PyMongo's native async GridFS (AsyncGridFSBucket), the successor to Motor's GridFS API,
so the project keeps one MongoDB driver. Postgres stores only the returned file id (24-char hex).

Files are validated by their content, not their extension or the browser's Content-Type, which
a client can set to anything.
"""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from bson import ObjectId
from bson.errors import InvalidId
from gridfs import AsyncGridFSBucket
from gridfs.errors import NoFile

from app.core.config import get_settings
from app.mongo.client import get_mongo_db

MB = 1024 * 1024


@dataclass(frozen=True)
class FileKind:
    label: str
    max_bytes: int
    # (extension, magic-bytes prefix, content type)
    formats: tuple[tuple[str, bytes, str], ...]


CV = FileKind("CV", 5 * MB, (
    (".pdf", b"%PDF-", "application/pdf"),
    (".docx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    (".txt", b"", "text/plain; charset=utf-8"),  # no signature: content checked in validate()
))
PITCH_DECK = FileKind("pitch deck", 20 * MB, (
    (".pdf", b"%PDF-", "application/pdf"),
    # .pptx is a ZIP container; the extension check below separates it from other ZIPs.
    (".pptx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
))


class FileRejected(ValueError):
    pass


@dataclass(frozen=True)
class StoredFile:
    file_id: str
    filename: str
    content_type: str
    size: int
    sha256: str


def _bucket() -> AsyncGridFSBucket:
    return AsyncGridFSBucket(get_mongo_db(), bucket_name=get_settings().gridfs_bucket)


def _is_text(data: bytes) -> bool:
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def validate(kind: FileKind, filename: str, data: bytes) -> str:
    """Return the trusted content type, or raise FileRejected with a user-facing message."""
    if not data:
        raise FileRejected(f"The {kind.label} file is empty")
    if len(data) > kind.max_bytes:
        raise FileRejected(f"The {kind.label} must be {kind.max_bytes // MB} MB or smaller")
    name = filename.lower()
    for ext, magic, content_type in kind.formats:
        if not name.endswith(ext):
            continue
        if magic and data.startswith(magic):
            return content_type
        if not magic and _is_text(data):
            return content_type
    allowed = " or ".join(ext.lstrip(".").upper() for ext, _, _ in kind.formats)
    raise FileRejected(f"The {kind.label} must be a valid {allowed} file")


async def save(kind: FileKind, filename: str, data: bytes, metadata: dict) -> StoredFile:
    content_type = validate(kind, filename, data)
    digest = hashlib.sha256(data).hexdigest()
    safe_name = (filename.replace("\\", "/").rsplit("/", 1)[-1] or "upload")[:200]
    file_id = await _bucket().upload_from_stream(
        safe_name, data,
        metadata={**metadata, "kind": kind.label, "content_type": content_type, "sha256": digest},
    )
    return StoredFile(str(file_id), safe_name, content_type, len(data), digest)


def _oid(file_id: str) -> ObjectId:
    try:
        return ObjectId(file_id)
    except (InvalidId, TypeError) as exc:
        raise FileNotFoundError(file_id) from exc


async def open_stream(file_id: str) -> tuple[dict, AsyncIterator[bytes]]:
    """Return (info, chunk iterator) for streaming a stored file. Raises FileNotFoundError."""
    try:
        grid_out = await _bucket().open_download_stream(_oid(file_id))
    except NoFile as exc:
        raise FileNotFoundError(file_id) from exc
    meta = grid_out.metadata or {}
    info = {
        "filename": grid_out.filename,
        "content_type": meta.get("content_type", "application/octet-stream"),
        "size": grid_out.length,
    }

    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await grid_out.readchunk():
            yield chunk

    return info, chunks()


async def delete(file_id: str | None) -> None:
    """Delete a stored file; missing files are ignored (deleting twice is harmless)."""
    if not file_id:
        return
    try:
        await _bucket().delete(_oid(file_id))
    except (NoFile, FileNotFoundError):
        pass
