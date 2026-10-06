# File: backend/app/presentation/media_routes.py
import asyncio
import io
import re
import stat
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from app.core.config import settings

router = APIRouter()
_read_slot = asyncio.Semaphore(1)
_HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'"}


def _reparse(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) &
                                    getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024))


def _read_media(folder, filename, screenshot=False):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", filename) or ".." in filename:
        raise HTTPException(404, "Media not found.")
    base = Path(settings.base_storage_dir).absolute()
    root, path = base / folder, base / folder / filename
    try:
        if any(_reparse(item) for item in (base, root, path)):
            raise HTTPException(404, "Media not found.")
        if not path.is_file() or path.resolve().parent != root.resolve():
            raise HTTPException(404, "Media not found.")
        with path.open("rb") as handle:
            content = handle.read(settings.max_encoded_proof_bytes + 1)
        if len(content) > settings.max_encoded_proof_bytes:
            raise HTTPException(413, "Media exceeds the allowed size.")
        if screenshot:
            if path.suffix.lower() != ".png":
                raise HTTPException(404, "Media not found.")
            with Image.open(io.BytesIO(content), formats=["PNG"]) as image:
                if image.width * image.height > settings.max_proof_pixels or image.n_frames != 1:
                    raise HTTPException(404, "Media not found.")
                image.verify()
            with Image.open(io.BytesIO(content), formats=["PNG"]) as image:
                image.load()
        return content
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(404, "Media not found.") from None


async def _load(folder, filename, screenshot=False):
    async with _read_slot:
        task = asyncio.create_task(asyncio.to_thread(_read_media, folder, filename, screenshot))
        canceled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                canceled = True
            except Exception:
                if not canceled:
                    raise
                break
        if canceled:
            # Retrieve errors before propagating cancellation; keep the slot until thread joins.
            if not task.cancelled():
                task.exception()
            raise asyncio.CancelledError
        return task.result()


@router.get("/static/uploads/{filename}")
async def download_proof(filename: str):
    content = await _load("uploads", filename)
    headers = dict(_HEADERS, **{"Content-Disposition": f'attachment; filename="{filename}"'})
    return Response(content, media_type="application/octet-stream", headers=headers)


@router.get("/static/screenshots/{filename}")
async def view_screenshot(filename: str):
    content = await _load("screenshots", filename, True)
    return Response(content, media_type="image/png", headers=_HEADERS)
