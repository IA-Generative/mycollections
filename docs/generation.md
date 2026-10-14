# Générer des paires question / réponse par persona

L'onglet « Questions générées » d'une collection fait rédiger, à partir de ses propres documents,
des paires **question / réponse de référence / passages d'origine**, du point de vue de
**personas** : la personne qui interroge la collection et la situation dans laquelle elle le fait.
Relues (valider / rejeter) puis exportées, ces paires servent à évaluer les réponses de
l'assistant. La bibliothèque est [ragas](https://github.com/vibrantlabsai/ragas) (`ragas.testset`),
en flux « pré-découpé » : elle travaille sur les passages déjà indexés, pas sur les fichiers.

Réservé à qui gère la collection (créateur, groupe `<racine>/<nom>-admin`, administration).

## Comment un run se déroule

| Phase | Ce qui se passe | Appels au modèle |
|---|---|---|
| `lecture` | 4 passages par paire demandée (plafond `MYCOLLECTIONS_GENERATION_MORCEAUX_MAX`), tirés en tourniquet sur tous les documents de la collection, relus dans OpenRAG (`/partition/<p>/chunks`, repli `file_detail` + `extract`) | aucun |
| `extraction` | ragas repère les entités nommées de chaque passage (et ses mots-clés si « Varier les sujets » est coché) | 1 par passage (2 avec les mots-clés) |
| `generation` | pour chaque passage retenu, ragas associe les personas aux sujets du passage, puis rédige une question du point de vue d'un persona, et sa réponse **à partir du seul passage** | ≈ 1 par passage consulté + 1 par paire |
| `enregistrement` | les paires sont écrites avec les identifiants de leur passage (`chunk_id` OpenRAG, `file_id`) et son texte | aucun |

