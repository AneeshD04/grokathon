"""JPEG frame sources: a local inbox (demo inject) and HTTP stills."""

from __future__ import annotations

import hashlib
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from camwatch.model import MAX_JPEG_BYTES, Camera, Frame

_JPEG_SUFFIXES = {".jpg", ".jpeg"}
_BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.google.internal.",
    "instance-data",
    "instance-data.",
}


class FrameFetchError(Exception):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def _host_is_blocked(host: str) -> bool:
    hostname = (host or "").split("%")[0].strip("[]").lower()
    if not hostname:
        return True
    if hostname in _BLOCKED_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
        return _ip_is_blocked(ip)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise FrameFetchError("still_url host could not be resolved") from exc
    return any(_ip_is_blocked(ipaddress.ip_address(info[4][0])) for info in infos)


def _ip_is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback:
        return False
    return bool(
        ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def assert_still_url_safe(url: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise FrameFetchError("still_url must be http or https")
    if parsed.username or parsed.password:
        raise FrameFetchError("still_url must not include credentials")
    if _host_is_blocked(parsed.hostname or ""):
        raise FrameFetchError("still_url host is not allowed")
    return parsed


class _RedirectGuard(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        assert_still_url_safe(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_jpeg(url: str, timeout: float = 10.0, opener=None) -> bytes:
    assert_still_url_safe(url)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "grokathon-camwatch/0.1"},
        method="GET",
    )
    if opener is None:
        opener = urllib.request.build_opener(_RedirectGuard()).open
    try:
        with opener(request, timeout=timeout) as response:
            data = response.read(MAX_JPEG_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise FrameFetchError(f"JPEG GET failed: HTTP {exc.code}", status=exc.code) from exc
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
    camera_name: str | None = None,
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
        camera_name=camera_name,
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


def jpeg_from_mp4(data: bytes) -> bytes:
    """Return the one JPEG sample stored in a local MP4 (ftyp + mdat).

    Stdlib only. The fixture is a JPEG inside the media data box, not an
    H.264 bitstream, so this does not shell out to ffmpeg.
    """
    if len(data) < 8 or data[4:8] != b"ftyp":
        raise FrameFetchError("mp4 fallback is not an mp4")
    start = data.find(b"\xff\xd8")
    if start < 0:
        raise FrameFetchError("mp4 fallback has no JPEG frame")
    end = data.find(b"\xff\xd9", start + 2)
    if end < 0:
        raise FrameFetchError("mp4 JPEG frame is truncated")
    jpeg = data[start : end + 2]
    if len(jpeg) > MAX_JPEG_BYTES:
        raise FrameFetchError("JPEG is larger than 5MB")
    return jpeg


def frame_from_mp4(path: Path, *, thumb_url: str | None = None) -> Frame:
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_JPEG_BYTES + 65537)
    except OSError as exc:
        raise FrameFetchError(f"mp4 fallback unreadable: {path.name}") from exc
    if len(data) > MAX_JPEG_BYTES + 65536:
        raise FrameFetchError("mp4 fallback is larger than 5MB")
    return frame_from_bytes(
        jpeg_from_mp4(data),
        filename=path.name,
        path=path,
        thumb_url=thumb_url,
    )


def frames_for_camera(camera: Camera, *, fetcher=fetch_jpeg) -> list[Frame]:
    """One live still, or every JPEG currently in the inbox, oldest first.

    HTTP 404 on ``still_url`` uses ``camera.mp4_path`` when that local file
    is set. Any other fetch error stays a fetch error.
    """
    if camera.still_url:
        try:
            data = fetcher(camera.still_url)
        except FrameFetchError as exc:
            if exc.status == 404 and camera.mp4_path is not None:
                return [frame_from_mp4(camera.mp4_path, thumb_url=camera.still_url)]
            raise
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
