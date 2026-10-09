import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("Europe/Madrid")).date()
date_str = today.strftime("%Y%m%d")
base_url = (
    "https://www.omie.es/es/file-download"
    f"?filename=marginalpdbc_{date_str}.{{version}}&parents=marginalpdbc"
)

def download_omie_file():
    last_error = None
    # OMIE can publish/revise versions; retry in case the file is not ready yet.
    for attempt in range(3):
        # Try the newest version first; OMIE may revise the same day's file.
        for version in range(9, 0, -1):
            url = base_url.format(version=version)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Energy-inteligente-OMIE-updater/1.0"}
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    raw = response.read().decode("latin-1")
                # Don't accept an HTML error page or an empty/incomplete file.
                if "MARGINALPDBC;" in raw and any(
                    line.strip().startswith(today.strftime("%Y;%m;%d;"))
                    for line in raw.splitlines()
                ):
                    return raw, version
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
        if attempt < 2:
            time.sleep(15)

    raise SystemExit(
        f"No se encontró un fichero de precios OMIE válido para {date_str}. "
        f"Último error: {last_error or 'fichero no publicado o formato inesperado'}"
    )

raw, used_version = download_omie_file()

rows = []
for line in raw.splitlines():
    parts = [part.strip() for part in line.strip().split(";")]
    # OMIE format: year;month;day;period;MarginalPT;MarginalES;
    # The final semicolon creates an empty trailing field, so the Spanish
    # price is parts[5], not parts[6].
    if len(parts) >= 6:
        try:
            year, month, day, period = map(int, parts[:4])
            if (year, month, day) != (today.year, today.month, today.day):
                continue
            price = float(parts[5].replace(",", "."))
            if period >= 1:
                rows.append({"period": period, "price": price})
        except (ValueError, IndexError):
            continue

if not rows:
    raise SystemExit("El fichero de OMIE se descargó, pero no contiene precios españoles válidos")

# Keep one value per market period and group quarter-hour periods into hours.
by_period = {}
for row in rows:
    by_period[row["period"]] = row["price"]
rows = [{"period": p, "price": price} for p, price in sorted(by_period.items())]
prices = [row["price"] for row in rows]

hourly = []
max_period = max(by_period)
for hour in range((max_period + 3) // 4):
    chunk = [
        price for period, price in by_period.items()
        if hour * 4 < period <= (hour + 1) * 4
    ]
    if chunk:
        hourly.append({"label": f"{hour:02d}:00", "price": round(sum(chunk) / len(chunk), 2)})

hourly_prices = [item["price"] for item in hourly]
if not hourly_prices:
    raise SystemExit("OMIE no contiene precios horarios válidos")

data = {
    "date": today.isoformat(),
    "source": "OMIE",
    "file_version": used_version,
    "average": round(sum(hourly_prices) / len(hourly_prices), 2),
    "min": round(min(hourly_prices), 2),
    "max": round(max(hourly_prices), 2),
    "hourly": hourly,
}

with open("data/omie.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(
    f"OMIE actualizado: {today.isoformat()}, versión {used_version}, "
    f"{len(prices)} periodos, media {data['average']} €/MWh"
)
