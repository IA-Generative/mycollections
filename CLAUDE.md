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
    [OpenRAG]           [Keycloak]          [API de modeles]
     :8180               :8082              (LLM + embeddings)
         |                    |
    ┌────┼────┐          [owuicore-main]
    |    |    |           Open WebUI :3000
  Milvus rdb etcd         Pipelines :9099
         MinIO             Tika :9998
```

### Services requis et ou les trouver

| Service | Port | Depot | Indispensable | Verification |
|---------|------|------------|:-------------:|-------------|
| **OpenRAG** | 8180 | `../openrag` | oui | `curl http://localhost:8180/health_check` |
| **Keycloak** | 8082 | `../owuicore-main` (compose) | oui | `curl http://localhost:8082/realms/openwebui` |
| **Open WebUI** | 3000 | `../owuicore-main` | non (publication) | `curl http://localhost:3000` |
| **Milvus** | — | Demarre par le compose OpenRAG | oui (via OpenRAG) | Inclus dans `docker compose up` OpenRAG |
| **PostgreSQL (rdb)** | — | Demarre par le compose OpenRAG | oui (via OpenRAG) | Inclus dans `docker compose up` OpenRAG |
| **API de modeles** (LLM + embeddings) | — | Service externe, compatible OpenAI | oui | Clefs dans le `.env` d'OpenRAG |

### Depots lies (ecosysteme Mirai)

Les chemins sont donnes **relativement a ce depot** : les depots se clonent cote a cote.

| Depot | Chemin | Role |
|-------|--------|------|
| `openrag` | `../openrag` | Backend RAG (indexation, search, chat) |
| `owuicore-main` | `../owuicore-main` | Open WebUI + Keycloak + Pipelines + Tika |
| `keycloak-comu` | `../keycloak-comu` | Self-service groupes Keycloak (gestion membres) |
| `keycloak-utils` | `../keycloak-utils` | Utilitaires admin Keycloak |
| `owuitools-legifrance` | `../owuitools-legifrance` | MCP Legifrance (API PISTE) |
| `owuipipe-grafragexp` | `../owuipipe-grafragexp` | Viewer graph Cytoscape.js (source du viewer) |
| `AssistantMiraiLibreOffice` | `../AssistantMiraiLibreOffice` | Extension LibreOffice (integration future) |
| `mirai-assistant-navigateur` | `../mirai-assistant-navigateur` | Extension navigateur (integration future) |
| `mirai-infra` | `../mirai-infra` | Infrastructure Kubernetes |
| `mirai-values` | `../mirai-values` | Helm values pour le deploiement |

### Demarrage du stack complet (Docker local)

```bash
# 1. Demarrer owuicore-main (Keycloak + Open WebUI + Pipelines + Tika)
cd ../owuicore-main
docker compose up -d

# 2. Demarrer OpenRAG (+ Milvus + PostgreSQL + MinIO)
cd ../openrag
docker compose --profile cpu up -d

# 3. Demarrer MyRAG (backend)
cd ../mycollections
docker build -t myrag:beta myrag/ && docker run -d --name myrag-test \
  -p 8200:8200 --dns 8.8.8.8 --dns 8.8.4.4 \
  --add-host=host.docker.internal:host-gateway \
  -v myrag-data:/app/data \
  -e OPENRAG_URL=http://openrag-openrag-cpu-1:8080 \
  -e OPENRAG_ADMIN_TOKEN=<jeton-admin-openrag> \
  -e KEYCLOAK_URL=http://host.docker.internal:8082 \
  -e KEYCLOAK_REALM=openwebui \
  -e KEYCLOAK_ADMIN_PASSWORD=<mot-de-passe-admin-keycloak> \
  -e MYRAG_PSEUDO_SEL=dev-sel \
  --network openrag_default myrag:beta

# 4. Demarrer le frontend (dev mode)
cd myrag/frontend
npm install && npx nuxt dev --port 8201
```

### Deploiement (Kubernetes)

Les manifestes sont dans `myrag/k8s/` ; la procedure est dans le README (section
« Deploiement sur Kubernetes ») et dans `myrag/DEPLOYMENT.md`. Registre d'images, namespace et
adresses dependent de l'environnement : ils ne sont pas ecrits dans ce depot.

```bash
# Variables d'environnement du backend, en cluster (exemples de forme, pas de valeurs reelles) :
#   DATABASE_URL=postgresql+asyncpg://<user>:<mot-de-passe>@<hote-postgres>:5432/myrag
#   OPENRAG_URL=http://<service-openrag>:8080
#   KEYCLOAK_URL=https://<votre-sso>
```

**Les adresses du SSO sont cuites dans l'image du frontend** (Nuxt statique : lues a la
construction, pas au demarrage). Les changer impose de reconstruire l'image.

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
     ├── /api/openrag/extract/{id}       → morceau relu dans OpenRAG : page HTML lisible, ou JSON brut avec ?raw=1
     ├── /api/openrag/static/{path}      → document complet (repli sur le morceau ; propage ?raw=1)
     ├── /api/sources/check-url          → verification URL distante
     ├── /api/sync                       → sync Keycloak ↔ OpenRAG
     ├── /graph                          → viewer Cytoscape.js
     └── /articles/{collection}/{id}     → vue article HTML DSFR
