# Piloter la qualité d'une collection

Une collection répond-elle juste ? La page **Qualité** (`/c/{collection}/qualite`, réservée à qui
gère la collection) répond à cette question et donne de quoi agir. L'étape 4 de l'assistant de
création, « Questions et qualité », en est le début : les mêmes composants, les mêmes données.
Rien de ce qui est fait à l'étape 4 ne se perd en la quittant.

## Le jeu de questions de référence

Un seul concept : la **question de référence**. Elle porte :

- la question, telle qu'un usager la poserait, et sa **réponse de référence** (la bonne réponse),
  toutes deux modifiables en place, d'un clic ;
- son **origine** : générée par l'IA (ragas, par persona, voir [generation.md](generation.md)),
  importée (JSON ou CSV), saisie, tirée d'un avis d'usager, ou posée par une amorce ;
- son état de relecture : à relire, validée, rejetée. **Seules les questions validées sont mesurées.**
- deux drapeaux : **hors sujet** (la bonne réponse est un refus poli) et **réponse fiable** (la réponse
  peut être donnée telle quelle ; voir « Réponses fiables » plus bas) ;
- son **dernier verdict**, et la date de la mesure qui l'a donné.

Règles tenues par le serveur ([questions_store.py](../myrag/app/services/questions_store.py)) :

- modifier la question ou la réponse **efface le dernier verdict** (la mesure ne vaut plus) ;
- « réponse fiable » exige une question validée et non hors sujet ; rejeter la question retire le drapeau ;
- une question hors sujet est complète sans réponse : importée, elle entre validée ;
- deux questions identiques (casse, accents et ponctuation mis à part) ne coexistent pas : 409 ;
- supprimer une rédaction (run de génération) garde ses questions validées : elles sont détachées
  du run, pas effacées.

Les paires générées par ragas **sont** des questions du jeu (origine « générée ») : une rédaction
terminée les fait apparaître « à relire ».

### Importer, exporter

Import : un JSON `{"questions": [...]}` au format de l'ancien jeu de test (`question`,
`expected_answer`, `must_cite`, `tags`, `out_of_scope`), un export eval-rag (`samples`, `answer`,
`persona_name`, `metadata`), ou un CSV avec une colonne `question` et de préférence `reponse`.
L'import ne remplace rien : il rend `{crees, doublons, ignores}`. Export : JSON ou CSV, de tout le jeu.

### Ce qui a été versé dans le jeu (migration)

Trois magasins tenaient des questions sans se parler. Au démarrage, une migration idempotente
([migration_questions.py](../myrag/app/services/migration_questions.py)) les verse dans le jeu ; chaque
question versée porte une `source_ref` unique par collection, une seconde passe ne crée rien :

| Ancien magasin | Devient |
|---|---|
| `eval_datasets` (jeux de test, banque du bac à sable, amorces) | origine amorce, générée ou importée ; validée si elle a une réponse écrite par une personne |
| `data/<collection>/qr_cache.json` (« réponses validées ») | validée ; « fiable » seulement si la réponse venait d'un avis corrigé ; le fichier est renommé `qr_cache.migre.json` |
| avis promus vers un jeu de test | origine avis, à relire, réponse vide |

Les anciennes routes `/api/eval/*` et `/api/qr-cache/*` répondent **410** ; les anciennes tables sont
conservées (retour arrière possible), plus rien n'y écrit.

## La mesure

« Mesurer » pose chaque question validée à la collection, comme le bac à sable (recherche, puis
replis), et compare la réponse obtenue à la réponse de référence. La mesure tourne **sur le serveur** :
quitter la page ne l'arrête pas, son résultat s'enregistre, et la page la reprend au retour.

| Verdict | Quand |
|---|---|
| Conforme | la réponse dit l'essentiel de la référence |
| Partielle | une partie seulement ; ou un terme exigé (`must_cite`) manque |
| Non conforme | fausse, ou à côté |
| Refus correct | question hors sujet, et la collection a refusé |
| Réponse inventée | question hors sujet, et la collection a répondu quand même |
| Aucun passage trouvé | la recherche n'a rien rendu |
| Erreur | la question n'a pas pu être posée (délai, service) |

Le **juge** est un appel OpenAI-compatible au fournisseur de la génération
([juge.py](../myrag/app/services/mesure/juge.py)) : la question, la référence et la réponse lui sont
données comme des données encadrées, jamais comme des consignes ; il rend un JSON
`{verdict, justification}`, réparé une fois s'il est mal formé. Si le juge est injoignable, la mesure
compare par **similarité de mots** (méthode affichée : on ne compare pas une mesure « juge » à une
mesure « similarité »). La mesure ne dépend pas de ragas.

