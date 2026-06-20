"""Couche d'accès SQLite — pas d'ORM, sqlite3 direct avec WAL."""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.config import settings

# ── Constantes UI ─────────────────────────────────────────────────────────────
SCHOOL_COLORS: dict[str, str] = {
    "abjuration": "#4a7bb5",
    "divination": "#5a4fcf",
    "enchantement": "#d87bbf",
    "évocation": "#e06030",
    "illusion": "#8b52c7",
    "invocation": "#4aaa67",
    "nécromancie": "#3a3a4a",
    "transmutation": "#c8922b",
    "universel": "#8a8a9a",
}

# Inner SVG path content for each school (viewBox 0 0 20 20, fill="currentColor").
# Icons sourced from Heroicons 2.0 mini (MIT) with minor adaptations.
SCHOOL_ICONS: dict[str, str] = {
    "abjuration": (
        # shield-check
        '<path d="M10 1.944A11.954 11.954 0 012.166 5C2.056 5.649 2 6.319 2 7'
        "c0 5.225 3.34 9.67 8 11.317C14.66 16.67 18 12.225 18 7"
        'c0-.682-.057-1.35-.166-2.001A11.954 11.954 0 0110 1.944z"/>'
        '<path d="M12.5 9.75a.75.75 0 00-1.06-1.06L9 11.128l-.97-.97'
        'a.75.75 0 00-1.06 1.06l1.5 1.5a.75.75 0 001.06 0l3-2.968z"/>'
    ),
    "divination": (
        # eye
        '<path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z"/>'
        '<path fill-rule="evenodd" clip-rule="evenodd"'
        ' d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3'
        "c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186"
        'A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41z"/>'
    ),
    "enchantement": (
        # heart
        '<path d="M9.653 16.915l-.005-.003-.019-.01'
        "a20.759 20.759 0 01-1.162-.682 22.045 22.045 0 01-2.582-2.09"
        "C4.03 12.503 2 9.973 2 7a5 5 0 019.75-1.61A5 5 0 0118 7"
        "c0 2.973-2.03 5.503-3.885 7.13a22.048 22.048 0 01-2.582 2.09"
        ' 20.757 20.757 0 01-1.162.682l-.019.01-.005.003h-.002a.739.739 0 01-.69 0l-.002-.001z"/>'
    ),
    "évocation": (
        # bolt / lightning
        '<path d="M11.983 1.907a.75.75 0 00-1.292-.657l-8.5 9.5'
        'A.75.75 0 002.75 12h6.572l-1.305 6.093a.75.75 0 001.292.657l8.5-9.5'
        'A.75.75 0 0017.25 8h-6.572l1.305-6.093z"/>'
    ),
    "illusion": (
        # sparkles
        '<path d="M15.98 1.804a1 1 0 00-1.96 0l-.24 1.192a1 1 0 01-.784.785'
        "l-1.192.238a1 1 0 000 1.962l1.192.238a1 1 0 01.785.785l.238 1.192"
        "a1 1 0 001.962 0l.238-1.192a1 1 0 01.785-.785l1.192-.238"
        'a1 1 0 000-1.962l-1.192-.238a1 1 0 01-.785-.785l-.238-1.192z"/>'
        '<path d="M6.949 5.684a1 1 0 00-1.898 0l-.683 2.051'
        "a1 1 0 01-.633.633l-2.051.683a1 1 0 000 1.898l2.051.684"
        "a1 1 0 01.633.632l.683 2.051a1 1 0 001.898 0l.683-2.051"
        "a1 1 0 01.633-.633l2.051-.683a1 1 0 000-1.898l-2.051-.683"
        'a1 1 0 01-.633-.633L6.95 5.684z"/>'
    ),
    "invocation": (
        # sun (summoning / calling)
        '<path d="M10 2a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0V2.75A.75.75 0 0110 2z'
        "m0 13a.75.75 0 01.75.75v1.5a.75.75 0 01-1.5 0v-1.5A.75.75 0 0110 15z"
        "m-8-5a.75.75 0 01.75-.75h1.5a.75.75 0 010 1.5H2.75A.75.75 0 012 10z"
        "m13 0a.75.75 0 01.75-.75h1.5a.75.75 0 010 1.5h-1.5A.75.75 0 0115 10z"
        "M4.1 4.1a.75.75 0 011.06 0l1.062 1.06A.75.75 0 115.16 6.22L4.1 5.16a.75.75 0 010-1.06z"
        "m9.68 9.68a.75.75 0 011.06 0l1.06 1.06a.75.75 0 01-1.06 1.06l-1.06-1.06a.75.75 0 010-1.06z"
        "M4.1 15.9a.75.75 0 010-1.06l1.06-1.06a.75.75 0 011.06 1.06L5.16 15.9a.75.75 0 01-1.06 0z"
        "m9.68-9.68a.75.75 0 010-1.06l1.06-1.06a.75.75 0 011.06 1.06l-1.06 1.06a.75.75 0 01-1.06 0z"
        'M10 7a3 3 0 100 6 3 3 0 000-6z"/>'
    ),
    "nécromancie": (
        # moon
        '<path d="M7.455 2.004a.75.75 0 01.26.77 7 7 0 009.958 7.967'
        '.75.75 0 011.067.853A8.5 8.5 0 116.647 1.921a.75.75 0 01.808.083z"/>'
    ),
    "transmutation": (
        # arrow-path (cycle / transform)
        '<path d="M7.793 2.232a.75.75 0 01-.025 1.06L3.622 7.25h10.003'
        "a5.375 5.375 0 010 10.75H10a.75.75 0 010-1.5h3.625a3.875 3.875 0 000-7.75H3.622"
        "l4.146 3.957a.75.75 0 01-1.036 1.085l-5.5-5.25a.75.75 0 010-1.085l5.5-5.25"
        'a.75.75 0 011.06.025z"/>'
    ),
    "universel": (
        # star
        '<path fill-rule="evenodd" clip-rule="evenodd"'
        ' d="M10.868 2.884c-.321-.772-1.415-.772-1.736 0l-1.83 4.401-4.753.381'
        "c-.833.067-1.171 1.107-.536 1.651l3.62 3.102-1.106 4.637"
        "c-.194.813.691 1.456 1.405 1.02L10 15.591l4.069 2.485"
        'c.713.436 1.598-.207 1.404-1.02l-1.106-4.637 3.62-3.102'
        'c.635-.544.297-1.584-.536-1.65l-4.752-.382-1.831-4.401z"/>'
    ),
}