```

## Stack Technique

- **Backend** : Python 3.12, FastAPI, SQLAlchemy async (SQLite dev / PostgreSQL prod), httpx, NetworkX
- **Frontend** : Nuxt 4, @gouvfr/dsfr, oidc-client-ts
- **Auth** : Keycloak OIDC PKCE (realm openwebui, client myrag-front)
- **Tests** : pytest (backend), vitest (frontend), TDD
- **Docker** : Docker Compose + manifestes Kubernetes (`myrag/k8s/`)

## Key Files

| Fichier | Description |
|---------|-------------|
| `myrag/app/main.py` | FastAPI app + lifespan (init DB) |
| `myrag/app/database.py` | SQLAlchemy engine (SQLite/PostgreSQL) |
| `myrag/app/models/db.py` | 16 tables : les 8 historiques + le collectif (demande, soutien, abonnement, proposition, signalement, grille_controle, evenement, amorce) |
| `myrag/app/services/etats.py` | Machine à états du collectif — module pur (docs/collectif.md, ADR-0001) |
| `myrag/app/services/collectif_store.py` | Écritures du collectif + journal (fil d'avancement) |
| `myrag/app/routers/demandes.py`, `collectif.py`, `amorces.py` | Routes du collectif |
| `myrag/app/amorces/catalogue.json`, `myrag/app/services/amorces/` | Les six amorces (lot 0) : catalogue, connecteurs, ingestion idempotente, banque de questions, CLI |
| `myrag/tests/conftest.py` | Base SQLite isolée par session, identités de test, capacités |
| `myrag/app/services/collection_store.py` | CRUD collections (DB) |
| `myrag/app/services/job_store.py` | CRUD ingestion jobs (DB) |
| `myrag/app/services/feedback_store.py` | CRUD feedback (DB) |
| `myrag/app/services/openrag_client.py` | Client API OpenRAG |
| `myrag/app/services/chunker.py` | 4 strategies de decoupage |
| `myrag/app/services/graph_builder.py` | Graph NetworkX + Cytoscape.js |
| `myrag/app/routers/ingest.py` | Upload + from-url + reindex |
| `myrag/app/routers/playground.py` | Chat RAG avec fallback + auto-eval |
| `myrag/frontend/components/playground/SourceChip.vue` | Puce de source : bulle au survol (Teleport, position fixe), ouvre la fenetre de lecture |
| `myrag/frontend/components/playground/SourceViewer.vue` | Fenetre de lecture d'un morceau ou d'un document : Markdown, export Word/PDF |
| `myrag/frontend/utils/extrait.ts` | `decouperMorceau` (retire les balises OpenRAG), exports ; pendant backend : `_decouper_morceau` dans `app/main.py` |
| `myrag/frontend/pages/index.vue`, `myrag/frontend/utils/accueil.ts` | Accueil : decouvrir, explorer, creer ; ce que l'accueil raconte est en fonctions pures testees |
| `myrag/app/routers/accueil.py`, `categories.py`, `guide.py` | Exemple de question et bilan de l'accueil ; categories du catalogue ; guide en six etapes (`myrag/app/guide/*.md`) |
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
cd myrag && python3 -m pytest tests/unit/ -v      # backend
cd myrag/frontend && npx vitest run              # frontend
```

Le comportement d'un survol, d'un focus ou d'un defilement ne se prouve pas par un test
unitaire : le jouer dans un navigateur (voir `docs/sources.md`).

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
| `MYRAG_PSEUDO_SEL` | `` | Sel HMAC des identités du collectif (le même que `obs-pseudo-salt` du bus) ; vide ⇒ routes du collectif en 503. En dev : `dev-sel` |
| `CAPACITES_URL` | `` | capacites.json du menu commun (service interne) ; vide ⇒ drapeaux à false |
| `SEUIL_CHANTIER_DEFAUT` | `5` | Seuil de soutiens si le menu ne répond pas |
| `SOMMEIL_JOURS` | `30` | Un chantier muet plus longtemps est « en sommeil » |
| `NATINFO_API_KEY` | `` | Clé natinfo.app (facultative) : enrichit les fiches NATINF (peines) au-delà de 120 appels/h |

## Regles de travail

- **`main` est protegee** : tout passe par une branche et une pull request. La construction des
  images lit `main` — un correctif qui n'y est pas fusionne n'est pas livre, meme s'il marche en local.
- **Le depot est public** : ni nom de personne, ni chemin de poste, ni identifiant d'infrastructure
  (registre, cluster, namespace), ni jeton — meme d'exemple — dans le code ou la documentation.
  Les adresses d'exemple sont en `fake-domain.name` ; les ecrans de documentation utilisent des
  donnees d'exemple, jamais celles d'un environnement reel.

## Problemes connus

- **DNS dans les containers Docker** : ajouter `--dns 8.8.8.8 --dns 8.8.4.4` au `docker run`
- **OIDC issuer mismatch** : utiliser `host.docker.internal:8082` (pas `localhost`) pour Keycloak depuis un container
- **PDF sur Mac ARM64** : bug pypdfium2, utiliser TXT/MD a la place
- **Le token admin OpenRAG est ecrase au restart** : definir `AUTH_TOKEN` dans le `.env` d'OpenRAG
