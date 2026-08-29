from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urlunparse

from dateutil import parser as date_parser


GENERIC_AUTHORS = {
    "",
    "redacción",
    "redaccion",
    "redacción web",
    "redaccion web",
    "equipo editorial",
    "staff",
    "administrador",
    "admin",
}


CATEGORY_MAP = {
    "politica": "Política",
    "política": "Política",

    "economia": "Economía",
    "economía": "Economía",

    "sociedad": "Sociedad",

    "seguridad": "Seguridad",

    "judiciales": "Justicia",
    "justicia": "Justicia",

    "internacionales": "Internacional",
    "internacional": "Internacional",

    "deportes": "Deportes",

    "tecnologia": "Tecnología",
    "tecnología": "Tecnología",

    "cultura": "Cultura",

    "salud": "Salud",

    "educacion": "Educación",
    "educación": "Educación",

    "opinion": "Opinión",
    "opinión": "Opinión",

    "nacionales": "Nacionales",

    "actualidad": "Actualidad",

    "pais": "País",
    "país": "País",
}


def clean_text(
    value: str | None,
) -> str | None:
    """
    Remove unnecessary whitespace from text.

    Example:
        "  Juan   Pérez  "
        ->
        "Juan Pérez"
    """

    if value is None:
        return None

    value = str(value)

    value = " ".join(
        value.strip().split()
    )

    return value or None


def normalize_author(
    author: str | None,
) -> str | None:
    """
    Normalize author names.

    Generic values such as "Redacción"
    are stored as None.
    """

    author = clean_text(author)

    if author is None:
        return None

    normalized = author.casefold()

    if normalized in GENERIC_AUTHORS:
        return None

    return author


def normalize_timestamp(
    value,
) -> datetime | None:
    """
    Convert timestamps into timezone-aware
    datetime objects.

    If the timestamp has no timezone,
    UTC is used as a fallback.
    """

    if value is None:
        return None

    if isinstance(value, datetime):
        dt = value

    else:
        try:
            dt = date_parser.parse(
                str(value)
            )

        except (
            ValueError,
            TypeError,
            OverflowError,
        ):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=timezone.utc
        )

    return dt


def normalize_url(
    url: str | None,
) -> str | None:
    """
    Normalize article URLs.

    Removes URL fragments such as:

        #comments

    while preserving the main URL.
    """

    if not url:
        return None

    url = url.strip()

    parsed = urlparse(url)

    clean = parsed._replace(
        fragment=""
    )

    return urlunparse(clean)


def normalize_image_url(
    image_url: str | None,
    article_url: str,
) -> str | None:
    """
    Convert image URLs into absolute URLs.

    Examples:

        //example.com/image.jpg
        ->
        https://example.com/image.jpg

        /images/photo.jpg
        ->
        https://site.com/images/photo.jpg
    """

    if not image_url:
        return None

    image_url = image_url.strip()

    if image_url.startswith("//"):
        return "https:" + image_url

    return urljoin(
        article_url,
        image_url,
    )


def normalize_language(
    language: str | None,
) -> str:
    """
    Normalize language codes.

    Examples:

        es-ES -> es
        es_PY -> es
        gn-PY -> gn

    Spanish is used as the default
    when language information is missing.
    """

    if not language:
        return "es"

    language = language.strip().lower()

    language = language.replace(
        "_",
        "-",
    )

    if language.startswith("es"):
        return "es"

    if language.startswith("gn"):
        return "gn"

    return language[:10]


def normalize_category(
    category: str | None,
) -> str | None:
    """
    Normalize source categories into
    consistent names.
    """

    category = clean_text(category)

    if category is None:
        return None

    normalized = category.casefold()

    return CATEGORY_MAP.get(
        normalized,
        category,
    )


def normalize_article(
    raw: dict,
    source_id: int,
    url: str,
    category: str | None = None,
) -> dict:
    """
    Normalize extracted article metadata
    before saving it to PostgreSQL.
    """

    title = clean_text(
        raw.get("title")
    )

    body = clean_text(
        raw.get("text")
        or raw.get("body")
    )

    author = normalize_author(
        raw.get("author")
    )

    published_at = normalize_timestamp(
        raw.get("date")
        or raw.get("published_at")
    )

    original_url = normalize_url(
        url
    )

    canonical_url = normalize_url(
        raw.get("url")
        or raw.get("canonical_url")
        or original_url
    )

    image_url = normalize_image_url(
        raw.get("image")
        or raw.get("image_url"),
        canonical_url or original_url,
    )

    language = normalize_language(
        raw.get("language")
    )

    source_category = normalize_category(
        category
        or raw.get("category")
    )

    return {
        "source_id": source_id,

        "url": original_url,

        "canonical_url": canonical_url,

        "title": title,

        "author": author,

        "published_at": published_at,

        "body": body,

        "language": language,

        "image_url": image_url,

        "category": source_category,
    }
