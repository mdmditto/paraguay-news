from collectors.abc import discover_articles as discover_abc
from collectors.ultimahora import discover_articles as discover_uh
from collectors.lanacion import discover_articles as discover_ln
from collectors.hoy import discover_articles as discover_hoy
from collectors.npy import discover_articles as discover_npy
from collectors.unicanal import discover_articles as discover_unicanal
from collectors.ip import discover_articles as discover_ip
from collectors.monumental import discover_articles as discover_monumental
from collectors.cincodias import discover_articles as discover_cincodias
from collectors.telefuturo import discover_articles as discover_telefuturo

from extraction.article import extract_article
from extraction.normalize import normalize_article

from database.repository import (
    article_exists,
    get_source_by_domain,
    save_article,
)


SOURCES = [
    {
        "name": "ABC Color",
        "domain": "abc.com.py",
        "collector": discover_abc,
    },
    {
        "name": "Última Hora",
        "domain": "ultimahora.com",
        "collector": discover_uh,
    },
    {
        "name": "La Nación",
        "domain": "lanacion.com.py",
        "collector": discover_ln,
    },
    {
        "name": "HOY",
        "domain": "hoy.com.py",
        "collector": discover_hoy,
    },
    {
        "name": "NPY",
        "domain": "npy.com.py",
        "collector": discover_npy,
    },
    {   "name": "UNICANAL",
        "domain": "unicanal.com.py",
        "collector": discover_unicanal,
    },
    {
        "name": "Agencia IP",
        "domain": "ip.gov.py",
        "collector": discover_ip,
    },
    {
        "name": "Monumental",
        "domain": "monumental.com.py",
        "collector": discover_monumental,
    },
    {   "name": "5 días",
        "domain": "5dias.com.py",
        "collector": discover_cincodias,
    },
    {   "name": "Telefuturo",
        "domain": "telefuturo.com.py",
        "collector": discover_telefuturo,
    }
]


def collect_source(source_config):

    print("\n" + "=" * 70)
    print(f"COLLECTING: {source_config['name']}")
    print("=" * 70)

    source = get_source_by_domain(
        source_config["domain"]
    )

    if source is None:
        print(
            f"ERROR: {source_config['name']} "
            "is not registered in the database."
        )

        return {
            "new": 0,
            "skipped": 0,
            "failed": 1,
        }

    try:
        discovered = source_config["collector"]()
    except Exception as exc:
        print(
            f"Discovery failed for "
            f"{source_config['name']}: {exc}"
        )

        return {
            "new": 0,
            "skipped": 0,
            "failed": 1,
        }

    print(
        f"Discovered {len(discovered)} articles."
    )

    new_count = 0
    skipped_count = 0
    failed_count = 0

    for item in discovered:

        url = item["url"]
        title = item["title"]

        if article_exists(url):

            print(
                f"SKIP: {title}"
            )

            skipped_count += 1

            continue

        print(
            f"NEW: {title}"
        )

        try:

            raw = extract_article(url)

            if raw is None:

                print(
                    f"  Extraction failed: {url}"
                )

                failed_count += 1
                continue

            normalized = normalize_article(
                raw=raw,
                source_id=source.id,
                url=url,
            )

            if not normalized["body"]:

                print(
                    f"  Empty body: {url}"
                )

                failed_count += 1
                continue

            article_id = save_article(
                normalized
            )

            print(
                f"  Saved as article ID {article_id}"
            )

            new_count += 1

        except Exception as exc:

            print(
                f"  ERROR: {url}"
            )

            print(
                f"  {exc}"
            )

            failed_count += 1

    return {
        "new": new_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }


def main():

    total_new = 0
    total_skipped = 0
    total_failed = 0

    for source_config in SOURCES:

        result = collect_source(
            source_config
        )

        total_new += result["new"]
        total_skipped += result["skipped"]
        total_failed += result["failed"]

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    print(
        f"New articles:     {total_new}"
    )

    print(
        f"Already existed:  {total_skipped}"
    )

    print(
        f"Failed:           {total_failed}"
    )


if __name__ == "__main__":
    main()