Un run de 30 paires sur une collection assez grande consulte donc environ 120 passages :
≈ 120 + 30 + 30 appels. La durée, les appels et les jetons lus et écrits sont affichés dans
l'onglet, enregistrés avec le run, écrits dans le journal du service (une ligne `generation
run=…`, sans aucun texte) et dans le fil de la collection (`generation.terminee`).

Ragas fait varier la forme des questions (bien rédigée, syntaxe approximative, fautes de frappe,
mots-clés) et leur longueur : c'est voulu, pour éprouver l'assistant sur des questions réalistes.

## Ce qui est garanti

- **Les passages restent liés aux paires.** Chaque paire garde l'identifiant de son passage et son
  texte : l'identifiant d'un passage OpenRAG change à la réindexation, la paire reste lisible.
- **Les échecs se voient.** Une paire que le modèle n'a pas su rendre en JSON lisible, malgré les
  réessais de ragas, est comptée « en échec » ; les réponses mal formées réparées par ragas sont
  comptées aussi (« réparations »). Rien n'est rejoué en silence.
- **Aucune donnée ne sort.** Le modèle est celui de la passerelle MirAI, la même qu'emploie
  OpenRAG (avec un jeton à part : voir « Limites connues »). Les statistiques d'usage que ragas envoie à son éditeur sont coupées
  (`RAGAS_DO_NOT_TRACK=true`, posé par le code et par l'image).
- **L'ingestion n'est pas touchée.** ragas est un extra (`uv sync --extra generation`) ; une image
  construite sans (`--build-arg AVEC_GENERATION=0`) répond 503 sur ces routes et fonctionne à
  l'identique pour le reste.

## Limites connues

- **Le quota de la passerelle est compté par jeton.** Celui d'OpenRAG est limité à 60 appels par
  minute : un run qui l'emprunterait prendrait le quota de l'assistant de tous les testeurs. Il
  faut **un jeton propre à Mes collections**, et un débit (`MYCOLLECTIONS_GENERATION_APPELS_PAR_MINUTE`)
  sous son quota. Un refus de quota (429) est compté à part et dit dans l'écran.

- **Un run à la fois par processus**, un run actif par collection (409). Les autres attendent,
  affichés « en attente ».
- **Pas d'annulation.** Un délai dépassé (`MYCOLLECTIONS_GENERATION_DUREE_MAX_S`) marque le run
  en échec, mais ragas termine sa phase en cours. Un redémarrage du service marque les runs en
  cours « interrompus » : ils se relancent à la main.
- **Personas saisis à la main.** ragas sait en proposer à partir de résumés et d'embeddings des
  passages ; c'est préparé (`personas_auto`, `MYCOLLECTIONS_GENERATION_EMBEDDINGS_MODELE`) mais
  pas exposé.
- **Questions à un seul passage** (*single-hop*). Les questions qui croisent plusieurs passages
  (*multi-hop*) viendront une fois le coût mesuré sur la bêta.
- **Mémoire** : l'image passe de 256 Mo à 796 Mo ; ragas et ses dépendances ajoutent environ
  200 Mo au processus pendant un run.

## Réglages

| Variable | Défaut | Rôle |
|---|---|---|
| `MYCOLLECTIONS_GENERATION_LLM_URL` | vide | Adresse OpenAI-compatible de la passerelle MirAI (`…/v1`). Vide ⇒ 503 |
| `MYCOLLECTIONS_GENERATION_LLM_CLE` | vide | Jeton de la passerelle (secret). Vide ⇒ 503 |
| `MYCOLLECTIONS_GENERATION_LLM_MODELE` | vide | Modèle de rédaction (ex. `chat` : rapide, JSON fiable). Vide ⇒ 503 |
| `MYCOLLECTIONS_GENERATION_EMBEDDINGS_MODELE` | vide | Modèle d'embeddings (ex. `bge-m3`) — pour les personas automatiques, à venir |
| `MYCOLLECTIONS_GENERATION_EMBEDDINGS_URL` | vide | Vide ⇒ l'adresse du modèle de rédaction |
| `MYCOLLECTIONS_GENERATION_MORCEAUX_MAX` | `200` | Plafond des passages lus par run (4 par paire sinon) |
| `MYCOLLECTIONS_GENERATION_APPELS_PAR_MINUTE` | `20` | Débit maximal vers la passerelle, tous fils confondus (0 = sans limite) |
| `MYCOLLECTIONS_GENERATION_PARALLELISME` | `4` | Appels simultanés au modèle |
| `MYCOLLECTIONS_GENERATION_MAX_TOKENS` | `4096` | Jetons de sortie par appel |
| `MYCOLLECTIONS_GENERATION_DELAI_APPEL_S` | `180` | Délai d'un appel au modèle |
| `MYCOLLECTIONS_GENERATION_DUREE_MAX_S` | `1800` | Durée maximale d'un run |

## Les prompts en français

ragas écrit ses prompts en anglais. Ils ont été traduits **une fois** par le modèle de la
passerelle (`python -m app.generation.adapter_prompts`), puis relus et corrigés à la main ; ils
sont versionnés dans `myrag/app/generation/prompts/` (voir le `LISEZMOI.md` de ce dossier) et
chargés à chaque run. Le moteur ne traduit jamais rien lui-même. En plus, chaque génération de
paire reçoit la consigne de rédiger en français.

## API

Toutes sous `/api/collections/{collection}/generation`, réservées à qui gère la collection.

| Route | Rôle |
|---|---|
| `GET ""` | Prête ? modèle, personas, run actif |
| `GET/POST /personas`, `PATCH/DELETE /personas/{id}` | Les personas de la collection |
| `POST /runs` | `{personas: [id…] (1 à 5), taille: 1-100, distribution: {entites, mots_cles}}` → 202 |
| `GET /runs`, `GET/DELETE /runs/{id}` | État, phase, compteurs, durée, erreur |
| `GET /runs/{id}/paires?persona=&relecture=&page=&par_page=` | Les paires, paginées |
| `PATCH /paires/{id}` | `{relecture: brut \| valide \| rejete, commentaire}` |
| `GET /runs/{id}/export?format=json\|csv` | JSON au format de l'outillage d'évaluation (`eval-rag`, `DatasetItem`) ; CSV pour un tableur |

## Dépendances

`ragas==0.4.3` (dernière version, janvier 2026), plus `langchain-community<0.4.2` : ragas 0.4.3
importe `langchain_community.chat_models.vertexai`, que la 0.4.2 a retiré. Le correctif du
`HeadlineSplitter` du fork `idostik/ragas` (PR amont #2587, non fusionnée) n'est pas nécessaire :
le flux pré-découpé n'utilise pas de découpeur. Décision et options : ADR-0002.
