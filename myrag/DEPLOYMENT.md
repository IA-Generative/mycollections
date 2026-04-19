# Déploiement Scaleway — Mes collections

Procédure pour déployer le backend + frontend de Mes collections sur le cluster Scaleway Kapsule `k8s-par-brave-bassi` dans le namespace `miraiku`, en pointant sur la VM OpenRAG publique `api.openrag.fake-domain.name`.

## Topologie cible

```
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│  Cluster Kapsule                 │    │  VM Scaleway (51.159.119.187)    │
│  k8s-par-brave-bassi             │    │  api.openrag.fake-domain.name    │
│  namespace miraiku               │    │                                  │
│                                  │    │  Traefik + HTTPS public          │
│  mycorpus.fake-domain.name       │    │  OpenRAG + Milvus + PG + MinIO   │
│    ├── /api → myrag-backend:8200 │═══▶│  Bearer token: sk-openrag-...    │
│    ├── /health → myrag-backend   │    │                                  │
│    ├── /graph → myrag-backend    │    └──────────────────────────────────┘
│    ├── /articles → myrag-backend │
│    └── /     → myrag-frontend:3000│    ┌──────────────────────────────────┐
│                                  │═══▶│  Shared postgres (miraiku)       │
│                                  │    │  DB: myrag, user: app            │
│                                  │    └──────────────────────────────────┘
└──────────────────────────────────┘
```

## Pré-requis

- `kubectl` configuré sur le context `admin@k8s-par-brave-bassi`
- `scw` CLI authentifié (pour la registry)
- Accès admin à la registry `rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/`
- DB `myrag` créée sur `postgres.miraiku.svc.cluster.local` (provisionnée à chaque init via [`postgres/init/01-create-databases.sql`](../../owuicore-main/postgres/init/01-create-databases.sql) du repo `owuicore-main`)

## 1. Build + push des images

```bash
cd /Users/etiquet/Documents/GitHub/mycollections
TAG=$(git rev-parse --short HEAD)

# Login Scaleway Container Registry
scw registry login

# Backend — IMPORTANT: --platform linux/amd64 si tu builds depuis un Mac ARM64,
# sinon exec format error au pod start sur Kapsule (AMD64).
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:latest \
  myrag/

# Frontend (build statique Nuxt + nginx), meme contrainte de plateforme.
docker buildx build --platform linux/amd64 --push \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:$TAG \
  -t rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:latest \
  myrag/frontend/
```

Les build args du Dockerfile frontend baken les URLs publiques (`MYRAG_API_URL=/api`, `KEYCLOAK_URL=https://mysso.fake-domain.name`, `AUTH_ENABLED=true`). Pour une autre cible (staging), re-builder avec `--build-arg MYRAG_API_URL=... --build-arg KEYCLOAK_URL=...`.

## 2. Créer la DB PostgreSQL

La DB `myrag` est déjà dans l'init SQL d'owuicore-main (cf. `postgres/init/01-create-databases.sql`). Pour une instance PG déjà en place, créer manuellement :

```bash
POD=$(kubectl -n miraiku get pod -l app=postgres -o jsonpath='{.items[0].metadata.name}')
kubectl -n miraiku exec $POD -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE myrag OWNER app"'

# Vérification
kubectl -n miraiku exec $POD -- sh -c \
  'psql -U "$POSTGRES_USER" -d postgres -t -c "SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY datname"'
```

## 3. Préparer le secret local

```bash
cp myrag/k8s/secret.yaml.template myrag/k8s/secret.yaml
# Editer myrag/k8s/secret.yaml pour renseigner les vraies valeurs
# Le fichier est git-ignored (cf. .gitignore racine).
```

Variables à renseigner (déjà pré-remplies avec les valeurs du brief) :
- `OPENRAG_ADMIN_TOKEN` : token Bearer de la VM OpenRAG
- `KEYCLOAK_CLIENT_SECRET` : secret du client Keycloak `openrag` (confidential)
- `LEGIFRANCE_CLIENT_ID` / `LEGIFRANCE_CLIENT_SECRET` : optionnels

> **Note** : les credentials PostgreSQL ne sont PAS dans ce secret. `DATABASE_URL` est composée à l'exécution du pod depuis le secret partagé `owui-socle-secrets` (keys `POSTGRES_USER` / `POSTGRES_PASSWORD`) via la substitution `$(VAR)` de Kubernetes, cf. `deployment-backend.yaml`.

## 4. Apply des manifests

L'ordre suit : secret → configmap → pvc → services → deployments → ingress.

