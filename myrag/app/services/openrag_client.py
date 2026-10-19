"""OpenRAG API client for MyRAG.

Chaque méthode publique rend un modèle Pydantic calqué sur la réponse d'OpenRAG
(`openrag/api/routers/`) : les consommateurs lisent des attributs, plus les
métadonnées libres via `extra="allow"` (`getattr(f, "livre", "")`).
"""

import io
import re
import uuid
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import settings

_PARTITION_DANS_CHEMIN = re.compile(r"^/(?:indexer/|search/)?partition/([^/?]+)")


class PartitionHorsPerimetre(PermissionError):
    """Une partition hors du préfixe imposé (preview) : refusée AVANT tout appel à OpenRAG."""


def verifier_partition(nom: str) -> None:
    """Rien hors preview ; en preview, `nom` doit commencer par le préfixe imposé."""
    prefixe = (settings.partition_prefixe or "").strip().lower()
    if prefixe and not (str(nom).lower().startswith(prefixe) and len(str(nom)) > len(prefixe)):
        raise PartitionHorsPerimetre(f"partition hors du périmètre de cet environnement : {nom!r}")


def _verifier_chemin(path: str) -> None:
    m = _PARTITION_DANS_CHEMIN.match(path)
    if m:
        verifier_partition(m.group(1))


# ─── Modèles des réponses d'OpenRAG ──────────────────────────────────────────────────────────


class ResultatPartition(BaseModel):
    """Création, suppression, envoi d'un morceau : `ok`, ou `exists`/`not_found` quand
    OpenRAG répond 409/404 (le client traduit, l'appelant ne voit jamais d'exception)."""

    model_config = ConfigDict(extra="ignore")

    status: Literal["ok", "exists", "not_found"] = "ok"
    task_status_url: str | None = None


class FichierOpenRAG(BaseModel):
    """Une ligne de `GET /partition/<p>` : un fichier indexé, ses métadonnées à plat.

    Les champs non déclarés (métadonnées libres : `livre`, `titre`, `chapitre`,
    `parent_path`, `indexed_at`…) restent des extras : accessibles comme attributs,
    rendus par `model_dump()`. `file_size` arrive chez OpenRAG en octets (int) ou
    déjà formaté (« 308.00 B »)."""

    model_config = ConfigDict(extra="allow")

    link: str | None = None
    partition: str | None = None
    file_id: str | None = None
    relationship_id: str | None = None
    parent_id: str | None = None
    filename: str | None = None
    original_filename: str | None = None
    title: str | None = None
    mimetype: str | None = None
    file_size: int | str | None = None
    url: str | None = None


class MorceauOpenRAG(BaseModel):
    """Un élément de `GET /partition/<p>/chunks` : un morceau, texte compris."""

    model_config = ConfigDict(extra="ignore")

    link: str | None = None
    content: str = ""
    metadata: dict | None = None


class ExtraitOpenRAG(BaseModel):
    """Réponse de `GET /extract/<id>` : un morceau relu, balises techniques comprises."""

    model_config = ConfigDict(extra="ignore")

    page_content: str = ""
    metadata: dict | None = None


class DocumentRecherche(BaseModel):
    """Un document rendu par `/search` : son texte, ses métadonnées, son lien d'extrait."""

    model_config = ConfigDict(extra="ignore")

    link: str | None = None
    content: str = ""
    metadata: dict | None = None


class ResultatRecherche(BaseModel):
    """Réponse de `/search` : les documents classés par pertinence."""

    model_config = ConfigDict(extra="ignore")

    documents: list[DocumentRecherche] = []


class EnvoiDocument(BaseModel):
    """Ce que rend l'envoi d'un document entier : l'indexation est asynchrone,
    `task_state` la suit, `task_error` dit la raison d'un échec."""

    model_config = ConfigDict(extra="ignore")

    file_id: str
    task_id: str = ""


class EtatTache(BaseModel):
    """L'état d'une indexation (`QUEUED`, `RUNNING`, `COMPLETED`/`SUCCESS`, `FAILED`)."""

    model_config = ConfigDict(extra="ignore")

    task_id: str | None = None
    task_state: str = ""
    details: dict | None = None
    error_url: str | None = None


class _ErreurTache(BaseModel):
    """La raison d'un échec d'indexation : `summary` (concis, pour l'appelant) ou
    `reason` (complet, admin) — OpenRAG rend l'un, l'autre, ou les deux."""

    model_config = ConfigDict(extra="ignore")

    task_id: str | None = None
    summary: str | None = None
    reason: str | None = None
    traceback: list[str] = []


class MessageChat(BaseModel):
    """Un message du chat : `content` est la réponse ; le raisonnement (`reasoning_content`)
    passe en extra — on ne le lit pas."""

    model_config = ConfigDict(extra="allow")

    role: str | None = None
    content: str | None = None


class ChoixChat(BaseModel):
    """Un choix de la réponse du chat (OpenAI n'en rend qu'un)."""

    model_config = ConfigDict(extra="ignore")

    message: MessageChat | None = None
    finish_reason: str | None = None
    index: int | None = None


