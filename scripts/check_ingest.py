#!/usr/bin/env python3
"""Validation itération 1+2 : télécharge le dump, parse, peuple la DB, sort JSON des 5 sorts canoniques.

Usage :
    python scripts/check_ingest.py [--data-dir ./data] [--no-download] [--no-db]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

# Permet l'exécution directe (sans pip install -e .)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import settings
from src.ingest.download import download_dump, extract_dump
from src.ingest.parser_fr import SpellData, parse_dump

CANONICAL = {
    "boule-de-feu",
    "soins-legers",
    "dissipation-de-la-magie",
    "charme-personne",
    "souhait",
}

CANONICAL_NAMES = {
    "boule de feu",
    "soins légers",
    "soins legers",
    "dissipation de la magie",
    "charme-personne",
    "charme personne",
    "souhait",
}


def _matches(spell: SpellData) -> bool:
    return spell.slug_fr in CANONICAL or spell.name_fr.lower() in CANONICAL_NAMES


async def main(data_dir: Path, no_download: bool, no_db: bool) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Localise ou télécharge le dump
    # Le dump extrait se trouve dans data/Out/Pathfinder-RPG/ (12 000+ fichiers XML)
    xml_dir = data_dir / "Out" / "Pathfinder-RPG"

    if no_download and xml_dir.exists() and any(xml_dir.glob("*.xml")):
        xml_path = xml_dir
        count = sum(1 for _ in xml_dir.glob("*.xml"))
        print(f"Utilisation du cache XML : {xml_path} ({count} fichiers)")
    else:
        print("Téléchargement du dump pathfinder-fr.org …")
        archive = await download_dump(settings.wiki_dump_url, data_dir)
        xml_path = extract_dump(archive, data_dir)

    # 2. Parse
    all_spells = parse_dump(str(xml_path))
    print(f"\nSorts parsés au total : {len(all_spells)}")

    # 3. Peuple la DB (sauf si --no-db)
    inserted = updated = 0
    if not no_db:
        from src.ingest.populate import upsert_spells
        print("Alimentation de la base SQLite …")
        inserted, updated = upsert_spells(all_spells)
        print(f"DB : {inserted} insérés, {updated} mis à jour")

    # 4. Vérifie les sorts canoniques
    found: dict[str, dict] = {}
    for spell in all_spells:
        if _matches(spell):
            found[spell.slug_fr] = asdict(spell)

    missing = CANONICAL - set(found.keys())
    print(f"\nSorts canoniques trouvés : {len(found)}/{len(CANONICAL)}")
    if missing:
        print(f"MANQUANTS : {', '.join(sorted(missing))}", file=sys.stderr)

    result = {
        "total_parse": len(all_spells),
        "db_inseres": inserted,
        "db_maj": updated,
        "canoniques_trouves": len(found),
        "canoniques_manquants": sorted(missing),
        "sorts": found,
    }
    print("\n" + json.dumps(result, ensure_ascii=False, indent=2))

    return 0 if len(found) >= 3 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Validation — parse + peuple la DB depuis le dump pathfinder-fr."
    )
    parser.add_argument(
        "--data-dir", type=Path, default=Path("./data"),
        help="Répertoire pour le dump (défaut : ./data)",
    )
    parser.add_argument(
        "--no-download", action="store_true",
        help="Ne pas télécharger si un XML est déjà présent",
    )
    parser.add_argument(
        "--no-db", action="store_true",
        help="Ne pas peupler la DB SQLite (parse seulement)",
    )
    args = parser.parse_args()

    sys.exit(asyncio.run(main(args.data_dir, args.no_download, args.no_db)))
