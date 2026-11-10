from datetime import date
from collectors.historical_discovery import discover_historical_urls

start = date(2026, 11, 4)
end = date(2026, 11, 9)

for source in ("abc", "lanacion", "ultimahora"):
    urls = discover_historical_urls(source, start, end)
    print(source, len(urls))
    print(*urls[:5], sep="\n")