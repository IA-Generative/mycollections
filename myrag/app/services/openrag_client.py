"""OpenRAG API client for MyRAG."""

import io
import uuid

import httpx

from app.config import settings


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
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                params=params,
            )
            resp.raise_for_status()
            return resp.json()

    async def _post(self, path: str, json: dict | None = None) -> dict:
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

    async def _upload_file(
        self, path: str, file_content: bytes, filename: str, metadata: dict | None = None
    ) -> dict:
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

    async def create_partition(self, name: str) -> dict:
        try:
            return await self._post(f"/partition/{name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                return {"status": "exists"}
            raise

    async def delete_partition(self, name: str) -> dict:
        try:
            return await self._delete(f"/partition/{name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return {"status": "not_found"}
            raise

    async def upload_chunk(self, partition: str, chunk: dict) -> dict:
        file_id = str(uuid.uuid4())
        content = chunk["content"].encode("utf-8")
        filename = chunk.get("filename", f"chunk-{file_id}.md")
        return await self._upload_file(
            f"/indexer/partition/{partition}/file/{file_id}",
            file_content=content,
            filename=filename,
        )

    async def upload_chunks(self, partition: str, chunks: list[dict]) -> list[dict]:
        results = []
        for chunk in chunks:
            result = await self.upload_chunk(partition, chunk)
            results.append(result)
        return results

    async def search(
        self, partition: str, query: str, top_k: int = 5
    ) -> dict:
        return await self._get(
            "/search",
            params={"text": query, "partitions": partition, "top_k": top_k},
        )

    async def chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.1,
        **extra,
    ) -> dict:
        """OpenAI-compatible chat completion via OpenRAG (auto-RAGs from the
        partition encoded in the model name, e.g. ``openrag-<partition>``).
        """
        body = {"model": model, "messages": messages, "temperature": temperature, **extra}
        return await self._post("/v1/chat/completions", json=body)

    async def list_files(self, partition: str) -> list[dict]:
        """List files indexed in an OpenRAG partition. Returns the files array
        from ``GET /partition/{partition}`` (empty list if the partition is
        missing or has no files)."""
        try:
            data = await self._get(f"/partition/{partition}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (404, 400):
                return []
            raise
        return data.get("files", []) if isinstance(data, dict) else []

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
            return "\n\n".join(
                c.get("content", "") if isinstance(c, dict) else str(c)
                for c in chunks
            )
        return ""

    async def list_models(self) -> dict:
        return await self._get("/v1/models")

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/health_check")
                return resp.status_code == 200
        except Exception:
            return False
