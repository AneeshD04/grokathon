"""JPEG frame sources: a local inbox (demo inject) and HTTP stills."""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from camwatch.model import MAX_JPEG_BYTES, Camera, Frame

_JPEG_SUFFIXES = {".jpg", ".jpeg"}


class FrameFetchError(Exception):
    pass


def fetch_jpeg(url: str, timeout: float = 10.0, opener=urllib.request.urlopen) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FrameFetchError("still_url must be http or https")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "grokathon-camwatch/0.1"},
        method="GET",
    )
    try:
        with opener(request, timeout=timeout) as response:
            data = response.read(MAX_JPEG_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise FrameFetchError(f"JPEG GET failed: HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FrameFetchError(f"JPEG GET failed: {exc.reason}") from exc
    if len(data) > MAX_JPEG_BYTES:
        raise FrameFetchError("JPEG is larger than 5MB")
    if not data.startswith(b"\xff\xd8"):
        raise FrameFetchError("response is not a JPEG")
    return data


def frame_from_bytes(
    data: bytes,
    *,
    filename: str | None,
    path: Path | None = None,
    thumb_url: str | None = None,
) -> Frame:
    if not data.startswith(b"\xff\xd8"):
        raise FrameFetchError("not a JPEG")
    if len(data) > MAX_JPEG_BYTES:
        raise FrameFetchError("JPEG is larger than 5MB")
    return Frame(
        jpeg=data,
        digest=hashlib.sha256(data).hexdigest(),
        filename=filename,
        path=path,
        thumb_url=thumb_url,
    )


def inbox_frames(directory: Path) -> list[Frame]:
    """New files are the caller's problem; this returns every valid JPEG."""
    if not directory.is_dir():
        return []
    paths = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in _JPEG_SUFFIXES
    ]
    paths.sort(key=lambda path: (path.stat().st_mtime, path.name))
    frames: list[Frame] = []
    for path in paths:
        try:
            frames.append(
                frame_from_bytes(path.read_bytes(), filename=path.name, path=path, thumb_url=None)
            )
        except (OSError, FrameFetchError):
            continue
    return frames


def frames_for_camera(camera: Camera, *, fetcher=fetch_jpeg) -> list[Frame]:
    """One live still, or every JPEG currently in the inbox, oldest first."""
    if camera.still_url:
        data = fetcher(camera.still_url)
        filename = Path(urllib.parse.urlparse(camera.still_url).path).name or None
        return [
            frame_from_bytes(
                data,
                filename=filename,
                thumb_url=camera.still_url,
            )
        ]
    if camera.inbox_dir is not None:
        return inbox_frames(camera.inbox_dir)
    return []
