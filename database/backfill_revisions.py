from sqlalchemy import select

from database.db import SessionLocal
from database.models import (
    Article,
    ArticleRevision,
)

from extraction.fingerprint import article_hash


def main():
    created = 0

    with SessionLocal() as db:
        articles = db.scalars(
            select(Article)
        ).all()

        for article in articles:
            existing = db.scalar(
                select(
                    ArticleRevision.id
                ).where(
                    ArticleRevision.article_id
                    == article.id
                )
            )

            if existing:
                continue

            article_data = {
                "title": article.title,
                "author": article.author,
                "published_at": (
                    article.published_at
                ),
                "body": article.body,
                "language": article.language,
                "image_url": article.image_url,
            }

            revision = ArticleRevision(
                article_id=article.id,
                revision_number=1,
                content_hash=article_hash(
                    article_data
                ),
                **article_data,
            )

            db.add(revision)
            created += 1

        db.commit()

    print(
        f"Created {created} initial revisions."
    )


if __name__ == "__main__":
    main()
