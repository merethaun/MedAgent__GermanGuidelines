import math
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.models.system.system_chat_interaction import Chat, RetrievedWorkflowItem, WorkflowComponentExecutionResult
from app.models.system.workflow_system import WorkflowConfig
from app.services.system.components.abstract_component import ComponentContext
from app.services.system.workflow_system_storage_service import WorkflowSystemStorageService
from app.services.tools import LLMInteractionService
from app.utils.logging import setup_logger
from app.utils.system.render_template import render_template
from app.utils.system.resolve_component_path import resolve_component_path

logger = setup_logger(__name__)


@dataclass
class WorkflowSystemInteractionService:
    """Build a runtime from a stored WorkflowConfig and execute it for a given chat."""
    
    storage: WorkflowSystemStorageService
    llm_interaction_service: LLMInteractionService
    
    def generate_response(
            self,
            wf_id: str,
            chat: Chat,
    ) -> Tuple[str, List[RetrievedWorkflowItem], float, float, List[WorkflowComponentExecutionResult]]:
        wf = self.storage.get_workflow_by_id(wf_id)
        runtime = WorkflowRuntime(
            wf_id=wf_id,
            config=WorkflowConfig(name=wf.name, nodes=wf.nodes, edges=wf.edges),
            deepcopy_params=True,
            context=ComponentContext(
                wf_id=wf_id,
                llm_interaction_service=self.llm_interaction_service,
            ),
        )
        
        # Restore component state from previous interactions (everything except the new last prompt).
        for past in (chat.interactions or [])[:-1]:
            execution = getattr(past, "workflow_execution", None)
            if execution:
                runtime.load_execution(execution)
        
        return runtime.run(chat)


@dataclass
class WorkflowRuntime:
    wf_id: str
    config: WorkflowConfig
    deepcopy_params: bool = True
    
    start_node: str = "start"
    end_node: str = "end"
    max_steps: int = 100
    
    components: Dict[str, Any] = field(default_factory=dict)
    context: Optional[ComponentContext] = None
    
    def __post_init__(self) -> None:
        self._build_components()
        self._build_edges()
        logger.info(
            "Workflow runtime initialized: wf_id=%s name=%s nodes=%d edges=%d",
            self.wf_id, self.config.name, len(self.config.nodes), len(self.config.edges),
        )
    
    # -------------------------
    # Restore component state
    # -------------------------
    def load_execution(self, execution: List[WorkflowComponentExecutionResult]) -> None:
        for entry in execution:
            cid = entry.component_id
            comp = self.components.get(cid)
            if comp is None:
                raise ValueError(f"Component '{cid}' not found in workflow '{self.config.name}'")
            comp.load_execution_result(entry)
    
    # -------------------------
    # Execute
    # -------------------------
    def run(
            self,
            chat: Chat,
    ) -> Tuple[str, List[RetrievedWorkflowItem], float, float, List[WorkflowComponentExecutionResult]]:
        current = self.start_node
        data: Dict[str, Any] = {"chat": chat}
        
        execution: List[WorkflowComponentExecutionResult] = []
        step = 0
        t0 = time.time()
        
        while True:
            if step > self.max_steps:
                raise ValueError(f"Max execution steps reached: {self.max_steps}")
            
            comp = self.components.get(current)
            if comp is None:
                raise ValueError(f"Component '{current}' not found in workflow '{self.config.name}'")
            
            before = _scrub_for_trace(deepcopy(data))
            
            update, next_id = comp.execute_with_time(data)
            data.update(update)
            
            after = _scrub_for_trace(deepcopy(data))
            diff = _diff_dict(before, after)
            
            execution.append(
                WorkflowComponentExecutionResult(
                    component_id=comp.id,
                    execution_order=step,
                    input={},  # keep minimal; diff-only output is usually enough
                    output=diff,
                ),
            )
            
            if not next_id or current == self.end_node:
                logger.info("Workflow finished: wf_id=%s steps=%d", self.wf_id, step)
                break
            
            if next_id not in self.components:
                raise ValueError(f"Next component '{next_id}' not found (from '{current}')")
            
            current = next_id
            step += 1
        
        t1 = time.time()
        
        response = render_template("{end.response}", data)
        retrieval = render_template("{end.retrieval}", data)
        retrieval_latency_raw = render_template("{end.retrieval_latency}", data)
        
        retrieval_latency = _safe_float(retrieval_latency_raw, default=0.0)
        total_latency = float(t1 - t0)
        
        return response, retrieval, total_latency, retrieval_latency, execution
    
    # -------------------------
    # Build runtime graph
    # -------------------------
    def _build_components(self) -> None:
        
        self.components = {}
        
        for node in self.config.nodes:
            component_path = node.type.split("/")
            variant_cls = resolve_component_path(component_path)
            
            params = deepcopy(node.parameters) if self.deepcopy_params else node.parameters
            instance = variant_cls(
                component_id=node.component_id,
                name=node.name,
                parameters=params,
                variant=component_path[-1],
            )
            
            if self.context is not None:
                instance.bind_context(self.context)
            
            self.components[node.component_id] = instance
        
        # Early sanity (optional but very helpful)
        if self.start_node not in self.components:
            raise ValueError(f"Workflow '{self.config.name}' missing start node id='{self.start_node}'")
        if self.end_node not in self.components:
            raise ValueError(f"Workflow '{self.config.name}' missing end node id='{self.end_node}'")
    
    def _build_edges(self) -> None:
        for edge in self.config.edges:
            if edge.source not in self.components:
                raise ValueError(f"Edge source '{edge.source}' not found in workflow '{self.config.name}'")
            if edge.target not in self.components:
                raise ValueError(f"Edge target '{edge.target}' not found in workflow '{self.config.name}'")
            self.components[edge.source].set_next_component(edge.target)


# -------------------------
# Trace helpers
# -------------------------
def _scrub_for_trace(d: Dict[str, Any]) -> Dict[str, Any]:
    if "chat" in d:
        d = dict(d)
        d["chat"] = {"note": "Chat omitted to avoid nesting"}
    return d


def _diff_dict(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in after.items():
        if k not in before or not _deep_equal(before[k], v):
            out[k] = v
    return out


def _deep_equal(a: Any, b: Any) -> bool:
    if a is b:
        return True
    if type(a) != type(b):
        return False
    
    if isinstance(a, float):
        return (math.isnan(a) and math.isnan(b)) or (a == b)
    
    if isinstance(a, dict):
        if a.keys() != b.keys():
            return False
        return all(_deep_equal(a[k], b[k]) for k in a)
    
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_deep_equal(x, y) for x, y in zip(a, b))
    
    if isinstance(a, set):
        return a == b
    
    try:
        return a == b
    except Exception:
        return False


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default
