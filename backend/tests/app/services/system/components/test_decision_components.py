import app.services.system.components.component_registry  # noqa: F401

from app.services.system.components.abstract_component import ComponentContext
from app.services.system.components.decision.expression_decision import ExpressionDecisionComponent
from app.services.system.components.decision.scope_decision import ScopeDecisionComponent
from app.services.system.components.structure.decider_component import DeciderComponent
from app.utils.system.resolve_component_path import resolve_component_path


def test_resolve_component_path_for_decision_components():
    assert resolve_component_path(["decision", "expression"]) is ExpressionDecisionComponent
    assert resolve_component_path(["decision", "is_within_scope"]) is ScopeDecisionComponent
    assert resolve_component_path(["decider"]) is DeciderComponent


def test_expression_decision_emits_true_label():
    component = ExpressionDecisionComponent(
        component_id="expr",
        name="Expression",
        parameters={
            "value": "{return len(query_aug.subqueries) > 1}",
            "reason": "Multiple subqueries available.",
        },
        variant="expression",
    )

    data, next_component_id = component.execute({"query_aug.subqueries": ["a", "b"]})

    assert next_component_id == ""
    assert data["expr.value"] is True
    assert data["expr.label"] == "true"
    assert data["expr.reason"] == "Multiple subqueries available."


def test_decider_selects_branch_from_boolean():
    component = DeciderComponent(
        component_id="branch",
        name="Branch",
        parameters={
            "decision": "{scope.value}",
            "cases": {
                "true": "in_scope_generator",
                "false": "out_of_scope_generator",
            },
        },
        variant="decider",
    )

    data, next_component_id = component.execute({"scope.value": False})

    assert next_component_id == "out_of_scope_generator"
    assert data["branch.case_key"] == "false"
    assert data["branch.selected_next_component_id"] == "out_of_scope_generator"


def test_scope_decision_parses_yes_no_response():
    class FakeLLMInteractionService:
        def generate_text(self, **kwargs):
            assert "oral and maxillofacial surgery" in kwargs["prompt"].lower()
            return "DECISION: yes\nREASON: Query concerns OMFS guideline content."

    component = ScopeDecisionComponent(
        component_id="scope",
        name="Scope decision",
        parameters={
            "scope_description": "German AWMF guideline questions about oral and maxillofacial surgery.",
            "llm_settings": {"model": "gpt-test"},
            "allowed_examples": ["Wie wird eine Kieferzyste behandelt?"],
            "disallowed_examples": ["Wie wird Asthma behandelt?"],
        },
        variant="is_within_scope",
    )
    component.bind_context(ComponentContext(wf_id="wf-test", llm_interaction_service=FakeLLMInteractionService()))

    data, next_component_id = component.execute({"start.current_user_input": "Wie wird eine Kieferzyste behandelt?"})

    assert next_component_id == ""
    assert data["scope.value"] is True
    assert data["scope.label"] == "true"
    assert data["scope.query"] == "Wie wird eine Kieferzyste behandelt?"
    assert data["scope.full_response"].startswith("DECISION: yes")
