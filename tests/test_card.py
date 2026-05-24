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


# ── Pagination (aucune dépendance WeasyPrint) ─────────────────────────────────

class TestPagination:
    def test_short_description_single_page(self):
        from src.routes.card import _paginate_description
        assert _paginate_description("Court.") == ["Court."]

    def test_empty_description(self):
        from src.routes.card import _paginate_description
        assert _paginate_description("") == [""]

    def test_long_description_splits(self):
        from src.routes.card import _paginate_description, _CHARS_PAGE1
        long_text = "Lorem ipsum dolor sit amet. " * 40  # ~1 120 chars
        pages = _paginate_description(long_text)
        assert len(pages) >= 2

    def test_splits_at_paragraph_boundary(self):
        from src.routes.card import _paginate_description, _CHARS_PAGE1
        # Construit un texte avec une frontière de paragraphe avant la limite
        para1 = "A" * 500
        para2 = "B" * 500
        text = para1 + "\n\n" + para2
        pages = _paginate_description(text)
        assert len(pages) == 2
        assert pages[0] == para1
        assert pages[1] == para2

    def test_all_text_preserved(self):
        from src.routes.card import _paginate_description
        long_text = ("Mot " * 300).strip()
        pages = _paginate_description(long_text)
        rejoined = " ".join(p.replace("\n\n", " ").strip() for p in pages)
        # Tous les mots originaux sont présents (peut y avoir des espaces différents)
        for word in long_text.split()[:20]:
            assert word in rejoined


# ── HTML de carte ─────────────────────────────────────────────────────────────

class TestCardHTML:
    def test_single_card_for_short_spell(self, patch_db):
        from tests.conftest import FIREBALL
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
        upsert_spells([FIREBALL])
        html = _render_card_html(_spell_dict("boule-de-feu"))
        assert html.count('class="card"') == 1

    def test_multiple_cards_for_long_spell(self, patch_db):
        from src.ingest.parser_fr import SpellData
        from src.ingest.populate import upsert_spells
        from src.routes.card import _render_card_html
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
        assert html.count('class="card"') >= 2

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
