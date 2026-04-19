# CLAUDE.md

## Project Overview

**Mes collections (beta)** — Front augmente DSFR pour OpenRAG. Module independant qui s'intercale entre l'utilisateur et OpenRAG pour offrir un decoupage intelligent de documents, un graph de references croisees, une administration des collections en DSFR, et une integration riche dans Open WebUI.

## Dependencies — services requis

Mes collections ne fonctionne PAS en standalone. Il depend de plusieurs services externes qui doivent etre demarres avant. **Avant toute operation (dev, test, debug), verifier que les services requis sont actifs.**

### Carte des dependances

```
                        [Mes collections]
                         MyRAG :8200
                         Frontend :8201
                              |
         ┌────────────────────┼────────────────────┐
         |                    |                    |
    [OpenRAG]           [Keycloak]          [Scaleway APIs]
     :8180               :8082              (LLM + embeddings)
         |                    |
    ┌────┼────┐          [owuicore-main]
    |    |    |           Open WebUI :3000
  Milvus rdb etcd         Pipelines :9099
         MinIO             Tika :9998
```

### Services requis et ou les trouver

| Service | Port | Repository | Indispensable | Verification |
|---------|------|------------|:-------------:|-------------|
| **OpenRAG** | 8180 | `/Users/etiquet/Documents/GitHub/openrag` | oui | `curl http://localhost:8180/health_check` |
| **Keycloak** | 8082 | `/Users/etiquet/Documents/GitHub/owuicore-main` (compose) | oui | `curl http://localhost:8082/realms/openwebui` |
| **Open WebUI** | 3000 | `/Users/etiquet/Documents/GitHub/owuicore-main` | non (publication) | `curl http://localhost:3000` |
| **Milvus** | — | Demarre par le compose OpenRAG | oui (via OpenRAG) | Inclus dans `docker compose up` OpenRAG |
| **PostgreSQL (rdb)** | — | Demarre par le compose OpenRAG | oui (via OpenRAG) | Inclus dans `docker compose up` OpenRAG |
| **Scaleway APIs** | — | Cloud (pas de repo local) | oui (LLM + embeddings) | Clefs dans `.env` OpenRAG |

### Repositories lies (ecosysteme Mirai)

| Repository | Chemin local | Role |
|-----------|-------------|------|
| `openrag` | `/Users/etiquet/Documents/GitHub/openrag` | Backend RAG (indexation, search, chat) |
| `owuicore-main` | `/Users/etiquet/Documents/GitHub/owuicore-main` | Open WebUI + Keycloak + Pipelines + Tika |
| `keycloak-comu` | `/Users/etiquet/Documents/GitHub/keycloak-comu` | Self-service groupes Keycloak (gestion membres) |
| `keycloak-utils` | `/Users/etiquet/Documents/GitHub/keycloak-utils` | Utilitaires admin Keycloak |
| `owuitools-legifrance` | `/Users/etiquet/Documents/GitHub/owuitools-legifrance` | MCP Legifrance (API PISTE) |
| `owuipipe-grafragexp` | `/Users/etiquet/Documents/GitHub/owuipipe-grafragexp` | Viewer graph Cytoscape.js (source du viewer) |
| `AssistantMiraiLibreOffice` | `/Users/etiquet/Documents/GitHub/AssistantMiraiLibreOffice` | Extension LibreOffice (integration future) |
| `mirai-assistant-navigateur` | `/Users/etiquet/Documents/GitHub/mirai-assistant-navigateur` | Extension navigateur (integration future) |
| `mirai-infra` | `/Users/etiquet/Documents/GitHub/mirai-infra` | Infrastructure K8s Scaleway |
| `mirai-values` | `/Users/etiquet/Documents/GitHub/mirai-values` | Helm values pour le deploiement |

### Demarrage du stack complet (Docker local)

