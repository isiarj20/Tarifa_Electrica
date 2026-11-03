#!/usr/bin/env python3
"""
Descarga los precios PVPC de hoy y de mañana (si ya están publicados) desde la
API pública de REE y los guarda en docs/prices.json para que la página estática
(GitHub Pages) los consuma sin depender de CORS ni de tokens.
"""

import os
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import urllib.request
import urllib.parse

MADRID_TZ = ZoneInfo("Europe/Madrid")
REE_URL = "https://apidatos.ree.es/es/datos/mercados/precios-mercados-tiempo-real"
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "docs", "prices.json")


def looks_like_placeholder(prices) -> bool:
    """Detecta datos no fiables: REE a veces devuelve el día siguiente con
    todas las horas en 0 (o todas idénticas) justo cuando aún está terminando
    de publicar/validar los precios. Eso no es un día real con tarifa a 0€,
    así que lo tratamos como 'todavía no disponible' y se reintentará más tarde."""
    if not prices:
        return False
    values = [p["price"] for p in prices]
    if all(v == 0 for v in values):
        return True
    if len(set(values)) == 1:
        return True
    return False


def fetch_prices_for_date(date_str: str, retries: int = 2, backoff_seconds: int = 15):
    """Devuelve (precios, motivo). Si no se pudo obtener, precios es None y motivo explica por qué."""
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
            "User-Agent": "Mozilla/5.0 (pvpc-widget script)",
        },
    )

    last_error = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except Exception as e:
            last_error = e
            if attempt < retries:
                print(f"Aviso: fallo al pedir {date_str} (intento {attempt + 1}): {e}. Reintentando...")
                time.sleep(backoff_seconds)
            else:
                print(f"Aviso: no se pudieron obtener los precios de {date_str} tras {retries + 1} intentos: {e}")
                return None, f"REE no responde tras {retries + 1} intentos ({e})"
    else:
        return None, "REE no responde"

    pvpc_block = next(
        (b for b in data.get("included", []) if b.get("type", "").startswith("PVPC")),
        None,
    )
    if not pvpc_block:
        print(f"Aviso: {date_str} sin bloque PVPC todavía (probablemente no publicado aún).")
        return None, "REE responde sin precios PVPC para ese día (¿aún sin publicar?)"

    values = pvpc_block["attributes"]["values"]
    if len(values) < 20:
        print(f"Aviso: {date_str} con datos incompletos ({len(values)} horas), no publicado aún.")
        return None, f"datos incompletos ({len(values)} horas)"

    prices = []
    for v in values:
        dt = datetime.fromisoformat(v["datetime"])
        prices.append({"hour": dt.hour, "price": round(v["value"] / 1000, 4)})
    prices.sort(key=lambda x: x["hour"])

    if looks_like_placeholder(prices):
        print(f"Aviso: {date_str} parece un dato placeholder (todo a 0 o todo idéntico). Se descarta y se reintentará más tarde.")
        return None, "datos placeholder (todo a 0 o todo idéntico)"

    return prices, None


def load_previous():
    try:
        with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main(now=None):
    now = now or datetime.now(MADRID_TZ)
    today_str = now.strftime("%Y-%m-%d")
    tomorrow_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")

    # Últimos precios buenos guardados, por fecha (el "mañana" de ayer es el "hoy" de hoy).
    previous = load_previous()
    previous_by_date = {}
    for key in ("today", "tomorrow"):
        day = previous.get(key) or {}
        if day.get("date") and day.get("prices"):
            previous_by_date[day["date"]] = day["prices"]

    results, errors, any_fresh = {}, {}, False
    for date_str in (today_str, tomorrow_str):
        prices, reason = fetch_prices_for_date(date_str)
        if prices:
            any_fresh = True
        else:
            errors[date_str] = reason
            # Un fallo puntual de REE no debe borrar precios buenos que ya teníamos de ese mismo día.
            if date_str in previous_by_date:
                prices = previous_by_date[date_str]
                errors[date_str] += " — se conservan los últimos precios guardados de ese día"
        results[date_str] = prices

    output = {
        # Hora de la última descarga que SÍ trajo datos nuevos (para que la página no aparente estar más al día de lo que está)
        "generated_at": now.isoformat() if any_fresh else previous.get("generated_at", now.isoformat()),
        "last_attempt_at": now.isoformat(),
        "errors": errors,
        "today": {"date": today_str, "prices": results[today_str]},
        "tomorrow": {"date": tomorrow_str, "prices": results[tomorrow_str]},
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Guardado {OUTPUT_PATH}")
    print(f"Hoy: {'OK' if results[today_str] else 'no disponible'} · Mañana: {'OK' if results[tomorrow_str] else 'no disponible'}")
    for d, r in errors.items():
        print(f"  {d}: {r}")


if __name__ == "__main__":
    main()
