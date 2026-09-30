import argparse
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from sqlalchemy import select
from urllib3.util.retry import Retry


# =========================================================
# PROJECT PATH
# =========================================================

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

BACKUP_DIR = PROJECT_ROOT / "backups"

AUDIT_FILE = (
    BACKUP_DIR
    / "published_at_backfill_audit.csv"
)

PROGRESS_FILE = (
    BACKUP_DIR
    / "published_at_backfill_progress.json"
)

DEFAULT_BATCH_SIZE = 50
DEFAULT_DELAY = 0.30
DEFAULT_TIMEOUT = 20


AUDIT_FIELDS = [
    "article_id",
    "source_id",
    "url",
    "old_published_at",
    "new_published_at",
    "raw_metadata",
    "processed_at",
]


# =========================================================
# HTTP SESSION
# =========================================================

def create_http_session():
    """
    Create a requests session with conservative retries.
    """

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=[
            429,
            500,
            502,
            503,
            504,
        ],
        allowed_methods=[
            "GET",
        ],
        raise_on_status=False,
    )

    adapter = HTTPAdapter(
        max_retries=retry
    )

    session.mount(
        "http://",
        adapter,
    )

    session.mount(
        "https://",
        adapter,
    )

    return session


# =========================================================
# AUDIT FILE
# =========================================================

def initialize_audit_file():
    """
    Create the audit CSV if it does not already exist.
    """

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if AUDIT_FILE.exists():
        return

    with AUDIT_FILE.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=AUDIT_FIELDS,
        )

        writer.writeheader()


def write_audit_row(
    article,
    old_timestamp,
    new_timestamp,
    raw_timestamp,
):
    """
    Append one timestamp modification to the audit log.

    The audit row is written BEFORE the corresponding
    database commit.
    """

    initialize_audit_file()

    with AUDIT_FILE.open(
        "a",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=AUDIT_FIELDS,
        )

        writer.writerow(
            {
                "article_id": article.id,
                "source_id": article.source_id,
                "url": article.url,
                "old_published_at": (
                    old_timestamp.isoformat()
                    if old_timestamp
                    else ""
                ),
                "new_published_at": (
                    new_timestamp.isoformat()
                    if new_timestamp
                    else ""
                ),
                "raw_metadata": raw_timestamp,
                "processed_at": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            }
        )

        # Make sure the audit entry reaches disk.
        file.flush()


# =========================================================
# PROGRESS
# =========================================================

def load_progress():
    """
    Load the last successfully committed article ID.
    """

    if not PROGRESS_FILE.exists():
        return None

    try:

        with PROGRESS_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        return data.get(
            "last_committed_article_id"
        )

    except (
        json.JSONDecodeError,
        OSError,
    ):

        return None


def save_progress(
    article_id,
):
    """
    Save the last successfully committed article ID.

    Write atomically through a temporary file.
    """

    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        PROGRESS_FILE.with_suffix(
            ".tmp"
        )
    )

    data = {
        "last_committed_article_id": (
            article_id
        ),
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
        )

    temporary_file.replace(
        PROGRESS_FILE
    )


# =========================================================
# TIMESTAMP EXTRACTION
# =========================================================

