"""FastAPI application — point d'entrée principal."""
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src import db as database
from src.config import settings
from src.routes.admin import router as admin_router
from src.routes.browse import router as browse_router
from src.routes.card import router as card_router
from src.routes.cart import router as cart_router
from src.routes.custom import router as custom_router
from src.routes.overrides import router as overrides_router

log = structlog.get_logger()

_STATIC_DIR = Path(__file__).parent / "static"


async def _ingest_job() -> None:
    """Tâche planifiée : télécharge et indexe le dump hebdomadairement."""
    log.info("ingest.start", trigger="scheduler")
    try:
        from src.ingest.download import download_dump, extract_dump
        from src.ingest.parser_fr import parse_dump
        from src.ingest.populate import upsert_spells

        archive = await download_dump(settings.wiki_dump_url, settings.data_dir)
        xml_dir = extract_dump(archive, settings.data_dir)
        spells = parse_dump(str(xml_dir))
        inserted, updated = upsert_spells(spells)
        archive.unlink(missing_ok=True)
        log.info(
            "ingest.done",
            spells_total=len(spells),
            inserted=inserted,
            updated=updated,
        )
    except Exception as exc:
        log.error("ingest.error", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    count = database.spell_count()
    if count == 0:
        log.warning(
            "Base de données vide. "
            "Lance 'make ingest' pour télécharger et indexer les sorts."
        )
    else:
        log.info("startup", port=settings.port, spells=count)

    scheduler = None
    if settings.scheduler_enabled:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(
            _ingest_job,
            "cron",
            day_of_week="sun",
            hour=3,
            minute=0,
            id="weekly_ingest",
        )
        scheduler.start()
        log.info("scheduler.started", next_run=str(scheduler.get_job("weekly_ingest").next_run_time))

    yield

    if scheduler is not None:
        scheduler.shutdown(wait=False)
    log.info("shutdown")


app = FastAPI(
    title="Pathfinder Spell Cards",
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(admin_router)
app.include_router(custom_router)   # must come before browse_router (/spells/new before /spells/{slug})
app.include_router(browse_router)
app.include_router(card_router)
app.include_router(cart_router)
app.include_router(overrides_router)


@app.get("/health")
async def health() -> JSONResponse:
    count = database.spell_count()
    return JSONResponse({
        "status": "ok",
        "version": "0.1.0",
        "spells_indexed": count,
        "last_ingest": database.last_ingest_time(),
    })
