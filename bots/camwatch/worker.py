"""One CamWatch pass: pull JPEGs, classify, publish on class change.

At most 8 cameras are sampled. The rest stay unlistened so the map can
still preview them (SAFETY-AGENT-DESIGN.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime

from camwatch.alerts import AlertsPublishError
from camwatch.model import MAX_CAMERAS, Camera, build_alert, iso_now, should_publish
from camwatch.sources import FrameFetchError, frames_for_camera
from camwatch.vision import Classifier, VisionError

logger = logging.getLogger("camwatch")

_DIGESTS_KEPT = 32


@dataclass
class WatchState:
    last_class: dict[str, str] = field(default_factory=dict)
    digests: dict[str, list[str]] = field(default_factory=dict)
    cursor: int = 0
    # camera id → (digest, vision class, alert) waiting on a failed POST
    pending: dict[str, tuple[str, str, dict]] = field(default_factory=dict)
    flood_keys: list[str] = field(default_factory=list)

    def seen(self, camera_id: str, digest: str) -> bool:
        return digest in self.digests.get(camera_id, [])

    def mark(self, camera_id: str, digest: str, vision_class: str) -> None:
        remembered = self.digests.setdefault(camera_id, [])
        if digest not in remembered:
            remembered.append(digest)
        del remembered[:-_DIGESTS_KEPT]
        self.last_class[camera_id] = vision_class


def select_cameras(
    cameras: list[Camera],
    watches: list[dict] | None,
    *,
    max_cameras: int = MAX_CAMERAS,
) -> list[Camera]:
    """Pick the cameras this tick will sample.

    ``watches is None`` or ``[]`` → local list (registry missing or no watch yet).
    A watch that does not include source ``camera`` contributes nothing.
    ``camera_ids`` empty means every configured camera on that watch.
    """
    limit = min(max_cameras, MAX_CAMERAS)
    if limit < 1:
        return []
    chosen = list(cameras)
    if watches:
        wanted: list[str] = []
        saw_camera_source = False
        explicit_ids = False
        for watch in watches:
            sources = [str(item) for item in watch.get("sources") or []]
            if "camera" not in sources:
                continue
            saw_camera_source = True
            ids = [str(item) for item in watch.get("camera_ids") or []]
            if ids:
                explicit_ids = True
                wanted.extend(ids)
        if not saw_camera_source:
            return []
        if explicit_ids:
            by_id = {camera.id: camera for camera in cameras}
            chosen = [by_id[camera_id] for camera_id in wanted if camera_id in by_id]
    active = chosen[:limit]
    skipped = [camera.id for camera in chosen[limit:]]
    if skipped:
        logger.info("sampling %s cameras; over cap and not sampled: %s", limit, skipped)
    return active


def run_once(
    cameras: list[Camera],
    *,
    classifier: Classifier,
    publisher,
    state: WatchState,
    watches: list[dict] | None = None,
    max_cameras: int = MAX_CAMERAS,
    max_frames: int = 1,
    now: datetime | None = None,
    fetcher=None,
) -> list[dict]:
    """Return the alert bodies that were published this pass.

    Up to 8 cameras are eligible. Each pass classifies one new frame
    (#33: at most one vision call per 15–30s). Unchanged JPEGs are skipped
    before classification. A failed POST is retried next pass without
    calling vision again.

    When ``watches`` is a non-empty registry with no ``camera`` source,
    this pass samples nothing (the region is not being watched).
    """
    stamp = iso_now(now)
    published: list[dict] = []
    pull = frames_for_camera if fetcher is None else _with_fetcher(fetcher)
    active = select_cameras(cameras, watches, max_cameras=max_cameras)
    if not active or max_frames < 1:
        return []
    start = state.cursor % len(active)
    order = list(range(start, len(active))) + list(range(start))
    used = 0
    for index in order:
        if used >= max_frames:
            break
        camera = active[index]
        held = state.pending.get(camera.id)
        if held is not None:
            digest, vision_class, alert = held
            if _publish(publisher, state, camera.id, digest, vision_class, alert, published):
                used += 1
                state.cursor = (index + 1) % len(active)
            continue
        try:
            frames = pull(camera)
        except FrameFetchError as exc:
            logger.warning("camera %s: %s", camera.id, exc)
            continue
        fresh = [frame for frame in frames if not state.seen(camera.id, frame.digest)]
        if not fresh:
            continue
        frame = replace(fresh[0], camera_name=camera.name)
        try:
            result = classifier.classify(frame)
        except VisionError as exc:
            logger.warning("camera %s: %s", camera.id, exc)
            return published
        used += 1
        if not should_publish(state.last_class.get(camera.id), result.vision_class):
            state.mark(camera.id, frame.digest, result.vision_class)
            state.cursor = (index + 1) % len(active)
            continue
        alert = build_alert(camera, result, frame, ts=stamp)
        _publish(
            publisher,
            state,
            camera.id,
            frame.digest,
            result.vision_class,
            alert,
            published,
        )
        state.cursor = (index + 1) % len(active)
    return published


def _publish(publisher, state: WatchState, camera_id: str, digest: str, vision_class: str, alert: dict, published: list[dict]) -> bool:
    """POST one alert. On failure, hold it and re-raise so the loop backs off."""
    try:
        response = publisher.publish(alert)
    except AlertsPublishError:
        state.pending[camera_id] = (digest, vision_class, alert)
        logger.warning("camera %s: alert publish failed; will retry without another vision call", camera_id)
        raise
    state.pending.pop(camera_id, None)
    state.mark(camera_id, digest, vision_class)
    # #11 dedupes the same dedupe_key for 60s and returns the original alert.
    if isinstance(response, dict) and response.get("deduped"):
        logger.info("bus deduped %s", alert["dedupe_key"])
        return True
    published.append(alert)
    logger.info("alert %s %s %s", camera_id, vision_class, alert["dedupe_key"])
    return True


def _with_fetcher(fetcher):
    def pull(camera: Camera):
        return frames_for_camera(camera, fetcher=fetcher)

    return pull
