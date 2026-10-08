import json
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

today = datetime.now(ZoneInfo("Europe/Madrid")).date()
date_str = today.strftime("%Y%m%d")
base = "https://www.omie.es/es/file-download?filename=marginalpdbc_" + date_str + ".{version}&parents=marginalpdbc"

raw = None
used_version = None
for version in range(1, 10):
    try:
        with urllib.request.urlopen(base.format(version=version), timeout=30) as response:
            raw = response.read().decode("latin-1")
        used_version = version
        break
    except Exception:
        continue

if raw is None:
    raise SystemExit("No se encontró el fichero de precios de OMIE para " + date_str)

rows = []
for line in raw.splitlines():
    parts = line.strip().split(";")
    if len(parts) >= 7 and parts[0].isdigit() and parts[3].isdigit():
        try:
            rows.append({"period": int(parts[3]), "price": float(parts[6])})
        except ValueError:
            pass

if not rows:
    raise SystemExit("El fichero de OMIE no contiene precios válidos")

prices = [r["price"] for r in rows]
hourly = []
for hour in range((max(r["period"] for r in rows) + 3) // 4):
    chunk = [r["price"] for r in rows if hour * 4 < r["period"] <= (hour + 1) * 4]
    if chunk:
        hourly.append({"label": f"{hour:02d}:00", "price": round(sum(chunk) / len(chunk), 2)})

data = {
    "date": today.isoformat(),
    "source": "OMIE",
    "file_version": used_version,
    "average": round(sum(prices) / len(prices), 2),
    "min": round(min(prices), 2),
    "max": round(max(prices), 2),
    "hourly": hourly,
}

with open("data/omie.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")
