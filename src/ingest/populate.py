"""Peuple la base SQLite à partir des SpellData parsées."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from src.db import get_conn, init_db
from src.ingest.parser_fr import SpellData

log = logging.getLogger(__name__)


def upsert_spells(spells: list[SpellData]) -> tuple[int, int]:
    """Insère ou met à jour les sorts. Retourne (insérés, mis à jour)."""
    init_db()

    now = datetime.now(timezone.utc).isoformat()
    inserted = updated = 0

    with get_conn() as conn:
        for spell in spells:
            existing = conn.execute(
                "SELECT id FROM spells WHERE slug_fr = ?", (spell.slug_fr,)
            ).fetchone()

            data = (
                spell.slug_fr,
                spell.name_fr,
                None,  # name_en
                spell.school,
                spell.subschool,
                spell.descriptors,
                json.dumps(spell.level_json, ensure_ascii=False),
                spell.casting_time,
                spell.components,
                spell.spell_range,
                spell.target,
                spell.area,
                spell.duration,
                spell.saving_throw,
                spell.spell_resistance,
                spell.description_fr,
                spell.source,
                spell.raw_url,
                int(spell.is_ogl),
                now,
            )

            if existing:
                conn.execute(
                    """
                    UPDATE spells SET
                        name_fr=?, name_en=?, school=?, subschool=?, descriptors=?,
                        level_json=?, casting_time=?, components=?, spell_range=?,
                        target=?, area=?, duration=?, saving_throw=?,
                        spell_resistance=?, description_fr=?, source=?,
                        raw_url=?, is_ogl=?, updated_at=?
                    WHERE slug_fr=?
                    """,
                    data[1:] + (spell.slug_fr,),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO spells (
                        slug_fr, name_fr, name_en, school, subschool, descriptors,
                        level_json, casting_time, components, spell_range, target, area,
                        duration, saving_throw, spell_resistance, description_fr,
                        source, raw_url, is_ogl, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    data,
                )
                inserted += 1

    log.info("Upsert terminé : %d insérés, %d mis à jour", inserted, updated)
    return inserted, updated
