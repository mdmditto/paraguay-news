from datetime import datetime


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def normalize_article(raw, source_id, url):
    return {
        "source_id": source_id,
        "url": url,
        "title": raw.get("title") or "Untitled",
        "author": raw.get("author"),
        "published_at": parse_date(raw.get("date")),
        "body": raw.get("text") or "",
        "language": raw.get("language"),
        "image_url": raw.get("image"),
    }
