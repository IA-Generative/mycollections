"""Graph builder — construct article reference graphs from chunks."""

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx

ARTICLE_REF_RE = re.compile(
    r"\b[Ll](?:'article|'article)\s+([LRD])\.\s?(\d+(?:-\d+)*)\b"
    r"|\b([LRD])\.\s?(\d+(?:-\d+)*)\b"
)


def extract_references(text: str) -> list[str]:
    """Extract article references from text."""
    refs = set()
    for match in ARTICLE_REF_RE.finditer(text):
        prefix = match.group(1) or match.group(3)
        number = match.group(2) or match.group(4)
        if prefix and number:
            refs.add(f"{prefix}{number}")
    return sorted(refs)


def build_graph_from_chunks(chunks: list[dict]) -> nx.DiGraph:
    """Build a directed graph from chunks with reference metadata."""
    graph = nx.DiGraph()

    # Index all article IDs
    article_ids = set()
    for chunk in chunks:
        article = chunk.get("metadata", {}).get("article")
        if article:
            article_ids.add(article)

    # Add nodes
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        article = meta.get("article")
        if not article:
            continue

        graph.add_node(
            article,
            label=f"Article {article}",
            entity_type="article",
            livre=meta.get("livre", ""),
            titre=meta.get("titre", ""),
            chapitre=meta.get("chapitre", ""),
            parent_path=meta.get("parent_path", ""),
            source_group=f"{meta.get('livre', '')}",
            content_preview=chunk.get("content", "")[:500],  # short brut (no LLM)
            content_full_length=len(chunk.get("content", "")),
            ai_summary="",  # populated by summarize_long_articles() if LLM enabled
            filename=chunk.get("filename", ""),
            referenced_by=[],
        )

    # Add edges from references
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        article = meta.get("article")
        if not article:
            continue

        references = meta.get("references", [])
        for ref in references:
            # Only add edge if target exists in our graph
            if ref in article_ids and ref != article:
                graph.add_edge(
                    article,
                    ref,
                    description="cite",
                    weight=1.0,
                )

                # Track referenced_by on target node
                if ref in graph.nodes:
                    rb = graph.nodes[ref].get("referenced_by", [])
                    if article not in rb:
                        rb.append(article)
                        graph.nodes[ref]["referenced_by"] = rb

    return graph


#: Garde-fous d'un graphe importé : au-delà, le visualiseur et le JSON ne suivent plus.
MAX_IMPORT_NODES = 20_000
MAX_IMPORT_EDGES = 200_000


class GraphImportError(ValueError):
    """Le graphe fourni est mal formé ; le message dit quoi corriger."""


def graph_from_import(data: dict) -> nx.DiGraph:
    """Valide un graphe ``{"nodes": [...], "edges": [...]}`` fourni de l'extérieur.

    Même forme que ``graph.json`` : chaque nœud porte un ``id`` unique, chaque arête
    un ``source`` et un ``target`` qui désignent des nœuds présents. ``referenced_by``
    est recalculé à partir des arêtes : on ne fait pas confiance à une liste fournie.
    """
    nodes, edges = data.get("nodes"), data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise GraphImportError("« nodes » doit être une liste non vide")
    if not isinstance(edges, list):
        raise GraphImportError("« edges » doit être une liste")
    if len(nodes) > MAX_IMPORT_NODES or len(edges) > MAX_IMPORT_EDGES:
        raise GraphImportError(
            f"graphe trop grand : {MAX_IMPORT_NODES} nœuds et {MAX_IMPORT_EDGES} arêtes au plus"
        )

    graph = nx.DiGraph()
    for node in nodes:
        node_id = node.get("id") if isinstance(node, dict) else None
        if not isinstance(node_id, str) or not node_id.strip():
            raise GraphImportError("chaque nœud doit porter un « id » texte non vide")
        if node_id in graph:
            raise GraphImportError(f"identifiant de nœud en double : {node_id}")
        attrs = {k: v for k, v in node.items() if k != "id"}
        attrs.setdefault("label", node_id)
        attrs.setdefault("entity_type", "article")
        attrs["referenced_by"] = []
        graph.add_node(node_id, **attrs)

    for edge in edges:
        source = edge.get("source") if isinstance(edge, dict) else None
        target = edge.get("target") if isinstance(edge, dict) else None
        if source not in graph or target not in graph:
            raise GraphImportError(f"arête vers un nœud absent : {source} → {target}")
        if source == target:
            continue
        attrs = {k: v for k, v in edge.items() if k not in ("source", "target")}
        attrs.setdefault("description", "cite")
        attrs.setdefault("weight", 1.0)
        graph.add_edge(source, target, **attrs)
        if source not in graph.nodes[target]["referenced_by"]:
            graph.nodes[target]["referenced_by"].append(source)
    return graph


