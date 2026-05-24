"""Tests des routes de navigation (liste + détail)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── Tests : /health ───────────────────────────────────────────────────────────

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_spell_count_empty(self, client):
        resp = client.get("/health")
        assert resp.json()["spells_indexed"] == 0

    def test_health_spell_count_populated(self, populated_client):
        resp = populated_client.get("/health")
        assert resp.json()["spells_indexed"] == 3


# ── Tests : liste /spells ─────────────────────────────────────────────────────

class TestSpellList:
    def test_empty_db_shows_warning(self, client):
        resp = client.get("/spells")
        assert resp.status_code == 200
        assert "Base de données vide" in resp.text or "make ingest" in resp.text

    def test_list_returns_200(self, populated_client):
        resp = populated_client.get("/spells")
        assert resp.status_code == 200
        assert "Boule de feu" in resp.text

    def test_filter_by_school(self, populated_client):
        resp = populated_client.get("/spells?school=évocation")
        assert resp.status_code == 200
        assert "Boule de feu" in resp.text
        assert "Souhait" not in resp.text

    def test_filter_by_class(self, populated_client):
        resp = populated_client.get("/spells?classe=prêtre")
        assert resp.status_code == 200
        assert "Soins" in resp.text
        assert "Boule de feu" not in resp.text

    def test_filter_by_class_and_level(self, populated_client):
        resp = populated_client.get("/spells?classe=magicien&level=3")
        assert resp.status_code == 200
        assert "Boule de feu" in resp.text
        assert "Souhait" not in resp.text

    def test_filter_by_level_only(self, populated_client):
        resp = populated_client.get("/spells?level=9")
        assert resp.status_code == 200
        assert "Souhait" in resp.text
        assert "Soins" not in resp.text

    def test_search(self, populated_client):
        resp = populated_client.get("/spells?q=souhait")
        assert resp.status_code == 200
        assert "Souhait" in resp.text
        assert "Boule de feu" not in resp.text

    def test_htmx_returns_no_html_tag(self, populated_client):
        resp = populated_client.get("/spells", headers={"HX-Request": "true"})
        assert resp.status_code == 200
        assert "<html" not in resp.text
        assert "Boule de feu" in resp.text

    def test_no_filter_returns_all(self, populated_client):
        resp = populated_client.get("/spells")
        assert "Boule de feu" in resp.text
        assert "Souhait" in resp.text
        assert "Soins" in resp.text


# ── Tests : détail /spells/{slug} ─────────────────────────────────────────────

class TestSpellDetail:
    def test_found(self, populated_client):
        resp = populated_client.get("/spells/boule-de-feu")
        assert resp.status_code == 200
        assert "Boule de feu" in resp.text

    def test_shows_school(self, populated_client):
        resp = populated_client.get("/spells/boule-de-feu")
        assert "vocation" in resp.text.lower()  # évocation

    def test_shows_description(self, populated_client):
        resp = populated_client.get("/spells/boule-de-feu")
        assert "boule de feu" in resp.text.lower()

    def test_shows_levels(self, populated_client):
        resp = populated_client.get("/spells/boule-de-feu")
        assert "3" in resp.text  # level 3

    def test_not_found_returns_404(self, populated_client):
        resp = populated_client.get("/spells/sort-inexistant")
        assert resp.status_code == 404

    def test_wish_detail(self, populated_client):
        resp = populated_client.get("/spells/souhait")
        assert resp.status_code == 200
        assert "Souhait" in resp.text
        assert "universel" in resp.text.lower()


# ── Tests : helpers DB ────────────────────────────────────────────────────────

class TestDBHelpers:
    def test_format_levels_ens_mag(self):
        from src.db import format_levels
        result = format_levels('{"magicien": 3, "ensorceleur": 3}')
        assert "3" in result
        # Les deux classes au même niveau → groupées
        assert "/" in result or ("Ens" in result and "Mag" in result)

    def test_format_levels_multi_level(self):
        from src.db import format_levels
        result = format_levels('{"barde": 1, "magicien": 3}')
        assert "1" in result
        assert "3" in result

    def test_format_levels_empty(self):
        from src.db import format_levels
        assert format_levels("{}") == ""
        assert format_levels("") == ""

    def test_list_spells_filter_class(self, patch_db):
        from src.ingest.populate import upsert_spells
        from tests.conftest import FIREBALL, WISH, CURE
        upsert_spells([FIREBALL, WISH, CURE])

        rows, total = patch_db.list_spells(class_name="magicien")
        # FIREBALL (Mag 3) et WISH (Mag 9) ont magicien — CURE non
        assert total == 2
        names = [r["name_fr"] for r in rows]
        assert "Boule de feu" in names
        assert "Souhait" in names
        assert "Soins légers" not in names

    def test_list_spells_filter_school(self, patch_db):
        from src.ingest.populate import upsert_spells
        from tests.conftest import FIREBALL, WISH, CURE
        upsert_spells([FIREBALL, WISH, CURE])

        rows, total = patch_db.list_spells(school="universel")
        assert total == 1
        assert rows[0]["name_fr"] == "Souhait"

    def test_list_spells_filter_level(self, patch_db):
        from src.ingest.populate import upsert_spells
        from tests.conftest import FIREBALL, WISH, CURE
        upsert_spells([FIREBALL, WISH, CURE])

        rows, total = patch_db.list_spells(level=9)
        assert total == 1
        assert rows[0]["name_fr"] == "Souhait"

    def test_get_spell(self, patch_db):
        from src.ingest.populate import upsert_spells
        from tests.conftest import FIREBALL
        upsert_spells([FIREBALL])

        spell = patch_db.get_spell("boule-de-feu")
        assert spell is not None
        assert spell["name_fr"] == "Boule de feu"

    def test_get_spell_missing(self, patch_db):
        assert patch_db.get_spell("inexistant") is None
