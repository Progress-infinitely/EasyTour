from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(file_path: str) -> str:
    digest = hashlib.sha256()
    with open(file_path, 'rb') as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_upload_file(file_obj) -> str:
    current_position = file_obj.tell()
    file_obj.seek(0)
    digest = hashlib.sha256()
    for chunk in iter(lambda: file_obj.read(1024 * 1024), b''):
        digest.update(chunk)
    file_obj.seek(current_position)
    return digest.hexdigest()


def build_document_id(file_hash: str) -> str:
    return file_hash[:16]


def build_chunk_hash(content: str) -> str:
    return sha256_bytes(content.encode('utf-8'))[:16]


def guess_source_label(file_path: str) -> str:
    return Path(file_path).name
