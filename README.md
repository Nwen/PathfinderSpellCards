# Pathfinder Spell Cards

Application web self-hosted générant des **cartes de sorts Pathfinder 1ère édition** en français, au format PDF imprimable.

- Carte individuelle : format poker **63×88mm** (WeasyPrint)
- Planche A4 : **9 cartes** en grille 3×3
- Deux thèmes : **sobre** (blanc épuré) et **parchemin** (crème vintage)
- Données : [wiki Pathfinder-fr](http://www.pathfinder-fr.org/) (CC-BY-SA), ~2 000 sorts indexés
- Rafraîchissement automatique du dump chaque **dimanche à 3h UTC**

---

## Démarrage rapide (Docker)

### Prérequis

- Docker ≥ 24
- Docker Compose ≥ 2.20

### Lancer l'application

```bash
docker compose up -d
```

L'interface est disponible sur **http://localhost:8000**.

### Premier import des sorts

La base de données est vide au premier démarrage. Lance l'ingestion manuellement :

```bash
make docker-ingest
# ou directement :
docker compose exec app python scripts/check_ingest.py --data-dir /app/data
```

Durée : ~5 min (téléchargement + parse de 12 000 fichiers XML).  
Ensuite, la cron hebdomadaire maintient la base à jour automatiquement.

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `PORT` | `8000` | Port d'écoute HTTP |
| `BASE_URL` | `http://localhost:8000` | URL publique de l'application |
| `DATABASE_URL` | `sqlite:////app/data/spells.db` | URI SQLite (volume Docker) |
| `DATA_DIR` | `/app/data` | Répertoire pour le dump XML |
| `LOG_LEVEL` | `INFO` | Niveau de log (`DEBUG`, `INFO`, `WARNING`) |
| `SCHEDULER_ENABLED` | `true` | Active le cron hebdomadaire d'ingestion |

Créer un fichier `.env` à la racine pour surcharger localement :

```env
PORT=8080
LOG_LEVEL=DEBUG
SCHEDULER_ENABLED=false
```

---

## Développement local

> **Note Windows** : WeasyPrint nécessite GTK3 (libgobject) pour générer des PDF.
> Sans GTK, les routes `/card.pdf` et `/sheet.pdf` renvoient un JSON 503 avec un lien vers l'aperçu HTML (qui fonctionne sans GTK).
> En Docker, tout fonctionne (GTK3 pré-installé dans l'image).

```bash
# 1. Environnement Python
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows

# 2. Dépendances
pip install -e ".[dev]"

# 3. Serveur de développement (rechargement automatique)
make dev                           # http://localhost:8000

# 4. Ingestion depuis le cache local (sans re-télécharger)
make ingest-cached

# 5. Tests
make test

# 6. Lint
make lint
```

---

## Ingestion manuelle

```bash
# Pipeline complet (télécharge + parse + indexe)
make ingest

# Depuis le cache XML déjà extrait
make ingest-cached

# Parse uniquement (sans modifier la DB)
make ingest-parse-only
```

Le dump source est : `http://db.pathfinder-fr.org/raw/wikixml.7z` (~40 MB compressé).  
Il est extrait dans `data/Out/Pathfinder-RPG/` (12 000+ fichiers XML).

---

## Routes principales

| Route | Description |
|---|---|
| `GET /spells` | Liste paginée avec filtres (école, classe, niveau, recherche) |
| `GET /spells/{slug}` | Fiche détail d'un sort |
| `GET /spells/{slug}/card.pdf?theme=sobre` | Carte PDF 63×88mm |
| `GET /spells/{slug}/card.html` | Aperçu HTML de la carte (debug) |
| `GET /cart` | Panier (localStorage) |
| `GET /sheet.pdf?slugs=a,b,c&theme=parchemin` | Planche A4 9 cartes en PDF |
| `GET /sheet.html?slugs=a,b,c` | Aperçu HTML de la planche (debug) |
| `GET /health` | JSON statut + nombre de sorts indexés + date dernier import |

---

## Architecture

```
src/
├── main.py          — FastAPI app, lifespan, cron APScheduler
├── config.py        — Pydantic settings (env vars)
├── db.py            — SQLite WAL, schéma, helpers
├── routes/
│   ├── browse.py    — Liste /spells + fiche /spells/{slug}
│   ├── card.py      — Carte PDF individuelle 63×88mm
│   └── cart.py      — Panier + planche A4 /sheet.pdf
├── ingest/
│   ├── download.py  — Téléchargement + extraction du dump .7z
│   ├── parser_fr.py — Parseur wiki XML → SpellData
│   └── populate.py  — Upsert SQLite
└── templates/
    ├── base.html.j2
    ├── browse/      — list + detail + _items (HTMX partiel)
    ├── card/        — card.html.j2 + sheet.html.j2
    └── cart/        — cart.html.j2
```

**Stack :** FastAPI · Jinja2 · HTMX · Tailwind (Play CDN) · WeasyPrint · SQLite WAL · APScheduler

---

## Licence

MIT.

Données issues du wiki Pathfinder-fr (CC-BY-SA).  
Pathfinder Roleplaying Game © Paizo Publishing, LLC.  
Contenu sous [Open Game License (OGL)](https://paizo.com/pathfinderRPG/prd/openGameLicense.html).
