"""Route d'administration : déclenchement manuel de l'ingestion."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src import db
from src.config import settings

log = logging.getLogger(__name__)
router = APIRouter()

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# ── État de l'ingestion en cours ──────────────────────────────────────────────
_state: dict = {
    "running": False,
    "inserted": 0,
    "updated": 0,
    "total": 0,
    "error": "",
    "log": [],
}


def _xml_dir() -> Path:
    return settings.data_dir / "Out" / "Pathfinder-RPG"


def _xml_exists() -> bool:
    d = _xml_dir()
    return d.is_dir() and any(d.glob("*.xml"))


async def _run_ingest(download: bool) -> None:
    if _state["running"]:
        return
    _state.update(running=True, error="", log=[], inserted=0, updated=0, total=0)

    def emit(msg: str) -> None:
        log.info(msg)
        _state["log"].append(msg)

    try:
        from src.ingest.parser_fr import parse_dump
        from src.ingest.populate import upsert_spells

        xml_dir = _xml_dir()

        if download or not _xml_exists():
            from src.ingest.download import download_dump, extract_dump
            emit("Téléchargement du dump en cours…")
            archive = await download_dump(settings.wiki_dump_url, settings.data_dir)
            emit(f"Archive téléchargée ({archive.stat().st_size // 1_048_576} Mo). Extraction…")
            xml_dir = await asyncio.to_thread(extract_dump, archive, settings.data_dir)
            archive.unlink(missing_ok=True)
            emit(f"Extraction terminée : {xml_dir}")
        else:
            count = sum(1 for _ in xml_dir.glob("*.xml"))
            emit(f"Données existantes trouvées ({count} fichiers XML). Pas de téléchargement.")

        emit("Analyse des pages wiki…")
        spells = await asyncio.to_thread(parse_dump, str(xml_dir))
        _state["total"] = len(spells)
        emit(f"{len(spells)} sorts analysés. Insertion en base…")

        inserted, updated = await asyncio.to_thread(upsert_spells, spells)
        _state.update(inserted=inserted, updated=updated)
        emit(f"Terminé : {inserted} insérés, {updated} mis à jour.")

    except Exception as exc:
        msg = f"Erreur : {exc}"
        log.error(msg, exc_info=True)
        _state["error"] = msg
        _state["log"].append(msg)
    finally:
        _state["running"] = False


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return _templates.TemplateResponse(
        request,
        "admin/admin.html.j2",
        {
            "spell_count": db.spell_count(),
            "last_ingest": db.last_ingest_time(),
            "xml_exists": _xml_exists(),
            "state": _state,
        },
    )


@router.post("/admin/ingest")
async def trigger_ingest(download: bool = Query(default=True)):
    if _state["running"]:
        return JSONResponse({"ok": False, "error": "Ingestion déjà en cours"}, status_code=409)
    asyncio.create_task(_run_ingest(download=download))
    return JSONResponse({"ok": True})


@router.get("/admin/ingest/status")
def ingest_status():
    return JSONResponse({
        "running": _state["running"],
        "inserted": _state["inserted"],
        "updated": _state["updated"],
        "total": _state["total"],
        "error": _state["error"],
        "log": _state["log"],
    })
