# File: backend/app/presentation/api/proof_upload.py
from pathlib import PurePath
from fastapi import HTTPException
from app.core.config import settings


async def read_proof_upload(upload):
    if upload is None:
        return None, None
    try:
        filename = upload.filename or ""
        if PurePath(filename).suffix.lower() not in (".png", ".jpg", ".jpeg", ".webp"):
            raise HTTPException(415, "Proof must be a static PNG, JPEG or WebP image.")
        content = await upload.read(settings.max_proof_bytes + 1)
        if len(content) > settings.max_proof_bytes:
            raise HTTPException(413, "Proof image exceeds the allowed size.")
        if not content:
            raise HTTPException(400, "Proof image is empty.")
        return content, filename
    finally:
        await upload.close()
