from __future__ import annotations

from datetime import datetime, timezone

from database.models import EventContent


def save_edits(
    session,
    event_id: int,
    title: str,
    summary: str,
):
    content = session.get(
        EventContent,
        event_id,
    )

    if content is None:
        raise ValueError(
            f"EventContent not found "
            f"for event {event_id}"
        )

    content.final_title = (
        title.strip()
    )

    content.final_summary = (
        summary.strip()
    )

    session.commit()


def approve_event(
    session,
    event_id: int,
    title: str,
    summary: str,
):
    content = session.get(
        EventContent,
        event_id,
    )

    if content is None:
        raise ValueError(
            f"EventContent not found "
            f"for event {event_id}"
        )

    title = title.strip()
    summary = summary.strip()

    if not title:
        raise ValueError(
            "Final title cannot be empty."
        )

    if not summary:
        raise ValueError(
            "Final summary cannot be empty."
        )

    # Whatever is currently visible in the editor
    # becomes the approved version.
    content.final_title = title
    content.final_summary = summary

    content.status = "approved"

    content.reviewed_at = (
        datetime.now(
            timezone.utc
        )
    )

    session.commit()


def reject_event(
    session,
    event_id: int,
):
    content = session.get(
        EventContent,
        event_id,
    )

    if content is None:
        raise ValueError(
            f"EventContent not found "
            f"for event {event_id}"
        )

    content.status = "rejected"

    content.reviewed_at = (
        datetime.now(
            timezone.utc
        )
    )

    session.commit()