class ReponseChat(BaseModel):
    """Réponse du chat d'OpenRAG (compatible OpenAI). `extra` : chaîne JSON (OpenRAG 2.2.1)
    ou objet (2.3.1) — forme libre, lue par `sources_de`, jamais par le client."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    model: str | None = None
    choices: list[ChoixChat] = []
    extra: Any = None

    def texte(self) -> str:
        """Le contenu du premier message qui en porte un, ou une chaîne vide."""
        for choix in self.choices:
            if choix.message and choix.message.content:
                return choix.message.content
        return ""


class ModeleOpenRAG(BaseModel):
    """Un modèle de `/v1/models` : chez OpenRAG, `openrag-<partition>` par collection."""

    model_config = ConfigDict(extra="ignore")

    id: str = ""
    object: str | None = None
    created: int | None = None
    owned_by: str | None = None


class ListeModeles(BaseModel):
    """Réponse de `/v1/models`."""

    model_config = ConfigDict(extra="ignore")

    object: str | None = None
    data: list[ModeleOpenRAG] = []


class _LienDocument(BaseModel):
    """Un lien vers la vue d'un morceau (`/extract/<id>`)."""

    model_config = ConfigDict(extra="ignore")

    link: str | None = None


class FileDetail(BaseModel):
    """Réponse de `GET /partition/<p>/file/<id>` : métadonnées libres et liens vers les morceaux."""

    model_config = ConfigDict(extra="ignore")

    metadata: dict | None = None
    documents: list[_LienDocument] | None = None


