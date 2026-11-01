# Essayer les assistants de recherche

Pour l'équipe technique et les bêta-testeurs. Le détail technique est dans
[assistants.md](assistants.md) ; ici, ce qu'on essaie et ce qu'on regarde.

## Ce qu'est un assistant

Une **collection** est un ensemble de documents. Un **assistant** cherche dans plusieurs collections
à la fois, en suivant des **consignes** : quand une question ressemble à un cas prévu, il interroge
certaines sources dans un ordre donné, enchaîne au besoin (« avec ce qu'on vient de trouver, cherche
dans… »), puis rédige la réponse selon une règle (« citer l'article de l'accord avant celui du code »).

Tout cela tient dans **un fichier de consignes** (YAML), lisible et versionnable : voir
[l'exemple](exemples/assistants/sejour-des-etrangers.yaml). Le moteur est le même pour tous les
assistants ; seul le fichier change.

Chaque source a un **régime** :

| Régime | L'assistant l'interroge… |
|---|---|
| `toujours` | à chaque question |
| `selon_question` | quand la question ressemble à sa description |
| `sur_consigne` | seulement quand une consigne le demande |

Personne ne lit, par un assistant, plus que ce qu'il a déjà le droit de lire : chaque recherche est
filtrée selon les droits de la personne qui la pose.

## Deux façons d'essayer

### 1. Dans Mes collections : le bac à sable d'un assistant

Menu « Mes collections & assistants » → un assistant → **Bac à sable**. Posez une question.

À regarder :
- **la réponse** : chaque affirmation porte un renvoi `[n]` ; un clic ouvre le passage cité ;
- **« Comment l'assistant a cherché »** : la consigne reconnue (ou aucune), les sources
  interrogées, dans quel ordre, et les sources écartées ;
- une question **hors sujet** doit donner « Les documents trouvés ne répondent pas à cette
  question », pas une réponse inventée.

### 2. Dans un agent conversationnel : « je ne sais pas où chercher »

Un agent conversationnel relié au serveur MCP de Mes collections ([clients.md](clients.md)) trouve
seul l'assistant ou la collection qui convient, y cherche, puis répond en citant les liens.
Posez une question sans dire où chercher ; regardez quel assistant il a choisi et si les liens
cités ouvrent bien le passage.

## Écrire ou modifier un fichier de consignes

- À l'écran : un assistant → **Consignes** → « Exporter le fichier », modifier, « Importer un
  fichier ». Une erreur dit le champ en cause (`consignes[2] › chercher[1] › avec : …`).
- En ligne de commande, depuis `myrag/` :

      uv run python -m scripts.fiche verifier mon-assistant.yaml
      uv run python -m scripts.fiche appliquer mon-assistant.yaml --cible https://mycollections.fake-domain.name --jeton-env JETON

Assembler un assistant demande de **gérer** chacune de ses collections. Pour un assistant sur les
collections d'une autre équipe, demandez à un administrateur de l'assembler.

Bon essai : comparez la même question sur un assistant **sans consigne** et **avec consignes** ;
c'est là que se voit l'apport des règles métier (sources mieux choisies, réponse dans la forme
attendue).

## Donner un avis

Notez la question, l'assistant, ce que vous attendiez et ce que vous avez eu (copie d'écran de
« Comment l'assistant a cherché » bienvenue), et transmettez-le par le canal habituel des
bêta-testeurs.
