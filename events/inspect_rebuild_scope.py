
import argparse
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, distinct
from database.db import SessionLocal
from database.models import (
    Article,
    Event,
    EventArticle,
    EventContent,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", required=True)
    parser.add_argument("--to-date", required=True)
    args = parser.parse_args()

    start = datetime.fromisoformat(
        args.from_date
    ).replace(tzinfo=timezone.utc)

    end = datetime.fromisoformat(
        args.to_date
    ).replace(tzinfo=timezone.utc) + timedelta(days=1)

    effective_time = func.coalesce(
        Article.published_at,
        Article.scraped_at,
    )

    with SessionLocal() as session:
        affected_event_ids = (
            select(distinct(EventArticle.event_id))
            .join(
                Article,
                Article.id == EventArticle.article_id,
            )
            .where(
                effective_time >= start,
                effective_time < end,
            )
        )

        events = session.scalars(
            select(Event)
            .where(Event.id.in_(affected_event_ids))
            .order_by(Event.first_seen_at)
        ).all()

        print(f"\nAffected events: {len(events)}")

        total_assignments = 0
        total_drafts = 0

        for event in events:
            article_count = session.scalar(
                select(func.count())
                .select_from(EventArticle)
                .where(EventArticle.event_id == event.id)
            )

            has_content = session.scalar(
                select(EventContent.event_id)
                .where(EventContent.event_id == event.id)
            ) is not None

            total_assignments += article_count
            total_drafts += int(has_content)

            print(
                f"\nEvent {event.id}: {event.title}"
                f"\n  First: {event.first_seen_at}"
                f"\n  Last:  {event.last_seen_at}"
                f"\n  Articles: {article_count}"
                f"\n  Has content: {has_content}"
            )

        print("\nSUMMARY")
        print("Events:", len(events))
        print("Assignments:", total_assignments)
        print("Generated content records:", total_drafts)


if __name__ == "__main__":
    main()
