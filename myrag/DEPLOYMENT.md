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

## 1.5. Provisionner le user bot Drive (source "drive" uniquement)

MyRAG s'authentifie à Drive via `client_credentials` sur le client Keycloak `mycollections-drive`. Drive (Suite Numérique) exige un `core.User` local dont le `sub` correspond au service account — pas de création auto pour les service accounts. On provisionne un user "bot" dédié ; idempotent.

```bash
# sub du service account mycollections-drive = preferred_username "service-account-mycollections-drive"
SUB=$(curl -s -X POST https://mysso.fake-domain.name/realms/openwebui/protocol/openid-connect/token \
  -d "grant_type=client_credentials&client_id=mycollections-drive&client_secret=$DRIVE_CLIENT_SECRET&scope=openid" \
  | python3 -c "
import sys,json,base64
t=json.load(sys.stdin)['access_token']; p=t.split('.')[1]+'=' * (4 - len(t.split('.')[1])%4)
print(json.loads(base64.urlsafe_b64decode(p))['sub'])")

P=$(kubectl -n miraiku get pod -l app.kubernetes.io/component=backend,app.kubernetes.io/name=drive --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
kubectl -n miraiku exec $P -- python -c "
import django; django.setup()
from core.models import User
SUB = '$SUB'
try:
    u = User.objects.get(sub=SUB); print('already exists', u.id)
except User.DoesNotExist:
    u = User(
        sub=SUB, email='mycollections-drive@bot.local',
        full_name='MyCollections Drive Bot', short_name='mycollections-drive',
        is_device=True, is_active=True,
        claims={'bot': True, 'for': 'mycollections'},
    )
    u.set_unusable_password()   # bot: no interactive login
    u.save()
    print('created', u.id)
"
```

**Partage des dossiers** : le bot ne voit par défaut aucun dossier. Pour qu'il puisse indexer un dossier, un admin doit le partager à `mycollections-drive@bot.local` via l'UI Drive (même workflow qu'un collègue humain). Permissions recommandées : `viewer` (lecture seule).

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

## 4.5. Branchement OWUI ↔ OpenRAG (one-shot par cluster)

Sans cette étape, le bouton **Publier** crée bien un wrapper de modèle dans OWUI mais cliquer dessus dans OWUI renvoie `404: Model not found` — OWUI n'a pas de provider qui expose les `openrag-<col>`. Une fois fait, c'est définitif : chaque future publication MyRAG marche sans intervention admin.

### 4.5.1. Ajouter OpenRAG comme provider OpenAI dans OWUI

OWUI auto-découvre tous les modèles (`/v1/models`) de chaque URL listée dans `OPENAI_API_BASE_URLS`. On ajoute l'URL publique de la VM OpenRAG comme troisième entrée (à côté de `pipelines:9099` et `api.scaleway.ai`).

```bash
# Vérifier d'abord que /v1/models répond bien (15+ modèles openrag-* attendus)
curl -sS "https://api.openrag.fake-domain.name/v1/models" \
  -H "Authorization: Bearer ${OPENRAG_ADMIN_TOKEN}" \
  | python3 -c "import sys,json; print(len(json.load(sys.stdin)['data']), 'modèles')"

# Ajouter OpenRAG. set env merge proprement avec les valeurs existantes
# (Pipelines + Scaleway Direct) — il suffit de redonner les 3 listes ;-séparées
# en entier. On lit les clés Pipelines et Scaleway depuis owui-socle-secrets pour
# ne pas les écrire en clair dans la commande.
kubectl -n miraiku set env deploy/openwebui \
  OPENAI_API_BASE_URLS="http://pipelines:9099/v1;https://api.scaleway.ai/<SCW_PROJECT_ID>/v1;https://api.openrag.fake-domain.name/v1" \
  OPENAI_API_KEYS="$(kubectl -n miraiku get secret owui-socle-secrets -o jsonpath='{.data.PIPELINES_API_KEY}' | base64 -d);$(kubectl -n miraiku get secret owui-socle-secrets -o jsonpath='{.data.SCW_SECRET_KEY_LLM}' | base64 -d);<OPENRAG_ADMIN_TOKEN>" \
  OPENAI_API_CONFIGS='[{"prefix":"scaleway-general.","name":"Pipelines"},{"prefix":"","name":"Scaleway Direct"},{"prefix":"openrag-","name":"OpenRAG MyRAG"}]'

kubectl -n miraiku rollout status deploy/openwebui --timeout=120s
```

### 4.5.2. Donner à MyRAG la clé API admin OWUI

Le router `/api/collections/{name}/publish` du backend MyRAG appelle `POST /api/v1/models/create` côté OWUI pour matérialiser le wrapper d'alias. OWUI v0.8.12 exige soit un cookie de session (impossible depuis un pod), soit une **clé API personnelle** d'un compte admin.

```bash
# 1. Dans OWUI : Paramètres > Compte > Clés API > "+ Créer une clé"
#    (le compte qui crée la clé doit être admin OWUI — la clé hérite du rôle).
# 2. Stocker dans le secret myrag-secrets :
kubectl -n miraiku patch secret myrag-secrets --type=merge \
  -p "{\"stringData\":{\"OWUI_ADMIN_API_KEY\":\"sk-<la-clé-générée>\"}}"

# 3. Le pod backend doit être redémarré pour relire le secret
kubectl -n miraiku rollout restart deploy/myrag-backend
kubectl -n miraiku rollout status deploy/myrag-backend
```

### 4.5.3. Vérification end-to-end

```bash
# Diagnostic : la clé est-elle valide, admin, et le base model existe-t-il ?
curl -sS https://mycollections.fake-domain.name/api/owui/probe | python3 -m json.tool

# Attendu (ordre des calls) :
# - GET /api/v1/users/      → 200 + JSON {users:[…role=admin…]}    (clé admin)
# - GET /api/models         → 200 + 30+ entrées dont 15 openrag-*  (provider OK)

# Test d'un publish complet
curl -sS -X POST https://mycollections.fake-domain.name/api/collections/<col>/publish \
  -H 'Content-Type: application/json' \
  -d '{"alias_enabled":true,"alias_name":"📚 <col>","alias_description":"Test","visibility":"all"}' \
  | python3 -m json.tool
# Doit retourner : "owui": {"synced": true, "error": null, "model_id": "openrag-<col>"}

# Et dans le picker OWUI sur https://mychat.fake-domain.name/, le modèle "📚 <col>"
# doit ouvrir une conversation fonctionnelle (pas de 404).
```

### 4.5.4. Persistance dans le repo source

Les `kubectl set env` et `patch secret` ci-dessus sont **éphémères** : un futur `kubectl apply -f` du repo `owuicore-main` les écraserait. Pour persister :

- Mettre à jour le ConfigMap source `owui-socle-config` dans [`owuicore-main/k8s/base/configmap.yaml`](../../owuicore-main/k8s/base/configmap.yaml) avec les 3 nouvelles valeurs `OPENAI_API_BASE_URLS`, `OPENAI_API_KEYS`, `OPENAI_API_CONFIGS`.
- Le secret `myrag-secrets` est géré par `myrag/k8s/secret.yaml` (gitignored) — penser à y ajouter `OWUI_ADMIN_API_KEY` si on régénère le secret depuis le template.

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
