import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# La web debe mostrar el mercado diario del DÍA SIGUIENTE, no el de hoy.
today = datetime.now(ZoneInfo("Europe/Madrid")).date()
target_date = today + timedelta(days=1)
date_str = target_date.strftime("%Y%m%d")
base_url = (
    "https://www.omie.es/es/file-download"
    f"?filename=marginalpdbc_{date_str}.{{version}}&parents=marginalpdbc"
)


def download_omie_file():
    last_error = None
    # OMIE puede publicar o revisar versiones; buscar primero la más reciente.
    for attempt in range(3):
        for version in range(9, 0, -1):
            url = base_url.format(version=version)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "Energy-inteligente-OMIE-updater/1.0"}
            )
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    raw = response.read().decode("latin-1")
                # No aceptar una página de error ni un fichero sin la fecha buscada.
                if "MARGINALPDBC;" in raw and any(
                    line.strip().startswith(target_date.strftime("%Y;%m;%d;"))
                    for line in raw.splitlines()
                ):
                    return raw, version
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_error = exc
        if attempt < 2:
            time.sleep(15)

    # Antes de la publicación de los precios de mañana, conservar los últimos datos.
    print(
        f"OMIE aún no ha publicado un fichero válido para {target_date.isoformat()}. "
        f"Se conservan los datos existentes. "
        f"Último error: {last_error or 'fichero aún no publicado'}"
    )
    return None, None


raw, used_version = download_omie_file()
if raw is None:
    raise SystemExit(0)

rows = []
for line in raw.splitlines():
    parts = [part.strip() for part in line.strip().split(";")]
    # Formato OMIE: año;mes;día;periodo;MarginalPT;MarginalES;
    # El precio español está en parts[5].
    if len(parts) >= 6:
        try:
            year, month, day, period = map(int, parts[:4])
            if (year, month, day) != (
                target_date.year, target_date.month, target_date.day
            ):
                continue
            price = float(parts[5].replace(",", "."))
            if period >= 1:
                rows.append({"period": period, "price": price})
        except (ValueError, IndexError):
            continue

if not rows:
    raise SystemExit(
        f"El fichero de OMIE se descargó, pero no contiene precios españoles válidos "
        f"para {target_date.isoformat()}"
    )

# Eliminar periodos duplicados y agrupar los periodos de 15 minutos por hora.
by_period = {}
for row in rows:
    by_period[row["period"]] = row["price"]

by_period = dict(sorted(by_period.items()))
prices = list(by_period.values())

hourly = []
max_period = max(by_period)
for hour in range((max_period + 3) // 4):
    chunk = [
        price for period, price in by_period.items()
        if hour * 4 < period <= (hour + 1) * 4
    ]
    if chunk:
        hourly.append({
            "label": f"{hour:02d}:00",
            "price": round(sum(chunk) / len(chunk), 2)
        })

hourly_prices = [item["price"] for item in hourly]
if not hourly_prices:
    raise SystemExit("OMIE no contiene precios horarios válidos")

data = {
    "date": target_date.isoformat(),
    "source": "OMIE",
    "file_version": used_version,
    "average": round(sum(hourly_prices) / len(hourly_prices), 2),
    # OMIE muestra máximos y mínimos por periodo de 15 minutos, no por media horaria.
    "min": round(min(prices), 2),
    "max": round(max(prices), 2),
    "hourly": hourly,
}

with open("data/omie.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
    f.write("\n")

print(
    f"OMIE actualizado para mañana: {target_date.isoformat()}, "
    f"versión {used_version}, {len(prices)} periodos, "
    f"media {data['average']} €/MWh"
)
