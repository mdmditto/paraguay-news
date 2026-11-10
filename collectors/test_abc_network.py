from playwright.sync_api import sync_playwright
from urllib.parse import quote

URL = "https://www.abc.com.py/buscador/?query=" + quote("Economía")

EXCLUDED = (
    "google",
    "doubleclick",
    "analytics",
    "facebook",
    "pubmatic",
    "adsystem",
    "adtraffic",
    "googlesyndication",
    "piano.io",
    "tinypass.com",
    "newsroom.bi",
    "crwdcntrl.net",
    "id5-sync.com",
)

KEYWORDS = (
    "queryly",
    "search",
    "buscador",
    "result",
    "api",
)


def main():
    with sync_playwright() as p:

        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1365, "height": 900}
        )

        def inspect_response(response):
            url = response.url
            lower_url = url.lower()

            if any(x in lower_url for x in EXCLUDED):
                return

            request = response.request

            if request.resource_type in (
                "image",
                "font",
                "stylesheet",
                "media",
            ):
                return

            content_type = response.headers.get(
                "content-type", ""
            )

            interesting = (
                any(x in lower_url for x in KEYWORDS)
                or request.resource_type in ("xhr", "fetch")
            )

            if not interesting:
                return

            print("\n" + "=" * 70)
            print("URL:", url)
            print("METHOD:", request.method)
            print("RESOURCE:", request.resource_type)
            print("STATUS:", response.status)
            print("CONTENT TYPE:", content_type)

            if request.resource_type == "script":
                return

            try:
                body = response.text()

                if any(
                    x in body.lower()
                    for x in (
                        "results",
                        "totalresults",
                        "searchresults",
                        "economía",
                        "economia",
                    )
                ):
                    print("POSSIBLE SEARCH RESPONSE")
                    print("BODY:", body[:1500])

            except Exception:
                pass

        page.on("response", inspect_response)

        print("Opening ABC search...")

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(15000)

        print("\nPage title:", page.title())

        print(
            "Search results visible:",
            page.get_by_text(
                "Mostrando",
                exact=False,
            ).count(),
        )

        browser.close()


if __name__ == "__main__":
    main()