def school_icon_html(school: str, css_class: str = "w-3.5 h-3.5 inline-block",
                     extra_style: str = "vertical-align:middle") -> str:
    """Retourne un élément <svg> inline pour l'école donnée, ou '' si inconnue."""
    inner = SCHOOL_ICONS.get(school.lower(), "")
    if not inner:
        return ""
    style_attr = f' style="{extra_style}"' if extra_style else ""
    class_attr = f' class="{css_class}"' if css_class else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"'
        f' fill="currentColor"{class_attr}{style_attr}'
        f' aria-hidden="true">{inner}</svg>'
    )

KNOWN_CLASSES: list[str] = [
    "alchimiste",
    "antipaladin",
    "barde",
    "druide",
    "ensorceleur",
    "inquisiteur",
    "invocateur",
    "magicien",
    "magus",
    "oracle",
    "paladin",
    "prêtre",
    "rôdeur",
    "sorcière",
]

KNOWN_SCHOOLS: list[str] = sorted(SCHOOL_COLORS.keys())

CLASS_ABBREV: dict[str, str] = {
    "alchimiste": "Alc",
    "antipaladin": "Ant",
    "barde": "Bar",
    "druide": "Dru",
    "ensorceleur": "Ens",
    "inquisiteur": "Inq",
    "invocateur": "Inv",
    "magicien": "Mag",
    "magus": "Mgus",
    "oracle": "Ora",
    "paladin": "Pal",
    "prêtre": "Prê",
    "rôdeur": "Rôd",
    "sorcière": "Sor",
}

# ── Connexion ─────────────────────────────────────────────────────────────────
def _db_path() -> Path:
    raw = settings.database_url.replace("sqlite:///", "")
    return Path(raw)


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schéma ────────────────────────────────────────────────────────────────────
def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS spells (
                id               INTEGER PRIMARY KEY,
                slug_fr          TEXT UNIQUE NOT NULL,
                name_fr          TEXT NOT NULL,
                name_en          TEXT,
                school           TEXT NOT NULL,
                subschool        TEXT,
                descriptors      TEXT,
                level_json       TEXT NOT NULL DEFAULT '{}',
                casting_time     TEXT,
                components       TEXT,
                spell_range      TEXT,
                target           TEXT,
                area             TEXT,
                duration         TEXT,
                saving_throw     TEXT,
                spell_resistance TEXT,
                description_fr   TEXT NOT NULL DEFAULT '',
                description_en   TEXT,
                source           TEXT,
                raw_url          TEXT,
                is_ogl           INTEGER DEFAULT 1,
                updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_school  ON spells(school);
            CREATE INDEX IF NOT EXISTS idx_name_fr ON spells(name_fr COLLATE NOCASE);
            CREATE INDEX IF NOT EXISTS idx_is_ogl  ON spells(is_ogl);

            CREATE TABLE IF NOT EXISTS spell_overrides (
                slug_fr    TEXT PRIMARY KEY REFERENCES spells(slug_fr) ON DELETE CASCADE,
                overrides  TEXT NOT NULL DEFAULT '{}',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)


# ── Compteurs ─────────────────────────────────────────────────────────────────
def spell_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM spells").fetchone()
        return row[0] if row else 0


def get_distinct_schools() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT school FROM spells WHERE is_ogl=1 ORDER BY school"
        ).fetchall()
    return [r[0] for r in rows]


