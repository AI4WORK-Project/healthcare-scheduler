from healthcare import Instance, Solution, NurseSchedulingFactory, SchedulingProblem
from healthcare.visualize import visualize


def parse_from_json_file(fname) -> SchedulingProblem:
    with open(fname, "r") as f:
        instance = f.read()

    instance: Instance = Instance.from_json(instance)
    return instance.scheduling_problem()


def main():
    instance = "instances/instance1.json"
    problem = parse_from_json_file(instance)

    factory = NurseSchedulingFactory(problem)
    model, nurse_view = factory.get_optimization_model()

    if model.solve(solver="ortools", time_limit=20 * 60):
        print("Total penalty:", model.objective_value())

        solution = Solution.from_nurse_view(nurse_view.value(), factory)
        with open("instances/instance1_solution.json", "w") as f:
            f.write(solution.to_json())

        style = visualize(problem, solution)
        with open(f"instances/instance1_visualize.html", "w") as f:
            f.write(style.to_html())
    else:
        print("No solution.")


if __name__ == "__main__":
    main()
