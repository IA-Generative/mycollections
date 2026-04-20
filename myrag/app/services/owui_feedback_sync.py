"""OWUI → MyRAG feedback sync.

Open WebUI writes user 👍/👎 on chat messages into its own Postgres database.
We pull those rows here so they show up in the MyRAG /playground bank and
the /c/{id} feedback tab, without OWUI needing to know anything about MyRAG.

How it identifies "our" feedbacks:
  OWUI's Feedback row carries data->>'model_id' which, for collections
  published via MyRAG, always follows the pattern 'openrag-<collection>'.
  Feedbacks on any other model (a plain LLM chat, a non-OpenRAG tool) are
  skipped.

Dedup:
  Each OWUI feedback row has a stable UUID. We map it to Feedback.owui_message_id
  on our side (unique via FeedbackStore.ingest) so re-running the sync is
  idempotent — an existing row gets its rating/reason updated instead of
  duplicated.

Extraction:
  OWUI's Feedback row has enough metadata to reconstruct question+answer
  without touching the chat thread:
    data.sibling_ids[] → user prompt(s) and assistant reply live here
    data.message_id    → the specific assistant message being rated
    data.chat_id       → surfaced to MyRAG as owui_chat_id for traceability

  When possible we also grab the text from the Chat.chat JSON blob, which is
  the canonical home of message content in OWUI. If the blob shape changed,
  we fall back to empty strings — we never fail a sync batch over one row.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from dataclasses import dataclass

from sqlalchemy import JSON, String, BigInteger, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.services.feedback_store import ingest_feedback as myrag_ingest

log = logging.getLogger(__name__)


# ---- Minimal reflection of the OWUI tables we need. ---------------------
# We only declare the columns we read. The real OWUI schema has many more
# columns (timestamps, user fk, meta) but nothing else is load-bearing for
# the pull.

class _OWUIBase(DeclarativeBase):
    pass


class OwuiFeedback(_OWUIBase):
    __tablename__ = "feedback"
    # All columns typed explicitly — Mapped[dict] isn't directly resolvable
    # by SQLAlchemy's registry, and we don't need the usual PEP 484 benefits
    # since this model is never written, only reflected for reads.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    version: Mapped[int] = mapped_column(BigInteger, default=0)
    type: Mapped[str] = mapped_column(String)
    data: Mapped[dict] = mapped_column(JSON)  # {rating, model_id, chat_id, message_id, reason?}
    meta: Mapped[dict] = mapped_column(JSON)
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[int] = mapped_column(BigInteger)


class OwuiChat(_OWUIBase):
    __tablename__ = "chat"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    chat: Mapped[dict] = mapped_column(JSON)  # Full message tree


@dataclass
class SyncResult:
    imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0

    def as_dict(self) -> dict:
        return {"imported": self.imported, "updated": self.updated,
                "skipped": self.skipped, "errors": self.errors}


def _extract_qa(chat_blob: dict | None, message_id: str) -> tuple[str, str]:
    """Given OWUI's chat JSON and the rated message id, return (question, answer).

    OWUI stores messages as a map under chat.history.messages: a dict of
    {msg_id: {role, content, parentId, childrenIds, ...}}. The rated message
    is the assistant reply; the question is its parent.

    Returns empty strings on any missing piece — callers decide whether that
    counts as a skippable row or an acceptable ingest with blanks.
    """
    if not chat_blob or not message_id:
        return "", ""
    try:
        msgs = (chat_blob.get("history") or {}).get("messages") or {}
        answer_msg = msgs.get(message_id) or {}
        answer = str(answer_msg.get("content") or "")
        parent_id = answer_msg.get("parentId") or ""
        question = ""
        if parent_id:
            q_msg = msgs.get(parent_id) or {}
            question = str(q_msg.get("content") or "")
        return question, answer
    except Exception:
        return "", ""


def _collection_from_model(model_id: str) -> str | None:
    """Return the collection name embedded in the OWUI model_id, or None if
    this row isn't about an OpenRAG partition.
    """
    if not model_id:
        return None
    if not model_id.startswith("openrag-"):
        return None
    return model_id[len("openrag-"):]


async def sync_batch(owui_db_url: str, limit: int | None = None) -> SyncResult:
    """Pull OWUI feedback, mirror into MyRAG Feedback. Idempotent by
    owui_message_id (mapped from OWUI feedback row id, which is stable).
    """
    result = SyncResult()
    engine = create_async_engine(owui_db_url, echo=False)
    owui_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with owui_session_factory() as owui_session:
            q = select(OwuiFeedback).order_by(OwuiFeedback.created_at.desc())
            if limit:
                q = q.limit(limit)
            rows = (await owui_session.execute(q)).scalars().all()

            log.info("owui_feedback_sync: %d OWUI feedback rows to scan", len(rows))

            # Cache chat blobs in-memory per batch — one OWUI chat can carry
            # multiple rated messages, and each chat row is a big JSONB.
            chat_cache: dict[str, dict] = {}

            for row in rows:
                data = row.data or {}
                model_id = data.get("model_id") or ""
                collection = _collection_from_model(model_id)
                if not collection:
                    result.skipped += 1
                    continue

                rating_val = data.get("rating")
                try:
                    rating_int = int(rating_val) if rating_val is not None else 0
                except (TypeError, ValueError):
                    rating_int = 0

                chat_id = data.get("chat_id") or ""
                message_id = data.get("message_id") or ""
                reason = data.get("reason") or data.get("comment") or ""

                chat_blob = chat_cache.get(chat_id)
                if chat_blob is None and chat_id:
                    chat_row = await owui_session.get(OwuiChat, chat_id)
                    chat_blob = (chat_row.chat if chat_row else {}) or {}
                    chat_cache[chat_id] = chat_blob

                question, answer = _extract_qa(chat_blob, message_id)

                try:
                    # FeedbackStore.ingest_feedback is idempotent on
                    # owui_message_id — we use the OWUI feedback row id as
                    # the stable key (not message_id, which could be reused
                    # across rating updates on the same message).
                    await myrag_ingest(
                        collection=collection,
                        question=question,
                        response=answer,
                        rating=rating_int,
                        reason=str(reason)[:500],
                        owui_chat_id=chat_id,
                        owui_message_id=row.id,
                    )
                    # The store doesn't distinguish insert vs update without
                    # an extra query; treat as imported for batch stats and
                    # let the log line surface duplicates if the user audits.
                    result.imported += 1
                except Exception:
                    log.exception("owui_feedback_sync: ingest failed for row %s", row.id)
                    result.errors += 1
    finally:
        await engine.dispose()

    log.info("owui_feedback_sync: done — %s", result.as_dict())
    return result


async def _cli_main():
    parser = argparse.ArgumentParser(description="Sync OWUI feedback into MyRAG")
    parser.add_argument("--owui-db-url", default=os.environ.get("OWUI_DB_URL", ""),
                        help="async SQLAlchemy URL for the OWUI postgres database")
    parser.add_argument("--limit", type=int, default=None,
                        help="max rows to pull this run (default: all)")
    parser.add_argument("--cron", action="store_true",
                        help="Print JSON result to stdout (for CronJob logs)")
    args = parser.parse_args()
    if not args.owui_db_url:
        raise SystemExit("OWUI_DB_URL env var or --owui-db-url flag required")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    r = await sync_batch(args.owui_db_url, limit=args.limit)
    if args.cron:
        print(json.dumps(r.as_dict()))


if __name__ == "__main__":
    asyncio.run(_cli_main())