```bash
# 1. Demarrer owuicore-main (Keycloak + Open WebUI + Pipelines + Tika)
cd /Users/etiquet/Documents/GitHub/owuicore-main
docker compose up -d

# 2. Demarrer OpenRAG (+ Milvus + PostgreSQL + MinIO)
cd /Users/etiquet/Documents/GitHub/openrag
docker compose --profile cpu up -d

# 3. Demarrer MyRAG (backend)
cd /Users/etiquet/Documents/GitHub/mycollections
docker build -t myrag:beta myrag/ && docker run -d --name myrag-test \
  -p 8200:8200 --dns 8.8.8.8 --dns 8.8.4.4 \
  --add-host=host.docker.internal:host-gateway \
  -v myrag-data:/app/data \
  -e OPENRAG_URL=http://openrag-openrag-cpu-1:8080 \
  -e OPENRAG_ADMIN_TOKEN=or-admin-openrag-2026 \
  -e KEYCLOAK_URL=http://host.docker.internal:8082 \
  -e KEYCLOAK_REALM=openwebui \
  -e KEYCLOAK_ADMIN_PASSWORD=xxx \
  --network openrag_default myrag:beta

# 4. Demarrer le frontend (dev mode)
cd /Users/etiquet/Documents/GitHub/mycollections/myrag/frontend
npm install && npx nuxt dev --port 8201
```

### Deploiement Scaleway (K8s)

```bash
# Les manifests K8s sont dans myrag/k8s/
# Le stack complet sur Scaleway :
#   - OpenRAG : namespace openrag (deployment + milvus + rdb)
#   - Keycloak : namespace owui (pod keycloak)
#   - Open WebUI : namespace owui (pod openwebui)
#   - MyRAG : namespace myrag (deployment + service + ingress)
#
# Variables d'environnement Scaleway :
#   DATABASE_URL=postgresql+asyncpg://user:pass@rdb.openrag.svc:5432/myrag
#   OPENRAG_URL=http://openrag.openrag.svc:8080
#   KEYCLOAK_URL=http://keycloak.owui.svc:8080
```

### Verification rapide de sante

```bash
# Tous les services en une commande
echo "OpenRAG:" && curl -s http://localhost:8180/health_check | head -1
echo "Keycloak:" && curl -s http://localhost:8082/realms/openwebui | python3 -c "import sys,json; print(json.load(sys.stdin).get('realm','KO'))" 2>/dev/null
echo "MyRAG:" && curl -s http://localhost:8200/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','KO'))" 2>/dev/null
echo "Open WebUI:" && curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
echo "Frontend:" && curl -s -o /dev/null -w "%{http_code}" http://localhost:8201
```

## Architecture interne

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
| `KEYCLOAK_ADMIN_PASSWORD` | `` | Mot de passe admin Keycloak (fallback si pas de client_secret) |
| `KEYCLOAK_CLIENT_ID` | `myrag-admin` | Client Keycloak pour l'API admin |
| `KEYCLOAK_CLIENT_SECRET` | `` | Secret du client (si service account) |
| `LEGIFRANCE_CLIENT_ID` | `` | Client ID API PISTE Legifrance |
| `LEGIFRANCE_CLIENT_SECRET` | `` | Secret API PISTE Legifrance |
| `MYRAG_API_URL` | `http://localhost:8200` | URL publique MyRAG (pour le frontend) |
| `AUTH_ENABLED` | `true` | Activer l'auth Keycloak sur le frontend |

## Problemes connus

- **DNS dans les containers Docker** : ajouter `--dns 8.8.8.8 --dns 8.8.4.4` au `docker run`
- **OIDC issuer mismatch** : utiliser `host.docker.internal:8082` (pas `localhost`) pour Keycloak depuis un container
- **PDF sur Mac ARM64** : bug pypdfium2, utiliser TXT/MD a la place
- **Le token admin OpenRAG est ecrase au restart** : definir `AUTH_TOKEN` dans le `.env` d'OpenRAG
