"""
Zeigt die Ergebnisse der KI-gestützten Vergleichsanalyse formatiert an.

Dieses Skript ist ein reines Anzeigewerkzeug und das Gegenstück zu
'run_comparison1.py'. Seine einzige Aufgabe ist es, die von jenem Skript
erzeugte Ergebnisdatei ('data/comparison_results.jsonl') zu lesen.

Für jedes in der Datei gefundene Business Epic werden die Analyseergebnisse
übersichtlich und menschenlesbar auf der Konsole ausgegeben. Die Ausgabe
ist klar strukturiert und hebt die folgenden Punkte hervor:
- Die Gesamtbewertung der KI.
- Eine Zusammenfassung der Bewertung.
- Aufgelisteter Informationsgewinn und -verlust.
- Die neue, vom LLM bereinigte Beschreibung.
- Der neue, vom LLM extrahierte Business Value im formatierten JSON-Format.
"""
import json
import os
import textwrap

# --- KONFIGURATION ---
# Passen Sie diesen Pfad an, falls Ihre Ergebnisdatei woanders liegt.
# Der Pfad geht davon aus, dass das Skript im 'src'-Ordner liegt und die
# Daten in einem parallelen 'data'-Ordner.
INPUT_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'comparison_results.jsonl')
# --- ENDE KONFIGURATION ---

def print_epic_assessment(data: dict):
    """Gibt die formatierte Auswertung für ein einzelnes Epic aus."""

    epic_key = data.get("epic_key", "N/A")
    ai_assessment = data.get("ai_assessment", {})
    new_description = data.get("new_description", "Keine Beschreibung vorhanden.")
    new_business_value = data.get("new_business_value", {})

    # --- Header mit Epic Key ---
    print(f"\n{'='*80}")
    print(f" E P I C :   {epic_key}")
    print(f"{'='*80}")

    # --- KI-Bewertung ---
    quality = ai_assessment.get('quality_assessment', 'N/A')
    summary = ai_assessment.get('assessment_summary', 'Keine Zusammenfassung.')

    print(f"\n📋 QUALITÄTSBEWERTUNG: {quality}")
    print("\n   Zusammenfassung:")
    # Textwrap sorgt für saubere Umbrüche bei langen Sätzen
    print(textwrap.indent(textwrap.fill(summary, width=75), '   > '))

    # --- Informationsgewinn ---
    print("\n[+] INFORMATIONSGEWINN:")
    gained_info = ai_assessment.get('information_gained', [])
    if gained_info:
        for item in gained_info:
            print(textwrap.indent(f"- {item}", '    '))
    else:
        print("    - Keiner")

    # --- Informationsverlust ---
    print("\n[-] INFORMATIONSVERLUST:")
    lost_info = ai_assessment.get('information_lost', [])
    if lost_info:
        for item in lost_info:
            print(textwrap.indent(f"- {item}", '    '))
    else:
        print("    - Keiner")

    # --- Neue, bereinigte Beschreibung ---
    print(f"\n{'-'*80}")
    print("📄 NEUE, BEREINIGTE BESCHREIBUNG:")
    print(f"{'-'*80}")
    print(textwrap.fill(new_description, width=80))

    # --- Neuer, extrahierter Business Value ---
    print(f"\n{'-'*80}")
    print("💰 NEUER BUSINESS VALUE (JSON):")
    print(f"{'-'*80}")
    # Gib das JSON-Objekt formatiert aus
    print(json.dumps(new_business_value, indent=2, ensure_ascii=False))
    print("\n")


def main():
    """Hauptfunktion zum Einlesen und Ausgeben der Datei."""
    if not os.path.exists(INPUT_FILE):
        print(f"FEHLER: Die Datei '{INPUT_FILE}' wurde nicht gefunden.")
        return

    print(f"Lese Ergebnisse aus '{INPUT_FILE}'...")

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                # Jede Zeile ist ein separates JSON-Objekt
                data = json.loads(line)
                print_epic_assessment(data)
            except json.JSONDecodeError:
                print(f"WARNUNG: Konnte eine Zeile nicht als JSON parsen: {line.strip()}")

if __name__ == "__main__":
    main()
