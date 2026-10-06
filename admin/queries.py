from __future__ import annotations

from sqlalchemy import func, select

from database.models import (
    Article,
    Event,
    EventArticle,
    EventContent,
    EventContentContext,
    Source,
)


def get_draft_events(session):
    """
    Return events waiting for human review.
    Newest events first.
    """

    stmt = (
        select(
            Event.id,
            Event.article_count,
            Event.first_seen_at,
            Event.last_seen_at,
            EventContent.generated_title,
            EventContent.generated_summary,
            EventContent.final_title,
            EventContent.final_summary,
            EventContent.status,
            EventContent.model,
            EventContent.generated_at,
        )
        .join(
            EventContent,
            EventContent.event_id == Event.id,
        )
        .where(
            EventContent.status == "draft"
        )
        .order_by(
            Event.last_seen_at.desc(),
            Event.id.desc(),
        )
    )

    return session.execute(
        stmt
    ).all()


def get_event_for_review(
    session,
    event_id: int,
):
    """
    Load event + generated/final editorial content.
    """

    stmt = (
        select(
            Event.id,
            Event.title.label(
                "original_title"
            ),
            Event.article_count,
            Event.first_seen_at,
            Event.last_seen_at,
            Event.representative_article_id,

            EventContent.generated_title,
            EventContent.generated_summary,
            EventContent.final_title,
            EventContent.final_summary,
            EventContent.selected_image_article_id,
            EventContent.status,
            EventContent.model,
            EventContent.generated_at,
            EventContent.reviewed_at,
        )
        .join(
            EventContent,
            EventContent.event_id == Event.id,
        )
        .where(
            Event.id == event_id
        )
    )

    return session.execute(
        stmt
    ).first()


def get_context_articles(
    session,
    event_id: int,
):
    """
    Return the exact articles that were sent to Qwen,
    preserving their original context order.
    """

    stmt = (
        select(
            EventContentContext.position,
            EventContentContext.is_representative,

            Article.id.label(
                "article_id"
            ),
            Article.title,
            Article.body,
            Article.url,
            Article.image_url,
            Article.published_at,
            Article.scraped_at,

            Source.id.label(
                "source_id"
            ),
            Source.name.label(
                "source_name"
            ),
        )
        .join(
            Article,
            Article.id
            == EventContentContext.article_id,
        )
        .join(
            Source,
            Source.id
            == Article.source_id,
        )
        .where(
            EventContentContext.event_id
            == event_id
        )
        .order_by(
            EventContentContext.position
        )
    )

    return session.execute(
        stmt
    ).all()


def get_all_event_articles(
    session,
    event_id: int,
):
    """
    Return every article assigned to the event.
    """

    stmt = (
        select(
            Article.id.label(
                "article_id"
            ),
            Article.title,
            Article.body,
            Article.url,
            Article.image_url,
            Article.published_at,
            Article.scraped_at,

            Source.id.label(
                "source_id"
            ),
            Source.name.label(
                "source_name"
            ),

            EventArticle.match_probability,
            EventArticle.similarity,
            EventArticle.is_seed,
        )
        .join(
            EventArticle,
            EventArticle.article_id
            == Article.id,
        )
        .join(
            Source,
            Source.id
            == Article.source_id,
        )
        .where(
            EventArticle.event_id
            == event_id
        )
        .order_by(
            func.coalesce(
                Article.published_at,
                Article.scraped_at,
            ).asc(),
            Article.id.asc(),
        )
    )

    return session.execute(
        stmt
    ).all()
