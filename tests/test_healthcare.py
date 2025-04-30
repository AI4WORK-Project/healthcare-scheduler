from healthcare import Instance, Solution, NurseSchedulingFactory
from healthcare.instance import ShiftRequest
import pathlib
import os
from typing import Tuple, List


def solve_instance(instance: int) -> Tuple[Instance, Solution]:
    instances_path = os.path.join(pathlib.Path(__file__).parent.resolve(), "instances")
    instance_path = os.path.join(instances_path, f"instance{instance}.json")

    with open(instance_path, "r") as f:
        instance = f.read()

    instance: Instance = Instance.from_json(instance)
    problem = instance.scheduling_problem()
    factory = NurseSchedulingFactory(problem)
    model, nurse_view = factory.get_optimization_model()

    assert model.solve(solver="ortools")
    return instance, Solution.from_nurse_view(nurse_view.value(), factory)


def assert_days_off(instance: Instance, solution: Solution):
    for days_off in instance.days_off:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == days_off.employee_id:
                for day in days_off.day_indexes:
                    assert shifts.shifts[day] == "-"


def assert_shift_on(requests: List[ShiftRequest], solution: Solution):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == "-"
                    or shifts.shifts[request.day] == request.shift_id
                )


def assert_shift_off(requests: List[ShiftRequest], solution: Solution):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == "-"
                    or shifts.shifts[request.day] != request.shift_id
                )


def test_instance0():
    instance, solution = solve_instance(0)
    assert_days_off(instance, solution)
    assert_shift_on(instance.shift_on_requests, solution)
    assert_shift_off(instance.shift_off_requests, solution)