_ROMAINS = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
AUTRES = "other"


def _groupe(attrs: dict) -> str:
    """La partie du corpus où vit un nœud : son Livre, ou « other »."""
    livre = (attrs or {}).get("livre", "")
    return f"Livre-{livre}" if livre else AUTRES


def _rang(identifiant: str) -> tuple:
    """Tri des parties : Livre I, II, III, IV, V… IX (en chiffres romains, pas en lettres — « IX »
    passait avant « V ») ; ce qui n'est pas un chiffre romain suit, par ordre alphabétique ; « other » ferme."""
    if identifiant == AUTRES:
        return (2, 0, "")
    suffixe = identifiant.split("-", 1)[-1].upper()
    if suffixe and all(c in _ROMAINS for c in suffixe):
        valeurs = [_ROMAINS[c] for c in suffixe]
        total = sum(-v if i + 1 < len(valeurs) and v < valeurs[i + 1] else v for i, v in enumerate(valeurs))
        return (0, total, "")
    return (1, 0, identifiant.lower())


def parties_du_corpus(groupes) -> list[dict]:
    """Ce que le sélecteur « Partie du corpus » du visualiseur attend : des `{id, label}`, la première
    entrée valant « tout ». Le serveur rendait des chaînes nues ; le visualiseur lisait `.id` et
    `.label` sur chacune, et affichait un menu d'options VIDES."""
    ids = sorted({g for g in groupes if g}, key=_rang)
    if len(ids) < 2:
        return [{"id": "", "label": "Tout le corpus"}]   # une seule partie : rien à choisir
    libelle = lambda g: "Hors livres" if g == AUTRES else g.replace("-", " ", 1)  # noqa: E731
    return [{"id": "", "label": "Tout le corpus"}] + [{"id": g, "label": libelle(g)} for g in ids]


