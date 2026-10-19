"""Exporter un jeu de questions : JSON au format de l'outillage d'évaluation (eval-rag,
`DatasetItem`), ou CSV pour un tableur (UTF-8 avec BOM, `;`, cellules neutralisées)."""

from __future__ import annotations

import csv
import io
import json

from app.models.qualite import QuestionFiche


def cellule(v) -> str:
    """Un tableur exécuterait une cellule qui commence par = + - @ : on la neutralise."""
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def vers_json(collection: str, questions: list[QuestionFiche], meta: dict | None = None) -> str:
    corps = {
        "metadata": {"collection": collection, "total_samples": len(questions), **(meta or {})},
        "samples": [
            {
                "question": q.question,
                "answer": q.reponse,
                "context": [c.get("texte", "") for c in q.contextes or []],
                "persona_name": q.persona or "",
                "query_style": q.style or "",
                "metadata": {
                    "origine": q.origine,
                    "relecture": q.relecture,
                    "hors_sujet": q.hors_sujet,
                    "fiable": q.fiable,
                    "must_cite": q.must_cite or [],
                    "tags": q.tags or [],
                    "dernier_verdict": q.dernier_verdict,
                    "commentaire": q.commentaire or "",
                    "chunk_ids": [c.get("chunk_id") for c in q.contextes or []],
                    "file_ids": [c.get("file_id") for c in q.contextes or []],
                },
            }
            for q in questions
        ],
    }
    return json.dumps(corps, ensure_ascii=False, indent=2)


def vers_csv(questions: list[QuestionFiche]) -> str:
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";")
    w.writerow(["id", "question", "reponse", "origine", "persona", "relecture", "hors_sujet", "fiable", "dernier_verdict", "commentaire", "fichiers"])
    for q in questions:
        w.writerow(
            [
                cellule(x)
                for x in (
                    q.id,
                    q.question,
                    q.reponse,
                    q.origine,
                    q.persona,
                    q.relecture,
                    "oui" if q.hors_sujet else "",
                    "oui" if q.fiable else "",
                    q.dernier_verdict or "",
                    q.commentaire or "",
                    " | ".join(str(c.get("fichier") or "") for c in q.contextes or []),
                )
            ]
        )
    return "﻿" + tampon.getvalue()
