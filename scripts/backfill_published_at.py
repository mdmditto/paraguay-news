import argparse
import time
from datetime import datetime
from pathlib import Path
import sys

import requests
from sqlalchemy import select

# ---------------------------------------------------------
# Allow running:
#
#   python scripts/backfill_published_at.py
#
# from the project root.
# ---------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )


from database.db import SessionLocal
from database.models import Article

from extraction.article import (
    HEADERS,
    extract_publication_date,
)

from extraction.normalize import (
    normalize_timestamp,
)


# =========================================================
# CONFIGURATION
# =========================================================

DEFAULT_BATCH_SIZE = 100
DEFAULT_DELAY = 0.25
DEFAULT_TIMEOUT = 20


# =========================================================
# HELPERS
# =========================================================

def fetch_precise_timestamp(
    session: requests.Session,
    url: str,
    timeout: int,
) -> tuple[str | None, datetime | None]:
    """
    Fetch an article page and extract a precise publication
    timestamp from JSON-LD or HTML metadata.

    Important:
    We intentionally do NOT use Trafilatura's date fallback
    here because this script is meant to repair timestamps
    only when better metadata is available.

    Returns:
        (raw_timestamp, normalized_datetime)
    """

    response = session.get(
        url,
        timeout=timeout,
    )

    response.raise_for_status()

    raw_timestamp = extract_publication_date(
        response.text
    )

    if not raw_timestamp:
        return None, None

    normalized = normalize_timestamp(
        raw_timestamp
    )

    return (
        raw_timestamp,
        normalized,
    )


def load_articles(
    db,
    start_id: int | None,
    limit: int | None,
):
    """
    Load articles in ID order.

    start_id allows the backfill to resume without
    beginning again from the first article.
    """

    stmt = (
        select(Article)
        .order_by(Article.id)
    )

    if start_id is not None:
        stmt = stmt.where(
            Article.id >= start_id
        )

    if limit is not None:
        stmt = stmt.limit(
            limit
        )

    return list(
        db.scalars(stmt)
    )


# =========================================================
# BACKFILL
# =========================================================

def backfill(
    start_id: int | None,
    limit: int | None,
    batch_size: int,
    delay: float,
    timeout: int,
    dry_run: bool,
):
    db = SessionLocal()

    http = requests.Session()

    http.headers.update(
        HEADERS
    )

    try:

        articles = load_articles(
            db=db,
            start_id=start_id,
            limit=limit,
        )

        total = len(
            articles
        )

        print()
        print("=" * 78)
        print("PUBLISHED_AT BACKFILL")
        print("=" * 78)

        print(
            f"Articles selected: {total}"
        )

        print(
            f"Start ID: {start_id}"
        )

        print(
            f"Limit: {limit}"
        )

        print(
            f"Batch size: {batch_size}"
        )

        print(
            f"Delay: {delay}s"
        )

        print(
            f"Dry run: {dry_run}"
        )

        print()

        stats = {
            "processed": 0,
            "updated": 0,
            "unchanged": 0,
            "no_precise_date": 0,
            "request_error": 0,
            "parse_error": 0,
        }

        for index, article in enumerate(
            articles,
            start=1,
        ):

            stats[
                "processed"
            ] += 1

            old_timestamp = (
                article.published_at
            )

            try:

                (
                    raw_timestamp,
                    new_timestamp,
                ) = fetch_precise_timestamp(
                    session=http,
                    url=article.url,
                    timeout=timeout,
                )

            except requests.RequestException as exc:

                stats[
                    "request_error"
                ] += 1

                print(
                    f"[{index}/{total}] "
                    f"ID={article.id} "
                    f"REQUEST ERROR: {exc}"
                )

                time.sleep(
                    delay
                )

                continue

            except Exception as exc:

                stats[
                    "parse_error"
                ] += 1

                print(
                    f"[{index}/{total}] "
                    f"ID={article.id} "
                    f"PARSE ERROR: {exc}"
                )

                time.sleep(
                    delay
                )

                continue

            if (
                raw_timestamp is None
                or new_timestamp is None
            ):

                stats[
                    "no_precise_date"
                ] += 1

                print(
                    f"[{index}/{total}] "
                    f"ID={article.id} "
                    f"NO PRECISE DATE"
                )

                time.sleep(
                    delay
                )

                continue

            # -------------------------------------------------
            # Compare timestamps
            # -------------------------------------------------

            if (
                old_timestamp is not None
                and old_timestamp == new_timestamp
            ):

                stats[
                    "unchanged"
                ] += 1

            else:

                stats[
                    "updated"
                ] += 1

                print()
                print(
                    f"[{index}/{total}] "
                    f"ID={article.id}"
                )

                print(
                    f"Source URL: "
                    f"{article.url}"
                )

                print(
                    f"Raw metadata: "
                    f"{raw_timestamp}"
                )

                print(
                    f"OLD: {old_timestamp}"
                )

                print(
                    f"NEW: {new_timestamp}"
                )

                if not dry_run:

                    article.published_at = (
                        new_timestamp
                    )

            # -------------------------------------------------
            # Commit periodically
            # -------------------------------------------------

            if (
                not dry_run
                and index % batch_size == 0
            ):

                db.commit()

                print()
                print(
                    f"--- COMMIT at "
                    f"{index}/{total} ---"
                )
                print()

            # -------------------------------------------------
            # Progress
            # -------------------------------------------------

            if index % 100 == 0:

                print()
                print(
                    f"Progress: "
                    f"{index}/{total}"
                )

                print(
                    f"Updated: "
                    f"{stats['updated']}"
                )

                print(
                    f"No precise date: "
                    f"{stats['no_precise_date']}"
                )

                print(
                    f"Errors: "
                    f"{stats['request_error'] + stats['parse_error']}"
                )

                print()

            time.sleep(
                delay
            )

        # -----------------------------------------------------
        # Final commit
        # -----------------------------------------------------

        if not dry_run:

            db.commit()

        # -----------------------------------------------------
        # SUMMARY
        # -----------------------------------------------------

        print()
        print("=" * 78)
        print("BACKFILL SUMMARY")
        print("=" * 78)

        for key, value in stats.items():

            print(
                f"{key:20s}: {value}"
            )

        print()

        if dry_run:

            print(
                "DRY RUN: no database rows were modified."
            )

    except KeyboardInterrupt:

        print()
        print()
        print("Interrupted by user.")

        if not dry_run:

            print(
                "Committing completed batch..."
            )

            db.commit()

        print(
            "You can resume using --start-id."
        )

    finally:

        http.close()

        db.close()


# =========================================================
# CLI
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Backfill precise article publication "
            "timestamps from HTML metadata."
        )
    )

    parser.add_argument(
        "--start-id",
        type=int,
        default=None,
        help=(
            "Start processing from this article ID."
        ),
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Maximum number of articles to process."
        ),
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=(
            "Delay between requests in seconds."
        ),
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Extract timestamps but do not update "
            "the database."
        ),
    )

    args = parser.parse_args()

    backfill(
        start_id=args.start_id,
        limit=args.limit,
        batch_size=args.batch_size,
        delay=args.delay,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
