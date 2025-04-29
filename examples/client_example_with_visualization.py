import os
import json
import requests
import webbrowser
from healthcare import Instance, Solution, SchedulingProblem
from healthcare.visualize import visualize


def parse_from_json_file(fname) -> SchedulingProblem:
    with open(fname, "r") as f:
        instance = f.read()

    instance: Instance = Instance.from_json(instance)
    return instance.scheduling_problem()


def main():
    url = "http://0.0.0.0:5000/schedule"

    instance_path = "instances/instance1.json"
    with open(instance_path, "r") as f:
        instance = json.load(f)

    response = requests.post(url, params={"time_limit": 10 * 60}, json=instance)

    print("Status Code:", response.status_code)
    if response.ok:
        print("Response JSON:", response.json())

        problem = parse_from_json_file(instance_path)
        solution: Solution = Solution.from_dict(response.json())
        style = visualize(problem, solution)
        visualize_path = "instances/instance1_visualize.html"
        with open(visualize_path, "w") as f:
            f.write(style.to_html())
            
        abs_path = os.path.abspath(visualize_path)
        webbrowser.open(f'file://{abs_path}')

    else:
        print("No solution.")


if __name__ == "__main__":
    main()
