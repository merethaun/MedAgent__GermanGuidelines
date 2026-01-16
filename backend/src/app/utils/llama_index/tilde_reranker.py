from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Dict, List

import numpy as np
import torch
import torch.nn.functional as F
from llama_index.core import QueryBundle
from llama_index.core.postprocessor.types import BaseNodePostprocessor
from llama_index.core.schema import NodeWithScore
from pydantic import PrivateAttr
from scipy.special import expit
from transformers import AutoTokenizer, AutoModelForMaskedLM, BertLMHeadModel, BertTokenizerFast

from app.utils.logger import setup_logger

logger = setup_logger(name=__name__)


@dataclass
class TILDEModel:
    """A reranker based on TILDE or TILDEv2."""
    
    model_name: str = "ielab/TILDE"
    device: Optional[str] = None
    alpha: float = 1.0
    use_tilde_v2: bool = False
    
    _model: torch.nn.Module = field(init=False, repr=False)
    _tokenizer: AutoTokenizer = field(init=False, repr=False)
    
    def __post_init__(self) -> None:
        self.device = self.device or "cpu"
        logger.debug("Initialising TILDE reranker on device %s", self.device)
        
        if self.use_tilde_v2:
            self._model = AutoModelForMaskedLM.from_pretrained(self.model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        else:
            self._model = BertLMHeadModel.from_pretrained(self.model_name)
            try:
                self._tokenizer = BertTokenizerFast.from_pretrained("bert-base-uncased")
            except Exception:
                self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        
        self._model.to(self.device).eval()
        
        torch.manual_seed(42)
        np.random.seed(42)
        torch.use_deterministic_algorithms(True)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(42)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    
    def _score_tilde(self, query: str, passage: str) -> float:
        enc = self._tokenizer(passage, return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}
        with torch.no_grad():
            logits = self._model(**enc).logits[:, 0]
            log_probs = F.log_softmax(logits, dim=-1)
        
        query_ids = self._tokenizer(query, add_special_tokens=False)["input_ids"]
        if not query_ids:
            return float("-inf")
        
        query_log_probs = log_probs[0, query_ids].sum().item() / len(query_ids)
        
        if self.alpha >= 1.0:
            return query_log_probs
        
        enc_q = self._tokenizer(query, return_tensors="pt")
        enc_q = {k: v.to(self.device) for k, v in enc_q.items()}
        with torch.no_grad():
            doc_logits = self._model(**enc_q).logits[:, 0]
            doc_log_probs = F.log_softmax(doc_logits, dim=-1)
        
        passage_ids = self._tokenizer(passage, add_special_tokens=False)["input_ids"]
        doc_log_prob = (
            doc_log_probs[0, passage_ids].sum().item() / len(passage_ids)
            if passage_ids else float("-inf")
        )
        
        return self.alpha * query_log_probs + (1.0 - self.alpha) * doc_log_prob
    
    def _score_tildev2(self, query: str, passage: str) -> float:
        # !! got some problems, but not worth looking into
        p_enc = self._tokenizer(passage, return_tensors="pt")
        q_enc = self._tokenizer(query, return_tensors="pt", add_special_tokens=False)
        p_enc = {k: v.to(self.device) for k, v in p_enc.items()}
        
        with torch.no_grad():
            outputs = self._model(**p_enc)
            last_hidden = getattr(outputs, "last_hidden_state", outputs[0]).squeeze(0)
            
            projection = next(
                (getattr(self._model, name)
                 for name in ("score", "project", "classifier", "lm_head")
                 if hasattr(self._model, name)),
                None,
            )
            if projection is None:
                raise RuntimeError("Unable to locate projection layer for TILDEv2 model")
            
            weights = projection(last_hidden).squeeze(-1)
            if weights.ndim > 1:
                weights = weights[:, 0]
        
        passage_ids = p_enc["input_ids"].squeeze(0).tolist()
        term_weights: Dict[int, float] = {}
        for token_id, weight in zip(passage_ids, weights.tolist()):
            if token_id in (self._tokenizer.cls_token_id, self._tokenizer.sep_token_id):
                continue
            term_weights[token_id] = term_weights.get(token_id, 0.0) + weight
        
        if not term_weights:
            return 0.0
        
        query_ids = q_enc["input_ids"].squeeze(0).tolist()
        return sum(term_weights.get(tid, 0.0) for tid in query_ids)
    
    def score(self, query: str, passages: Sequence[str]) -> List[float]:
        return [
            self._score_tildev2(query, psg) if self.use_tilde_v2 else self._score_tilde(query, psg)
            for psg in passages
        ]
    
    @staticmethod
    def normalize_tildev2(scores: List[float]) -> List[float]:
        return [float(expit(s)) for s in scores]


class TILDEv2Reranker(BaseNodePostprocessor):
    _tilde_model: TILDEModel = PrivateAttr()
    _top_n: int = PrivateAttr()
    
    def __init__(
            self,
            tilde_model: str = "ielab/TILDE",
            tilde_v2: bool = False,
            alpha: float = 1.0,
            top_n: int = 5,
            **data: Any,
    ):
        """
        TILDEv2-based reranker for LlamaIndex nodes using transformer-based query-passage scoring.
        """
        super().__init__(**data)
        self._tilde_model = TILDEModel(model_name=tilde_model, use_tilde_v2=tilde_v2, alpha=alpha)
        self._top_n = top_n
    
    def postprocess_nodes(
            self,
            nodes: List[NodeWithScore],
            query_bundle: Optional[QueryBundle] = None,
            query_str: Optional[str] = None,
    ) -> List[NodeWithScore]:
        query = query_bundle.query_str if query_bundle is not None else query_str
        if query is None:
            raise ValueError("Either query_bundle or query_str must be provided.")
        
        texts = [node.node.text for node in nodes]
        raw_scores = self._tilde_model.score(query, texts)
        
        for node, score in zip(nodes, raw_scores):
            node.score = score
        
        return sorted(nodes, key=lambda n: n.score or 0.0, reverse=True)[:self._top_n]
    
    def _postprocess_nodes(
            self, nodes: List[NodeWithScore], query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        return self.postprocess_nodes(nodes, query_bundle)
    
    def normalize_score(self, original_score: float) -> float:
        return self._tilde_model.normalize_tildev2([original_score])[0]
