"""Fixtures partagées — isolation de la DB SQLite par test."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from src.ingest.parser_fr import SpellData


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test_spells.db"


@pytest.fixture()
def patch_db(db_path, monkeypatch):
    """Redirige _db_path() vers un fichier temporaire, initialise le schéma."""
    import src.db as db_mod
    monkeypatch.setattr(db_mod, "_db_path", lambda: db_path)
    db_mod.init_db()
    return db_mod


@pytest.fixture()
def client(patch_db):
    """TestClient FastAPI avec la DB isolée."""
    from src.main import app
    return TestClient(app, raise_server_exceptions=True)


FIREBALL = SpellData(
    title="Pathfinder-RPG.Boule de feu",
    name_fr="Boule de feu",
    slug_fr="boule-de-feu",
    school="évocation",
    subschool=None,
    descriptors="feu",
    level_json={"ensorceleur": 3, "magicien": 3, "barde": 3},
    casting_time="1 action simple",
    components="V, G",
    spell_range="longue (120 m + 12 m/niveau)",
    target=None,
    area="boule de feu de 6 m de rayon",
    duration="instantanée",
    saving_throw="Réflexes, 1/2 dégâts",
    spell_resistance="oui",
    description_fr="Une boule de feu jaillit du bout du doigt du personnage.",
    source="MJ",
    raw_url="http://www.pathfinder-fr.org/Wiki/Pathfinder-RPG.Boule de feu.ashx",
)

WISH = SpellData(
    title="Pathfinder-RPG.Souhait",
    name_fr="Souhait",
    slug_fr="souhait",
    school="universel",
    subschool=None,
    descriptors=None,
    level_json={"ensorceleur": 9, "magicien": 9},
    casting_time="1 action simple",
    components="V",
    spell_range="illimitée",
    target="voir description",
    area=None,
    duration="voir description",
    saving_throw="aucun",
    spell_resistance="oui",
    description_fr="Le sort le plus puissant disponible.",
    source="MJ",
    raw_url=None,
)

CURE = SpellData(
    title="Pathfinder-RPG.Soins legers",
    name_fr="Soins légers",
    slug_fr="soins-legers",
    school="invocation",
    subschool="guérison",
    descriptors=None,
    level_json={"prêtre": 1, "barde": 1, "paladin": 1},
    casting_time="1 action simple",
    components="V, G",
    spell_range="contact",
    target="une créature",
    area=None,
    duration="instantanée",
    saving_throw="Vigueur pour la moitié (inoffensif)",
    spell_resistance="oui (inoffensif)",
    description_fr="Ce sort soigne 1d8 points de dégâts + 1/niveau.",
    source="MJ",
    raw_url=None,
)


@pytest.fixture()
def populated_db(patch_db):
    """DB avec 3 sorts de test insérés."""
    from src.ingest.populate import upsert_spells
    upsert_spells([FIREBALL, WISH, CURE])
    return patch_db


@pytest.fixture()
def populated_client(populated_db):
    from src.main import app
    return TestClient(app, raise_server_exceptions=True)