def fetch_precise_timestamp(
    session,
    url,
    timeout,
):
    """
    Fetch article HTML and extract a precise publication
    timestamp.

    We intentionally do NOT use Trafilatura's date-only
    fallback here.
    """

    response = session.get(
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
# ARTICLE QUERY
# =========================================================

def load_articles(
    db,
    start_id=None,
    limit=None,
):
    """
    Load articles in deterministic ID order.
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
    start_id,
    limit,
    batch_size,
    delay,
    timeout,
    dry_run,
    resume,
):
    db = SessionLocal()

    http = create_http_session()

    initialize_audit_file()

    # -----------------------------------------------------
    # RESUME
    # -----------------------------------------------------

    if (
        resume
        and start_id is None
    ):

        last_committed = (
            load_progress()
        )

        if last_committed is not None:

            start_id = (
                last_committed + 1
            )

            print(
                f"Resuming after article "
                f"ID={last_committed}"
            )

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
        f"Articles selected : {total}"
    )

    print(
        f"Start ID          : {start_id}"
    )

    print(
        f"Limit             : {limit}"
    )

    print(
        f"Batch size        : {batch_size}"
    )

    print(
        f"Delay             : {delay}s"
    )

    print(
        f"Timeout           : {timeout}s"
    )

    print(
        f"Dry run           : {dry_run}"
    )

    print(
        f"Resume            : {resume}"
    )

    print(
        f"Audit file        : {AUDIT_FILE}"
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

    last_successful_article_id = None

    pending_changes = []

    try:

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

            # ---------------------------------------------
            # DOWNLOAD + EXTRACT
            # ---------------------------------------------

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

                # Do NOT advance resumable progress past
                # an unsuccessful article.
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

            # ---------------------------------------------
            # NO PRECISE DATE
            # ---------------------------------------------

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

                last_successful_article_id = (
                    article.id
                )

            # ---------------------------------------------
            # ALREADY CORRECT
            # ---------------------------------------------

            elif (
                old_timestamp is not None
                and old_timestamp == new_timestamp
            ):

                stats[
                    "unchanged"
                ] += 1

                last_successful_article_id = (
                    article.id
                )

            # ---------------------------------------------
            # UPDATE
            # ---------------------------------------------

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
                    f"OLD: "
                    f"{old_timestamp}"
                )

                print(
                    f"NEW: "
                    f"{new_timestamp}"
                )

                if not dry_run:

                    # Save information required to write
                    # the audit log immediately before
                    # committing.
                    pending_changes.append(
                        (
                            article,
                            old_timestamp,
                            new_timestamp,
                            raw_timestamp,
                        )
                    )

                    article.published_at = (
                        new_timestamp
                    )

                last_successful_article_id = (
                    article.id
                )

            # ---------------------------------------------
            # COMMIT BATCH
            # ---------------------------------------------

            if (
                not dry_run
                and index % batch_size == 0
            ):

                # Write audit information first.
                for (
                    changed_article,
                    old_value,
                    new_value,
                    raw_value,
                ) in pending_changes:

                    write_audit_row(
                        article=changed_article,
                        old_timestamp=old_value,
                        new_timestamp=new_value,
                        raw_timestamp=raw_value,
                    )

                db.commit()

                pending_changes.clear()

                if (
                    last_successful_article_id
                    is not None
                ):

                    save_progress(
                        last_successful_article_id
                    )

                print()
                print(
                    f"--- COMMIT "
                    f"{index}/{total} ---"
                )
                print()

            # ---------------------------------------------
            # PROGRESS REPORT
            # ---------------------------------------------

            if index % 100 == 0:

                print()
                print("-" * 78)

                print(
                    f"Progress: "
                    f"{index}/{total}"
                )

                print(
                    f"Updated: "
                    f"{stats['updated']}"
                )

                print(
                    f"Unchanged: "
                    f"{stats['unchanged']}"
                )

                print(
                    f"No precise date: "
                    f"{stats['no_precise_date']}"
                )

                print(
                    f"Request errors: "
                    f"{stats['request_error']}"
                )

                print(
                    f"Parse errors: "
                    f"{stats['parse_error']}"
                )

                print(
                    "-" * 78
                )
                print()

            time.sleep(
                delay
            )

        # -------------------------------------------------
        # FINAL COMMIT
        # -------------------------------------------------

        if not dry_run:

            for (
                changed_article,
                old_value,
                new_value,
                raw_value,
            ) in pending_changes:

                write_audit_row(
                    article=changed_article,
                    old_timestamp=old_value,
                    new_timestamp=new_value,
                    raw_timestamp=raw_value,
                )

            db.commit()

            pending_changes.clear()

            if (
                last_successful_article_id
                is not None
            ):

                save_progress(
                    last_successful_article_id
                )

    except KeyboardInterrupt:

        print()
        print()
        print(
            "Interrupted by user."
        )

        if not dry_run:

            print(
                "Rolling back the current "
                "uncommitted batch..."
            )

            db.rollback()

        print(
            "Previously committed batches "
            "remain safe."
        )

        print(
            "Run again with --resume."
        )

    except Exception:

        if not dry_run:

            db.rollback()

        raise

    finally:

        http.close()
        db.close()

    # =====================================================
    # SUMMARY
    # =====================================================

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
            "DRY RUN: database was not modified."
        )

    else:

        print(
            f"Audit log: {AUDIT_FILE}"
        )

        print(
            f"Progress: {PROGRESS_FILE}"
        )


# =========================================================
# CLI
# =========================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Safely backfill precise publication "
            "timestamps."
        )
    )

    parser.add_argument(
        "--start-id",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
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
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume after the last committed "
            "article ID."
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
        resume=args.resume,
    )


if __name__ == "__main__":
    main()