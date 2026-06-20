"""Routes de navigation : liste paginée + fiche détail.

Note API : Starlette 1.0.x — signature TemplateResponse(request, name, context).
Le dict context ne doit PAS inclure 'request' (géré en premier argument).
"""
from __future__ import annotations

import html as _html_stdlib
import json
import re as _re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src import db

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_TABLE_SPLIT_RE = _re.compile(r"(<table[\s\S]*?</table>)", _re.IGNORECASE)


def _desc_html(text: str) -> str:
    """Prépare une description pour le rendu HTML.

    Les blocs <table> (issus des tableaux wiki) sont conservés tels quels.
    Le reste est échappé et les sauts de ligne convertis en <br>.
    """
    if not text:
        return ""
    parts = _TABLE_SPLIT_RE.split(text)
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2 == 0:  # texte brut
            escaped = _html_stdlib.escape(part)
            escaped = escaped.replace("\n\n", "<br><br>").replace("\n", " ")
            out.append(escaped)
        else:  # bloc <table>
            out.append(part)
    return "".join(out)


# ── Filtres Jinja2 (ne brisent pas le cache LRU Jinja2 3.1.2+) ───────────────
templates.env.filters["school_color"] = lambda s: db.SCHOOL_COLORS.get(s, "#888")
templates.env.filters["school_icon"] = lambda s: db.school_icon_html(s)
templates.env.filters["format_levels"] = db.format_levels
templates.env.filters["jsonparse"] = json.loads
templates.env.filters["urlencode_filters"] = lambda f: urlencode(
    {k: v for k, v in f.items() if v != "" and v is not None}
)
templates.env.filters["desc_html"] = _desc_html


def _ctx(**kwargs) -> dict:
    """Contexte de base commun (sans 'request' — passé en 1er arg Starlette 1.0)."""
    return {
        "known_classes": db.KNOWN_CLASSES,
        "known_schools": db.KNOWN_SCHOOLS,
        **kwargs,
    }


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "browse/list.html.j2",
        _ctx(
            spells=[],
            total=0,
            page=1,
            per_page=24,
            pages=1,
            filters={"classe": "", "level": "", "school": "", "q": ""},
            db_empty=db.spell_count() == 0,
        ),
    )


@router.get("/spells", response_class=HTMLResponse)
def spell_list(
    request: Request,
    classe: str | None = Query(None),
    level: int | None = Query(None, ge=0, le=9),
    school: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
):
    per_page = 24
    spells, total = db.list_spells(
        class_name=classe,
        level=level,
        school=school,
        q=q,
        page=page,
        per_page=per_page,
    )

    ctx = _ctx(
        spells=spells,
        total=total,
        page=page,
        per_page=per_page,
        pages=max(1, (total + per_page - 1) // per_page),
        filters={
            "classe": classe or "",
            "level": level if level is not None else "",
            "school": school or "",
            "q": q or "",
        },
        db_empty=db.spell_count() == 0,
    )

    tpl = "browse/_items.html.j2" if _is_htmx(request) else "browse/list.html.j2"
    return templates.TemplateResponse(request, tpl, ctx)


@router.get("/spells/{slug}", response_class=HTMLResponse)
def spell_detail(request: Request, slug: str):
    raw = db.get_spell(slug)
    if raw is None:
        return templates.TemplateResponse(
            request, "404.html.j2", _ctx(), status_code=404
        )

    original = dict(raw)
    try:
        original["levels"] = json.loads(original.get("level_json") or "{}")
    except (json.JSONDecodeError, TypeError):
        original["levels"] = {}

    active_overrides = db.get_overrides(slug)
    spell_dict = db.apply_overrides(original, active_overrides)
    spell_dict["levels"] = original["levels"]   # levels always from DB level_json

    return templates.TemplateResponse(
        request, "browse/detail.html.j2",
        _ctx(spell=spell_dict, original_spell=original, active_overrides=active_overrides),
    )
