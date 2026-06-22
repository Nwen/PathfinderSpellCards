"""Routes CRUD pour les sorts personnalisés."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src import db

router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
_templates.env.filters["school_color"] = lambda s: db.SCHOOL_COLORS.get(s, "#888")


def _form_data(form) -> dict:
    """Extrait et valide les champs d'un FormData."""
    level_json = form.get("level_json", "{}")
    try:
        json.loads(level_json)
    except (json.JSONDecodeError, TypeError):
        level_json = "{}"
    return {
        "name_fr":          (form.get("name_fr",          "") or "").strip(),
        "school":           (form.get("school",           "") or "").strip(),
        "subschool":        (form.get("subschool",        "") or "").strip(),
        "descriptors":      (form.get("descriptors",      "") or "").strip(),
        "level_json":       level_json,
        "casting_time":     (form.get("casting_time",     "") or "").strip(),
        "components":       (form.get("components",       "") or "").strip(),
        "spell_range":      (form.get("spell_range",      "") or "").strip(),
        "target":           (form.get("target",           "") or "").strip(),
        "area":             (form.get("area",             "") or "").strip(),
        "duration":         (form.get("duration",         "") or "").strip(),
        "saving_throw":     (form.get("saving_throw",     "") or "").strip(),
        "spell_resistance": (form.get("spell_resistance", "") or "").strip(),
        "description_fr":   (form.get("description_fr",  "") or "").strip(),
    }


def _form_ctx(spell, action: str, error: str = "") -> dict:
    return {
        "spell":         spell,
        "known_schools": db.KNOWN_SCHOOLS,
        "known_classes": db.KNOWN_CLASSES,
        "action":        action,
        "error":         error,
    }


@router.get("/spells/new", response_class=HTMLResponse)
def new_spell_form(request: Request):
    return _templates.TemplateResponse(
        request, "custom/spell_form.html.j2", _form_ctx(None, "/spells/new")
    )


@router.post("/spells/new")
async def create_spell(request: Request):
    data = _form_data(await request.form())
    if not data["name_fr"] or not data["school"]:
        return _templates.TemplateResponse(
            request, "custom/spell_form.html.j2",
            _form_ctx(data, "/spells/new", "Le nom et l'école sont obligatoires."),
            status_code=422,
        )
    slug = db.create_custom_spell(data)
    return RedirectResponse(url=f"/spells/{slug}", status_code=303)


@router.get("/spells/{slug}/edit", response_class=HTMLResponse)
def edit_spell_form(request: Request, slug: str):
    raw = db.get_spell(slug)
    if raw is None or not raw["is_custom"]:
        return _templates.TemplateResponse(request, "404.html.j2", {}, status_code=404)
    spell = dict(raw)
    spell["levels"] = json.loads(spell.get("level_json") or "{}")
    return _templates.TemplateResponse(
        request, "custom/spell_form.html.j2",
        _form_ctx(spell, f"/spells/{slug}/edit"),
    )


@router.post("/spells/{slug}/edit")
async def update_spell(request: Request, slug: str):
    raw = db.get_spell(slug)
    if raw is None or not raw["is_custom"]:
        return JSONResponse(status_code=404, content={"error": "Sort introuvable"})
    data = _form_data(await request.form())
    if not data["name_fr"] or not data["school"]:
        spell = {**dict(raw), **data}
        spell["levels"] = json.loads(data["level_json"] or "{}")
        return _templates.TemplateResponse(
            request, "custom/spell_form.html.j2",
            _form_ctx(spell, f"/spells/{slug}/edit", "Le nom et l'école sont obligatoires."),
            status_code=422,
        )
    db.update_custom_spell(slug, data)
    return RedirectResponse(url=f"/spells/{slug}", status_code=303)


@router.delete("/spells/{slug}")
def delete_spell(slug: str):
    raw = db.get_spell(slug)
    if raw is None or not raw["is_custom"]:
        return JSONResponse(status_code=404, content={"error": "Sort introuvable ou non supprimable"})
    db.delete_custom_spell(slug)
    return JSONResponse({"ok": True})
