
"""
Historical article backfill for Paraguay News.

Discovery methods:
    ABC Color    -> Queryly search API
    La Nación    -> XML sitemaps
    Última Hora  -> XML sitemaps

Examples:
    python -m collectors.run_backfill \
        --from-date 2026-11-04 \
        --to-date 2026-11-06

    python -m collectors.run_backfill \
        --from-date 2026-11-04 \
        --to-date 2026-11-09 \
        --sources abc

    python -m collectors.run_backfill \
        --from-date 2026-11-04 \
        --to-date 2026-11-09 \
        --sources abc lanacion ultimahora
"""

import argparse
import time

from datetime import date

from collectors.abc_queryly import discover_abc_historical
from collectors.historical_discovery import discover_historical_urls

from run_collector import SOURCES, collect_source
from collectors.dpn_archive import discover_dpn_historical

from collectors.abc_queryly import discover_abc_historical
from collectors.lanacion_archive import discover_lanacion_historical
from collectors.historical_discovery import discover_historical_urls
from collectors.rdn_archive import discover_rdn_historical
from run_collector import SOURCES, collect_source
from collectors import five_dias_archive


SOURCE_DOMAINS = {
    "abc": "abc.com.py",
    "lanacion": "lanacion.com.py",
    "ultimahora": "ultimahora.com",
    "rdn": "rdn.com.py",
    "dpn": "dpn.com.py",
    "5dias": "5dias.com.py",
}


def get_source_config(source_name):
    """
    Find the source configuration in run_collector.py.
    """

    domain = SOURCE_DOMAINS[source_name]

    for source in SOURCES:
        if source["domain"] == domain:
            return source

    raise ValueError(
        f"Source '{source_name}' not found in SOURCES"
    )


def discover_articles(source_name, start_date, end_date, max_pages=15):

    # ABC Color: Queryly API
    if source_name == "abc":
        print("\nUsing Queryly API for ABC Color")

        return discover_abc_historical(
            start_date=start_date,
            end_date=end_date,
            max_pages_per_query=max_pages,
        )

    # La Nación: Arc Publishing API
    if source_name == "lanacion":
        print("\nUsing Arc Publishing API for La Nación")

        return discover_lanacion_historical(
            start_date=start_date,
            end_date=end_date,
            max_pages_per_query=max_pages,
        )

    if source_name == "rdn":
        print("\nUsing RDN Archive for RDN")

        return discover_rdn_historical(
            start_date=start_date,
            end_date=end_date
        )

    if source_name == "lanacion":
        print("\nUsing Arc Publishing API for La Nación")
    
        return discover_lanacion_historical(
            start_date=start_date,
            end_date=end_date,
            max_pages_per_query=max_pages,
        )
    if source_name == "dpn":
        print("\nUsing category archives for Diario Paraguayo")
        
        return discover_dpn_historical(
            start_date=start_date,
            end_date=end_date,
            max_pages_per_category=max_pages,
        )

    if source_name == "5dias":
        return five_dias_archive.discover_5dias_historical(
            start_date,
            end_date,
        )


    
    # Other newspapers: XML sitemaps
    print(f"\nUsing XML sitemaps for {source_name}")

    urls = discover_historical_urls(
        source=source_name,
        start_date=start_date,
        end_date=end_date,
    )

    return [
        {"url": url, "title": None}
        for url in urls
    ]



def run_backfill(
    start_date,
    end_date,
    source_names,
    max_pages=15,
):
    """
    Discover and ingest historical articles.
    """

    print("\n" + "=" * 70)
    print("PARAGUAY NEWS - HISTORICAL BACKFILL")
    print("=" * 70)

    print(f"From: {start_date}")
    print(f"To:   {end_date}")

    print(
        "Sources: " + ", ".join(source_names)
    )

    summaries = {}

    for source_name in source_names:

        print("\n" + "=" * 70)
        print(f"BACKFILL: {source_name.upper()}")
        print("=" * 70)

        try:
            source_config = get_source_config(
                source_name
            )

            discovered = discover_articles(
                source_name=source_name,
                start_date=start_date,
                end_date=end_date,
                max_pages=max_pages,
            )

            print(
                f"\nHistorical candidates: "
                f"{len(discovered)}"
            )

            if not discovered:
                print("No articles discovered.")

                summaries[source_name] = {
                    "candidates": 0,
                    "status": "no_articles",
                }

                continue

            # Existing ingestion logic:
            # - Skip existing articles
            # - Extract new articles
            # - Validate publication dates
            # - Save to PostgreSQL

            result = collect_source(
                source_config,
                discovered_override=discovered,
                published_from=start_date,
                published_to=end_date,
            )

            summaries[source_name] = {
                "candidates": len(discovered),
                "result": result,
                "status": "completed",
            }

            print(
                f"\nCompleted backfill: {source_name}"
            )

        except Exception as exc:

            print(
                f"\nERROR in {source_name}: {exc}"
            )

            summaries[source_name] = {
                "status": "failed",
                "error": str(exc),
            }

        time.sleep(1)

    print("\n" + "=" * 70)
    print("FINAL BACKFILL SUMMARY")
    print("=" * 70)

    for source_name, summary in summaries.items():

        print(f"\n{source_name.upper()}")

        print(
            f"  Status: "
            f"{summary['status']}"
        )

        if "candidates" in summary:
            print(
                f"  Candidates: "
                f"{summary['candidates']}"
            )

        if "result" in summary:
            print(
                f"  Ingestion result: "
                f"{summary['result']}"
            )

        if "error" in summary:
            print(
                f"  Error: {summary['error']}"
            )

    return summaries


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Recover historical articles for Paraguay News"
        )
    )

    parser.add_argument(
        "--from-date",
        required=True,
        type=date.fromisoformat,
        help="Start date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--to-date",
        required=True,
        type=date.fromisoformat,
        help="End date (YYYY-MM-DD)",
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        choices=list(SOURCE_DOMAINS.keys()),
        default=list(SOURCE_DOMAINS.keys()),
        help="Sources to backfill",
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        default=15,
        help="Maximum Queryly pages per search term",
    )

    args = parser.parse_args()

    if args.from_date > args.to_date:
        parser.error(
            "--from-date must be before or equal to --to-date"
        )

    run_backfill(
        start_date=args.from_date,
        end_date=args.to_date,
        source_names=args.sources,
        max_pages=args.max_pages,
    )


if __name__ == "__main__":
    main()
