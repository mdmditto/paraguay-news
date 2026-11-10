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
from collectors.elobservador import discover_articles as discover_elobservador
from collectors.laclave import discover_articles as discover_laclave
from collectors.cdehot import discover_articles as discover_cdehot
from collectors.ahoracde import discover_articles as discover_ahoracde
from collectors.tnpress import discover_articles as discover_tnpress
from collectors.noticiascde import discover_articles as discover_noticiascde
from collectors.primeraplana import discover_articles as discover_diarioprimeraplana
from collectors.amambaydigital import discover_articles as discover_amambaydigital
from collectors.pedrojuandigital import discover_articles as discover_pedrojuandigital
from collectors.amambaynews import discover_articles as discover_amambaynews
from collectors.amambayahora import discover_articles as discover_amambayahora
from collectors.oviedopress import discover_articles as discover_oviedopress
from collectors.caazapaahora import discover_articles as discover_caazapaahora
from collectors.luquenoticias import discover_articles as discover_luquenoticias
from collectors.sanlorenzopy import discover_articles as discover_sanlorenzopy
from collectors.sanlorenzohoy import discover_articles as discover_sanlorenzohoy
from collectors.qap import discover_articles as discover_qapchaconews
from collectors.concepcionaldia import discover_articles as discover_concepcionaldia
from collectors.itapuanoticias import discover_articles as discover_itapuanoticias
from collectors.masencarnacion import discover_articles as discover_masencarnacion
from collectors.digitalmisiones import discover_articles as discover_digitalmisiones
from collectors.reddigitalsanpedro import discover_articles as discover_reddigitalsanpedro
from collectors.asunciontimes import discover_articles as discover_theasunciontimes
from collectors.nanduti import discover_articles as discover_nanduti


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
    },
    {
        "name": "El Observador",
        "domain": "elobservador.com.py",
        "collector": discover_elobservador,
    },
    {
        "name": "La Clave",
        "domain": "laclave.com.py",
        "collector": discover_laclave,
    },
    {
        "name": "CDE Hot",
        "domain": "cdehot.com.py",
        "collector": discover_cdehot,
    },
    {
        "name": "Ahora CDE",
        "domain": "ahoracde.com",
        "collector": discover_ahoracde,
    },
    {
        "name": "TN Press",
        "domain": "tnpress.com.py",
        "collector": discover_tnpress,
    },
    {
        "name": "Noticias CDE",
        "domain": "noticiascde.com.py",
        "collector": discover_noticiascde,
    },
    {
        "name": "Primera Plana",
        "domain": "diarioprimeraplana.com.py",
        "collector": discover_diarioprimeraplana,
    },
    {
        "name": "Amambay Digital",
        "domain": "amambaydigital.com.py",
        "collector": discover_amambaydigital,
    },
    {
        "name": "Pedro Juan Digital",
        "domain": "pedrojuandigital.com.py",
        "collector": discover_pedrojuandigital,
    },
    {
        "name": "Amambay News",
        "domain": "amambaynews.com",
        "collector": discover_amambaynews,
    },
    {
        "name": "Amambay Ahora",
        "domain": "amambayahora.com.py",
        "collector": discover_amambayahora,
    },
    {
        "name": "Oviedo Press",
        "domain": "oviedopress.com",
        "collector": discover_oviedopress,
    },
    {
        "name": "Caazapa Ahora",
        "domain": "caazapaahora.com.py",
        "collector": discover_caazapaahora,
    },
    {
        "name": "Luque Noticias",
        "domain": "luquenoticias.com.py",
        "collector": discover_luquenoticias,
    },
    {
        "name": "San Lorenzo Py",
        "domain": "sanlorenzopy.com",
        "collector": discover_sanlorenzopy,
    },
    {
        "name": "San Lorenzo Hoy",
        "domain": "sanlorenzohoy.com",
        "collector": discover_sanlorenzohoy,
    },
    {
        "name": "QAP Chaco News",
        "domain": "qapchaconews.com",
        "collector": discover_qapchaconews,
    },
    {
        "name": "Concepción al Día",
        "domain": "concepcionaldia.com",
        "collector": discover_concepcionaldia,
    },
    {
        "name": "Itapúa en Noticias",
        "domain": "itapuanoticias.tv",
        "collector": discover_itapuanoticias,
    },
    {
        "name": "Más Encarnación",
        "domain": "masencarnacion.com",
        "collector": discover_masencarnacion,
    },
    {
        "name": "Digital Misiones",
        "domain": "digitalmisiones.com.py",
        "collector": discover_digitalmisiones,
    },
    {
        "name": "Red Digital San Pedro",
        "domain": "reddigitalsanpedro.com.py",
        "collector": discover_reddigitalsanpedro,
    },
    {
        "name": "The Asuncion Times",
        "domain": "theasunciontimes.com.py",
        "collector": discover_theasunciontimes,
    },
    {
        "name": "Nanduti",
        "domain": "nanduti.com.py",
        "collector": discover_nanduti,
    }

]


