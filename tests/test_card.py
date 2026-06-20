"""Tests de la route PDF /spells/{slug}/card.pdf (iter 3 + 4)."""
from __future__ import annotations

import pytest

# WeasyPrint nécessite libgobject (GTK3) — absent sur Windows sans GTK.
# Les tests PDF sont sautés si les libs système manquent ; ils passent en Docker.
def _weasyprint_available() -> bool:
    try:
        from weasyprint import HTML
        HTML(string="<p>x</p>").write_pdf()
        return True
    except Exception:
        return False

_HAS_WEASYPRINT = _weasyprint_available()
needs_weasyprint = pytest.mark.skipif(
    not _HAS_WEASYPRINT,
    reason="WeasyPrint system libs (GTK3/libgobject) non disponibles",
)


# ── Helper ────────────────────────────────────────────────────────────────────

def _spell_dict(slug: str):
    import json
    from src import db
    row = db.get_spell(slug)
    assert row is not None, f"Sort {slug!r} absent de la DB de test"
    spell = dict(row)
    spell["levels"] = json.loads(spell.get("level_json") or "{}")
    return spell


# ── Calcul de taille de police (aucune dépendance WeasyPrint) ────────────────

class TestFontScaling:
    def test_short_description_uses_base_size(self):
        from src.routes.card import _description_font_pt, _BASE_FONT_PT
        assert _description_font_pt("Court.") == f"{_BASE_FONT_PT}pt"

    def test_empty_description_uses_base_size(self):
        from src.routes.card import _description_font_pt, _BASE_FONT_PT
        assert _description_font_pt("") == f"{_BASE_FONT_PT}pt"

    def test_at_threshold_uses_base_size(self):
        from src.routes.card import _description_font_pt, _BASE_FONT_PT, _BASE_CHARS
        assert _description_font_pt("x" * _BASE_CHARS) == f"{_BASE_FONT_PT}pt"

    def test_long_description_shrinks_font(self):
        from src.routes.card import _description_font_pt, _BASE_FONT_PT, _BASE_CHARS
        long_text = "x" * (_BASE_CHARS * 4)
        size = _description_font_pt(long_text)
        assert size != f"{_BASE_FONT_PT}pt"
        pt = float(size.rstrip("pt"))
        assert pt < _BASE_FONT_PT

    def test_very_long_description_clamps_to_minimum(self):
        from src.routes.card import _description_font_pt, _MIN_FONT_PT
        size = _description_font_pt("x" * 50_000)
        assert size == f"{_MIN_FONT_PT}pt"

    def test_returns_pt_string(self):
        from src.routes.card import _description_font_pt
        assert _description_font_pt("texte").endswith("pt")


# ── HTML de carte ─────────────────────────────────────────────────────────────

class TestCardHTML:
    def test_single_card_for_short_spell(self, patch_db):
        from tests.conftest import FIREBALL
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        upsert_spells([FIREBALL])
        html = _render_card_html(_spell_dict("boule-de-feu"))
        assert html.count('class="card"') == 1

    def test_long_spell_still_single_card_with_smaller_font(self, patch_db):
        from src.ingest.parser_fr import SpellData
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html, _BASE_FONT_PT
        long_desc = ("Description très longue. " * 80).strip()  # ~2 000 chars
        spell = SpellData(
            title="Sort Long",
            name_fr="Sort Long",
            slug_fr="sort-long",
            school="évocation",
            subschool=None,
            descriptors=None,
            level_json={"magicien": 5},
            casting_time="1 action",
            components="V",
            spell_range="courte",
            target="1 créature",
            area=None,
            duration="instantanée",
            saving_throw="aucun",
            spell_resistance="non",
            description_fr=long_desc,
            source=None,
            raw_url=None,
        )
        upsert_spells([spell])
        html = _render_card_html(_spell_dict("sort-long"))
        assert html.count('class="card"') == 1
        # Font size should be smaller than the base 6pt
        assert f"font-size: {_BASE_FONT_PT}pt" not in html

    def test_suite_label_present_on_continuation(self, patch_db):
        from src.ingest.parser_fr import SpellData
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        long_desc = ("Suite test. " * 100).strip()
        spell = SpellData(
            title="Sort Suite",
            name_fr="Sort Suite",
            slug_fr="sort-suite",
            school="invocation",
            subschool=None,
            descriptors=None,
            level_json={"prêtre": 3},
            casting_time="1 action",
            components="V, G",
            spell_range="contact",
            target="1 créature",
            area=None,
            duration="instantanée",
            saving_throw="aucun",
            spell_resistance="oui",
            description_fr=long_desc,
            source=None,
            raw_url=None,
        )
        upsert_spells([spell])
        html = _render_card_html(_spell_dict("sort-suite"))
        assert "suite" in html.lower()

    def test_html_contains_spell_name(self, patch_db):
        from tests.conftest import FIREBALL
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        upsert_spells([FIREBALL])
        assert "Boule de feu" in _render_card_html(_spell_dict("boule-de-feu"))

    def test_html_contains_school(self, patch_db):
        from tests.conftest import FIREBALL
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        upsert_spells([FIREBALL])
        assert "vocation" in _render_card_html(_spell_dict("boule-de-feu")).lower()

    def test_html_contains_ogl_attribution(self, patch_db):
        from tests.conftest import FIREBALL
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        upsert_spells([FIREBALL])
        html = _render_card_html(_spell_dict("boule-de-feu"))
        assert "Paizo" in html
        assert "pathfinder-fr.org" in html


# ── Routes HTTP ───────────────────────────────────────────────────────────────

class TestCardPDF:
    @needs_weasyprint
    def test_returns_pdf_content_type(self, populated_client):
        resp = populated_client.get("/spells/boule-de-feu/card.pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]

    @needs_weasyprint
    def test_pdf_magic_bytes(self, populated_client):
        assert populated_client.get("/spells/boule-de-feu/card.pdf").content[:4] == b"%PDF"

    @needs_weasyprint
    def test_pdf_has_content(self, populated_client):
        assert len(populated_client.get("/spells/boule-de-feu/card.pdf").content) > 1024

    @needs_weasyprint
    def test_content_disposition_inline(self, populated_client):
        cd = populated_client.get("/spells/boule-de-feu/card.pdf").headers.get("content-disposition", "")
        assert "inline" in cd and "boule-de-feu.pdf" in cd

    def test_not_found_returns_404(self, populated_client):
        assert populated_client.get("/spells/sort-inexistant/card.pdf").status_code == 404

    @needs_weasyprint
    def test_wish_card(self, populated_client):
        resp = populated_client.get("/spells/souhait/card.pdf")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

    @needs_weasyprint
    def test_cure_card(self, populated_client):
        resp = populated_client.get("/spells/soins-legers/card.pdf")
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"
