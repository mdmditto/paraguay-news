from datetime import datetime

from sqlalchemy import select

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleRevision,
    Source,
)
from extraction.fingerprint import article_hash


def get_source_by_domain(domain: str):
    """
    Find a news source using its domain.
    """

    with SessionLocal() as db:
        source = db.scalar(
            select(Source).where(
                Source.domain == domain
            )
        )

        return source


def create_article(article_data: dict) -> int:
    """
    Create a new article and its first revision.
    """

    with SessionLocal() as db:
        article = Article(**article_data)

        db.add(article)
        db.flush()

        revision = ArticleRevision(
            article_id=article.id,
            revision_number=1,
            content_hash=article_hash(article_data),
            title=article_data["title"],
            author=article_data.get("author"),
            published_at=article_data.get("published_at"),
            body=article_data["body"],
            language=article_data.get("language"),
            image_url=article_data.get("image_url"),
        )

        db.add(revision)

        db.commit()
        db.refresh(article)

        return article.id


def update_article_if_changed(
    article_id: int,
    article_data: dict,
) -> bool:
    """
    Compare the current title, author and body
    against the latest revision.

    Create a new revision only if one of those
    fields changed.

    Returns:
        True if a new revision was created.
        False if nothing relevant changed.
    """

    new_hash = article_hash(article_data)

    with SessionLocal() as db:
        article = db.get(
            Article,
            article_id,
        )

        if article is None:
            raise ValueError(
                f"Article {article_id} does not exist."
            )

        latest_revision = db.scalar(
            select(ArticleRevision)
            .where(
                ArticleRevision.article_id == article_id
            )
            .order_by(
                ArticleRevision.revision_number.desc()
            )
            .limit(1)
        )

        if (
            latest_revision is not None
            and latest_revision.content_hash == new_hash
        ):
            return False

        next_revision = (
            latest_revision.revision_number + 1
            if latest_revision is not None
            else 1
        )

        revision = ArticleRevision(
            article_id=article.id,
            revision_number=next_revision,
            content_hash=new_hash,
            title=article_data["title"],
            author=article_data.get("author"),
            published_at=article_data.get("published_at"),
            body=article_data["body"],
            language=article_data.get("language"),
            image_url=article_data.get("image_url"),
        )

        db.add(revision)

        # Keep the articles table as the latest version.
        article.title = article_data["title"]
        article.author = article_data.get("author")
        article.published_at = article_data.get(
            "published_at"
        )
        article.body = article_data["body"]
        article.language = article_data.get(
            "language"
        )
        article.image_url = article_data.get(
            "image_url"
        )

        db.commit()

        return True


def get_article_info_by_url(
    url: str,
) -> tuple[int, datetime] | None:
    """
    Return the article ID and the timestamp of
    the first scrape.

    Returns:
        (article_id, scraped_at)

    or:
        None if the article has not been stored.
    """

    with SessionLocal() as db:
        result = db.execute(
            select(
                Article.id,
                Article.scraped_at,
            ).where(
                Article.url == url
            )
        ).first()

        if result is None:
            return None

        return (
            result.id,
            result.scraped_at,
        )