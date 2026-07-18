import logging

from langchain.chat_models import init_chat_model

from prompts.planner.prompt import PLANNER_PROMPT
from prompts.planner.schema import Plan

from config import settings

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PlannerAgent:

    def __init__(
        self,
        model: str = settings.model_name,
        model_provider: str = settings.model_provider,
    ):
        self.llm = init_chat_model(
            model,
            model_provider=model_provider,
        ).with_structured_output(Plan)

    def plan(self, user_request: str) -> Plan:
        messages = [
            ("system", PLANNER_PROMPT),
            ("user", user_request),
        ]

        try:
            return self.llm.invoke(messages)
        except Exception:
            logger.exception(
                "Planner LLM call failed for request: %.200s", user_request
            )
            raise