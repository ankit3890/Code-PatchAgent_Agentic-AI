from agents.planner import PlannerAgent
from agents.reader import ReaderAgent
from rag.retriever import CodeRetriever


planner = PlannerAgent()

retriever = CodeRetriever(
    collection_name="ML-Movie-Recommendation",
)

reader = ReaderAgent(retriever)

plan = planner.plan(
    "Add JWT authentication."
)

result = reader.read(plan)

print(result.model_dump_json(indent=4))