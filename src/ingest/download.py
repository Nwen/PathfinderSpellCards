"""Téléchargement et extraction du dump XML pathfinder-fr."""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)


async def download_dump(url: str, dest_dir: Path) -> Path:
    """Télécharge le dump .7z depuis pathfinder-fr.org."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    archive_path = dest_dir / "wikixml.7z"

    log.info("Téléchargement depuis %s …", url)
    async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", 0))
            downloaded = 0
            with archive_path.open("wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        print(
                            f"\r  {pct}% "
                            f"({downloaded // 1048576} Mo / {total // 1048576} Mo)",
                            end="",
                            flush=True,
                        )
        print()

    size_mb = archive_path.stat().st_size / 1048576
    log.info("Téléchargé %.1f Mo → %s", size_mb, archive_path)
    return archive_path


def extract_dump(archive_path: Path, dest_dir: Path) -> Path:
    """Extrait l'archive .7z et retourne le répertoire contenant les fichiers XML."""
    import py7zr  # import tardif — non requis au runtime si on ne décompresse pas

    log.info("Extraction de %s …", archive_path)
    with py7zr.SevenZipFile(archive_path, mode="r") as z:
        z.extractall(path=dest_dir)

    # Le dump pathfinder-fr extrait toujours dans Out/Pathfinder-RPG/
    xml_dir = dest_dir / "Out" / "Pathfinder-RPG"
    if not xml_dir.is_dir():
        # Fallback : le dossier avec le plus de fichiers XML
        from collections import Counter
        all_xml = list(dest_dir.rglob("*.xml"))
        if not all_xml:
            raise FileNotFoundError(
                f"Aucun fichier XML trouvé dans {dest_dir} après extraction."
            )
        counts = Counter(f.parent for f in all_xml)
        xml_dir = counts.most_common(1)[0][0]

    count = sum(1 for _ in xml_dir.glob("*.xml"))
    if count == 0:
        raise FileNotFoundError(f"Aucun fichier XML trouvé dans {xml_dir}.")
    log.info("Extrait : %s (%d fichiers XML)", xml_dir, count)
    return xml_dir
