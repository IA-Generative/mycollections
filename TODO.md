# TODO

Backlog des travaux non urgents. Les items urgents (bugs, blockers) passent
par des commits directs ou des issues — ici on ne garde que ce qu'on veut
suivre sans le perdre.

---

## Bugs connus

### P5 — `POST /graph/{name}/build` renvoie 404 "No documents in collection"

*Constat d'avril 2026, a reverifier.* Meme apres indexation OK. Viewer Cytoscape tourne a vide. Pas critique
(le graph n'est pas un feature critique sur la premiere vague), mais a
fixer avant d'annoncer la fonctionnalite.

### P2 — Chunker `article` renvoie 0 chunk sur MD simple

*Toujours vrai : `chunk_by_article` rend une liste vide quand aucun en-tete d'article n'est trouve.*
Crashe l'upload quand la strategy est `article`. Workaround actuel :
wizard force `auto`. A corriger dans
[chunker.py](myrag/app/services/chunker.py) pour que `article` tombe
gracieusement sur un split par paragraphe quand il ne trouve pas de
marqueurs article.

---

## Ameliorations UX

### Compteur d'interrogations par collection

*En partie fait : le bac a sable enregistre chaque question (une collection, un instant, un
condense — jamais le texte), et l'accueil en tire le bilan « ce que vos collections ont rendu
possible ». Ce compte sous-estime l'usage : l'assistant et l'API d'OpenRAG n'y passent pas. Ce
qui suit reste la piste pour compter l'usage complet.*

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

Le badge "sans fiche" est en place sur les cartes de collection. Le backend sait adopter. Reste cote frontend : sur une carte orpheline, CTA
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

## Plan d'integration global (lots 1 a 5)

Suivi synthetique :

| Lot | Contenu | Statut |
|-----|---------|--------|
| Lot 1 — Auth | OIDC middleware, sync Keycloak groups, OWUI config | Fait |
| Lot 2 — Admin | Profils d'indexation par partition, eval Q&A + override | Partiel (eval OK, override = cache semantique a faire) |
| Lot 3 — Drive | Connecteur Drive + liens dans les sources | Fait (picker + sync download OK) |
| Lot 4 — Feedback | Remontee des avis OWUI, promotion review → Q&A | Fait (tirage periodique depuis la base d'OWUI, idempotent) |
| Lot 5 — Comms+ERI | Annonces/sondages, endpoints ERI pour OWUI | A faire |

### Q&A override comme cache semantique (Lot 2)

Agit comme un cache semantique verifie **avant** la pipeline RAG. Si une
question tres proche d'une Q&A validee par l'admin arrive, servir
directement la reponse validee au lieu de regenerer via LLM. Gain :
qualite constante sur les questions frequentes + reduction cout LLM.

### Annonces + sondages (Lot 5)

OpenRAG gere le contenu + le targeting (qui voit quoi), l'affichage et
la messagerie restent externes (Tchap, email, webhook). Besoin d'un
module admin cote MyRAG pour rediger/planifier les annonces.

---

## QA et mise en production

### Parcours utilisateur a valider en navigateur

Avant chaque ouverture a de nouveaux utilisateurs, rejouer a la main les
parcours du wizard et de l'administration. La liste est a ecrire : elle
est aujourd'hui informelle.

### Scenario de bout en bout, connecte, pour le bac a sable

Le survol d'une puce de source, l'ouverture de la fenetre de lecture et
les exports ne sont couverts par aucun scenario automatise connecte au
SSO. Ils ont ete verifies a la main et sur une page d'essai locale
(voir `docs/sources.md`).

### Backup automatise de la DB `myrag` (PostgreSQL)

Actuellement aucune sauvegarde programmee. A minima :
- Dump quotidien via CronJob Kubernetes vers un stockage objet
- Retention 30 jours
- Test de restauration trimestriel