def get_distinct_classes() -> list[str]:
    """Retourne toutes les classes présentes dans au moins un sort."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT je.key FROM spells, json_each(level_json) je WHERE is_ogl=1"
        ).fetchall()
    return sorted(r[0] for r in rows)


# ── Liste avec filtres ────────────────────────────────────────────────────────
_CLASS_NAME_RE = re.compile(r"^[a-zéèêëàâùûüîïôœæç\-]+$")


def list_spells(
    class_name: str | None = None,
    level: int | None = None,
    school: str | None = None,
    q: str | None = None,
    page: int = 1,
    per_page: int = 24,
) -> tuple[list[sqlite3.Row], int]:
    conditions: list[str] = ["is_ogl = 1"]
    params: list = []

    # Filtre par classe ± niveau
    if class_name and _CLASS_NAME_RE.match(class_name):
        json_path = f"$.{class_name}"
        if level is not None and 0 <= level <= 9:
            conditions.append("CAST(json_extract(level_json, ?) AS INTEGER) = ?")
            params.extend([json_path, level])
        else:
            conditions.append("json_extract(level_json, ?) IS NOT NULL")
            params.append(json_path)
    elif level is not None and 0 <= level <= 9:
        # Niveau seul : n'importe quelle classe à ce niveau
        conditions.append(
            "EXISTS (SELECT 1 FROM json_each(level_json) WHERE CAST(value AS INTEGER) = ?)"
        )
        params.append(level)

    if school:
        conditions.append("school = ?")
        params.append(school)

    if q and q.strip():
        conditions.append("name_fr LIKE ?")
        params.append(f"%{q.strip()}%")

    where = " AND ".join(conditions)
    offset = (page - 1) * per_page

    with get_conn() as conn:
        total: int = conn.execute(
            f"SELECT COUNT(*) FROM spells WHERE {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""
            SELECT id, slug_fr, name_fr, school, subschool, descriptors,
                   level_json, components, casting_time, spell_range,
                   duration, is_ogl, source
            FROM spells
            WHERE {where}
            ORDER BY name_fr COLLATE NOCASE
            LIMIT ? OFFSET ?
            """,
            params + [per_page, offset],
        ).fetchall()

    return list(rows), total


def last_ingest_time() -> str | None:
    """Retourne le timestamp ISO de la dernière mise à jour en base."""
    with get_conn() as conn:
        row = conn.execute("SELECT MAX(updated_at) FROM spells").fetchone()
    return row[0] if row and row[0] else None


def get_spell(slug: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM spells WHERE slug_fr = ? AND is_ogl = 1", (slug,)
        ).fetchone()


# ── Overrides ─────────────────────────────────────────────────────────────────
OVERRIDE_ALLOWED: frozenset[str] = frozenset({
    "name_fr", "school", "subschool", "descriptors",
    "casting_time", "components", "spell_range",
    "target", "area", "duration", "saving_throw",
    "spell_resistance", "description_fr",
})


def get_overrides(slug: str) -> dict:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT overrides FROM spell_overrides WHERE slug_fr = ?", (slug,)
        ).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0]) or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def save_overrides(slug: str, overrides: dict) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO spell_overrides (slug_fr, overrides, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(slug_fr) DO UPDATE SET
                 overrides  = excluded.overrides,
                 updated_at = CURRENT_TIMESTAMP""",
            (slug, json.dumps(overrides, ensure_ascii=False)),
        )


def clear_overrides(slug: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM spell_overrides WHERE slug_fr = ?", (slug,))


def apply_overrides(spell: "sqlite3.Row | dict", overrides: dict) -> dict:
    """Fusionne les corrections utilisateur sur un dict de sort."""
    result = dict(spell)
    result.update(overrides)
    return result


# ── Helpers template ──────────────────────────────────────────────────────────
def format_levels(level_json_str: str) -> str:
    """Formate le JSON de niveaux en texte lisible : 'Ens/Mag 3, Bar 3'."""
    try:
        levels: dict[str, int] = json.loads(level_json_str or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""

    by_level: dict[int, list[str]] = {}
    for cls, lvl in levels.items():
        by_level.setdefault(lvl, []).append(cls)

    parts = []
    for lvl, classes in sorted(by_level.items()):
        abbrevs = "/".join(
            CLASS_ABBREV.get(c, c[:3].capitalize()) for c in sorted(classes)
        )
        parts.append(f"{abbrevs} {lvl}")

    return ", ".join(parts)
