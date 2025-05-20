from healthcare import Instance, Solution, NurseSchedulingFactory
from healthcare.instance import ShiftRequest
from healthcare.solution import EmployeeShifts
import pathlib
import os
from typing import Tuple, List, Dict, Optional
import pytest


FREE = "-"


def solve_instance(
    instance: int, time_limit: Optional[int] = None
) -> Tuple[Instance, Solution, int]:
    instances_path = os.path.join(pathlib.Path(__file__).parent.resolve(), "instances")
    instance_path = os.path.join(instances_path, f"instance{instance}.json")

    with open(instance_path, "r") as f:
        instance = f.read()

    instance: Instance = Instance.from_json(instance)
    problem = instance.scheduling_problem()
    factory = NurseSchedulingFactory(problem)
    model, nurse_view = factory.get_optimization_model()

    assert model.solve(solver="ortools", time_limit=time_limit)
    return (
        instance,
        Solution.from_nurse_view(nurse_view.value(), factory),
        model.objective_value(),
    )


def nurse_scheduled_shifts(
    employee_id: str, solution: Solution
) -> Optional[EmployeeShifts]:
    for nurse_schedule in solution.shift_schedule:
        if nurse_schedule.employee_id != employee_id:
            continue
        return nurse_schedule
    return None


def count_nurse_shifts(employee_id: str, solution: Solution) -> Dict[str, int]:
    nurse_schedule = nurse_scheduled_shifts(employee_id, solution)
    assert nurse_schedule is not None

    shifts_count = {}
    for shift in nurse_schedule.shifts:
        if shift not in shifts_count:
            shifts_count[shift] = 0
        shifts_count[shift] += 1
    return shifts_count


def shifts_duration(instance: Instance) -> Dict[str, int]:
    shifts_duration = {FREE: 0}
    for shift in instance.shifts:
        shifts_duration[shift.shift_id] = shift.length
    return shifts_duration


def assert_cannot_follow(instance: Instance, solution: Solution):
    for shift in instance.shifts:
        for nurse_schedule in solution.shift_schedule:
            for i in range(len(nurse_schedule.shifts) - 1):
                if nurse_schedule.shifts[i] == shift.shift_id:
                    assert nurse_schedule.shifts[i + 1] not in shift.cannot_follow


def assert_max_shifts(instance: Instance, solution: Solution):
    for nurse in instance.staff:
        max_shifts = {shift.shift_id: 0 for shift in instance.shifts}
        for shift in nurse.max_shifts:
            max_shifts[shift.shift_id] = shift.max_shifts

        shifts_count = count_nurse_shifts(nurse.employee_id, solution)
        for shift in max_shifts:
            assert shift not in shifts_count or shifts_count[shift] <= max_shifts[shift]


def assert_total_and_weekly_minutes(instance: Instance, solution: Solution):
    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(nurse.employee_id, solution)
        assert nurse_schedule is not None

        shifts_durations = shifts_duration(instance)
        total_minutes = sum(map(lambda s: shifts_durations[s], nurse_schedule.shifts))
        assert total_minutes <= nurse.max_total_minutes
        assert total_minutes >= nurse.min_total_minutes

        for day in range(instance.horizon, 7):
            week_shifts = nurse_schedule.shifts[day : day + 7]
            week_durations = map(lambda s: shifts_durations[s], week_shifts)
            total_week_minutes = sum(week_durations)
            assert total_week_minutes <= nurse.max_weekly_minutes
            assert total_week_minutes >= nurse.min_weekly_minutes


def assert_min_max_consecutive_shifts_and_days_off(
    instance: Instance, solution: Solution
):
    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(nurse.employee_id, solution)
        assert nurse_schedule is not None

        max_consecutive_shifts = 0
        consecutive_shifts = 0
        for day in range(instance.horizon):
            if nurse_schedule.shifts[day] == FREE:
                consecutive_shifts = 0
            else:
                consecutive_shifts += 1
                max_consecutive_shifts = max(max_consecutive_shifts, consecutive_shifts)

        assert max_consecutive_shifts <= nurse.max_consecutive_shifts

        for day in range(1, instance.horizon):
            if (
                nurse_schedule.shifts[day - 1] == FREE
                and nurse_schedule.shifts[day] != FREE
            ):
                assert (
                    FREE
                    not in nurse_schedule.shifts[
                        day : day + nurse.min_consecutive_shifts
                    ]
                )
                assert (
                    len(
                        list(
                            filter(
                                lambda s: s != FREE,
                                nurse_schedule.shifts[
                                    max(0, day - nurse.min_consecutive_days_off) : day
                                ],
                            )
                        )
                    )
                    == 0
                )


def assert_max_weekends(instance: Instance, solution: Solution):
    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(nurse.employee_id, solution)
        assert nurse_schedule is not None

        working_weekends = 0
        for saturday in range(5, instance.horizon, 7):
            sunday = saturday + 1
            if (
                nurse_schedule.shifts[saturday] != FREE
                or nurse_schedule.shifts[sunday] != FREE
            ):
                working_weekends += 1
        assert working_weekends <= nurse.max_weekends


def assert_days_off(instance: Instance, solution: Solution):
    for days_off in instance.days_off:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == days_off.employee_id:
                for day in days_off.day_indexes:
                    assert shifts.shifts[day] == FREE


def assert_shift_on(requests: List[ShiftRequest], solution: Solution):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == FREE
                    or shifts.shifts[request.day] == request.shift_id
                )


def assert_shift_off(requests: List[ShiftRequest], solution: Solution):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == FREE
                    or shifts.shifts[request.day] != request.shift_id
                )


@pytest.mark.parametrize("instance", list(range(11)))
def test_instance(instance: int):
    instance, solution, objective_value = solve_instance(0, time_limit=60)

    assert_cannot_follow(instance, solution)
    assert_max_shifts(instance, solution)
    assert_total_and_weekly_minutes(instance, solution)
    assert_min_max_consecutive_shifts_and_days_off(instance, solution)
    assert_max_weekends(instance, solution)

    assert_days_off(instance, solution)


def test_instance0():
    instance, solution, objective_value = solve_instance(0)
    assert objective_value == 808
    assert_shift_on(instance.shift_on_requests, solution)
    assert_shift_off(instance.shift_off_requests, solution)
