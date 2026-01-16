import time
from copy import deepcopy
from typing import Dict, Any, List, Tuple

from app.models.chat.chat import Chat, RetrievalResult, WorkflowComponentExecutionResult
from app.models.system.workflow_system import WorkflowConfig
from app.services.system.components import render_template
from app.services.system.components.resolve_component_path import resolve_component_path
from app.services.system.workflow_system_storage import WorkflowSystemStorageService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WorkflowSystemInteractionService:
    """
    Service that manages all initialized WorkflowSystemInteraction instances.
    """
    
    def __init__(self, wf_def_service: WorkflowSystemStorageService):
        self.wf_def_service = wf_def_service
    
    def generate_response(
            self, wf_id: str, chat: Chat,
    ) -> Tuple[str, List[RetrievalResult], float, float, List[WorkflowComponentExecutionResult]]:
        wf = self.wf_def_service.get_workflow_entry_by_id(wf_id=wf_id)
        
        wf_interaction = _WorkflowSystemInteraction(wf_id, WorkflowConfig(name=wf.name, nodes=wf.nodes, edges=wf.edges))
        for passed_interaction in chat.interactions[:-1]:
            wf_interaction.load_execution(passed_interaction.workflow_execution)
        
        return wf_interaction.generate_response(chat)


class _WorkflowSystemInteraction:
    def __init__(self, wf_id: str, config: WorkflowConfig):
        self.wf_id = wf_id
        self._initialize_from_config(config, deepcopy_params=True)
        logger.info(f"Workflow '{self.name}' parsed successfully")
    
    def load_execution(self, execution: List[WorkflowComponentExecutionResult]):
        for entry in execution:
            component_id = entry.component_id
            if component_id not in self.components:
                raise ValueError(f"Component '{component_id}' not found.")
            
            self.components[component_id].load_execution_result(entry)
    
    def _initialize_from_config(self, config: WorkflowConfig, deepcopy_params: bool = False):
        self.name = config.name
        self.components = {}
        
        self.start_node, self.end_node = "start", "end"
        self.max_execution_steps = 100
        
        self._build_components(config, deepcopy_params=deepcopy_params)
        self._build_edges(config)
    
    def _build_components(self, config: WorkflowConfig, deepcopy_params: bool = False):
        for node_config in config.nodes:
            logger.info(f"Adding node '{node_config.name}' (ID: {node_config.component_id})")
            component_path = node_config.type.split("/")
            variant_cls = resolve_component_path(component_path)
            parameters = deepcopy(node_config.parameters) if deepcopy_params else node_config.parameters
            component = variant_cls(
                component_id=node_config.component_id,
                name=node_config.name,
                parameters=parameters,
                variant=component_path[-1],
            )
            self.components[node_config.component_id] = component
    
    def _build_edges(self, config: WorkflowConfig):
        for edge in config.edges:
            source, target = edge.source, edge.target
            if source not in self.components:
                raise ValueError(f"Source node '{source}' not found in workflow '{self.name}'")
            if target not in self.components:
                raise ValueError(f"Target node '{target}' not found in workflow '{self.name}'")
            self.components[source].set_next_component(target)
    
    def _deep_equal(self, a, b):
        # treat NaNs as equal; handle dicts/lists/tuples/sets recursively
        import math
        if a is b:  # same object or both None
            return True
        if type(a) != type(b):
            # special-case bool vs int to avoid 1 == True masking changes
            return False
        if isinstance(a, float):
            return (math.isnan(a) and math.isnan(b)) or (a == b)
        if isinstance(a, dict):
            if a.keys() != b.keys():
                return False
            return all(self._deep_equal(a[k], b[k]) for k in a)
        if isinstance(a, (list, tuple)):
            return len(a) == len(b) and all(self._deep_equal(x, y) for x, y in zip(a, b))
        if isinstance(a, set):
            return a == b
        try:
            return a == b
        except Exception:
            # Fallback for types with elementwise equality (e.g., NumPy/Pandas)
            try:
                import numpy as np
                return np.array_equal(a, b, equal_nan=True)
            except Exception:
                return False
    
    def generate_response(self, chat: Chat) -> Tuple[str, List[RetrievalResult], float, float, List[WorkflowComponentExecutionResult]]:
        current_node = self.start_node
        data: Dict[str, Any] = {"chat": chat}
        
        execution_tracker: List[WorkflowComponentExecutionResult] = []
        execution_tracker_counter = 0
        
        start_time = time.time()
        
        def _clean_in_output(obj):
            if "chat" in obj:
                obj["chat"] = {"note": "Chat object omitted from input / output to avoid nesting"}
            return obj
        
        while True:
            execution_tracker_input = _clean_in_output(deepcopy(data))
            
            component = self.components.get(current_node)
            if component is None:
                raise ValueError(f"Component '{current_node}' not found in workflow definition")
            
            execution_tracker_component = component.id
            
            update_data, next_component_id = component.execute_with_time(data)
            data.update(update_data)
            execution_tracker_output = _clean_in_output(deepcopy(data))
            
            diff_output = {
                d: v
                for d, v in execution_tracker_output.items()
                if not d in execution_tracker_input or not self._deep_equal(execution_tracker_input[d], v)
            }
            
            execution_tracker.append(
                WorkflowComponentExecutionResult(
                    component_id=execution_tracker_component,
                    execution_order=execution_tracker_counter,
                    input={},
                    output=diff_output,
                ),
            )
            if next_component_id == "" or current_node == self.end_node:
                logger.info(f"Reached end node '{self.end_node}' after {execution_tracker_counter} steps.")
                break
            elif next_component_id not in self.components:
                logger.warning(f"Component '{next_component_id}' not found in workflow definition")
                raise ValueError(f"No outgoing edge found for node '{current_node}', and it's not the end node.")
            
            current_node = next_component_id
            execution_tracker_counter += 1
            if execution_tracker_counter > self.max_execution_steps:
                raise ValueError(f"Maximum execution steps ({self.max_execution_steps}) reached.")
        
        end_time = time.time()
        
        response = render_template("{end.response}", data)
        retrieval = render_template("{end.retrieval}", data)
        retrieval_latency = render_template("{end.retrieval_latency}", data)
        
        return response, retrieval, float(end_time - start_time), retrieval_latency, execution_tracker
