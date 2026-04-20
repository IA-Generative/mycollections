# TODO

Backlog des travaux non urgents. Les items urgents (bugs, blockers) passent
par des commits directs ou des issues — ici on ne garde que ce qu'on veut
suivre sans le perdre.

## Telemetrie — compteur d'interrogations par collection

Afficher sur chaque fiche collection (page `/c/{id}`) le nombre de requetes
RAG qu'a recues son corpus. Aujourd'hui OpenRAG n'expose aucun compteur par
partition ; son middleware Prometheus aggregate par `endpoint/method/status`
uniquement.

**Option retenue : compteur Prometheus par partition, cote OpenRAG.**

Travaux :
- Modifier `openrag/openrag/routers/monitoring.py` (`MonitoringMiddleware`)
  pour extraire le champ `model` du body des requetes `/chat/completions`
  et `/completions`, en deriver la partition (`strip('openrag-')`), et
  incrementer un `openrag_partition_queries_total{partition=...}`.
- Exposer ce compteur sur l'endpoint `/metrics` existant (admin-only).
- Cote MyRAG, ajouter un petit client qui scrape `/metrics` (ou reutiliser
  `openrag_client`), parse le counter `openrag_partition_queries_total`
  pour une partition donnee, et le retourne via `/api/collections/{n}/stats`.
- Frontend : afficher la valeur dans le header de la fiche collection,
  avec un tooltip "Depuis le dernier redemarrage du service".

Limites connues :
- Compteur en memoire — reset au restart du pod OpenRAG. Acceptable pour
  "activite recente". Pour de la persistence, passer a une table SQL
  `query_logs` (variante plus lourde, option 3 evaluee puis ecartee).
- Ne distingue pas les utilisateurs (on a juste un total). Si plus tard
  on veut par-utilisateur, il faudra passer par une table SQL.
