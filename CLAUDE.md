# CLAUDE.md

## Project Overview

**Mes collections (beta)** — Front augmente DSFR pour OpenRAG. Module independant qui s'intercale entre l'utilisateur et OpenRAG pour offrir un decoupage intelligent de documents, un graph de references croisees, une administration des collections en DSFR, et une integration riche dans Open WebUI.

## Architecture

```
[Frontend Nuxt 4 + DSFR — port 8201]
     |
[MyRAG FastAPI — port 8200]
     |
     ├── /api/ingest/{collection}        → decoupage + upload vers OpenRAG
     ├── /api/collections                → CRUD collections (SQLAlchemy DB)
     ├── /api/collections/{n}/publish    → publication dans OWUI
     ├── /api/feedback                   → feedback OWUI
     ├── /api/playground/{n}/chat        → test RAG avec debug
     ├── /api/sources/check-url          → verification URL distante
     ├── /api/sync                       → sync Keycloak ↔ OpenRAG
     ├── /graph                          → viewer Cytoscape.js
     └── /articles/{collection}/{id}     → vue article HTML DSFR
         |
[OpenRAG API — port 8180]     [Keycloak — port 8082]     [Scaleway APIs]
```

## Common Commands

```bash
# Backend MyRAG
cd myrag && docker build -t myrag:beta . && docker run -p 8200:8200 \
  -v myrag-data:/app/data \
  -e OPENRAG_URL=http://openrag:8080 \
  -e OPENRAG_ADMIN_TOKEN=xxx \
  --network openrag_default myrag:beta

# Frontend
cd myrag/frontend && npm install && npx nuxt dev --port 8201

# Tests
cd myrag && python3 -m pytest tests/unit/ -v

# API Swagger
http://localhost:8200/docs
```

## Stack Technique

- **Backend** : Python 3.12, FastAPI, SQLAlchemy async (SQLite dev / PostgreSQL prod), httpx, NetworkX
- **Frontend** : Nuxt 4, @gouvfr/dsfr, oidc-client-ts
- **Auth** : Keycloak OIDC PKCE (realm openwebui, client myrag-front)
- **Tests** : pytest, TDD
- **Docker** : Docker Compose + K8s Scaleway manifests

## Key Files

| Fichier | Description |
|---------|-------------|
| `myrag/app/main.py` | FastAPI app + lifespan (init DB) |
| `myrag/app/database.py` | SQLAlchemy engine (SQLite/PostgreSQL) |
| `myrag/app/models/db.py` | 8 tables : collections, publications, jobs, feedback, eval, source_files |
| `myrag/app/services/collection_store.py` | CRUD collections (DB) |
| `myrag/app/services/job_store.py` | CRUD ingestion jobs (DB) |
| `myrag/app/services/feedback_store.py` | CRUD feedback (DB) |
| `myrag/app/services/openrag_client.py` | Client API OpenRAG |
| `myrag/app/services/chunker.py` | 4 strategies de decoupage |
| `myrag/app/services/graph_builder.py` | Graph NetworkX + Cytoscape.js |
| `myrag/app/routers/ingest.py` | Upload + from-url + reindex |
| `myrag/app/routers/playground.py` | Chat RAG avec fallback + auto-eval |
| `myrag/frontend/pages/admin/create/` | Wizard 5 etapes |
| `myrag/frontend/composables/useApi.ts` | Client API centralise |

## Database

SQLite pour le dev (`/app/data/myrag.db`), PostgreSQL pour la prod via `DATABASE_URL` :
```
DATABASE_URL=sqlite+aiosqlite:////app/data/myrag.db        # dev
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/myrag  # prod
```

## Testing

```bash
cd myrag && python3 -m pytest tests/unit/ -v
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/myrag.db` | Base de donnees |
| `OPENRAG_URL` | `http://openrag:8080` | URL du service OpenRAG |
| `OPENRAG_ADMIN_TOKEN` | `` | Token admin OpenRAG |
| `KEYCLOAK_URL` | `http://keycloak:8080` | URL Keycloak |
| `KEYCLOAK_REALM` | `openwebui` | Realm Keycloak |
| `KEYCLOAK_ADMIN_PASSWORD` | `` | Mot de passe admin Keycloak |
| `MYRAG_API_URL` | `http://localhost:8200` | URL publique MyRAG (frontend) |
