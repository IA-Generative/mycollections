"""Le harnais de recherche des assistants (ADR-0003).

`contrat.py` et `interfaces.py` sont la donnée partagée du chantier : ils ne changent que par
une PR dédiée. Le reste du paquet (connecteurs, planificateurs, exécution, fusion, journal)
arrive par les lots suivants. Aucun module d'ici n'importe FastAPI ni la base : un
planificateur, un connecteur ou un banc s'écrivent et se testent sans l'application.

Vocabulaire de l'interface et des docs : assistant (de recherche), source, consigne (quand /
chercher / répondre), réponse fiable, question de référence, plan de recherche. Le mot
« harnais » ne vit qu'ici et dans les docs techniques.
"""
