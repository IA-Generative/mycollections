"""Les tables du réseau d'entraide (lot G du chantier des assistants de recherche).

Coquille posée au lot 0 : le lot G y écrit ses tables `entraide_*` sans toucher `db.py`, qui
l'importe. Module détachable : rien d'autre que `db.py` ne doit l'importer.
"""

from app.database import Base  # noqa: F401 — les tables à venir en héritent
