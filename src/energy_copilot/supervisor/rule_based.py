"""G0 fixed orchestrator; determines routing, never a heat start or service threshold."""
from .contracts import SupervisorAction


class RuleBasedModel:
    name='G0-rule';is_live_llm=False
    def decide(self,context,tools):
        return SupervisorAction(context['required_next_tool'],context.get('next_plan_mode'))
