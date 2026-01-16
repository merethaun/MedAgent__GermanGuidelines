import hashlib
import json
import os
from collections import defaultdict, deque
from pathlib import Path
from typing import List, Optional, Set, Dict, Any, Tuple
from urllib.parse import urlparse

import weaviate
from pymongo.synchronous.collection import Collection

from app.constants.mongodb_constants import WEAVIATE_HIERARCHY_INDEX_FOLDER
from app.models.knowledge.vector.hierarchical_index_models import HierConfig, HierIndex, ParentNode
from app.models.knowledge.vector.weaviate_related_models import WeaviateSearchChunkResult
from app.services.knowledge.vector import WeaviateVectorDBService
from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


# noinspection PyPep8Naming
class HierarchicalIndexVectorDBService:
    
    def __init__(self, weaviate_vector_db_service: WeaviateVectorDBService, vector_dbs_collection: Collection):
        self.weaviate_vector_db_service = weaviate_vector_db_service
        self.vector_dbs_collection = vector_dbs_collection
        
        weaviate_url = os.getenv("WEAVIATE_URL", "http://localhost:8081")
        parsed = urlparse(weaviate_url)
        self.client = weaviate.connect_to_custom(
            http_host=parsed.hostname, http_port=parsed.port, http_secure=parsed.scheme == "https",
            grpc_host=parsed.hostname, grpc_port=50051, grpc_secure=parsed.scheme == "https",
        )
        self.client.connect()
        
        # in-memory cache: collection_name -> HierIndex
        self._hier_by_collection: Dict[str, HierIndex] = {}
    
    # ---------------------------------------------------------------------
    # Persistence (filesystem JSON)
    # ---------------------------------------------------------------------
    @staticmethod
    def _index_folder() -> Path:
        folder = WEAVIATE_HIERARCHY_INDEX_FOLDER
        p = Path(folder)
        p.mkdir(parents=True, exist_ok=True)
        return p
    
    def _index_path(self, collection_name: str) -> Path:
        return self._index_folder() / f"{collection_name}.json"
    
    def save_hierarchy(self, collection_name: str) -> None:
        H = self._hier_by_collection.get(collection_name)
        if not H:
            logger.warning(f"[automerge.save] no hierarchy cached for '{collection_name}'")
            return
        
        # parents -> plain dicts
        parents_dump: Dict[str, Dict[str, Any]] = {}
        for pid, node in H.parents.items():
            parents_dump[pid] = {
                "id": getattr(node, "id", pid),
                "label": getattr(node, "label", ""),
                "parent_id": getattr(node, "parent_id", None),
                "depth": getattr(node, "depth", 0),
                "child_parent_ids": list(getattr(node, "child_parent_ids", [])),
                "child_leaf_ids": list(getattr(node, "child_leaf_ids", [])),
                "desc_leaf_count": getattr(node, "desc_leaf_count", 0),
                "desc_leaf_ids": list(getattr(node, "desc_leaf_ids", [])),
            }
        
        data = {
            "cfg": {
                "text_property": H.cfg.text_property,
                "heading_path_property": H.cfg.heading_path_property,
                "guideline_id_property": H.cfg.guideline_id_property,
                "order_property": H.cfg.order_property,
                "direct_parent_property": H.cfg.direct_parent_property,
            },
            "parents": parents_dump,
            "roots": list(H.roots),
            "leaf_to_parent": H.leaf_to_parent,
            "parent_of_parent": H.parent_of_parent,
            "leaf_text": H.leaf_text,
            "leaf_order": H.leaf_order,
            "leaf_guideline": H.leaf_guideline,
        }
        
        path = self._index_path(collection_name)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(path)
        logger.info(f"[automerge.save] wrote hierarchy JSON: {path}")
    
    def load_hierarchy(self, collection_name: str) -> bool:
        path = self._index_path(collection_name)
        if not path.exists():
            logger.info(f"[automerge.load] no index file at {path}")
            return False
        
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        cfg = HierConfig(
            text_property=data["cfg"]["text_property"],
            heading_path_property=data["cfg"]["heading_path_property"],
            guideline_id_property=data["cfg"]["guideline_id_property"],
            order_property=data["cfg"]["order_property"],
            direct_parent_property=data["cfg"]["direct_parent_property"],
        )
        H = HierIndex(cfg=cfg)
        
        H.parents = {}
        for pid, nd in data["parents"].items():
            H.parents[pid] = ParentNode(
                id=nd.get("id", pid),
                label=nd.get("label", ""),
                parent_id=nd.get("parent_id", None),
                depth=nd.get("depth", 0),
                child_parent_ids=list(nd.get("child_parent_ids", [])),
                child_leaf_ids=list(nd.get("child_leaf_ids", [])),
                desc_leaf_ids=list(nd.get("desc_leaf_ids", [])),
                desc_leaf_count=nd.get("desc_leaf_count", 0),
            )
        
        H.roots = set(data.get("roots", []))
        H.leaf_to_parent = {k: v for k, v in data.get("leaf_to_parent", {}).items()}
        H.parent_of_parent = {k: v for k, v in data.get("parent_of_parent", {}).items()}
        H.leaf_text = {k: v for k, v in data.get("leaf_text", {}).items()}
        H.leaf_order = {k: int(v) for k, v in data.get("leaf_order", {}).items()}
        H.leaf_guideline = {k: v for k, v in data.get("leaf_guideline", {}).items()}
        
        # Safety: recompute depths + desc lists if missing or inconsistent
        if not any(getattr(n, "desc_leaf_ids", None) for n in H.parents.values()):
            # compute depths from roots
            for pid, node in H.parents.items():
                if node.parent_id:
                    H.parent_of_parent[pid] = node.parent_id
                else:
                    H.parent_of_parent[pid] = None
                    H.roots.add(pid)
            for rid in list(H.roots):
                if rid not in H.parents:
                    continue
                H.parents[rid].depth = 0
                q = deque([rid])
                while q:
                    cur = q.popleft()
                    curd = H.parents[cur].depth
                    for child_pid in H.parents[cur].child_parent_ids:
                        H.parents[child_pid].depth = curd + 1
                        q.append(child_pid)
            
            # build descendant lists
            def build_desc(pid: str) -> List[str]:
                node = H.parents[pid]
                ids = list(node.child_leaf_ids)
                for cpid in node.child_parent_ids:
                    ids.extend(build_desc(cpid))
                ids.sort(key=lambda lid: H.leaf_order.get(lid, 0))
                node.desc_leaf_ids = ids
                node.desc_leaf_count = len(ids)
                return ids
            
            for rid in list(H.roots):
                if rid in H.parents:
                    build_desc(rid)
        
        self._hier_by_collection[collection_name] = H
        logger.info(f"[automerge.load] loaded hierarchy for '{collection_name}' from {path}")
        return True
    
    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------
    @staticmethod
    def _hash_id(guideline_id: str, path_segments: List[str]) -> str:
        base = guideline_id + "|" + " / ".join([seg.strip() for seg in path_segments])
        return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]
    
    @staticmethod
    def _parse_heading_path(raw: str) -> List[str]:
        # split on ' / ' and strip; filter empty
        if not raw:
            return []
        parts = [p.strip() for p in raw.split("/") if p.strip()]
        return parts
    
    @staticmethod
    def _ensure_parent_node(H: HierIndex, parent_id: str, label: str, parent_parent_id: Optional[str]):
        if parent_id not in H.parents:
            H.parents[parent_id] = ParentNode(
                id=parent_id, label=label, parent_id=parent_parent_id,
                depth=0, child_parent_ids=[], child_leaf_ids=[],
                desc_leaf_ids=[], desc_leaf_count=0,
            )
            if parent_parent_id:
                if parent_parent_id not in H.parents:
                    H.parents[parent_parent_id] = ParentNode(
                        id=parent_parent_id, label=str(parent_parent_id), parent_id=None,
                        depth=0, child_parent_ids=[], child_leaf_ids=[],
                        desc_leaf_ids=[], desc_leaf_count=0,
                    )
                H.parents[parent_parent_id].child_parent_ids.append(parent_id)
            else:
                H.roots.add(parent_id)
        else:
            node = H.parents[parent_id]
            if node.parent_id is None and parent_parent_id is not None:
                node.parent_id = parent_parent_id
                if parent_parent_id not in H.parents:
                    H.parents[parent_parent_id] = ParentNode(
                        id=parent_parent_id, label=str(parent_parent_id), parent_id=None,
                        depth=0, child_parent_ids=[], child_leaf_ids=[],
                        desc_leaf_ids=[], desc_leaf_count=0,
                    )
                H.parents[parent_parent_id].child_parent_ids.append(parent_id)
    
    @staticmethod
    def _first_leaf_order_in_subtree(H: HierIndex, parent_id: str) -> int:
        node = H.parents[parent_id]
        if node.desc_leaf_ids:
            return H.leaf_order.get(node.desc_leaf_ids[0], 0)
        # if subtree empty, fallback 0
        return 0
    
    @staticmethod
    def _get_ancestors(H: HierIndex, parent_id: str) -> List[str]:
        """Return ancestors (excluding self), nearest first up to root."""
        chain: List[str] = []
        cur = parent_id
        while True:
            cur = H.parent_of_parent.get(cur)
            if not cur:
                break
            chain.append(cur)
        return chain
    
    def _sorted_content_items(self, H: HierIndex, node: ParentNode) -> List[Tuple[str, str]]:
        """
        Returns a merged, document-ordered list of items under `node`:
        [("leaf", leaf_id), ("parent", child_parent_id), ...]
        Order is based on leaf_order (first leaf in each subtree).
        """
        items: List[Tuple[str, str, int]] = []
        # direct leaves
        for lid in node.child_leaf_ids:
            items.append(("leaf", lid, H.leaf_order.get(lid, 0)))
        # child parents as blocks, keyed by their first leaf's order
        for cpid in node.child_parent_ids:
            items.append(("parent", cpid, self._first_leaf_order_in_subtree(H, cpid)))
        items.sort(key=lambda t: t[2])
        return [(t[0], t[1]) for t in items]
    
    def _synthesize_parent_text(self, H: HierIndex, parent_id: str, include_headings: bool = True) -> str:
        """
        Build a readable section text from the hierarchy preserving order.
        Inserts heading titles when sub-sections are merged.
        """
        node = H.parents[parent_id]
        
        def emit_for(nid: str, depth: int) -> List[str]:
            n = H.parents[nid]
            parts: List[str] = []
            # 1) direct leaves in order (interleaved with child parents based on doc order)
            for kind, ref in self._sorted_content_items(H, n):
                if kind == "leaf":
                    txt = H.leaf_text.get(ref, "")
                    if txt:
                        parts.append(txt)
                else:  # child parent block
                    child = H.parents[ref]
                    # Insert heading for the child block if requested
                    if include_headings:
                        # Simple visual separation; keep it plain (not markdown unless you want)
                        parts.append(f"\n{child.label}\n")
                    parts.extend(emit_for(ref, depth + 1))
            return parts
        
        out = emit_for(parent_id, H.parents[parent_id].depth)
        return "\n".join([p for p in out if p.strip() != ""])
    
    # ---------------------------------------------------------------------
    # Build / Load
    # ---------------------------------------------------------------------
    def build_automerge_retrieval_source(self, original_weaviate_collection: str, force_update=False):
        """
        Builds a full multi-level hierarchy (parents at all depths) and maps leaves to their direct parent.
        Default: parse 'headers' on each leaf.
        Tries to load from JSON first; if not present, scans Weaviate and then saves to JSON.
        """
        # Try to load existing
        if not force_update and self.load_hierarchy(original_weaviate_collection):
            logger.info(f"[automerge.build] loaded persisted hierarchy for '{original_weaviate_collection}', skipping rebuild")
            return
        
        cfg = HierConfig(
            text_property="text",
            heading_path_property="headers",
            guideline_id_property="guideline_id",
            order_property="chunk_index",
            direct_parent_property=None,
        )
        H = HierIndex(cfg=cfg)
        
        logger.info(f"[automerge.build] start scanning collection='{original_weaviate_collection}'")
        coll = self.client.collections.get(original_weaviate_collection)
        
        # 1) Scan all leaves to learn headings, parents, and cache leaf text/order
        props = ["reference_id", cfg.text_property, cfg.guideline_id_property]
        if cfg.heading_path_property:
            props.append(cfg.heading_path_property)
        if cfg.order_property:
            props.append(cfg.order_property)
        if cfg.direct_parent_property:
            props.append(cfg.direct_parent_property)
        
        logger.debug(f"[automerge.build] fetching properties: {props}")
        
        limit = 1000
        offset = 0
        n = 0
        page_no = 0
        
        while True:
            try:
                page = coll.query.fetch_objects(
                    limit=limit, offset=offset, include_vector=False, return_properties=props,
                )
            except Exception as e:
                logger.error(f"[automerge.build] fetch_objects failed at offset={offset}: {e}")
                break
            objs = page.objects or []
            page_no += 1
            logger.debug(f"[automerge.build] page #{page_no}: size={len(objs)} (offset={offset})")
            
            if not objs:
                break
            
            for obj in objs:
                p = obj.properties or {}
                
                # Prefer Mongo reference_id as the stable leaf id; fallback to weaviate uuid
                leaf_id = str(p.get("reference_id") or getattr(obj, "uuid", "") or "")
                if not leaf_id:
                    logger.warning("[automerge.build] skip object without reference_id/uuid")
                    continue
                
                text = p.get(cfg.text_property, "") or ""
                try:
                    order_val = int(p.get(cfg.order_property, 0) or 0)
                except Exception:
                    order_val = 0
                guideline_id = str(p.get(cfg.guideline_id_property) or "")
                
                H.leaf_text[leaf_id] = text
                H.leaf_order[leaf_id] = order_val
                H.leaf_guideline[leaf_id] = guideline_id
                
                # Decide parent path and direct parent id
                if cfg.direct_parent_property and p.get(cfg.direct_parent_property):
                    direct_parent_id = str(p[cfg.direct_parent_property])
                    self._ensure_parent_node(H, parent_id=direct_parent_id, label=direct_parent_id, parent_parent_id=None)
                    H.leaf_to_parent[leaf_id] = direct_parent_id
                else:
                    raw_path = p.get(cfg.heading_path_property, "")
                    segments = self._parse_heading_path(raw_path)
                    
                    if segments:
                        parent_chain_ids = []
                        for i in range(len(segments)):
                            prefix = segments[: i + 1]
                            pid = self._hash_id(guideline_id or segments[0], prefix)
                            parent_chain_ids.append(pid)
                            label = segments[i]
                            parent_parent_id = parent_chain_ids[i - 1] if i > 0 else None
                            self._ensure_parent_node(H, pid, label, parent_parent_id)
                        if parent_chain_ids:
                            H.leaf_to_parent[leaf_id] = parent_chain_ids[-1]
                    else:
                        # No headers -> fall back to a per-guideline root
                        root_label = guideline_id or "root"
                        root_id = self._hash_id(guideline_id or "root", [root_label])
                        self._ensure_parent_node(H, root_id, root_label, None)
                        H.leaf_to_parent[leaf_id] = root_id
                
                n += 1
                if n % 5000 == 0:
                    logger.debug(f"[automerge.build] processed leaves: {n}")
            
            # advance offset
            if len(objs) < limit:
                break
            offset += limit
        
        logger.info(f"[automerge.build] scanned leaves total={n} from '{original_weaviate_collection}'")
        
        # 2) Link reverse edges: parent -> child leaves; compute parent_of_parent/roots
        for leaf_id, pid in H.leaf_to_parent.items():
            if pid not in H.parents:
                self._ensure_parent_node(H, pid, label=pid, parent_parent_id=None)
            H.parents[pid].child_leaf_ids.append(leaf_id)
        
        for pid, node in H.parents.items():
            if node.parent_id:
                H.parent_of_parent[pid] = node.parent_id
            else:
                H.parent_of_parent[pid] = None
                H.roots.add(pid)
        
        logger.debug(f"[automerge.build] parents={len(H.parents)} (pre-depth), leaf->parent edges={len(H.leaf_to_parent)}")
        
        # 3) Compute depths (BFS from roots)
        for rid in list(H.roots):
            if rid not in H.parents:
                continue
            H.parents[rid].depth = 0
            q = deque([rid])
            while q:
                cur = q.popleft()
                curd = H.parents[cur].depth
                for child_pid in H.parents[cur].child_parent_ids:
                    H.parents[child_pid].depth = curd + 1
                    q.append(child_pid)
        
        logger.debug(f"[automerge.build] roots={len(H.roots)} (after depth assignment)")
        
        # 4) Post-order: compute descendant leaves and counts (ordered by chunk_index)
        def build_desc(pid: str) -> List[str]:
            node = H.parents[pid]
            ids = list(node.child_leaf_ids)
            for cpid in node.child_parent_ids:
                ids.extend(build_desc(cpid))
            ids.sort(key=lambda lid: H.leaf_order.get(lid, 0))
            node.desc_leaf_ids = ids
            node.desc_leaf_count = len(ids)
            return ids
        
        total_desc = 0
        for rid in list(H.roots):
            if rid in H.parents:
                total_desc += len(build_desc(rid))
        
        logger.info(
            f"[automerge.build] done: parents={len(H.parents)} roots={len(H.roots)} "
            f"mapped_leaves={len(H.leaf_to_parent)} total_desc_lists={total_desc}",
        )
        
        self._hier_by_collection[original_weaviate_collection] = H
        
        # Persist to filesystem
        self.save_hierarchy(original_weaviate_collection)
    
    def print_hierarchy_graph(
            self,
            collection_name: str,
            *,
            max_leaf_chars: int = 160,
            log: bool = True,
            save_to_file: bool = True,
    ) -> str:
        """
        Print the entire hierarchy as an ASCII tree.
        Parents: show the heading title (or "/" if empty).
        Leaves : show 'reference_id: text...' (snippet).
        Returns the full rendered string. Optionally logs and saves to a .graph.txt file.

        Args:
            collection_name: Weaviate collection / index name.
            max_leaf_chars : Truncate leaf text to this many chars for readability.
            log           : If True, log each line at INFO.
            save_to_file  : If True, write a '<collection_name>.graph.txt' in the index folder.

        Example line format:
            [ROOT] 007-003 Title
            ├─ [P] 1 Einleitung
            │  ├─ [L] ref_abc123: First chunk text...
            │  └─ [P] 1.1 Priorisierungsgründe
            │     └─ [L] ref_def456: Subsection chunk text...
            └─ [P] 2 Maßnahmen
        """
        # Ensure hierarchy is available
        if collection_name not in self._hier_by_collection:
            loaded = self.load_hierarchy(collection_name)
            if not loaded:
                # build will also save JSON
                self.build_automerge_retrieval_source(collection_name)
        
        H = self._hier_by_collection.get(collection_name)
        if not H:
            raise RuntimeError("Hierarchy not available after load/build.")
        
        lines: List[str] = []
        
        def emit_line(s: str):
            lines.append(s)
            if log:
                logger.info(s)
        
        def leaf_snippet(leaf_id: str) -> str:
            raw = (H.leaf_text.get(leaf_id) or "").replace("\n", " ").strip()
            if len(raw) > max_leaf_chars:
                return raw[:max_leaf_chars].rstrip() + "…"
            return raw
        
        def title_of(pid: str) -> str:
            node = H.parents.get(pid)
            if not node:
                return "/"
            t = (node.label or "").strip()
            return t or "/"
        
        def emit_children(parent_id: str, prefix: str):
            """Emit interleaved children (direct leaves + child parents) in doc order."""
            node = H.parents[parent_id]
            items = self._sorted_content_items(H, node)  # [("leaf", lid), ("parent", cpid), ...]
            total = len(items)
            for idx, (kind, ref) in enumerate(items):
                is_last = (idx == total - 1)
                branch = "└─ " if is_last else "├─ "
                next_prefix = prefix + ("   " if is_last else "│  ")
                
                if kind == "leaf":
                    # print: [L] <reference_id>: <snippet>
                    snippet = leaf_snippet(ref)
                    emit_line(f"{prefix}{branch}[L] {ref}: {snippet}")
                else:
                    # child parent node line: [P] <title>
                    emit_line(f"{prefix}{branch}[P] {title_of(ref)}")
                    emit_children(ref, next_prefix)
        
        # Multiple roots are possible (e.g. one per guideline). Keep deterministic order:
        root_ids = sorted(H.roots, key=lambda rid: title_of(rid))
        
        for i, rid in enumerate(root_ids):
            if i > 0:
                # Blank line between roots for readability
                emit_line("")
            emit_line(f"[ROOT] {title_of(rid)}")
            emit_children(rid, "")
        
        rendered = "\n".join(lines)
        
        # Optionally save to <folder>/<collection_name>.graph.txt
        if save_to_file:
            out_path = (self._index_folder() / f"{collection_name}.graph.txt")
            with out_path.open("w", encoding="utf-8") as f:
                f.write(rendered + "\n")
            logger.info(f"[automerge.graph] wrote ASCII tree: {out_path}")
        
        return rendered
    
    def parent_descendant_leaf_ids(self, collection_name: str, parent_id: str) -> List[str]:
        """Return ALL descendant leaf reference_ids for a given parent."""
        H = self._hier_by_collection.get(collection_name)
        if not H and not self.load_hierarchy(collection_name):
            raise RuntimeError("Hierarchy not built or persisted.")
        H = self._hier_by_collection[collection_name]
        node = H.parents.get(parent_id)
        if not node:
            return []
        return list(node.desc_leaf_ids)
    
    # ---------------------------------------------------------------------
    # Retrieve + Auto-merge
    # ---------------------------------------------------------------------
    def retrieve_automerge(
            self,
            collection_name: str,
            retrieval_start: List[WeaviateSearchChunkResult],
            simple_ratio_threshold: float = 0.6,
    ) -> List[WeaviateSearchChunkResult]:
        """
        Input  : retrieval_start = leaf hits from your Weaviate hybrid search.
        Output : ONLY leaf nodes (original references). Parents are used for promotion/expansion,
                 but are not returned themselves.
                 If a parent is promoted, include ALL of its descendant leaves (each as an individual hit).
        Length : trimmed to the same size as retrieval_start.
        """
        # Ensure hierarchy is loaded (allow warm starts)
        if collection_name not in self._hier_by_collection:
            loaded = self.load_hierarchy(collection_name)
            if not loaded:
                raise RuntimeError(
                    "Hierarchy not built or persisted. "
                    "Call build_automerge_retrieval_source(...) first.",
                )
        
        H = self._hier_by_collection.get(collection_name)
        if not H:
            raise RuntimeError("Hierarchy not built. Call build_automerge_retrieval_source(...) first.")
        
        k = len(retrieval_start)
        logger.info(f"[automerge.retrieve] start collection='{collection_name}' hits={k} ratio={simple_ratio_threshold:.2f}")
        
        # Build quick lookup: original leaf hits by reference_id
        leaf_hits_map: Dict[str, WeaviateSearchChunkResult] = {}
        for hit in retrieval_start:
            rc = hit.retrieved_chunk or {}
            lid = str(rc.get("reference_id") or rc.get("id") or rc.get("_id") or "")
            if lid:
                leaf_hits_map[lid] = hit
        
        # 1) Aggregate coverage bottom-up for all ancestors
        cov: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"leaf_ids": set(), "sum": 0.0, "max": 0.0})
        used_hits = 0
        for lid, hit in leaf_hits_map.items():
            pid = H.leaf_to_parent.get(lid)
            if not pid:
                continue
            used_hits += 1
            score = float(hit.score or 0.0)
            chain = [pid] + self._get_ancestors(H, pid)
            for p in chain:
                s = cov[p]
                if lid not in s["leaf_ids"]:
                    s["leaf_ids"].add(lid)
                    s["sum"] += score
                    s["max"] = max(s["max"], score)
        
        logger.debug(f"[automerge.retrieve] covered parents={len(cov)} from used_hits={used_hits}")
        
        # 2) Select candidates by ratio
        candidates: Set[str] = set()
        for pid, s in cov.items():
            node = H.parents.get(pid)
            if not node:
                continue
            denom = max(1, node.desc_leaf_count)
            numer = len(s["leaf_ids"])
            ratio = numer / float(denom)
            if ratio >= simple_ratio_threshold:
                candidates.add(pid)
        
        logger.debug(f"[automerge.retrieve] candidates={len(candidates)}")
        
        # 3) Promotion frontier (no promoted node whose ancestor is also promoted)
        def has_promoted_ancestor(p_id: str) -> bool:
            for anc in self._get_ancestors(H, p_id):
                if anc in candidates:
                    return True
            return False
        
        frontier: Set[str] = {pid for pid in candidates if not has_promoted_ancestor(pid)}
        logger.info(f"[automerge.retrieve] frontier={len(frontier)}")
        
        # 4) Expand parents -> leaves, keep only leaf items
        expanded_leaf_ids: Set[str] = set()
        synthesized_leaf_hits: List[WeaviateSearchChunkResult] = []
        
        for pid in frontier:
            node = H.parents[pid]
            s = cov[pid]
            # Inherit score uniformly to non-retrieved descendants
            denom = max(1, node.desc_leaf_count)
            inherited_score = float(s["sum"]) / float(denom) if denom else 0.0
            
            for lid in node.desc_leaf_ids:
                expanded_leaf_ids.add(lid)
                if lid in leaf_hits_map:
                    # Already have a real hit; keep as-is
                    continue
                full_chunk = self.weaviate_vector_db_service.find_by_reference_id(collection_name, lid)
                # Create a synthesized leaf hit (minimal properties)
                synthesized_leaf_hits.append(
                    WeaviateSearchChunkResult(
                        retrieved_chunk={
                            **full_chunk,
                            "reference_id": lid,
                            "text": H.leaf_text.get(lid, ""),
                            "is_automerge_expanded": True,
                            "expanded_from_parent_id": pid,
                            "expanded_from_parent_label": node.label,
                        },
                        score=inherited_score,
                    ),
                )
        
        logger.info(
            "[automerge.retrieve] expanded_parents=%d -> expanded_leaves=%d synthesized=%d",
            len(frontier), len(expanded_leaf_ids), len(synthesized_leaf_hits),
        )
        
        # 5) Keep remaining original leaves that are NOT under any promoted parent
        remaining_original_hits: List[WeaviateSearchChunkResult] = []
        for lid, hit in leaf_hits_map.items():
            if lid in expanded_leaf_ids:
                # if it's under a promoted parent and we already have a real hit, keep it,
                # but don't duplicate; we’ll add all real hits later
                continue
            remaining_original_hits.append(hit)
        
        # 6) Combine:
        # - all real hits whose lids are under promoted parents (so they don't get lost),
        # - synthesized expanded leaf hits for lids not present in original hits,
        # - remaining original hits outside promoted parents
        real_hits_under_promoted: List[WeaviateSearchChunkResult] = [
            leaf_hits_map[lid] for lid in expanded_leaf_ids if lid in leaf_hits_map
        ]
        
        final_leaf_hits: List[WeaviateSearchChunkResult] = (
                real_hits_under_promoted + synthesized_leaf_hits + remaining_original_hits
        )
        
        # 7) Sort and trim to original length
        final_leaf_hits.sort(key=lambda x: x.score, reverse=True)
        
        logger.info(
            "[automerge.retrieve] final_leaf_count=%d (real_under_promoted=%d, synthesized=%d, remaining=%d)",
            len(final_leaf_hits), len(real_hits_under_promoted), len(synthesized_leaf_hits), len(remaining_original_hits),
        )
        return final_leaf_hits
