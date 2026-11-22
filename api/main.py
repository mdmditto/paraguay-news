from datetime import datetime

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text

from database.db import SessionLocal


app = FastAPI(
    title="Paraguay News API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


class EventCard(BaseModel):
    id: int
    title: str
    image_url: str | None
    article_count: int
    source_count: int
    latest_article_at: datetime


class ArticleItem(BaseModel):
    id: int
    title: str
    url: str
    published_at: datetime | None
    source_name: str
    source_domain: str


class EventDetail(EventCard):
    summary: str
    articles: list[ArticleItem]


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/events", response_model=list[EventCard])
def list_events(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    sql = text("""
        SELECT
            e.id,
            ec.final_title AS title,
            COALESCE(
                selected_image.image_url,
                representative_image.image_url
            ) AS image_url,
            COUNT(DISTINCT ea.article_id) AS article_count,
            COUNT(DISTINCT a.source_id) AS source_count,
            MAX(
                COALESCE(a.published_at, a.scraped_at)
            ) AS latest_article_at
        FROM events e
        JOIN event_content ec
            ON ec.event_id = e.id
        JOIN event_articles ea
            ON ea.event_id = e.id
        JOIN articles a
            ON a.id = ea.article_id
        LEFT JOIN articles selected_image
            ON selected_image.id = ec.selected_image_article_id
        LEFT JOIN articles representative_image
            ON representative_image.id = e.representative_article_id
        WHERE ec.status = 'approved'
          AND NULLIF(TRIM(ec.final_title), '') IS NOT NULL
          AND NULLIF(TRIM(ec.final_summary), '') IS NOT NULL
        GROUP BY
            e.id,
            ec.final_title,
            selected_image.image_url,
            representative_image.image_url
        ORDER BY latest_article_at DESC, e.id DESC
        LIMIT :limit OFFSET :offset
    """)

    with SessionLocal() as session:
        rows = session.execute(
            sql,
            {"limit": limit, "offset": offset},
        ).mappings().all()

        return [dict(row) for row in rows]


@app.get("/api/events/{event_id}", response_model=EventDetail)
def get_event(event_id: int):
    event_sql = text("""
        SELECT
            e.id,
            ec.final_title AS title,
            ec.final_summary AS summary,
            COALESCE(
                selected_image.image_url,
                representative_image.image_url
            ) AS image_url,
            COUNT(DISTINCT ea.article_id) AS article_count,
            COUNT(DISTINCT a.source_id) AS source_count,
            MAX(
                COALESCE(a.published_at, a.scraped_at)
            ) AS latest_article_at
        FROM events e
        JOIN event_content ec
            ON ec.event_id = e.id
        JOIN event_articles ea
            ON ea.event_id = e.id
        JOIN articles a
            ON a.id = ea.article_id
        LEFT JOIN articles selected_image
            ON selected_image.id = ec.selected_image_article_id
        LEFT JOIN articles representative_image
            ON representative_image.id = e.representative_article_id
        WHERE e.id = :event_id
          AND ec.status = 'approved'
          AND NULLIF(TRIM(ec.final_title), '') IS NOT NULL
          AND NULLIF(TRIM(ec.final_summary), '') IS NOT NULL
        GROUP BY
            e.id,
            ec.final_title,
            ec.final_summary,
            selected_image.image_url,
            representative_image.image_url
    """)

    articles_sql = text("""
        SELECT
            a.id,
            a.title,
            a.url,
            a.published_at,
            s.name AS source_name,
            s.domain AS source_domain
        FROM event_articles ea
        JOIN articles a
            ON a.id = ea.article_id
        JOIN sources s
            ON s.id = a.source_id
        WHERE ea.event_id = :event_id
        ORDER BY
            a.published_at DESC NULLS LAST,
            a.scraped_at DESC,
            a.id DESC
    """)

    with SessionLocal() as session:
        event = session.execute(
            event_sql,
            {"event_id": event_id},
        ).mappings().first()

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Approved event not found",
            )

        articles = session.execute(
            articles_sql,
            {"event_id": event_id},
        ).mappings().all()

        return {
            **dict(event),
            "articles": [dict(article) for article in articles],
        }