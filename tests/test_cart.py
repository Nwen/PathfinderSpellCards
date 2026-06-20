"""Tests des routes /cart, /sheet.html et /sheet.pdf (itération 5)."""
from __future__ import annotations

import pytest

# Réutilise le marker WeasyPrint défini dans test_card
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


# ── Page panier ───────────────────────────────────────────────────────────────

class TestCartPage:
    def test_cart_page_returns_200(self, client):
        assert client.get("/cart").status_code == 200

    def test_cart_page_has_html(self, client):
        r = client.get("/cart")
        assert "planche" in r.text.lower()

    def test_cart_page_has_cart_js(self, client):
        r = client.get("/cart")
        assert "localStorage" in r.text or "pf-cart" in r.text


# ── Sheet HTML ────────────────────────────────────────────────────────────────

class TestSheetHTML:
    def test_no_slugs_returns_400(self, client):
        assert client.get("/sheet.html").status_code == 400

    def test_empty_slugs_returns_400(self, client):
        assert client.get("/sheet.html?slugs=").status_code == 400

    def test_unknown_slug_returns_404(self, client):
        assert client.get("/sheet.html?slugs=sort-inexistant").status_code == 404

    def test_single_spell_renders(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        assert r.status_code == 200
        assert "Boule de feu" in r.text

    def test_multiple_spells_render(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu,souhait,soins-legers")
        assert r.status_code == 200
        assert "Boule de feu" in r.text
        assert "Souhait" in r.text
        assert "Soins" in r.text

    def test_invalid_slug_filtered_valid_returned(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu,sort-inexistant")
        assert r.status_code == 200
        assert "Boule de feu" in r.text

    def test_ogl_attribution_present(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        assert "Paizo" in r.text
        assert "pathfinder-fr.org" in r.text

    def test_three_spells_three_cards(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu,souhait,soins-legers")
        assert r.text.count('class="card"') == 3

    def test_single_spell_one_card(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        assert r.text.count('class="card"') == 1

    def test_sheet_grid_present(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        assert 'class="sheet"' in r.text

    def test_school_color_inline(self, populated_client):
        r = populated_client.get("/sheet.html?slugs=boule-de-feu")
        # évocation → #e06030, couleur inlinée sur color-bar et school-badge
        assert "#e06030" in r.text


# ── Sheet PDF ─────────────────────────────────────────────────────────────────

class TestSheetPDF:
    def test_no_slugs_returns_400(self, client):
        assert client.get("/sheet.pdf").status_code == 400

    def test_unknown_slug_returns_404(self, client):
        assert client.get("/sheet.pdf?slugs=sort-inexistant").status_code == 404

    def test_not_found_returns_json_error(self, client):
        r = client.get("/sheet.pdf?slugs=sort-inexistant")
        assert r.headers["content-type"].startswith("application/json")

    @needs_weasyprint
    def test_returns_pdf_content_type(self, populated_client):
        r = populated_client.get("/sheet.pdf?slugs=boule-de-feu")
        assert r.status_code == 200
        assert "application/pdf" in r.headers["content-type"]

    @needs_weasyprint
    def test_pdf_magic_bytes(self, populated_client):
        r = populated_client.get("/sheet.pdf?slugs=boule-de-feu")
        assert r.content[:4] == b"%PDF"

    @needs_weasyprint
    def test_three_spells_pdf(self, populated_client):
        r = populated_client.get("/sheet.pdf?slugs=boule-de-feu,souhait,soins-legers")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    @needs_weasyprint
    def test_content_disposition_inline(self, populated_client):
        r = populated_client.get("/sheet.pdf?slugs=boule-de-feu")
        cd = r.headers.get("content-disposition", "")
        assert "inline" in cd and "planche.pdf" in cd
