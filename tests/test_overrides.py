"""Tests pour le système de corrections (spell_overrides)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FIREBALL


# ── Helpers DB ────────────────────────────────────────────────────────────────

class TestOverrideHelpers:
    def test_get_overrides_returns_empty_when_none(self, patch_db):
        assert patch_db.get_overrides("boule-de-feu") == {}

    def test_save_and_get_overrides(self, patch_db):
        from src.ingest.populate import upsert_spells
        upsert_spells([FIREBALL])
        patch_db.save_overrides("boule-de-feu", {"name_fr": "Fireball"})
        assert patch_db.get_overrides("boule-de-feu") == {"name_fr": "Fireball"}

    def test_save_overrides_upserts(self, patch_db):
        from src.ingest.populate import upsert_spells
        upsert_spells([FIREBALL])
        patch_db.save_overrides("boule-de-feu", {"name_fr": "A"})
        patch_db.save_overrides("boule-de-feu", {"name_fr": "B", "duration": "1 round"})
        assert patch_db.get_overrides("boule-de-feu") == {"name_fr": "B", "duration": "1 round"}

    def test_clear_overrides(self, patch_db):
        from src.ingest.populate import upsert_spells
        upsert_spells([FIREBALL])
        patch_db.save_overrides("boule-de-feu", {"name_fr": "X"})
        patch_db.clear_overrides("boule-de-feu")
        assert patch_db.get_overrides("boule-de-feu") == {}

    def test_apply_overrides_merges_correctly(self, patch_db):
        base = {"name_fr": "Original", "school": "évocation", "duration": "instantanée"}
        result = patch_db.apply_overrides(base, {"name_fr": "Corrigé"})
        assert result["name_fr"] == "Corrigé"
        assert result["school"] == "évocation"    # untouched
        assert result["duration"] == "instantanée"

    def test_apply_overrides_does_not_mutate_original(self, patch_db):
        base = {"name_fr": "Original", "school": "évocation"}
        patch_db.apply_overrides(base, {"name_fr": "Corrigé"})
        assert base["name_fr"] == "Original"


# ── API routes ────────────────────────────────────────────────────────────────

class TestOverridesAPI:
    def test_get_returns_empty_dict(self, populated_client: TestClient):
        r = populated_client.get("/spells/boule-de-feu/overrides")
        assert r.status_code == 200
        assert r.json() == {}

    def test_post_saves_overrides(self, populated_client: TestClient):
        r = populated_client.post(
            "/spells/boule-de-feu/overrides",
            json={"name_fr": "Fireball", "duration": "instant"},
        )
        assert r.status_code == 200
        assert r.json() == {"ok": True}
        r2 = populated_client.get("/spells/boule-de-feu/overrides")
        assert r2.json() == {"name_fr": "Fireball", "duration": "instant"}

    def test_post_rejects_unknown_fields(self, populated_client: TestClient):
        r = populated_client.post(
            "/spells/boule-de-feu/overrides",
            json={"name_fr": "OK", "champ_inconnu": "valeur"},
        )
        assert r.status_code == 422
        assert "champ_inconnu" in r.json()["detail"]

    def test_post_returns_404_for_unknown_slug(self, populated_client: TestClient):
        r = populated_client.post(
            "/spells/sort-inexistant/overrides",
            json={"name_fr": "X"},
        )
        assert r.status_code == 404

    def test_delete_clears_overrides(self, populated_client: TestClient):
        populated_client.post(
            "/spells/boule-de-feu/overrides", json={"name_fr": "Fireball"}
        )
        r = populated_client.delete("/spells/boule-de-feu/overrides")
        assert r.status_code == 200
        assert populated_client.get("/spells/boule-de-feu/overrides").json() == {}

    def test_post_replaces_previous_overrides(self, populated_client: TestClient):
        populated_client.post("/spells/boule-de-feu/overrides", json={"name_fr": "A"})
        populated_client.post("/spells/boule-de-feu/overrides", json={"duration": "1 round"})
        # Second POST is a full replacement, so name_fr should be gone
        assert "name_fr" not in populated_client.get("/spells/boule-de-feu/overrides").json()


# ── Card rendering reflects overrides ────────────────────────────────────────

class TestOverrideInCard:
    def test_card_html_uses_overridden_name(self, populated_client: TestClient):
        populated_client.post(
            "/spells/boule-de-feu/overrides", json={"name_fr": "FIREBALL CORRIGÉ"}
        )
        r = populated_client.get("/spells/boule-de-feu/card.html")
        assert r.status_code == 200
        assert "FIREBALL CORRIGÉ" in r.text

    def test_card_html_uses_overridden_description(self, populated_client: TestClient):
        populated_client.post(
            "/spells/boule-de-feu/overrides",
            json={"description_fr": "Description corrigée pour le test."},
        )
        r = populated_client.get("/spells/boule-de-feu/card.html")
        assert r.status_code == 200
        assert "Description corrigée pour le test." in r.text

    def test_detail_page_shows_overridden_name(self, populated_client: TestClient):
        populated_client.post(
            "/spells/boule-de-feu/overrides", json={"name_fr": "Boule de Feu CORRIGÉ"}
        )
        r = populated_client.get("/spells/boule-de-feu")
        assert r.status_code == 200
        assert "Boule de Feu CORRIGÉ" in r.text
