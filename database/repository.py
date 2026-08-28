from sqlalchemy import select

from database.db import SessionLocal
from database.models import Article, Source


def get_source_by_domain(domain: str):
    """
    Find a news source using its domain.

    Example:
        get_source_by_domain("ultimahora.com")
    """

    with SessionLocal() as db:

        source = db.scalar(
            select(Source).where(
                Source.domain == domain
            )
        )

        return source


def article_exists(url: str) -> bool:
    """
    Check whether an article URL is already
    stored in PostgreSQL.
    """

    with SessionLocal() as db:

        article = db.scalar(
            select(Article.id).where(
                Article.url == url
            )
        )

        return article is not None


def save_article(article_data: dict):
    """
    Save a normalized article to PostgreSQL.

    article_data should contain fields such as:

    {
        "source_id": 2,
        "url": "...",
        "title": "...",
        "author": "...",
        "published_at": ...,
        "body": "...",
        "language": "es",
        "image_url": "..."
    }
    """

    with SessionLocal() as db:

        article = Article(
            **article_data
        )

        db.add(article)

        db.commit()

        db.refresh(article)

        article_id = article.id

    return article_id