def collect_source(
    source_config,
    discovered_override=None,
    published_from=None,
    published_to=None,
):
    """
    Collect articles from one news source.

    Normal mode:
        collect_source(source_config)

    Historical backfill:
        collect_source(
            source_config,
            discovered_override=historical_articles,
            published_from=date(2026, 11, 4),
            published_to=date(2026, 11, 9),
        )

    Historical mode:
        - Uses supplied article URLs instead of live discovery.
        - Validates actual publication dates.
        - Inserts only missing articles.
        - Does not overwrite existing historical articles.
    """

    from datetime import date, datetime, timezone
    from zoneinfo import ZoneInfo

    local_timezone = ZoneInfo("America/Asuncion")

    print("\n" + "=" * 70)
    print(f"COLLECTING: {source_config['name']}")
    print("=" * 70)

    historical_mode = (
        discovered_override is not None
        or published_from is not None
        or published_to is not None
    )

    source = get_source_by_domain(source_config["domain"])

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
        discovered = (
            source_config["collector"]()
            if discovered_override is None
            else discovered_override
        )

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

    print(f"Discovered {len(discovered)} articles.")

    new_count = 0
    updated_count = 0
    unchanged_count = 0
    old_count = 0
    failed_count = 0

    skipped_date_count = 0
    skipped_unknown_date_count = 0

    for index, item in enumerate(discovered, start=1):

        url = normalize_url(item["url"])

        if url is None:
            print("FAILED: invalid URL")
            failed_count += 1
            continue

        listing_title = item.get("title") or url

        print(
            f"\n[{index}/{len(discovered)}] "
            f"{listing_title}"
        )

        try:
            article_info = get_article_info_by_url(url)

            existing_article_id = None

            # ---------------------------------------------
            # EXISTING ARTICLE
            # ---------------------------------------------

            if article_info is not None:

                (
                    existing_article_id,
                    first_scraped_at,
                ) = article_info

                # In historical mode, an article already
                # stored in the database does not need
                # to be extracted again.
                if historical_mode:
                    print(f"ALREADY EXISTS: {url}")
                    old_count += 1
                    continue

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

                # Preserve normal revision behavior.
                if article_age >= REVISION_WINDOW:

                    print(f"OLD: {listing_title}")

                    old_count += 1
                    continue

            # ---------------------------------------------
            # EXTRACT ARTICLE
            # ---------------------------------------------

            raw = extract_article(url)

            if raw is None:

                print(f"FAILED: {listing_title}")
                print(f"  Extraction failed: {url}")

                failed_count += 1
                continue

            normalized = normalize_article(
                raw=raw,
                source_id=source.id,
                url=url,
            )

            if not normalized["body"]:

                print(f"FAILED: {listing_title}")
                print(f"  Empty body: {url}")

                failed_count += 1
                continue

            # ---------------------------------------------
            # HISTORICAL PUBLICATION DATE FILTER
            # ---------------------------------------------

            if historical_mode and (
                published_from is not None
                or published_to is not None
            ):

                published_at = normalized.get(
                    "published_at"
                )

                if published_at is None:

                    print(
                        "SKIPPED: publication date "
                        "could not be determined."
                    )

                    skipped_unknown_date_count += 1
                    continue

                if isinstance(published_at, str):

                    try:
                        published_at = datetime.fromisoformat(
                            published_at.replace("Z", "+00:00")
                        )
                    except ValueError:

                        print(
                            "SKIPPED: invalid "
                            f"publication date: {published_at}"
                        )

                        skipped_unknown_date_count += 1
                        continue

                if isinstance(published_at, datetime):

                    if published_at.tzinfo is None:
                        # Assumes naive timestamps from the
                        # extractor represent Paraguay time.
                        # Adjust if your extractor uses UTC.
                        published_at = published_at.replace(
                            tzinfo=local_timezone
                        )

                    publication_date = (
                        published_at
                        .astimezone(local_timezone)
                        .date()
                    )

                elif isinstance(published_at, date):
                    publication_date = published_at

                else:
                    print(
                        "SKIPPED: unsupported "
                        "publication date format."
                    )

                    skipped_unknown_date_count += 1
                    continue

                if (
                    published_from is not None
                    and publication_date < published_from
                ):
                    print(
                        f"SKIPPED: {publication_date} "
                        "is before the requested period."
                    )

                    skipped_date_count += 1
                    continue

                if (
                    published_to is not None
                    and publication_date > published_to
                ):
                    print(
                        f"SKIPPED: {publication_date} "
                        "is after the requested period."
                    )

                    skipped_date_count += 1
                    continue

            # ---------------------------------------------
            # NEW ARTICLE
            # ---------------------------------------------

            if article_info is None:

                article_id = create_article(normalized)

                print(
                    f"NEW: {normalized['title']}"
                )

                print(
                    f"  Saved as article ID {article_id}"
                )

                new_count += 1

            # ---------------------------------------------
            # EXISTING ARTICLE WITHIN REVISION WINDOW
            # ---------------------------------------------

            else:

                changed = update_article_if_changed(
                    article_id=existing_article_id,
                    article_data=normalized,
                )

                if changed:

                    print(
                        f"UPDATED: {normalized['title']}"
                    )

                    print(
                        "  New revision created for "
                        f"article ID {existing_article_id}"
                    )

                    updated_count += 1

                else:

                    print(
                        f"UNCHANGED: {normalized['title']}"
                    )

                    unchanged_count += 1

        except Exception as exc:

            print(f"ERROR: {url}")
            print(f"  {exc}")

            failed_count += 1

    # ---------------------------------------------
    # SOURCE SUMMARY
    # ---------------------------------------------

    print("\n" + "-" * 70)
    print(f"SUMMARY: {source_config['name']}")
    print("-" * 70)

    print(f"New articles:           {new_count}")
    print(f"Updated articles:       {updated_count}")
    print(f"Unchanged articles:     {unchanged_count}")
    print(f"Already existing / old: {old_count}")
    print(f"Outside date range:     {skipped_date_count}")
    print(f"Unknown dates:          {skipped_unknown_date_count}")
    print(f"Failed:                 {failed_count}")

    return {
        "new": new_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "old": old_count,
        "failed": failed_count,
        "skipped_date": skipped_date_count,
        "skipped_unknown_date": skipped_unknown_date_count,
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