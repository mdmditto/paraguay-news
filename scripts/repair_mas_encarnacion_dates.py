import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import select

from database.db import SessionLocal
from database.models import Article, Source
from extraction.article import (
    HEADERS,
    extract_publication_date,
)
from extraction.normalize import normalize_timestamp


# =========================================================
# CONFIG
# =========================================================

SOURCE_NAME = "Más Encarnación"

DEFAULT_TIMEOUT = 20
DEFAULT_BATCH_SIZE = 25

AUDIT_DIR = Path("data/audits")
AUDIT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# =========================================================
# HELPERS
# =========================================================

def format_timestamp(value):
    """
    Convert datetime values to strings suitable for
    printing and CSV audit output.
    """

    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.isoformat()

    return str(value)


def create_audit_path():
    """
    Create a unique audit filename for this repair run.
    """

    timestamp = datetime.now(
        timezone.utc
    ).strftime("%Y%m%d_%H%M%S")

    return (
        AUDIT_DIR
        / f"mas_encarnacion_date_repair_{timestamp}.csv"
    )


def write_audit_header(writer):
    writer.writeheader()


def write_audit_row(
    writer,
    article,
    old_timestamp,
    new_timestamp,
    raw_timestamp,
    status,
    error=None,
):
    writer.writerow(
        {
            "article_id": article.id,
            "url": article.url,
            "old_published_at": format_timestamp(
                old_timestamp
            ),
            "new_published_at": format_timestamp(
                new_timestamp
            ),
            "raw_metadata": (
                raw_timestamp or ""
            ),
            "status": status,
            "error": error or "",
        }
    )


# =========================================================
# ARTICLE LOADING
# =========================================================

def load_articles(
    db,
    limit=None,
):
    """
    Load all Más Encarnación articles.

    Articles are processed in deterministic ID order.
    """

    stmt = (
        select(Article)
        .join(
            Source,
            Source.id == Article.source_id,
        )
        .where(
            Source.name == SOURCE_NAME
        )
        .order_by(
            Article.id.asc()
        )
    )

    if limit is not None:
        stmt = stmt.limit(limit)

    return list(
        db.scalars(stmt).all()
    )


# =========================================================
# DATE EXTRACTION
# =========================================================

def fetch_precise_timestamp(
    http_session,
    url,
    timeout,
):
    """
    Fetch the article page and extract ONLY a trustworthy
    publication timestamp.

    Trafilatura's inferred date is deliberately NOT used.

    Returns:

        raw_timestamp
        normalized_timestamp

    If no precise publication metadata exists:

        None, None
    """

    response = http_session.get(
        url,
        timeout=timeout,
    )

    response.raise_for_status()

    raw_timestamp = (
        extract_publication_date(
            response.text
        )
    )

    if not raw_timestamp:
        return None, None

    normalized_timestamp = (
        normalize_timestamp(
            raw_timestamp
        )
    )

    return (
        raw_timestamp,
        normalized_timestamp,
    )


# =========================================================
# REPAIR
# =========================================================

