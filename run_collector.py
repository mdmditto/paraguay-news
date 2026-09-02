from datetime import datetime, timedelta, timezone

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
from collectors.elindependiente import discover_articles as discover_elindependiente
from collectors.rdn import discover_articles as discover_rdn
from collectors.adn import discover_articles as discover_adn
from collectors.latribuna import discover_articles as discover_latribuna
from collectors.megacadena import discover_articles as discover_megacadena
from collectors.popular import discover_articles as discover_popular
from collectors.lajornada import discover_articles as discover_lajornada
from collectors.dpn import discover_articles as discover_dpn
from collectors.extra import discover_articles as discover_extra
from collectors.cronica import discover_articles as discover_cronica
from collectors.elpoder import discover_articles as discover_elpoder


from extraction.article import extract_article
from extraction.normalize import (
    normalize_article,
    normalize_url,
)

from database.repository import (
    create_article,
    get_article_info_by_url,
    get_source_by_domain,
    update_article_if_changed,
)


REVISION_WINDOW = timedelta(hours=24)


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
    {
        "name": "UNICANAL",
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
    {
        "name": "5 días",
        "domain": "5dias.com.py",
        "collector": discover_cincodias,
    },
    {
        "name": "Telefuturo",
        "domain": "telefuturo.com.py",
        "collector": discover_telefuturo,
    },
    {
        "name": "El Independiente",
        "domain": "independiente.com.py",
        "collector": discover_elindependiente,
    },
    {
        "name": "Resumen de Noticias",
        "domain": "rdn.com.py",
        "collector": discover_rdn,
    },
    {
        "name": "adn",
        "domain": "adn.com.py",
        "collector": discover_adn,
    },
    {
        "name": "La Tribuna",
        "domain": "latribuna.com.py",
        "collector": discover_latribuna,
    },
    {
        "name": "Megacadena",
        "domain": "megacadena.com.py",
        "collector": discover_megacadena,
    },
    {
        "name": "Popular",
        "domain": "popular.com.py",
        "collector": discover_popular,
    },
    {
        "name": "La Jornada",
        "domain": "lajornada.com.py",
        "collector": discover_lajornada,
    },
    {
        "name": "Diario Paraguayo Noticias",
        "domain": "dpn.com.py",
        "collector": discover_dpn,
    },
    {
        "name": "Extra",
        "domain": "extra.com.py",
        "collector": discover_extra,
    },
    {
        "name": "Crónica",
        "domain": "cronica.com.py",
        "collector": discover_cronica,
    },
    {
        "name": "El Poder",
        "domain": "elpoder.com.py",
        "collector": discover_elpoder,
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
            "updated": 0,
            "unchanged": 0,
            "old": 0,
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
            "updated": 0,
            "unchanged": 0,
            "old": 0,
            "failed": 1,
        }

    print(
        f"Discovered {len(discovered)} articles."
    )

    new_count = 0
    updated_count = 0
    unchanged_count = 0
    old_count = 0
    failed_count = 0

    for item in discovered:

        url = normalize_url(
            item["url"]
        )

        if url is None:
            print(
                "FAILED: invalid URL"
           )

            failed_count += 1
            continue

        listing_title = (
            item.get("title") or url
        )

        article_info = (
            get_article_info_by_url(url)
        )

        existing_article_id = None

        # -------------------------------------------------
        # EXISTING ARTICLE
        # -------------------------------------------------

        if article_info is not None:

            (
                existing_article_id,
                first_scraped_at,
            ) = article_info

            # Ensure timestamp is timezone-aware.
            if first_scraped_at.tzinfo is None:
                first_scraped_at = (
                    first_scraped_at.replace(
                        tzinfo=timezone.utc
                    )
                )

            article_age = (
                datetime.now(timezone.utc)
                - first_scraped_at
            )

            # Stop checking revisions after 24 hours.
            if article_age >= REVISION_WINDOW:

                print(
                    f"OLD: {listing_title}"
                )

                old_count += 1
                continue

        # -------------------------------------------------
        # EXTRACT ARTICLE
        # -------------------------------------------------

        try:
            raw = extract_article(url)

            if raw is None:

                print(
                    f"FAILED: {listing_title}"
                )

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
                    f"FAILED: {listing_title}"
                )

                print(
                    f"  Empty body: {url}"
                )

                failed_count += 1
                continue

            # -------------------------------------------------
            # NEW ARTICLE
            # -------------------------------------------------

            if article_info is None:

                article_id = create_article(
                    normalized
                )

                print(
                    f"NEW: "
                    f"{normalized['title']}"
                )

                print(
                    f"  Saved as article ID "
                    f"{article_id}"
                )

                new_count += 1

            # -------------------------------------------------
            # EXISTING ARTICLE WITHIN 24 HOURS
            # -------------------------------------------------

            else:

                changed = (
                    update_article_if_changed(
                        article_id=existing_article_id,
                        article_data=normalized,
                    )
                )

                if changed:

                    print(
                        f"UPDATED: "
                        f"{normalized['title']}"
                    )

                    print(
                        f"  New revision created "
                        f"for article ID "
                        f"{existing_article_id}"
                    )

                    updated_count += 1

                else:

                    print(
                        f"UNCHANGED: "
                        f"{normalized['title']}"
                    )

                    unchanged_count += 1

        except Exception as exc:

            print(
                f"ERROR: {url}"
            )

            print(
                f"  {exc}"
            )

            failed_count += 1

    return {
        "new": new_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "old": old_count,
        "failed": failed_count,
    }


def main():

    total_new = 0
    total_updated = 0
    total_unchanged = 0
    total_old = 0
    total_failed = 0

    for source_config in SOURCES:

        result = collect_source(
            source_config
        )

        total_new += result["new"]
        total_updated += result["updated"]
        total_unchanged += result["unchanged"]
        total_old += result["old"]
        total_failed += result["failed"]

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    print(
        f"New articles:        {total_new}"
    )

    print(
        f"Updated articles:    {total_updated}"
    )

    print(
        f"Unchanged (<24h):    {total_unchanged}"
    )

    print(
        f"Older than 24h:      {total_old}"
    )

    print(
        f"Failed:              {total_failed}"
    )


if __name__ == "__main__":
    main()