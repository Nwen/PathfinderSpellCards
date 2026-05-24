"""Route PDF : génère une carte de sort 63×88mm via WeasyPrint."""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, Response
from fastapi.templating import Jinja2Templates

from src import db

log = logging.getLogger(__name__)
router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
_templates.env.filters["school_color"] = lambda s: db.SCHOOL_COLORS.get(s, "#888")
_templates.env.filters["school_icon"] = lambda s: db.school_icon_html(
    s, css_class="", extra_style="width:5pt;height:5pt;vertical-align:middle"
)
_templates.env.filters["format_levels"] = db.format_levels

# Capacité estimée : nombre de caractères confortables à 6pt dans la zone description.
# chars_capacity ∝ 1/font_size², donc font_size = BASE_PT × sqrt(BASE_CHARS / n).
_BASE_FONT_PT = 6.0
_BASE_CHARS = 700
_MIN_FONT_PT = 3.5

_VALID_THEMES = frozenset({"sobre", "parchemin"})


def _validate_theme(theme: str) -> str:
    return theme if theme in _VALID_THEMES else "sobre"


def _description_font_pt(text: str) -> str:
    """Calcule la taille de police (en pt) qui fait tenir la description sur une carte."""
    n = len(text or "")
    if n <= _BASE_CHARS:
        return f"{_BASE_FONT_PT}pt"
    pt = _BASE_FONT_PT * math.sqrt(_BASE_CHARS / n)
    pt = max(_MIN_FONT_PT, round(pt, 2))
    return f"{pt}pt"


def _prepare_spell(row) -> dict:
    spell = dict(row)
    try:
        spell["levels"] = json.loads(spell.get("level_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        spell["levels"] = {}
    return spell


def _render_card_html(spell: dict, theme: str = "sobre") -> str:
    return _templates.env.get_template("card/card.html.j2").render(
        spell=spell,
        desc_font_size=_description_font_pt(spell.get("description_fr", "")),
        theme=theme,
    )


def _html_to_pdf(html: str) -> bytes:
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise RuntimeError(
            "WeasyPrint nécessite les bibliothèques système GTK3/Pango "
            "(libgobject-2.0-0). Installez-les ou utilisez Docker. "
            f"Détail : {exc}"
        ) from exc
    return HTML(string=html).write_pdf()


@router.get("/spells/{slug}/card.html", include_in_schema=False)
def spell_card_html(slug: str, theme: str = Query("sobre")):
    """Route de debug : retourne le HTML brut de la (ou des) carte(s)."""
    spell = db.get_spell(slug)
    if spell is None:
        return Response(status_code=404, content=b"Sort introuvable")
    html = _render_card_html(_prepare_spell(spell), theme=_validate_theme(theme))
    return Response(content=html.encode(), media_type="text/html; charset=utf-8")


@router.get("/spells/{slug}/card.pdf")
def spell_card_pdf(slug: str, theme: str = Query("sobre")):
    spell = db.get_spell(slug)
    if spell is None:
        return Response(status_code=404, content=b"Sort introuvable")

    html = _render_card_html(_prepare_spell(spell), theme=_validate_theme(theme))
    try:
        pdf = _html_to_pdf(html)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "PDF non disponible sur ce système",
                "detail": str(exc),
                "html_preview": f"/spells/{slug}/card.html?theme={theme}",
            },
        )

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{slug}.pdf"'},
    )