```bash
kubectl apply -f myrag/k8s/secret.yaml
kubectl apply -f myrag/k8s/configmap.yaml
kubectl apply -f myrag/k8s/pvc.yaml
kubectl apply -f myrag/k8s/service-backend.yaml
kubectl apply -f myrag/k8s/service-frontend.yaml
kubectl apply -f myrag/k8s/deployment-backend.yaml
kubectl apply -f myrag/k8s/deployment-frontend.yaml
kubectl apply -f myrag/k8s/ingress.yaml

kubectl -n miraiku rollout status deploy/myrag-backend --timeout=120s
kubectl -n miraiku rollout status deploy/myrag-frontend --timeout=60s
kubectl -n miraiku get pod,svc,ingress -l 'app in (myrag-backend,myrag-frontend)'
```

## 5. DNS

Le CNAME `mycorpus.fake-domain.name → mychat.fake-domain.name.` est déjà configuré (vérifiable via `scw dns record list dns-zone=fake-domain.name`). cert-manager génère le certificat TLS automatiquement via `letsencrypt-prod` dès que l'Ingress est en place (compter 1-2 minutes).

```bash
# Vérifier l'émission du certificat
kubectl -n miraiku get certificate mycorpus-tls -o wide
```

## 6. Smoke test

```bash
# Santé backend via ingress
curl -s https://mycorpus.fake-domain.name/health

# Page d'accueil frontend (HTML Nuxt)
curl -s https://mycorpus.fake-domain.name/ | head -20

# Santé depuis un pod dans le cluster (sans passer par l'ingress)
kubectl -n miraiku run smoke --rm -it --image=curlimages/curl --restart=Never -- \
  curl -s http://myrag-backend.miraiku.svc.cluster.local:8200/health
```

Puis rejouer les parcours usagers depuis un navigateur sur `https://mycorpus.fake-domain.name`.

## 7. Rollback

```bash
# Revenir au tag précédent
TAG_ROLLBACK=<sha-d'avant>
kubectl -n miraiku set image deploy/myrag-backend \
  backend=rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-backend:$TAG_ROLLBACK
kubectl -n miraiku set image deploy/myrag-frontend \
  frontend=rg.fr-par.scw.cloud/funcscwnspricelessmontalcinhiacgnzi/myrag-frontend:$TAG_ROLLBACK

# Ou rollback du rollout
kubectl -n miraiku rollout undo deploy/myrag-backend
kubectl -n miraiku rollout undo deploy/myrag-frontend
```

## 8. Troubleshooting

### Backend en CrashLoopBackOff

```bash
kubectl -n miraiku logs -l app=myrag-backend --tail=100
```

Causes fréquentes :
- **`FATAL: database "myrag" does not exist`** → jouer l'étape 2 (créer la DB)
- **`HTTPStatusError 401 from api.openrag.fake-domain.name`** → vérifier `OPENRAG_ADMIN_TOKEN` dans le secret
- **`no route to host`** vers OpenRAG → firewall de la VM : vérifier que les egress Kapsule sont autorisés sur :443

### Frontend affiche la page d'accueil Nuxt (welcome)

Le build image a bien été fait depuis `mycollections/myrag/frontend/` et pas depuis l'ancien emplacement `openrag/integrations/myrag/frontend/`. Rebuilder avec le bon contexte.

### `exec /docker-entrypoint.sh: exec format error` au pod start

Image construite sur Mac ARM64 (darwin/arm64) alors que le cluster tourne en AMD64. Rebuilder avec `docker buildx build --platform linux/amd64 --push`.

### `can't subtract offset-naive and offset-aware datetimes` dans les logs backend

Le code utilise tz-aware datetimes mais SQLAlchemy `DateTime` mappe sur `TIMESTAMP WITHOUT TIME ZONE` sur PostgreSQL. Assure-toi que `utcnow()` dans `app/models/db.py` retourne bien un datetime naive (`.replace(tzinfo=None)`). Corrigé à partir du commit 968ab8e.

### Login Keycloak renvoie "invalid redirect_uri"

Dans Keycloak (realm `openwebui`), client `myrag-front`, ajouter dans Valid Redirect URIs : `https://mycorpus.fake-domain.name/auth/callback`.

## 9. Fichiers critiques

- [myrag/frontend/Dockerfile](frontend/Dockerfile) — build statique Nuxt + nginx
- [myrag/frontend/nginx.conf](frontend/nginx.conf) — SPA fallback
- [myrag/k8s/deployment-backend.yaml](k8s/deployment-backend.yaml) — API FastAPI port 8200
- [myrag/k8s/deployment-frontend.yaml](k8s/deployment-frontend.yaml) — nginx port 3000
- [myrag/k8s/configmap.yaml](k8s/configmap.yaml) — URLs publiques
- [myrag/k8s/secret.yaml.template](k8s/secret.yaml.template) — template des secrets applicatifs
- [myrag/k8s/ingress.yaml](k8s/ingress.yaml) — routing `/api` + `/graph` + `/articles` + `/`
