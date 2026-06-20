"""Routes CRUD pour les corrections de champs de sorts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from src import db

router = APIRouter()


@router.get("/spells/{slug}/overrides")
def get_spell_overrides(slug: str) -> JSONResponse:
    return JSONResponse(db.get_overrides(slug))


@router.post("/spells/{slug}/overrides")
async def save_spell_overrides(slug: str, request: Request) -> JSONResponse:
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=422, detail="Le corps doit être un objet JSON")
    unknown = set(body) - db.OVERRIDE_ALLOWED
    if unknown:
        raise HTTPException(status_code=422, detail=f"Champs inconnus : {sorted(unknown)}")
    if db.get_spell(slug) is None:
        raise HTTPException(status_code=404, detail="Sort introuvable")
    db.save_overrides(slug, body)
    return JSONResponse({"ok": True})


@router.delete("/spells/{slug}/overrides")
def clear_spell_overrides(slug: str) -> JSONResponse:
    db.clear_overrides(slug)
    return JSONResponse({"ok": True})
