from healthcare import Instance, Solution, NurseSchedulingFactory, SchedulingProblem
from healthcare.visualize import visualize
import pathlib
import os
import json


def parse_from_json_file(fname) -> SchedulingProblem:
    with open(fname, "r") as f:
        instance = f.read()

    instance: Instance = Instance.from_json(instance)
    return instance.scheduling_problem()


def main():
    examples_path = pathlib.Path(__file__).parent.resolve()
    instance_path = os.path.join(examples_path, "instances/instance1.json")
    solution_path = os.path.join(examples_path, "instances/instance1_solution.json")
    visualization_path = os.path.join(
        examples_path, "instances/instance1_visualize.html"
    )
    problem = parse_from_json_file(instance_path)

    factory = NurseSchedulingFactory(problem)
    model, nurse_view = factory.get_optimization_model()

    if model.solve(solver="ortools", time_limit=20 * 60):
        print("Total penalty:", model.objective_value())

        solution = Solution.from_nurse_view(nurse_view.value(), factory)
        with open(solution_path, "w") as f:
            f.write(json.dumps(json.loads(solution.to_json()), indent=4))

        style = visualize(problem, solution)
        with open(visualization_path, "w") as f:
            f.write(style.to_html())
    else:
        print("No solution.")


if __name__ == "__main__":
    main()
