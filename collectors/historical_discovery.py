from datetime import date
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import requests

from collectors.abc import is_article_url as is_abc_article
from collectors.lanacion import is_article_url as is_ln_article
from collectors.ultimahora import is_article_url as is_uh_article

SOURCES = {
    "abc": {
        "base": "https://www.abc.com.py",
        "validator": is_abc_article,
    },
    "ultimahora": {
        "base": "https://www.ultimahora.com",
        "validator": is_uh_article,
    },
    "lanacion": {
        "base": "https://www.lanacion.com.py",
        "validator": is_ln_article,
    },
}

HEADERS = {
    "User-Agent": "ParaguayNewsResearch/1.0"
}


def get_sitemap_urls(base):
    response = requests.get(
        f"{base}/robots.txt",
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    sitemaps = []

    for line in response.text.splitlines():
        if line.lower().startswith("sitemap:"):
            sitemaps.append(line.split(":", 1)[1].strip())

    return sitemaps or [f"{base}/sitemap.xml"]


from datetime import datetime, date, timedelta
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import requests


def parse_sitemap_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def discover_historical_urls(
    source,
    start_date,
    end_date,
    max_sitemaps=500,
):
    config = SOURCES[source]
    pending = get_sitemap_urls(config["base"])
    visited = set()
    results = set()

    stats = {
        "sitemaps": 0,
        "articles_checked": 0,
        "missing_dates": 0,
    }

    session = requests.Session()
    session.headers.update(HEADERS)

    while pending and len(visited) < max_sitemaps:
        sitemap_url = pending.pop()

        if sitemap_url in visited:
            continue

        visited.add(sitemap_url)

        try:
            response = session.get(sitemap_url, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.content)
        except Exception as exc:
            print(f"Failed sitemap: {sitemap_url}: {exc}")
            continue

        stats["sitemaps"] += 1

        for node in root:
            tag = node.tag.rsplit("}", 1)[-1]

            fields = {
                child.tag.rsplit("}", 1)[-1]: child.text
                for child in node
            }

            loc = fields.get("loc")

            if not loc:
                continue

            if tag == "sitemap":
                pending.append(loc)
                continue

            if tag != "url":
                continue

            if not config["validator"](loc):
                continue

            stats["articles_checked"] += 1

            if source in ("abc", "lanacion"):
                parts = urlparse(loc).path.strip("/").split("/")

                try:
                    article_date = date(
                        int(parts[1]),
                        int(parts[2]),
                        int(parts[3]),
                    )
                except (ValueError, IndexError):
                    continue

                if not start_date <= article_date <= end_date:
                    continue

            else:
                # Última Hora: sitemap lastmod is a candidate
                # discovery filter, not a publication date.
                lastmod = parse_sitemap_date(fields.get("lastmod"))

                if lastmod is None:
                    stats["missing_dates"] += 1
                    continue

                if not start_date <= lastmod <= end_date:
                    continue

            results.add(loc)

    print(
        f"{source}: visited {stats['sitemaps']} sitemaps; "
        f"checked {stats['articles_checked']} article URLs; "
        f"missing lastmod: {stats['missing_dates']}; "
        f"remaining sitemap queue: {len(pending)}"
    )

    return sorted(results)