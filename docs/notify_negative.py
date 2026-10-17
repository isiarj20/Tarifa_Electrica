#!/usr/bin/env python3
"""
Lee docs/prices.json (ya generado por fetch_prices.py en el mismo workflow) y,
si hay horas a precio 0€ o negativo hoy o mañana, manda un aviso por Telegram.
Pensado para gente que no abre la app cada día: esto es la red de seguridad
para no perderse esas horas especiales.
"""

import os
import json
import urllib.request

JSON_PATH = os.path.join(os.path.dirname(__file__), "docs", "prices.json")
STATE_PATH = os.path.join(os.path.dirname(__file__), "docs", "last_notified.json")
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def find_free_hours(day_label: str, date_str: str, prices):
    if not prices:
        return []
    return [
        (p["hour"], p["price"])
        for p in prices
        if p["price"] <= 0
    ]


def format_hour(h):
    return f"{h:02d}:00–{(h + 1) % 24:02d}:00"


def build_message(data):
    blocks = []
    for day_label, day_key in (("Hoy", "today"), ("Mañana", "tomorrow")):
        day = data.get(day_key) or {}
        free_hours = find_free_hours(day_label, day.get("date", ""), day.get("prices"))
        if free_hours:
            lines = [f"⚡🆓 *{day_label} ({day.get('date')})* — horas a 0€ o menos:"]
            for hour, price in free_hours:
                tag = "te PAGAN" if price < 0 else "gratis"
                lines.append(f"  • {format_hour(hour)} → {price:.4f} €/kWh ({tag})")
            blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Faltan TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID, no se envía Telegram.")
        print(text)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = json.dumps(
        {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    ).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        resp.read()


def free_hours_signature(data):
    """Identifica de forma única qué horas gratis/negativas hay ahora mismo,
    por fecha, para poder comparar con lo último notificado."""
    sig = {}
    for day_key in ("today", "tomorrow"):
        day = data.get(day_key) or {}
        date = day.get("date")
        free = find_free_hours(day_key, date, day.get("prices"))
        if free:
            sig[date] = sorted(hour for hour, _ in free)
    return sig


def load_last_notified():
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_last_notified(sig):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(sig, f, ensure_ascii=False, indent=2)


def main():
    if not os.path.exists(JSON_PATH):
        print(f"No existe {JSON_PATH}, nada que comprobar todavía.")
        return

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    current_sig = free_hours_signature(data)
    last_sig = load_last_notified()

    if not current_sig:
        print("Sin horas a 0€ o negativas. No se envía nada.")
        if last_sig:
            save_last_notified({})  # limpia el estado: ya no hay nada activo
        return

    if current_sig == last_sig:
        print("Ya se avisó de estas mismas horas, no se repite el mensaje.")
        return

    message = build_message(data)
    send_telegram(message)
    save_last_notified(current_sig)
    print("Aviso enviado:")
    print(message)


if __name__ == "__main__":
    main()
