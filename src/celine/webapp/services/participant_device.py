"""Resolve the metered device of a participant from the Digital Twin assets."""

from __future__ import annotations

import logging
from typing import Any

from celine.webapp.services.log_safety import failure

logger = logging.getLogger(__name__)


async def resolve_device_id(dt: Any, participant_id: str) -> str:
    """Return the first asset with a sensor id, or "" when the participant has no meter.

    Args:
        dt: Digital Twin client (``dt.participants.assets``).
        participant_id: The caller's subject.

    Returns:
        The device id, or an empty string on no asset or on a lookup failure (logged).
    """
    try:
        assets = await dt.participants.assets(participant_id)
    except Exception as exc:
        logger.warning("asset lookup failed (%s)", failure(exc))
        return ""
    if assets and assets.items:
        for asset in assets.items:
            if asset.sensor_id:
                return str(asset.sensor_id)
    return ""
