"""One CamWatch pass: pull JPEGs, classify, publish on class change.

At most 8 cameras are sampled. The rest stay unlistened so the map can
still preview them (SAFETY-AGENT-DESIGN.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from camwatch.alerts import AlertsPublishError
from camwatch.model import MAX_CAMERAS, Camera, build_alert, iso_now, should_publish
from camwatch.sources import FrameFetchError, frames_for_camera
from camwatch.vision import Classifier

logger = logging.getLogger("camwatch")

_DIGESTS_KEPT = 32


@dataclass
class WatchState:
    last_class: dict[str, str] = field(default_factory=dict)
    digests: dict[str, list[str]] = field(default_factory=dict)

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
    now: datetime | None = None,
    fetcher=None,
) -> list[dict]:
    """Return the alert bodies that were published this pass.

    A publish failure leaves that frame unmarked so the next pass retries.
    """
    stamp = iso_now(now)
    published: list[dict] = []
    pull = frames_for_camera if fetcher is None else _with_fetcher(fetcher)
    for camera in select_cameras(cameras, watches, max_cameras=max_cameras):
        try:
            frames = pull(camera)
        except FrameFetchError as exc:
            logger.warning("camera %s: %s", camera.id, exc)
            continue
        for frame in frames:
            if state.seen(camera.id, frame.digest):
                continue
            result = classifier.classify(frame)
            if not should_publish(state.last_class.get(camera.id), result.vision_class):
                state.mark(camera.id, frame.digest, result.vision_class)
                continue
            alert = build_alert(camera, result, frame, ts=stamp)
            try:
                response = publisher.publish(alert)
            except AlertsPublishError:
                logger.warning("camera %s: alert publish failed; will retry", camera.id)
                raise
            state.mark(camera.id, frame.digest, result.vision_class)
            # #11 dedupes the same dedupe_key for 60s and returns the original alert.
            if isinstance(response, dict) and response.get("deduped"):
                logger.info("bus deduped %s", alert["dedupe_key"])
                continue
            published.append(alert)
            logger.info(
                "alert %s %s %s",
                camera.id,
                result.vision_class,
                alert["dedupe_key"],
            )
    return published


def _with_fetcher(fetcher):
    def pull(camera: Camera):
        return frames_for_camera(camera, fetcher=fetcher)

    return pull
