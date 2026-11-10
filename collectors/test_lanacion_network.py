
from playwright.sync_api import sync_playwright

URL = "https://www.lanacion.com.py/buscar/"

EXCLUDED = (
    "google.com",
    "google-analytics",
    "analytics.google",
    "doubleclick",
    "googlesyndication",
    "adtrafficquality",
    "facebook",
    "recaptcha",
    "go-mpulse",
    "piano.io",
    "tinypass.com",
    "pubmatic",
)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        page = browser.new_page(
            viewport={"width": 1365, "height": 900}
        )

        def inspect_response(response):
            url = response.url
            lower = url.lower()

            if any(x in lower for x in EXCLUDED):
                return

            resource_type = response.request.resource_type

            if resource_type not in (
                "xhr",
                "fetch",
                "document",
                "script",
            ):
                return

            print("\n" + "=" * 70)
            print("URL:", url)
            print("TYPE:", resource_type)
            print("STATUS:", response.status)

            if resource_type in ("xhr", "fetch"):
                try:
                    body = response.text()
                    print("BODY:", body[:1500])
                except Exception:
                    pass

        page.on("response", inspect_response)

        print("Opening La Nación search...")

        page.goto(
            URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )

        page.wait_for_timeout(3000)

        # Use the search input in the main search page.
        search_input = page.get_by_placeholder(
            "¿Qué estás buscando?"
        )

        print("Search input count:", search_input.count())

        search_input.fill("Paraguay")
        search_input.press("Enter")

        page.wait_for_timeout(10000)

        print("\nFINAL URL:", page.url)
        print("PAGE TITLE:", page.title())

        print("\nARTICLE LINKS:")

        links = page.locator(
            'a[href*="/2026/11/"]'
        )

        print("Count:", links.count())

        for link in links.all()[:15]:
            print(link.get_attribute("href"))

        print("\nPAGE TEXT SAMPLE:")
        print(page.locator("body").inner_text()[:2000])

        browser.close()


if __name__ == "__main__":
    main()