def repair_dates(
    dry_run=True,
    limit=None,
    timeout=DEFAULT_TIMEOUT,
    batch_size=DEFAULT_BATCH_SIZE,
):
    """
    Repair published_at for Más Encarnación.

    Policy:

    1. If reliable publication metadata exists:
           use it.

    2. If no reliable publication metadata exists:
           set published_at = NULL.

    3. If the HTTP request or parsing fails:
           leave the existing value untouched.

    This distinction is important because downstream
    event processing can safely use scraped_at when
    published_at is NULL.
    """

    audit_path = create_audit_path()

    db = SessionLocal()

    http_session = requests.Session()
    http_session.headers.update(
        HEADERS
    )

    stats = {
        "processed": 0,
        "precise_date_found": 0,
        "no_precise_date": 0,
        "unchanged": 0,
        "updated": 0,
        "cleared": 0,
        "request_error": 0,
        "parse_error": 0,
    }

    try:

        articles = load_articles(
            db,
            limit=limit,
        )

        total = len(articles)

        print()
        print("=" * 78)
        print("MÁS ENCARNACIÓN DATE REPAIR")
        print("=" * 78)

        print(
            f"Articles: {total}"
        )

        print(
            f"Mode: "
            f"{'DRY RUN' if dry_run else 'WRITE'}"
        )

        print(
            f"Audit: {audit_path}"
        )

        print()

        fieldnames = [
            "article_id",
            "url",
            "old_published_at",
            "new_published_at",
            "raw_metadata",
            "status",
            "error",
        ]

        # newline="" is the recommended way to write
        # CSV files with Python's csv module.
        with audit_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as audit_file:

            writer = csv.DictWriter(
                audit_file,
                fieldnames=fieldnames,
            )

            write_audit_header(
                writer
            )

            for index, article in enumerate(
                articles,
                start=1,
            ):

                stats["processed"] += 1

                old_timestamp = (
                    article.published_at
                )

                print(
                    f"[{index}/{total}] "
                    f"ID={article.id}"
                )

                print(
                    f"URL: {article.url}"
                )

                print(
                    f"OLD: "
                    f"{old_timestamp}"
                )

                # =========================================
                # FETCH
                # =========================================

                try:

                    (
                        raw_timestamp,
                        new_timestamp,
                    ) = fetch_precise_timestamp(
                        http_session,
                        article.url,
                        timeout,
                    )

                except requests.RequestException as exc:

                    stats[
                        "request_error"
                    ] += 1

                    print(
                        f"REQUEST ERROR: {exc}"
                    )

                    print(
                        "ACTION: unchanged"
                    )

                    write_audit_row(
                        writer=writer,
                        article=article,
                        old_timestamp=old_timestamp,
                        new_timestamp=old_timestamp,
                        raw_timestamp=None,
                        status="REQUEST_ERROR",
                        error=str(exc),
                    )

                    audit_file.flush()

                    print()
                    continue

                except Exception as exc:

                    stats[
                        "parse_error"
                    ] += 1

                    print(
                        f"PARSE ERROR: {exc}"
                    )

                    print(
                        "ACTION: unchanged"
                    )

                    write_audit_row(
                        writer=writer,
                        article=article,
                        old_timestamp=old_timestamp,
                        new_timestamp=old_timestamp,
                        raw_timestamp=None,
                        status="PARSE_ERROR",
                        error=str(exc),
                    )

                    audit_file.flush()

                    print()
                    continue

                # =========================================
                # NO PRECISE DATE
                # =========================================

                if raw_timestamp is None:

                    stats[
                        "no_precise_date"
                    ] += 1

                    new_timestamp = None

                    if old_timestamp is None:

                        stats[
                            "unchanged"
                        ] += 1

                        status = (
                            "NO_PRECISE_DATE_ALREADY_NULL"
                        )

                        print(
                            "Precise metadata: NONE"
                        )

                        print(
                            "ACTION: already NULL"
                        )

                    else:

                        stats[
                            "cleared"
                        ] += 1

                        stats[
                            "updated"
                        ] += 1

                        status = (
                            "NO_PRECISE_DATE_CLEARED"
                        )

                        print(
                            "Precise metadata: NONE"
                        )

                        print(
                            "NEW: NULL"
                        )

                        print(
                            "ACTION: clear published_at"
                        )

                        if not dry_run:
                            article.published_at = None

                    write_audit_row(
                        writer=writer,
                        article=article,
                        old_timestamp=old_timestamp,
                        new_timestamp=None,
                        raw_timestamp=None,
                        status=status,
                    )

                    audit_file.flush()

                # =========================================
                # PRECISE DATE FOUND
                # =========================================

                else:

                    stats[
                        "precise_date_found"
                    ] += 1

                    print(
                        f"Raw metadata: "
                        f"{raw_timestamp}"
                    )

                    print(
                        f"NEW: "
                        f"{new_timestamp}"
                    )

                    if new_timestamp is None:

                        # Metadata existed but normalization
                        # failed. Do NOT destroy the old value.

                        stats[
                            "parse_error"
                        ] += 1

                        status = (
                            "NORMALIZATION_FAILED"
                        )

                        print(
                            "ACTION: unchanged"
                        )

                        write_audit_row(
                            writer=writer,
                            article=article,
                            old_timestamp=old_timestamp,
                            new_timestamp=old_timestamp,
                            raw_timestamp=raw_timestamp,
                            status=status,
                            error=(
                                "normalize_timestamp "
                                "returned None"
                            ),
                        )

                        audit_file.flush()

                        print()
                        continue

                    if (
                        old_timestamp
                        == new_timestamp
                    ):

                        stats[
                            "unchanged"
                        ] += 1

                        status = (
                            "PRECISE_DATE_UNCHANGED"
                        )

                        print(
                            "ACTION: unchanged"
                        )

                    else:

                        stats[
                            "updated"
                        ] += 1

                        status = (
                            "PRECISE_DATE_UPDATED"
                        )

                        print(
                            "ACTION: update"
                        )

                        if not dry_run:
                            article.published_at = (
                                new_timestamp
                            )

                    write_audit_row(
                        writer=writer,
                        article=article,
                        old_timestamp=old_timestamp,
                        new_timestamp=new_timestamp,
                        raw_timestamp=raw_timestamp,
                        status=status,
                    )

                    audit_file.flush()

                # =========================================
                # COMMIT BATCH
                # =========================================

                if (
                    not dry_run
                    and index % batch_size == 0
                ):

                    db.commit()

                    print(
                        f"Committed through "
                        f"article {index}/{total}"
                    )

                print()

            # =============================================
            # FINAL COMMIT
            # =============================================

            if not dry_run:
                db.commit()

        # =================================================
        # SUMMARY
        # =================================================

        print()
        print("=" * 78)
        print("SUMMARY")
        print("=" * 78)

        print(
            f"Processed:            "
            f"{stats['processed']}"
        )

        print(
            f"Precise date found:   "
            f"{stats['precise_date_found']}"
        )

        print(
            f"No precise date:      "
            f"{stats['no_precise_date']}"
        )

        print(
            f"Updated:              "
            f"{stats['updated']}"
        )

        print(
            f"  Cleared to NULL:    "
            f"{stats['cleared']}"
        )

        print(
            f"Unchanged:            "
            f"{stats['unchanged']}"
        )

        print(
            f"Request errors:       "
            f"{stats['request_error']}"
        )

        print(
            f"Parse errors:         "
            f"{stats['parse_error']}"
        )

        print()

        if dry_run:

            print(
                "DRY RUN ONLY — database was not changed."
            )

        else:

            print(
                "Changes committed to database."
            )

        print(
            f"Audit written to: {audit_path}"
        )

        print()

    except Exception:

        db.rollback()
        raise

    finally:

        http_session.close()
        db.close()


# =========================================================
# CLI
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Repair Más Encarnación publication "
            "timestamps using only explicit HTML "
            "publication metadata."
        )
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Apply changes to PostgreSQL. "
            "Without this flag the script runs "
            "in dry-run mode."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Process only the first N articles."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=(
            "HTTP request timeout in seconds."
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Commit every N processed articles."
        ),
    )

    args = parser.parse_args()

    repair_dates(
        dry_run=not args.write,
        limit=args.limit,
        timeout=args.timeout,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    main()
