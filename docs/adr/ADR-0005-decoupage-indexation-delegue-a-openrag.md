# ADR-0005 — Déléguer tout le découpage d'indexation à OpenRAG

- **Statut** : Accepted (branche `refactor/decoupage-openrag`)
- **Date** : 2026-10-19
- **Décideurs** : PO bêta
- **Sujet** : qui découpe les documents en passages cherchables, et ce qu'il reste du
  découpage maison.

## Contexte

Cinq faits du code ont pesé :

1. Deux pipelines d'ingestion coexistaient : les textes (.txt, .md, .csv) étaient découpés
   par Mes collections (`chunker.py`, cinq stratégies) puis envoyés morceau par morceau ;
   les documents (PDF, Word…) partaient entiers et OpenRAG les découpait.
2. Le chunker par défaut d'OpenRAG (`structured_section`) couvre déjà les cas visés :
   articles de code juridique atomiques (motif feuille `Article L###-#`), découpe sur les
   titres, chemin d'en-tête préfixé à chaque passage (`prepend_heading_path`), contextual
   retrieval.
3. La sensibilité n'était jamais transmise à OpenRAG : `upload_chunk` n'envoie que le
   fichier et son nom.
4. Le graphe de références croisées se construisait depuis les fichiers `Article-*.md` que
   notre découpage article produisait dans la partition.
5. OpenRAG refuse le CSV (absent de ses mimetypes et de ses loaders).

## Options considérées

| Option | Pour | Contre |
|---|---|---|
| A. Maintenir le découpage maison | Contrôle du grain ; fichiers `Article-*.md` nommés | Deux chunkers à maintenir ; stratégies redondantes avec `structured_section` |
| **B. Déléguer tout le découpage d'indexation à OpenRAG** | Un seul pipeline ; la sensibilité part enfin en métadonnée ; moins de code sur le chemin critique | Citations au grain document + chemin d'en-tête ; CSV refusé ; le build du graphe perd ses fichiers Article |
| C. Reconstruire le graphe depuis les morceaux OpenRAG | Zéro découpage local restant | Heuristique fragile sur les chemins d'en-tête préfixés |

## Décision

- **B** : tout fichier, texte compris, part entier chez OpenRAG via `upload_document` ;
  Mes collections ne découpe plus rien pour l'indexation.
- Le graphe se construit depuis les **fichiers sources conservés localement** (découpage de
  structuration, stratégie article, rien n'est indexé par ce chemin) ; les boutons
  « Construire » et « Importer » sont désactivés dans le front — la feature se réactive en
  les débloquant.
- `chunker.py` est conservé entier, comme bibliothèque pure du graphe, hors indexation.
- Le CSV est refusé (convertir en .txt ou .md) ; la sensibilité part en métadonnée
  document ; les « types de collection » deviennent des **consignes** (prompt seul) ; la
  réindexation devient une action de maintenance (vider la partition, renvoyer les sources
  telles quelles, sensibilité reprise par fichier).
- Les presets d'indexation d'OpenRAG (choix par collection à la création) : en suivi ;
  rien dans cette décision ne doit les empêcher.

## Conséquences

- Les citations passent du numéro d'article (porté par le nom de fichier) au document et
  son chemin d'en-tête.
- Les collections existantes ne sont pas migrées : leurs anciens morceaux restent
  cherchables ; une réindexation manuelle les convertit au nouveau régime.
- Les amorces se ré-ingèrent au premier démarrage suivant (l'étiquette versionnée passe à
  `openrag-v1`) ; l'idempotence par checksum est conservée.
- Nouvelle colonne `source_files.sensitivity`, posée par la migration au démarrage.

## Points ouverts

- Exposer les presets d'indexation d'OpenRAG dans l'assistant de création et les
  paramètres (PR dédiée) ; un changement de preset après indexation exige une réindexation.
- Réactivation du graphe : débloquer les boutons ; à terme, graphes par sections ou par
  questions (stratégies conservées dans `chunker.py`).
