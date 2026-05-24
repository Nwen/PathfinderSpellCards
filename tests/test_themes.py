"""Tests des thèmes CSS (sobre / parchemin) sur les routes card et sheet."""
from __future__ import annotations

import pytest


# ── Thème sur carte individuelle ──────────────────────────────────────────────

class TestCardTheme:
    def test_sobre_is_default_card(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html")
        assert r.status_code == 200
        assert "--card-bg:       #fff" in r.text

    def test_parchemin_card_background(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=parchemin")
        assert r.status_code == 200
        assert "#f5e9cc" in r.text

    def test_parchemin_card_border(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=parchemin")
        assert "#b8915a" in r.text

    def test_sobre_no_parchemin_colors(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=sobre")
        assert "#f5e9cc" not in r.text
        assert "#b8915a" not in r.text

    def test_invalid_theme_falls_back_to_sobre(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=pirate")
        assert r.status_code == 200
        assert "--card-bg:       #fff" in r.text

    def test_parchemin_card_has_spell_name(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=parchemin")
        assert "Boule de feu" in r.text

    def test_parchemin_card_ogl_attribution(self, populated_client):
        r = populated_client.get("/spells/boule-de-feu/card.html?theme=parchemin")
        assert "Paizo" in r.text


# ── Thème sur planche ─────────────────────────────────────────────────────────

class TestSheetTheme:
    def test_sobre_is_default_sheet(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        assert r.status_code == 200
        assert "--card-bg:       #fff" in r.text

    def test_parchemin_sheet_background(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu&theme=parchemin")
        assert r.status_code == 200
        assert "#f5e9cc" in r.text

    def test_parchemin_sheet_border(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu&theme=parchemin")
        assert "#b8915a" in r.text

    def test_sobre_sheet_no_parchemin_colors(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu&theme=sobre")
        assert "#f5e9cc" not in r.text

    def test_invalid_theme_sheet_falls_back(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu&theme=invalid")
        assert r.status_code == 200
        assert "--card-bg:       #fff" in r.text

    def test_parchemin_sheet_preserves_school_color(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu&theme=parchemin")
        # évocation school color is always present regardless of theme
        assert "#e06030" in r.text

    def test_parchemin_multi_spell_sheet(self, populated_client):
        r = populated_client.get(
            "/sheet.html?slugs=boule-de-feu,souhait,soins-legers&theme=parchemin"
        )
        assert r.status_code == 200
        assert r.text.count('class="card"') == 3
        assert "#f5e9cc" in r.text


# ── Cart page contient le sélecteur de thème ─────────────────────────────────

class TestCartThemeSelector:
    def test_theme_select_present(self, client):
        r = client.get("/cart")
        assert 'id="theme-select"' in r.text

    def test_theme_options_present(self, client):
        r = client.get("/cart")
        assert 'value="sobre"' in r.text
        assert 'value="parchemin"' in r.text
