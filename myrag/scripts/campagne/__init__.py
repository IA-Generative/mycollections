"""La campagne de nuit des deux chemins de recherche (harnais et MCP), contre une cible réelle.

    cible.py      client HTTP de la cible (jeton renouvelé, reconnexion, cadence, règles d'arrêt)
                  et de la passerelle de modèles (clef dédiée, budget)
    corpus.py     fiches d'essai (alias → identifiants), jeu de questions
    agent_mcp.py  « OWUI simulé » : un modèle qui appelle les outils du vrai /mcp
    juges.py      juges déterministes, juge-modèle optionnel
    run.py        lanceur reprenable : fenêtre, budgets, règles d'arrêt, journal JSONL
    rapport.py    synthese.md + mesures.json de chaque nuit

Mode d'emploi : docs/campagne-recherche.md. Rien ici ne connaît une adresse, un compte ou un
identifiant réel : tout vient de l'environnement et d'un fichier de correspondance privé.
"""