class GraphBuilder:
    """Manages graphs per collection with persistence."""

    def __init__(self, data_dir: str | None = None):
        from app.config import settings
        self.data_dir = data_dir or settings.data_dir
        self._graphs: dict[str, nx.DiGraph] = {}

    def build(self, collection: str, chunks: list[dict]) -> nx.DiGraph:
        """Build a graph from chunks and store in memory."""
        graph = build_graph_from_chunks(chunks)
        self._graphs[collection] = graph
        return graph

    def get(self, collection: str) -> nx.DiGraph | None:
        """Get a graph from memory, or try to load from disk."""
        if collection not in self._graphs:
            loaded = self.load(collection)
            if loaded:
                self._graphs[collection] = loaded
        return self._graphs.get(collection)

    def save(self, collection: str):
        """Save a graph to disk as JSON."""
        graph = self._graphs.get(collection)
        if not graph:
            return

        path = Path(self.data_dir) / collection / "graph.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "nodes": [],
            "edges": [],
        }
        if graph.graph:
            # Provenance du graphe (import externe…) : doit survivre à un aller-retour disque.
            data["meta"] = dict(graph.graph)

        for node_id, attrs in graph.nodes(data=True):
            data["nodes"].append({"id": node_id, **attrs})

        for source, target, attrs in graph.edges(data=True):
            data["edges"].append({"source": source, "target": target, **attrs})

        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def load(self, collection: str) -> nx.DiGraph | None:
        """Load a graph from disk."""
        path = Path(self.data_dir) / collection / "graph.json"
        if not path.exists():
            return None

        data = json.loads(path.read_text())
        graph = nx.DiGraph()
        graph.graph.update(data.get("meta") or {})

        for node in data.get("nodes", []):
            node_id = node.pop("id")
            graph.add_node(node_id, **node)

        for edge in data.get("edges", []):
            source = edge.pop("source")
            target = edge.pop("target")
            graph.add_edge(source, target, **edge)

        self._graphs[collection] = graph
        return graph

    def import_graph(self, collection: str, data: dict, imported_by: str = "") -> nx.DiGraph:
        """Remplace le graphe d'une collection par un graphe construit ailleurs.

        Sert aux corpus dont les renvois sont connus à la source (liens Légifrance,
        par exemple) et que ``build`` ne saurait pas reconstruire depuis les morceaux.
        """
        graph = graph_from_import(data)
        graph.graph.update({
            "origin": "import",
            "imported_by": imported_by,
            "imported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        self._graphs[collection] = graph
        self.save(collection)
        return graph

    def is_imported(self, collection: str) -> bool:
        graph = self.get(collection)
        return bool(graph is not None and graph.graph.get("origin") == "import")

    def get_subgraph(
        self, collection: str, article_ids: list[str], depth: int = 1
    ) -> nx.DiGraph | None:
        """Get a subgraph centered on given articles, expanding N hops."""
        graph = self.get(collection)
        if not graph:
            return None

        nodes_to_include = set()
        frontier = set(a for a in article_ids if a in graph.nodes)

        for _ in range(depth + 1):
            nodes_to_include.update(frontier)
            next_frontier = set()
            for node in frontier:
                next_frontier.update(graph.successors(node))
                next_frontier.update(graph.predecessors(node))
            frontier = next_frontier - nodes_to_include

        return graph.subgraph(nodes_to_include).copy()

    async def summarize_long_articles(
        self,
        collection: str,
        chunks: list[dict],
        threshold: int = 1000,
        llm_url: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> dict:
        """Generate AI summaries for articles longer than threshold.

        Requires LLM access (Scaleway, OpenAI-compatible).
        Stores summaries in graph nodes as ai_summary field.
        """
        import httpx
        from app.config import settings

        graph = self.get(collection)
        if not graph:
            return {"summarized": 0, "skipped": 0, "errors": 0}

        url = llm_url or settings.openrag_url.replace(":8080", "")  # fallback
        # Use the configured LLM from .env if available
        base_url = llm_url or "https://api.scaleway.ai/v1"
        api_key = llm_api_key or ""
        model = llm_model or "mistral-small-3.2-24b-instruct-2506"

        # Index chunks by article for full content
        chunk_by_article = {}
        for chunk in chunks:
            article = chunk.get("metadata", {}).get("article")
            if article:
                chunk_by_article[article] = chunk.get("content", "")

        summarized = 0
        skipped = 0
        errors = 0

        async with httpx.AsyncClient(timeout=60) as client:
            for node_id in graph.nodes:
                full_text = chunk_by_article.get(node_id, "")
                if len(full_text) < threshold:
                    skipped += 1
                    continue

                try:
                    resp = await client.post(
                        f"{base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": model,
                            "messages": [
                                {
                                    "role": "system",
                                    "content": "Tu es un assistant juridique. Resume l'article suivant en 3-5 phrases. Conserve les numeros d'articles cites. Commence par 'Cet article...'",
                                },
                                {"role": "user", "content": full_text[:8000]},
                            ],
                            "max_tokens": 300,
                            "temperature": 0.1,
                        },
                    )
                    if resp.status_code == 200:
                        summary = resp.json()["choices"][0]["message"]["content"]
                        graph.nodes[node_id]["ai_summary"] = summary
                        summarized += 1
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        # Save updated graph
        self.save(collection)

        return {"summarized": summarized, "skipped": skipped, "errors": errors}

    def to_graph_data_response(
        self,
        collection: str,
        query: str = "",
        max_nodes: int = 80,
        min_weight: float = 0.0,
        source_prefix: str = "",
    ) -> dict:
        """Convert graph to GraphDataResponse format (compatible with grafragexp viewer).

        `source_prefix` restreint le graphe à une PARTIE du corpus (un Livre, pour un code). Le
        visualiseur l'envoyait depuis toujours ; le serveur l'ignorait."""
        graph = self.get(collection)
        if not graph:
            return {
                "graph_ready": False,
                "graph_kind": "article",
                "corpus_id": collection,
                "nodes": [],
                "edges": [],
                "total_nodes": 0,
                "total_edges": 0,
                "message": "Cette collection n'a pas encore de graphe de références.",
                # Le visualiseur parcourt TOUJOURS cette liste : absente, il plantait sur « Erreur de
                # chargement » au lieu de dire que le graphe n'existe pas.
                "source_prefix": "",
                "available_sources": parties_du_corpus([]),
            }

        # Les parties se lisent sur le graphe ENTIER, avant tout filtre : la liste offerte ne doit pas
        # dépendre de ce qui est affiché (80 éléments au plus).
        parties = parties_du_corpus(_groupe(d) for _, d in graph.nodes(data=True))
        partie = source_prefix if any(p["id"] == source_prefix for p in parties) else ""
        if partie:
            graph = graph.subgraph([n for n, d in graph.nodes(data=True) if _groupe(d) == partie]).copy()

        # Le filtre est une recherche LITTÉRALE (sous-chaîne) dans l'identifiant, le libellé et l'aperçu.
        # S'il ne trouve rien, le graphe entier est rendu — et on le DIT (`query_matched`) : sans cela,
        # une question en langage courant semblait « marcher » alors qu'elle ne filtrait rien.
        filtre_trouve = True
        if query:
            # Find nodes matching query
            matching = [
                n for n, d in graph.nodes(data=True)
                if query.lower() in n.lower()
                or query.lower() in d.get("content_preview", "").lower()
                or query.lower() in d.get("label", "").lower()
            ]
            filtre_trouve = bool(matching)
            if matching:
                subgraph = self.get_subgraph(collection, matching, depth=1)
                if subgraph:
                    graph = subgraph

        # Limit nodes
        if graph.number_of_nodes() > max_nodes:
            # Keep nodes with highest degree
            sorted_nodes = sorted(
                graph.nodes, key=lambda n: graph.degree(n), reverse=True
            )[:max_nodes]
            graph = graph.subgraph(sorted_nodes).copy()

        nodes = []
        for node_id, attrs in graph.nodes(data=True):
            degree = graph.degree(node_id)
            size = max(8, min(32, degree * 4 + 8))
            livre = attrs.get("livre", "")

            # Use AI summary if available, otherwise raw preview
            ai_summary = attrs.get("ai_summary", "")
            preview = attrs.get("content_preview", "")
            full_length = attrs.get("content_full_length", 0)

            if ai_summary:
                description = f"🤖 Resume IA :\n{ai_summary}"
                fragment_text = f"🤖 Resume par l'IA (article original : {full_length} caracteres)\n\n{ai_summary}"
            else:
                description = preview
                fragment_text = preview
                if full_length > 500:
                    fragment_text += f"\n\n[... tronque — {full_length} caracteres au total]"

            nodes.append({
                "id": node_id,
                "label": attrs.get("label", node_id),
                "entity_type": attrs.get("entity_type", "article"),
                "description": description,
                "degree": degree,
                "frequency": 1,
                "size": size,
                "source_group": _groupe(attrs),
                "document_paths": [attrs.get("filename", "")],
                "fragments": [{
                    "id": f"{node_id}:preview",
                    "text": fragment_text,
                    "token_count": 0,
                    "document_paths": [attrs.get("filename", "")],
                }] if preview or ai_summary else [],
            })

        edges = []
        for source, target, attrs in graph.edges(data=True):
            weight = attrs.get("weight", 1.0)
            if weight < min_weight:
                continue
            edges.append({
                "source": source,
                "target": target,
                "description": attrs.get("description", "cite"),
                "weight": weight,
                "document_paths": [],
                "fragments": [],
            })

        return {
            "graph_ready": True,
            "graph_kind": "article",
            "corpus_id": collection,
            "query": query,
            "query_matched": filtre_trouve,
            "max_nodes": max_nodes,
            "min_weight": min_weight,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes,
            "edges": edges,
            "message": "",
            "source_prefix": partie,
            "available_sources": parties,
        }