Le **score** (0 à 100) compte les conformes et refus corrects pour 1, les partielles pour ½, le reste
pour 0 ; les questions en erreur sont exclues du calcul. La
synthèse affiche l'appréciation : très bonne (≥ 80), satisfaisante (≥ 60), à améliorer (≥ 40),
insuffisante.

Coût : par question, 1 à 3 appels à OpenRAG et 1 appel au juge ; le débit est partagé avec la
génération (une seule limite par processus). Une mesure à la fois par collection, refusée pendant
une rédaction (409), plafonnée en nombre de questions (413).

Une question se re-teste seule depuis son volet (« Re-tester cette question ») : rien n'est enregistré.

## La page

- **Aujourd'hui** : la dernière mesure terminée, son appréciation, et la satisfaction des usagers (👍 / 👎).
- **Dans le temps** : la courbe des dix dernières mesures.
- **À faire** : des actions déduites par règles ([qualite.py](../myrag/app/services/qualite.py)) —
  constituer le jeu, relire, mesurer, corriger les échecs, revoir le découpage (beaucoup de « aucun
  passage »), ajouter une règle de garde (une réponse inventée), traiter les avis.
- Quatre onglets : **Jeu de questions**, **Mesures** (historique, détail question par question,
  filtre par verdict), **Avis des usagers** (« En faire une question de référence » : la bonne réponse
  écrite, la question entre validée), **Leviers**.
- Le **volet d'une question** montre la référence (modifiable), la réponse obtenue, le verdict et sa
  raison, et « Que faire ? » selon le défaut : corriger la référence, revoir le découpage, préciser les
  consignes, marquer la réponse fiable.

La fiche de la collection garde un résumé (score, satisfaction, avis à relire) et le bouton
« Piloter la qualité ». Les anciens onglets Avis, Réponses validées et Questions générées de la fiche
mènent à la page Qualité.

## Les leviers

- **Découpage** : choisir une autre stratégie et redécouper les documents conservés, avec le suivi
  des travaux d'indexation. Les passages sont effacés puis recréés : la collection répond mal pendant
  quelques minutes. Mesurer à nouveau ensuite.
- **Consignes** : un extrait, le lien vers leur modification, et l'ajout d'une **règle de garde**
  (refuser poliment les questions hors sujet).
- **Réponses fiables** : le nombre de réponses marquées.

## Réponses fiables (à venir)

Une réponse fiable est validée par le gestionnaire pour être **donnée telle quelle**. Le drapeau est
posé et compté ; le service qui la sert en priorité dans le bac à sable (avant la recherche) est
préparé mais pas branché. Limite connue : l'assistant (Open WebUI) interroge OpenRAG directement,
il ne passera pas par ce raccourci.

## Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `MYCOLLECTIONS_MESURE_JUGE_MODELE` | `` | Modèle du juge ; vide ⇒ celui de la génération |
| `MYCOLLECTIONS_MESURE_PARALLELISME` | `2` | Questions posées en même temps |
| `MYCOLLECTIONS_MESURE_QUESTIONS_MAX` | `200` | Questions au plus par mesure (au-delà : 413) |
| `MYCOLLECTIONS_MESURE_DUREE_MAX_S` | `1800` | Durée au-delà de laquelle la mesure s'arrête en erreur |
| `MYCOLLECTIONS_MESURE_DELAI_APPEL_S` | `120` | Délai accordé à chaque appel (collection, juge) |

Une mesure en cours lors d'un redémarrage est marquée « interrompue » : il faut la relancer.

## Routes

Toutes sous `/api/collections/{collection}/qualite`, réservées à qui gère la collection.

| Route | Rôle |
|---|---|
| `GET ""` | synthèse : comptes du jeu, dernière mesure, tendance, satisfaction, actions |
| `GET/POST /questions` | lister (filtres `origine`, `relecture`, `verdict` dont `jamais`, `fiable`, `hors_sujet`, `persona`, `q`) ; ajouter |
| `POST /questions/import` | importer (`questions` ou `samples`) |
| `POST /questions/depuis-avis/{feedback_id}` | un avis devient une question (`{reponse}`) |
| `GET /questions/export?format=json\|csv` | exporter |
| `GET/PATCH/DELETE /questions/{id}` | lire (avec son dernier résultat), modifier, supprimer |
| `POST /questions/{id}/tester` | re-tester une question, sans rien enregistrer |
| `POST /mesures` | lancer une mesure (202) |
| `GET /mesures`, `GET/DELETE /mesures/{id}` | historique, une mesure |
| `GET /mesures/{id}/resultats?verdict=` | le détail question par question |

## Vérifier dans un navigateur

Le comportement d'un volet, d'une édition en place ou d'un suivi se joue dans un navigateur. Un faux
OpenRAG suffit : une route `/v1/chat/completions` qui rend des réponses scriptées pour les modèles
`openrag-…`, et un JSON `{verdict, justification}` pour le juge.