class OpenRAGClient:
    def __init__(
        self,
        base_url: str | None = None,
        admin_token: str | None = None,
        timeout: float = 60.0,
    ):
        self.base_url = (base_url or settings.openrag_url).rstrip("/")
        self.admin_token = admin_token or settings.openrag_admin_token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.admin_token}",
            "Content-Type": "application/json",
        }

    async def _get(self, path: str, params: dict | None = None) -> dict:
        _verifier_chemin(path)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
        _verifier_chemin(path)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=json,
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    async def _upload_file(self, path: str, file_content: bytes, filename: str, metadata: dict | None = None) -> dict:
        _verifier_chemin(path)
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            files = {"file": (filename, io.BytesIO(file_content), "text/markdown")}
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=headers,
                files=files,
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    async def _delete(self, path: str) -> dict:
        _verifier_chemin(path)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.delete(
                f"{self.base_url}{path}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    async def _upload_form(self, path: str, data: dict) -> dict:
        """POST form data (for endpoints that expect form fields, not JSON)."""
        _verifier_chemin(path)
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers=headers,
                data=data,
            )
            if resp.status_code == 409:
                return {"status": "exists"}
            resp.raise_for_status()
            if resp.status_code == 204 or not resp.content:
                return {"status": "ok"}
            return resp.json()

    # --- Public API ---

    async def create_partition(self, name: str) -> ResultatPartition:
        try:
            return ResultatPartition.model_validate(await self._post(f"/partition/{name}"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return ResultatPartition(status="exists")
            raise

    async def delete_partition(self, name: str) -> ResultatPartition:
        try:
            return ResultatPartition.model_validate(await self._delete(f"/partition/{name}"))
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return ResultatPartition(status="not_found")
            raise

    async def upload_chunk(self, partition: str, chunk: dict) -> ResultatPartition:
        file_id = str(uuid.uuid4())
        content = chunk["content"].encode("utf-8")
        filename = chunk.get("filename", f"chunk-{file_id}.md")
        return ResultatPartition.model_validate(
            await self._upload_file(
                f"/indexer/partition/{partition}/file/{file_id}",
                file_content=content,
                filename=filename,
            )
        )

    async def upload_document(self, partition: str, filename: str, content: bytes, mimetype: str, metadata: dict | None = None) -> EnvoiDocument:
        """Un document entier (PDF, Word…) confié à OpenRAG, qui le lit et le découpe lui-même.
        Rend `EnvoiDocument` : l'indexation est asynchrone, `task_state` la suit."""
        import json as _json

        file_id = str(uuid.uuid4())
        path = f"/indexer/partition/{partition}/file/{file_id}"
        _verifier_chemin(path)
        donnees = {"metadata": _json.dumps({"mimetype": mimetype, **(metadata or {})}, ensure_ascii=False)}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}{path}",
                headers={"Authorization": f"Bearer {self.admin_token}"},
                files={"file": (filename, io.BytesIO(content), mimetype)},
                data=donnees,
            )
            resp.raise_for_status()
            corps = resp.json() if resp.content else {}
        url = str(corps.get("task_status_url") or "")
        return EnvoiDocument(file_id=file_id, task_id=url.rstrip("/").rsplit("/", 1)[-1] if url else "")

    async def task_state(self, task_id: str) -> EtatTache:
        """L'état d'une indexation (`QUEUED`, `RUNNING`, `COMPLETED`/`SUCCESS`, `FAILED`)."""
        return EtatTache.model_validate(await self._get(f"/indexer/task/{task_id}"))

    async def task_error(self, task_id: str) -> str:
        """La raison d'un échec d'indexation, concise (`summary`), à défaut complète (`reason`),
        tronquée à 500 caractères. Vide si OpenRAG ne répond pas ou ne dit rien."""
        try:
            d = await self._get(f"/indexer/task/{task_id}/error")
        except httpx.HTTPError:
            return ""
        if not isinstance(d, dict):
            return str(d)[:500]
        e = _ErreurTache.model_validate(d)
        return str(e.summary or e.reason or "")[:500]

    async def upload_chunks(self, partition: str, chunks: list[dict]) -> list[ResultatPartition]:
        return [await self.upload_chunk(partition, chunk) for chunk in chunks]

    async def search(self, partition: str | list[str], query: str, top_k: int = 5) -> ResultatRecherche:
        """`/search` d'OpenRAG. `partition` : un nom, ou une liste (`partitions=a&partitions=b`).
        Une liste vide est refusée : OpenRAG la lirait comme « toutes les partitions »."""
        partitions = [partition] if isinstance(partition, str) else list(partition)
        if not partitions:
            raise ValueError("Aucune partition à interroger")
        for p in partitions:
            verifier_partition(p)
        data = await self._get(
            "/search",
            params={"text": query, "partitions": partitions if len(partitions) > 1 else partitions[0], "top_k": top_k},
        )
        return ResultatRecherche.model_validate(data) if isinstance(data, dict) else ResultatRecherche()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.1,
        **extra,
    ) -> ReponseChat:
        """OpenAI-compatible chat completion via OpenRAG (auto-RAGs from the
        partition encoded in the model name, e.g. ``openrag-<partition>``).
        """
        if (settings.partition_prefixe or "").strip():
            # `openrag-all` interrogerait toutes les partitions, celles de la bêta comprises.
            verifier_partition(model[len("openrag-") :] if model.startswith("openrag-") else model)
        body = {"model": model, "messages": messages, "temperature": temperature, **extra}
        return ReponseChat.model_validate(await self._post("/v1/chat/completions", json=body))

    async def list_files(self, partition: str) -> list[FichierOpenRAG]:
        """List files indexed in an OpenRAG partition. Returns the files array
        from ``GET /partition/{partition}`` (empty list if the partition is
        missing or has no files)."""
        try:
            data = await self._get(f"/partition/{partition}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 400):
                return []
            raise
        if not isinstance(data, dict):
            return []
        return [FichierOpenRAG.model_validate(f) for f in data.get("files", [])]

    async def file_detail(self, partition: str, file_id: str) -> FileDetail | None:
        """Le détail d'un fichier indexé (`GET /partition/<p>/file/<id>`) : ses métadonnées
        et les liens vers ses morceaux. `None` si OpenRAG ne le connaît pas."""
        try:
            data = await self._get(f"/partition/{partition}/file/{file_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 400):
                return None
            raise
        return FileDetail.model_validate(data) if isinstance(data, dict) else None

    async def partition_chunks(self, partition: str, file_id: str | None = None, limit: int | None = None) -> list[MorceauOpenRAG] | None:
        """Les morceaux d'une partition, texte compris, sans vecteurs (`GET /partition/<p>/chunks`),
        filtrés sur un fichier si `file_id`. `None` si l'instance ne connaît pas la route (OpenRAG
        ancien) : l'appelant se replie sur `file_detail` + `extract`."""
        params: dict = {"include_embedding": "false"}
        if file_id:
            params["file_id"] = file_id
        if limit is not None:
            params["limit"] = limit
        try:
            data = await self._get(f"/partition/{partition}/chunks", params=params)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 405):
                return None
            raise
        chunks = data.get("chunks") if isinstance(data, dict) else None
        if not isinstance(chunks, list):
            return None
        return [MorceauOpenRAG.model_validate(c) for c in chunks]

    async def extract(self, chunk_id: str) -> ExtraitOpenRAG | None:
        """Un morceau relu (`GET /extract/<id>`), balises techniques comprises. `None` s'il manque."""
        try:
            data = await self._get(f"/extract/{chunk_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 400):
                return None
            raise
        return ExtraitOpenRAG.model_validate(data) if isinstance(data, dict) else None

    async def get_file_content(self, partition: str, file_id: str) -> str:
        """Best-effort plain-text retrieval of an indexed file's content.
        Used by generate-eval to build a sample. Returns an empty string if
        the endpoint is unavailable."""
        try:
            data = await self._get(f"/search/partition/{partition}/file/{file_id}")
        except httpx.HTTPStatusError:
            return ""
        if isinstance(data, dict):
            chunks = data.get("chunks") or data.get("documents") or []
            return "\n\n".join(c.get("content", "") if isinstance(c, dict) else str(c) for c in chunks)
        return ""

    async def list_models(self) -> ListeModeles:
        return ListeModeles.model_validate(await self._get("/v1/models"))

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health_check")
                return resp.status_code == 200
        except Exception:
            return False
