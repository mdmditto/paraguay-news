
from playwright.sync_api import sync_playwright
from urllib.parse import urljoin
from collections import Counter
from datetime import date
from urllib.parse import urlparse

BASE = "https://www.lanacion.com.py"
SEARCH_URL = BASE + "/buscar/Paraguay/"


def article_date(url):
    parts = urlparse(url).path.strip("/").split("/")

    if len(parts) < 5:
        return None

    try:
        return date(
            int(parts[1]),
            int(parts[2]),
            int(parts[3]),
        )
    except (ValueError, IndexError):
        return None


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def inspect_response(response):
            resource_type = response.request.resource_type

            if resource_type not in ("xhr", "fetch"):
                return

            url = response.url.lower()

            if any(x in url for x in (
                "google",
                "analytics",
                "doubleclick",
                "recaptcha",
                "metricool",
                "adtraffic",
                "go-mpulse",
            )):
                return

            print("\nNETWORK:", response.status, response.url)

            try:
                print("BODY:", response.text()[:500])
            except Exception:
                pass

        page.on("response", inspect_response)

        page.goto(
            SEARCH_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(5000)

        print("PAGE TITLE:", page.title())
        print("FINAL URL:", page.url)

        def get_articles():
            urls = set()

            for link in page.locator(
                'a[href*="/2026/11/"]'
            ).all():
                href = link.get_attribute("href")

                if href:
                    urls.add(urljoin(BASE, href))

            return urls

        previous = get_articles()

        print("\nINITIAL ARTICLES:", len(previous))

        for i in range(5):
            button = page.get_by_text(
                "Cargar más noticias",
                exact=False,
            )

            if button.count() == 0:
                print("No load-more button found.")
                break

            print(f"\nCLICK {i + 1}")

            try:
                button.first.click(timeout=10000)
                page.wait_for_timeout(3000)
            except Exception as exc:
                print("Click failed:", exc)
                break

            current = get_articles()
            new_urls = current - previous

            print("Total unique:", len(current))
            print("New URLs:", len(new_urls))

            previous = current

        counts = Counter(
            article_date(url)
            for url in previous
            if article_date(url)
        )

        print("\nARTICLES BY DATE")

        for day, count in sorted(counts.items()):
            print(day, count)

        browser.close()


if __name__ == "__main__":
    main()
