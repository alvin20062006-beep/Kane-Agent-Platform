from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..id_utils import new_id
from ..models import NotificationChannel, NotificationDelivery, NotificationChannelType
from ..store.repositories import notification_channels_repo, notification_deliveries_repo


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def list_channels() -> list[NotificationChannel]:
    return notification_channels_repo.list()


def upsert_channel(body: dict[str, Any]) -> NotificationChannel:
    existing = notification_channels_repo.get(body["channel_id"])
    now = _now_iso()
    payload = {
        "channel_id": body["channel_id"],
        "type": NotificationChannelType.webhook,
        "enabled": bool(body.get("enabled", False)),
        "name": body.get("name"),
        "webhook_url": body.get("webhook_url"),
        "created_at": existing.created_at if existing else now,
        "updated_at": now,
    }
    ch = NotificationChannel.model_validate(payload)
    notification_channels_repo.upsert(ch)
    return ch


def deliver_watchdog_event(event: dict[str, Any]) -> list[NotificationDelivery]:
    """
    Best-effort webhook delivery for ops visibility.
    Beta constraints:
    - no retries/backoff; failures are persisted for inspection
    - avoids hard dependencies by being best-effort
    """
    channels = [c for c in notification_channels_repo.list() if c.enabled and c.type == NotificationChannelType.webhook and c.webhook_url]
    deliveries: list[NotificationDelivery] = []
    for ch in channels:
        delivery_id = new_id("nd")
        ok = False
        err: str | None = None
        meta: dict[str, Any] = {"url": ch.webhook_url}
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.post(ch.webhook_url, json={"source": "octopus_watchdog", "event": event})
                ok = r.status_code < 400
                if not ok:
                    err = f"http_{r.status_code}"
                    meta["response_text"] = (r.text or "")[:2000]
        except Exception as e:  # noqa: BLE001
            ok = False
            err = str(e)

        d = NotificationDelivery(
            delivery_id=delivery_id,
            channel_id=ch.channel_id,
            event_id=str(event.get("event_id", "unknown")),
            event_type=str(event.get("type", "unknown")),
            created_at=_now_iso(),
            status="succeeded" if ok else "failed",
            error=err,
            meta=meta,
        )
        notification_deliveries_repo.upsert(d)
        deliveries.append(d)
    return deliveries

