# Mes collections (beta)

Front augmenté DSFR pour OpenRAG. Module qui s'intercale entre l'utilisateur et OpenRAG pour offrir un découpage intelligent de documents, un graph de références croisées, une administration des collections en DSFR, et une intégration riche dans Open WebUI.

**Production** : [https://mycollections.fake-domain.name](https://mycollections.fake-domain.name) (alias : `mycorpus.fake-domain.name`).

## Sommaire

1. [Ce que fait l'application](#ce-que-fait-lapplication)
2. [Architecture](#architecture)
3. [Sources d'indexation supportées](#sources-dindexation-supportées)
4. [Démarrage local](#démarrage-local)
5. [Déploiement Scaleway](#déploiement-scaleway)
6. [Documentation](#documentation)

## Ce que fait l'application

- **Catalog DSFR** des collections de documents (parcours `/admin/catalog`).
- **Wizard 5 étapes** de création d'une collection : source, métadonnées, ingestion, évaluation, publication.
- **Connecteurs de source** : fichiers locaux (PDF/MD/DOCX…), URL distante, Légifrance (API PISTE), **Drive (Suite Numérique)** — indexation à la demande d'un dossier Drive partagé.
- **Chunking intelligent** (4 stratégies : auto, article, chunk, directory) avec stockage du fichier source sur PVC pour permettre la réindexation.
- **Archivage / purge réversible** d'une collection : archiver = dépublier OWUI + cacher du catalog (data conservée). Purger = hard-delete (OpenRAG partition + fichiers + DB en cascade). Modale de confirmation stricte avec re-saisie du nom.
- **Publication vers Open WebUI** : la collection devient un modèle `openrag-<nom>` utilisable comme outil ou alias dans OWUI, avec visibilité par groupe Keycloak.
- **Feedback OWUI** : ingestion des retours utilisateurs, review/promote vers des datasets d'évaluation.
- **Playground RAG** : test rapide depuis le front avec affichage des sources.
- **Graph de références croisées** (NetworkX + Cytoscape.js) pour les collections le supportant.
- **Sync Keycloak ↔ OpenRAG** : propagation des groupes `rag-query/<collection>` vers les partitions.

## Architecture

```
[Frontend Nuxt 4 + DSFR — port 8201 en dev, 3000 en prod via ingress]
     │
     ▼
[MyRAG FastAPI — port 8200]
     │
     ├── OpenRAG         (RAG backend, sur VM Scaleway en prod, Docker compose en local)
     ├── Keycloak        (OIDC realm openwebui)
     ├── Drive           (Suite Numérique, via /external_api/v1.0/)
     ├── Open WebUI      (publication des collections comme modèles)
     └── PostgreSQL      (DB myrag, partagée avec keycloak/myvault en prod)
```

Stack :
- **Backend** : Python 3.12, FastAPI, SQLAlchemy async (SQLite dev / PostgreSQL prod), httpx, NetworkX.
- **Frontend** : Nuxt 4, `@gouvfr/dsfr`, `oidc-client-ts` (PKCE).
- **Auth** : Keycloak OIDC PKCE (realm `openwebui`, client `myrag-front` public + client `mycollections-drive` confidential pour service-to-service Drive).
- **Tests** : pytest + pytest-asyncio.
- **Images** : Docker multi-stage, déployées en K8s (Scaleway Kapsule) via manifests dans `myrag/k8s/`.

Schéma détaillé + ports + variables d'environnement → [CLAUDE.md](CLAUDE.md).

## Sources d'indexation supportées

| Source | Statut | Flux |
|-------|:-----:|------|
| Fichier local (upload) | ✅ | POST `/api/ingest/{collection}` multipart |
| URL distante | ✅ | POST `/api/ingest/{collection}/from-url` |
| Légifrance (PISTE) | ✅ | `/api/sources/legifrance/*` |
| **Drive (Suite Numérique)** | ✅ | `/api/sources/drive/*` |
| Nextcloud | 🟡 UI présente, backend TODO | — |
| Resana | 🟡 UI présente, backend TODO | — |

### Drive : comment ça marche

MyRAG s'authentifie à Drive via **`client_credentials`** sur le client Keycloak confidentiel `mycollections-drive`, puis appelle l'API OIDC-RS de Drive (`/external_api/v1.0/items/*`) avec un Bearer. Drive accepte les requêtes au nom d'un **user "bot" local** (`mycollections-drive@bot.local`) dont le `sub` matche celui du service account.

Pour qu'un dossier Drive soit indexable :
1. L'admin/propriétaire du dossier le **partage au bot** `mycollections-drive@bot.local` (viewer) via l'UI Drive — c'est le même geste que partager à un collègue.
2. Dans le wizard `/admin/create` → Drive → étape 3 affiche le picker des dossiers visibles par le bot.
3. Clic **"Indexer ce dossier"** → POST `/api/sources/drive/add` → import async : chaque fichier devient un `ingest_job` trackable dans `/admin`.
4. Re-sync incrémentale via `POST /api/sources/drive/sync/{collection}` (bouton "Rafraîchir").

Détail technique du provisioning bot + Helm Drive → [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md) section 1.5.

### Sécurité : qui voit quoi ?

Partager un dossier Drive au bot ≠ rendre son contenu public. Il y a **deux couches d'ACL** empilées :

1. **Drive ACL** (côté source) — le bot voit uniquement ce qu'on lui partage. Les autres humains ne sont pas affectés.
2. **MyRAG / OWUI ACL** (côté indexé) — une fois ingéré, le contenu appartient à une collection MyRAG. Cloisonnement via :
   - `scope = group` à la création → visible uniquement aux membres du groupe Keycloak.
   - `visibility_groups` à la publication OWUI → modèle proposé aux groupes listés uniquement.
   - `POST /api/sync` → propagation des groupes Keycloak vers OpenRAG pour filtrer les réponses RAG.

**Par défaut, sans précautions, une collection `scope=all` indexée depuis Drive est interrogeable par tout utilisateur MyRAG.** Choisir explicitement `scope=group` à l'étape 2 du wizard pour cloisonner.

Points à durcir (cf. `continue-keen-hamming.md` priorité 3) : `/admin/catalog` et `/c/{id}/playground` ne sont pas encore filtrés par rôle — tout user authentifié peut lister et interroger.

### Filtrage du picker Drive par utilisateur (impersonation)

**Problème résolu** : en v1 naïve, le picker appelait Drive avec un service account (`mycollections-drive`) → tous les dossiers partagés au bot étaient listés à **tous** les admins MyRAG. Un admin A pouvait indexer le dossier partagé par l'admin B sans son consentement.

**Solution implémentée (2026-04-19, option 1a)** :
- Les routes `/api/sources/drive/folders`, `/drive/add`, `/drive/sync/*`, `/drive/status/*` **reçoivent et relaient le token OIDC de l'utilisateur connecté** (`Authorization: Bearer <user_access_token>`). Drive voit l'appel comme fait par cet utilisateur → retourne uniquement les dossiers que cet utilisateur peut voir.
- **Download synchrone avant async** : dans `/drive/add`, MyRAG télécharge tous les fichiers du dossier **pendant l'appel HTTP initial** (où le token user est encore valide), puis lance le chunking + upload OpenRAG en arrière-plan depuis les bytes déjà en mémoire. Plus aucun appel Drive après que la route a répondu.
- **Access token lifespan bumped à 15 min** pour le client Keycloak `myrag-front` (attribut `access.token.lifespan=900`), ce qui laisse largement le temps de télécharger un dossier raisonnable avant expiry.
- **Garde-fou** : refus si le dossier contient > 500 fichiers ou > 500 MB cumulés (HTTP 413) — l'utilisateur doit fractionner.

**Conséquence pratique** :
- Dans le picker, chaque user voit **ses propres dossiers + ceux qu'on lui a partagés** (via l'UI Drive). Pas ceux de ses collègues.
- L'audit Drive montre le vrai user comme auteur de la lecture massive (plus traçable qu'un bot).
- Plus besoin de provisionner un user bot dans Drive pour le flow nominal (le user bot reste uniquement utilisé par `/api/sources/drive/sync/*` en ligne de commande d'admin, où aucun user n'est connecté).

**Limite connue** : si le téléchargement prend > 15 min (gros dossiers, Drive lent), le token expire pendant l'appel et `/drive/add` retourne 502. Dans ce cas : fractionner, ou implémenter l'offline_access + refresh token (V2).

**Pré-requis utilisateur** : Drive auto-provisionne son `core.User` local à la **première connexion interactive** sur `https://mesfichiers.fake-domain.name`. Tant que ce n'est pas fait, le resource server de Drive répond `403 Forbidden` (on voit dans MyRAG : *"Votre compte n'est pas encore connu de Drive. Connectez-vous une fois sur https://mesfichiers.fake-domain.name puis revenez ici."*). Un seul login suffit, ensuite tout fonctionne.

## Démarrage local

Prérequis : Docker Desktop, Node 22, Python 3.12, le repo `openrag` et `owuicore-main` clonés à côté.

```bash
# 1. Démarrer les dépendances
cd ../owuicore-main      && docker compose up -d   # Keycloak + OWUI + Pipelines + Tika
cd ../openrag            && docker compose --profile cpu up -d

# 2. Démarrer MyRAG backend (image Docker locale)
cd ../mycollections
docker build -t myrag:beta myrag/
docker run -d --name myrag-test \
  -p 8200:8200 --dns 8.8.8.8 --dns 8.8.4.4 \
  --add-host=host.docker.internal:host-gateway \
  -v myrag-data:/app/data \
  -e OPENRAG_URL=http://openrag-openrag-cpu-1:8080 \
  -e OPENRAG_ADMIN_TOKEN=or-admin-openrag-2026 \
  -e KEYCLOAK_URL=http://host.docker.internal:8082 \
  -e KEYCLOAK_REALM=openwebui \
  --network openrag_default myrag:beta

# 3. Démarrer le frontend en dev
cd myrag/frontend
npm install
AUTH_ENABLED=false npx nuxt dev --port 8201

# 4. Vérifier
curl http://localhost:8200/health            # backend
curl http://localhost:8201/                  # frontend
```

## Déploiement Scaleway

Cible : Kapsule **`k8s-par-brave-bassi`**, namespace **`miraiku`**. OpenRAG tourne sur une VM Scaleway séparée (`api.openrag.fake-domain.name`). DB PostgreSQL partagée dans `miraiku` (DB dédiée `myrag`, user `app`).

```bash
# Build + push images (TOUJOURS linux/amd64 — Mac ARM64 par défaut = exec format error)
TAG=$(git rev-parse --short HEAD)
scw registry login
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:latest myrag/
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:latest myrag/frontend/

# Apply (secret.yaml à remplir localement depuis secret.yaml.template)
cp myrag/k8s/secret.yaml.template myrag/k8s/secret.yaml  # puis éditer
kubectl apply -f myrag/k8s/secret.yaml -f myrag/k8s/configmap.yaml -f myrag/k8s/pvc.yaml \
              -f myrag/k8s/service-backend.yaml -f myrag/k8s/service-frontend.yaml \
              -f myrag/k8s/deployment-backend.yaml -f myrag/k8s/deployment-frontend.yaml \
              -f myrag/k8s/ingress.yaml
kubectl -n miraiku rollout status deploy/myrag-backend
```

Procédure complète (création DB, provisioning bot user Drive, troubleshooting amd64 / naive UTC datetimes / nginx redirects / redirect_uri Keycloak) → [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md).

## Documentation

- [CLAUDE.md](CLAUDE.md) — architecture interne, variables d'environnement, problèmes connus, procédure de démarrage du stack complet local.
- [myrag/DEPLOYMENT.md](myrag/DEPLOYMENT.md) — procédure de déploiement Scaleway pas-à-pas + troubleshooting.
- [openwebui/README.md](openwebui/README.md) — plugin Open WebUI pour consommer les collections publiées.

## Licence

(À définir.)
