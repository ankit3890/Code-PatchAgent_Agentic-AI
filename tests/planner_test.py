import json
import logging

from agents.planner import PlannerAgent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
)


def run_test(planner: PlannerAgent, request: str):
    print("\n" + "=" * 100)
    print(f"USER REQUEST:\n{request}")
    print("=" * 100)

    try:
        plan = planner.plan(request)

        print("\nPLAN\n")
        print(json.dumps(plan.model_dump(), indent=4))

        # Basic validations
        assert plan.goal
        assert len(plan.subtasks) > 0
        assert len(plan.required_context) > 0
        assert plan.next_agent == "reader"

        print("\n✅ Test Passed")

    except Exception as e:
        print(f"\n❌ Test Failed: {e}")


def main():

    planner = PlannerAgent()

    requests = [

         "Fix the NullPointerException in UserService.",
        # "Refactor the authentication module.",
        # "Write unit tests for LoginController.",
        # "Update the README with installation instructions.",
        # "Implement OAuth2 login using Google.",
        # "Optimize SQL queries for the dashboard.",
        # "Add Redis caching for user sessions.",
    ]

    for request in requests:
        run_test(planner, request)


if __name__ == "__main__":
    main()