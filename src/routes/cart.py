"""Routes panier : page /cart et planche A4 /sheet.{html,pdf}."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from src import db
from src.routes.card import _description_font_pt, _html_to_pdf, _validate_theme

log = logging.getLogger(__name__)
router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
_templates.env.filters["school_color"] = lambda s: db.SCHOOL_COLORS.get(s, "#888")
_templates.env.filters["format_levels"] = db.format_levels


def _prepare_spell(row) -> dict:
    spell = dict(row)
    try:
        spell["levels"] = json.loads(spell.get("level_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        spell["levels"] = {}
    return spell


def _slugs_from_param(slugs_param: str) -> list[str]:
    return [s.strip() for s in slugs_param.split(",") if s.strip()]


def _render_sheet_html(spells: list[dict], theme: str = "sobre") -> str:
    return _templates.env.get_template("card/sheet.html.j2").render(
        spells=spells,
        desc_font_pt=_description_font_pt,
        theme=theme,
    )


@router.get("/cart", response_class=HTMLResponse)
def cart_page(request: Request):
    return _templates.TemplateResponse(request, "cart/cart.html.j2", {})


@router.get("/sheet.html", include_in_schema=False)
def spell_sheet_html(slugs: str = Query(default=""), theme: str = Query("sobre")):
    slug_list = _slugs_from_param(slugs)
    if not slug_list:
        return Response(status_code=400, content="Aucun sort sélectionné".encode())
    spells = [
        _prepare_spell(row)
        for slug in slug_list
        if (row := db.get_spell(slug)) is not None
    ]
    if not spells:
        return Response(status_code=404, content="Aucun sort trouvé".encode())
    html = _render_sheet_html(spells, theme=_validate_theme(theme))
    return Response(content=html.encode(), media_type="text/html; charset=utf-8")


@router.get("/sheet.pdf")
def spell_sheet_pdf(slugs: str = Query(default=""), theme: str = Query("sobre")):
    slug_list = _slugs_from_param(slugs)
    if not slug_list:
        return JSONResponse(status_code=400, content={"error": "Aucun sort sélectionné"})
    spells = [
        _prepare_spell(row)
        for slug in slug_list
        if (row := db.get_spell(slug)) is not None
    ]
    if not spells:
        return JSONResponse(status_code=404, content={"error": "Aucun sort trouvé"})
    validated = _validate_theme(theme)
    html = _render_sheet_html(spells, theme=validated)
    try:
        pdf = _html_to_pdf(html)
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={
                "error": "PDF non disponible sur ce système",
                "detail": str(exc),
                "html_preview": f"/sheet.html?slugs={slugs}&theme={validated}",
            },
        )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="planche.pdf"'},
    )
