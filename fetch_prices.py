#!/usr/bin/env python3
"""
Descarga los precios PVPC de hoy y de mañana (si ya están publicados) desde la
API pública de REE y los guarda en docs/prices.json para que la página estática
(GitHub Pages) los consuma sin depender de CORS ni de tokens.
"""

import os
import json
from datetime import datetime, timedelta, timezone
import urllib.request
import urllib.parse

MADRID_TZ = timezone(timedelta(hours=2))  # ajustar a +1 en horario de invierno
REE_URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "prices.json")


def fetch_prices_for_date(date_str: str):
    start = f"{date_str}T00:00"
    end = f"{date_str}T23:59"
    params = {
        "start_date": start,
        "end_date": end,
        "time_trunc": "hour",
        "geo_ids": "8741",  # Península
    }
    url = f"{REE_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json; application/vnd.esios-api-v1+json",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    pvpc_block = next(
        (b for b in data.get("included", []) if b.get("type", "").startswith("PVPC")),
        None,
    )
    if not pvpc_block:
        return None

    values = pvpc_block["attributes"]["values"]
    if len(values) < 20:
        return None  # datos incompletos / no publicados aún

    prices = []
    for v in values:
        dt = datetime.fromisoformat(v["datetime"])
        prices.append({"hour": dt.hour, "price": round(v["value"] / 1000, 4)})
    prices.sort(key=lambda x: x["hour"])
    return prices


def main():
    now = datetime.now(MADRID_TZ)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    today_prices = fetch_prices_for_date(today_str)
    tomorrow_prices = fetch_prices_for_date(tomorrow_str)

    output = {
        "generated_at": now.isoformat(),
        "today": {"date": today_str, "prices": today_prices},
        "tomorrow": {"date": tomorrow_str, "prices": tomorrow_prices},
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Guardado {OUTPUT_PATH}")
    print(f"Hoy: {'OK' if today_prices else 'no disponible'} · Mañana: {'OK' if tomorrow_prices else 'no disponible'}")


if __name__ == "__main__":
    main()
