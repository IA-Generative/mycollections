# ADR-0003 — Assistants de recherche : une fiche-donnée et un harnais à planificateurs interchangeables

- **Statut** : Proposed (lot 0 du chantier, PR vers `beta`)
- **Date** : 2026-10-19
- **Décideurs** : PO bêta
- **Sujet** : interroger plusieurs sources (collections et connecteurs) derrière un seul
  « assistant », selon des consignes, sans perdre les droits ni ce qui existe.

## Contexte

Une collection publiée est aujourd'hui un modèle `openrag-<nom>` dans le socle (Open WebUI) et un
périmètre de la recherche de Mon portail (`/api/v1/search`). Les questions réelles traversent
plusieurs collections (un accord bilatéral, le code, un référentiel d'éligibilité) : la personne
doit savoir où chercher, et rien ne dit au modèle dans quel ordre ni avec quelle règle répondre.

Faits du code qui ont pesé :

1. Les droits sont ceux de `access.can_read` ; une collection hors droit est **ignorée** par la
   recherche, jamais refusée (contrat v1). Rien ne doit se calculer depuis un paramètre du client.
2. Le jeu de questions de référence existe (`paire_qa`), avec un drapeau `fiable` jamais servi.
3. Mes collections n'a pas de client d'embeddings (ADR-0002) ; OpenRAG cherche sur plusieurs
   partitions en un appel.
4. Dans le code existant, « l'assistant » désignait Open WebUI (`fiche_assistant.py`).

## Options considérées

### Option A — un prompt par assistant dans le socle
- Un modèle Open WebUI par assistant, avec un prompt système qui décrit les sources.
- Pour : rien à construire côté serveur.
- **Pourquoi pas** : ni droits par source, ni plan montrable, ni mesure possible ; chaque client
  (portail, fenêtre, API) referait le travail.

### Option B — une fiche-donnée et un harnais dans Mes collections
- La fiche (sources, régimes, consignes quand / chercher / répondre) est une donnée versionnée ;
  un harnais unique calcule le périmètre, sert les réponses fiables, planifie, exécute, fusionne,
  journalise ; un module `Planificateur` interchangeable (`toutes_les_sources`, `regles`, `llm`).
- Pour : une seule logique derrière toutes les entrées (socle, portail, fenêtre, API, MCP) ; le
  plan se montre et se mesure sur un banc.
- Contre : un chantier en huit lots ; un contrat à tenir stable.

### Option C — un orchestrateur externe, seulement par MCP
- **Pourquoi pas** : déplace les droits hors du service qui les connaît ; le portail et la
  fenêtre ne parlent pas MCP.

## Décision

**Option retenue : B.**

- **Contrat** (`myrag/app/harnais/contrat.py`, PR dédiée pour tout changement) : `FicheAssistant`,
  `Plan`, `Passage`, `Resultat`, `JournalPlan` (aucun champ de texte libre) ; interfaces
  `Planificateur`, `Connecteur`, `Apparieur` (`interfaces.py`). Texte canonique (clés triées,
  listes dans leur ordre, canaux et dérivés exclus) et empreinte sha256 ; projection sans perte
  d'un `Passage` sur `results[]` du contrat v1.
- **Tables** : `assistants` (brouillon), `assistant_versions` (immuables), `consignes`,
  `plans_journal`. Réponses fiables : `paire_qa.fiable`, pas de table nouvelle.
- **Compatibilité** : chaque collection publiée a son assistant à une source (« miroir »),
  créé à la publication ou au démarrage, mis en sommeil à la dépublication, jamais effacé hors
  purge. Le contrat v1 reste valide sans paramètre nouveau.
- **Droits** : voir un assistant = au moins une collection source lisible (ou créateur, ou
  administration) ; une source illisible est ignorée et comptée, jamais nommée ; modifier ou
  publier = gérer toutes ses collections. Une source `connecteur` n'ouvre aucun droit.
- **Drapeaux** `assistants` et `entraide` (capacites.json, faux par défaut) : route 404 et
  entrée de menu absente ; `MYCOLLECTIONS_CAPACITES_SURCHARGE` les allume sur une prévisualisation.
- **Vocabulaire** : « assistant » = assistant de recherche ; « le socle » = Open WebUI
  (`fiche_socle.py`) ; « agent » reste le mot du contrat Mes agents. « Harnais » ne paraît
  jamais dans l'interface.
- **Architecture d'information cible** : menu Accueil · Collections · Assistants · Réseau
  d'entraide · Catalogue · Guide ; collection : Vue d'ensemble · Documents · Qualité ·
  Publication ; assistant : Sources · Consignes · Réponses fiables · Qualité · Publication · Bac
  à sable. Le lot 0 pose les entrées sous drapeau ; le lot D applique le reste.

Lots : 0 socle ; A harnais (exécution, banc, règles, fiables, LLM, éligibilité, MCP et OpenAI) ;
B interface des assistants ; C socle et fenêtre embarquée ; D accueil et menus ; E étape 4 de
l'assistant de création ; F connecteur Resana ; G réseau d'entraide. Le mode de travail (branches,
périmètres, ordre de fusion) est tenu hors du dépôt.

## Conséquences

- **Positives** : un seul chemin de recherche, montrable et mesurable ; les droits restent
  calculés là où ils sont connus ; rien de ce qui existe ne se perd.
- **Négatives** : les routeurs du chantier sont montés dès le lot 0, vides ; une doublure du
  harnais (`MYCOLLECTIONS_DOUBLURE_ASSISTANTS`) vit dans l'application jusqu'au lot A.
- **À surveiller** : un planificateur qui contacte moins de sources mais perd plus d'un point
  sur le banc face à « toutes les sources » ; tout incident de droits au banc.

## Points ouverts

- Les questions propres d'un assistant (hors jeux de ses sources) n'ont pas de table.
- Rétention de `plans_journal` (il porte un condensé de personne) : non fixée.
- Le catalogue des connecteurs et leurs droits (lot A6) ; l'API d'éligibilité est sans authentification.
- L'enchaînement `avec` passe une référence courte (numéro d'article), pas un passage entier.
- `ADR-0004`, citée par `app/version.py`, n'est pas dans ce dossier.

## Suivi

- [ ] Lot 0 : PR « feat(assistants): le socle du chantier »
- [ ] `docs/assistants.md` rempli par les lots A et B
- [ ] Ligne `"assistants": false, "entraide": false` proposée au `capacites.json` du menu commun
