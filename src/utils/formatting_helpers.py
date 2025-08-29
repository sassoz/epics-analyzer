# src/utils/formatting_helpers.py
from datetime import datetime, timedelta

def format_timedelta_to_months_days(td: timedelta) -> str:
    """
    Formatiert eine Zeitdifferenz in einen lesbaren String (Monate und Tage).
    Nimmt an, dass ein Monat 30 Tage hat.
    """
    if not isinstance(td, timedelta) or td.total_seconds() <= 0:
        return "0 Tage"

    total_days = td.days
    months, days = divmod(total_days, 30)

    parts = []
    if months > 0:
        parts.append(f"{months} Monat{'e' if months > 1 else ''}")
    if days > 0:
        parts.append(f"{days} Tag{'e' if days > 1 else ''}")

    return ", ".join(parts) or "0 Tage"

def calculate_duration_string(start_iso: str, end_iso: str) -> str:
    """
    Berechnet die Dauer zwischen zwei ISO-Datumsstrings und formatiert sie.
    """
    if not start_iso or not end_iso:
        return "Nicht berechenbar"

    try:
        start_dt = datetime.fromisoformat(start_iso)
        end_dt = datetime.fromisoformat(end_iso)
        duration = end_dt - start_dt
        if duration.days < 0:
            return "Enddatum liegt vor Startdatum"
        return format_timedelta_to_months_days(duration)
    except (ValueError, TypeError):
        return "Ungültiges Datumsformat"

def format_iso_to_dd_mm_yyyy(iso_date: str) -> str | None:
    """
    Formatiert einen ISO-Datumsstring in das Format DD-MM-YYYY.
    """
    if not iso_date:
        return None
    try:
        return datetime.fromisoformat(iso_date).strftime('%d-%m-%Y')
    except (ValueError, TypeError):
        return None
