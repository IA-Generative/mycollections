# TODO

Backlog des travaux non urgents. Les items urgents (bugs, blockers) passent
par des commits directs ou des issues — ici on ne garde que ce qu'on veut
suivre sans le perdre.

---

## Bugs connus (pre-existants a la mise en prod 2026-04-19)

### P3 — Playground crash sur `/api/playground/{n}/chat`

`OpenRAGClient` n'a pas de methode `chat()`. Les appels dans
[playground.py](myrag/app/routers/playground.py) (lignes 122, 212, 266)
font un `client.chat(...)` qui crashe en 500. Bloque :
- le wizard etape 4 (test d'eval)
- tout le tab Playground sur la fiche collection

Fix : implementer `OpenRAGClient.chat()` en wrappant un POST vers
`/v1/chat/completions` d'OpenRAG avec `model=openrag-{partition}`.

### P5 — `POST /graph/{name}/build` renvoie 404 "No documents in collection"

Meme apres indexation OK. Viewer Cytoscape tourne a vide. Pas critique
(le graph n'est pas un feature critique sur la premiere vague), mais a
fixer avant d'annoncer la fonctionnalite.

### P2 — Chunker `article` renvoie 0 chunk sur MD simple

Crashe l'upload quand la strategy est `article`. Workaround actuel :
wizard force `auto`. A corriger dans
[chunker.py](myrag/app/services/chunker.py) pour que `article` tombe
gracieusement sur un split par paragraphe quand il ne trouve pas de
marqueurs article.

---

## Ameliorations UX

### Compteur d'interrogations par collection

Afficher sur chaque fiche collection (page `/c/{id}`) le nombre de
requetes RAG qu'a recues son corpus. Aujourd'hui OpenRAG n'expose aucun
compteur par partition ; son middleware Prometheus agrege par
`endpoint/method/status` uniquement.

**Option retenue : compteur Prometheus par partition, cote OpenRAG.**

Travaux :
- Modifier `openrag/openrag/routers/monitoring.py` (`MonitoringMiddleware`)
  pour extraire le champ `model` du body des requetes `/chat/completions`
  et `/completions`, en deriver la partition (`strip('openrag-')`), et
  incrementer `openrag_partition_queries_total{partition=...}`.
- Exposer ce compteur sur `/metrics` (admin-only, deja existant).
- Cote MyRAG, ajouter un client qui scrape `/metrics`, parse le counter
  pour une partition donnee, et le retourne via
  `/api/collections/{n}/stats`.
- Frontend : afficher la valeur dans le header de la fiche collection,
  tooltip "Depuis le dernier redemarrage du service".

Limites :
- Compteur en memoire — reset au restart du pod OpenRAG. Acceptable pour
  "activite recente". Pour de la persistence : passer a une table SQL
  `query_logs` (variante plus lourde, ecartee pour l'instant).
- Pas de ventilation par utilisateur.

### Flux "adopter une collection orpheline"

Le badge "sans fiche" est en place sur la home. Le backend sait adopter
(commit 716b4ac). Reste cote frontend : sur une carte orpheline, CTA
explicite "Adopter cette collection" qui ouvre un formulaire pre-rempli
(nom = partition, strategy = auto, sensitivity = public) pour creer
la fiche en un clic, plutot que de passer par le wizard complet.

### Message d'erreur Drive 403 — deuxieme passe

Le message est maintenant honnete (cause audience ou provisionnement)
et affiche un lien vers Drive. Amelioration : quand on detecte une
erreur 403 Drive, declencher **automatiquement** une tentative de
renew-token silencieuse avant d'afficher le message (une proportion
des 403 se resolvent par un simple refresh, pas besoin d'embeter
l'utilisateur).

---

## Plan d'integration global (Lots 1-5, avril 2026)

Plan complet dans la memoire projet (`project_integration_plan.md`).
Suivi synthetique ici :

| Lot | Contenu | Statut |
|-----|---------|--------|
| Lot 1 — Auth | OIDC middleware, sync Keycloak groups, OWUI config | Fait |
| Lot 2 — Admin | Profils d'indexation par partition, eval Q&A + override | Partiel (eval OK, override = cache semantique a faire) |
| Lot 3 — Drive | Connecteur Drive + liens dans les sources | Fait (picker + sync download OK) |
| Lot 4 — Feedback | Forwarder OWUI feedback, promotion review → Q&A | A faire |
| Lot 5 — Comms+ERI | Annonces/sondages, endpoints ERI pour OWUI | A faire |

### Q&A override comme cache semantique (Lot 2)

Agit comme un cache semantique verifie **avant** la pipeline RAG. Si une
question tres proche d'une Q&A validee par l'admin arrive, servir
directement la reponse validee au lieu de regenerer via LLM. Gain :
qualite constante sur les questions frequentes + reduction cout LLM.

### Forwarder feedback OWUI (Lot 4)

OWUI n'a pas de webhook natif pour les ratings (+1/-1 sur les messages).
Il faut une pipeline custom OWUI ou un cron qui poll la DB OWUI et
push vers MyRAG. A prototyper apres ouverture aux utilisateurs (sinon
pas de feedback a forwarder).

### Annonces + sondages (Lot 5)

OpenRAG gere le contenu + le targeting (qui voit quoi), l'affichage et
la messagerie restent externes (Tchap, email, webhook). Besoin d'un
module admin cote MyRAG pour rediger/planifier les annonces.

---

## QA et mise en production

### 12 parcours utilisateur a valider en prod

Avant d'ouvrir aux utilisateurs finaux, rejouer manuellement en
navigateur les 12 parcours du wizard + admin sur
`https://mycollections.fake-domain.name`. Liste exhaustive a redresser
(actuellement informelle).

### Backup automatise de la DB `myrag` (PostgreSQL)

Actuellement aucune sauvegarde programmee. A minima :
- Dump quotidien via CronJob K8s vers le bucket Object Storage Scaleway
- Retention 30 jours
- Restoration test trimestrielle
