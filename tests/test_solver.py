from healthcare import Instance, Solution, NurseSchedulingFactory
from healthcare.instance import ShiftRequest
from healthcare.solution import EmployeeShifts
import pathlib
import os
import json
from typing import Tuple, List, Dict, Optional
import pytest
from datetime import datetime, timedelta

FREE = "-"


def load_instance_dict(instance: int) -> Dict:
    instances_path = os.path.join(
        pathlib.Path(__file__).parent.resolve(),
        "instances",
    )
    instance_path = os.path.join(
        instances_path,
        f"instance{instance}.json",
    )

    with open(instance_path, "r") as f:
        return json.load(f)


def solve_instance(
    instance: int,
    time_limit: Optional[int] = None,
) -> Tuple[Instance, Solution, int]:  # type: ignore
    instance_obj: Instance = Instance.from_dict(load_instance_dict(instance))  # type: ignore
    return solve_instance_obj(instance_obj, time_limit)


def solve_instance_obj(
    instance_obj: Instance,
    time_limit: Optional[int] = None,
) -> Tuple[Instance, Solution, int]:  # type: ignore
    problem = instance_obj.scheduling_problem()

    factory = NurseSchedulingFactory(problem)
    model, nurse_view = factory.get_optimization_model()

    assert model.solve(
        solver="ortools",
        time_limit=time_limit,
    )

    return (
        instance_obj,
        Solution.from_nurse_view(
            nurse_view.value(),
            factory,
        ),
        model.objective_value(),
    )


def nurse_scheduled_shifts(
    employee_id: str,
    solution: Solution,
) -> Optional[EmployeeShifts]:
    for nurse_schedule in solution.shift_schedule:
        if nurse_schedule.employee_id == employee_id:
            return nurse_schedule

    return None


def count_nurse_shifts(
    employee_id: str,
    solution: Solution,
) -> Dict[str, int]:
    nurse_schedule = nurse_scheduled_shifts(
        employee_id,
        solution,
    )

    assert nurse_schedule is not None

    shifts_count = {}

    for shift in nurse_schedule.shifts:
        if shift not in shifts_count:
            shifts_count[shift] = 0

        shifts_count[shift] += 1

    return shifts_count


def shifts_duration(instance: Instance) -> Dict[str, int]:
    durations = {FREE: 0}

    for shift in instance.shifts:
        durations[shift.shift_id] = shift.length

    return durations


def assert_cannot_follow(
    instance: Instance,
    solution: Solution,
):
    for shift in instance.shifts:
        for nurse_schedule in solution.shift_schedule:
            for i in range(len(nurse_schedule.shifts) - 1):
                if nurse_schedule.shifts[i] == shift.shift_id:
                    assert nurse_schedule.shifts[i + 1] not in shift.cannot_follow


def assert_max_shifts(
    instance: Instance,
    solution: Solution,
):
    for nurse in instance.staff:
        max_shifts = {
            shift.shift_id: 0
            for shift in instance.shifts
        }

        for shift in nurse.max_shifts:
            max_shifts[shift.shift_id] = shift.max_shifts

        shifts_count = count_nurse_shifts(
            nurse.employee_id,
            solution,
        )

        for shift in max_shifts:
            assert (
                shift not in shifts_count
                or shifts_count[shift] <= max_shifts[shift]
            )


def assert_total_and_weekly_minutes(
    instance: Instance,
    solution: Solution,
):
    """
    Max total and max weekly minutes remain hard.

    Min total and min weekly minutes are now soft, so they must NOT be
    asserted as hard constraints anymore. Instead, check that
    underallocations exist and match the shortage.
    """

    durations = shifts_duration(instance)

    underallocation_by_nurse = {
        item.employee_id: item
        for item in solution.underallocations
    }

    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(
            nurse.employee_id,
            solution,
        )

        assert nurse_schedule is not None

        total_minutes = sum(
            durations[s]
            for s in nurse_schedule.shifts
        )

        assert total_minutes <= nurse.max_total_minutes

        expected_under_total = max(
            0,
            nurse.min_total_minutes - total_minutes,
        )

        assert nurse.employee_id in underallocation_by_nurse

        reported_under = underallocation_by_nurse[nurse.employee_id]

        assert reported_under.assigned_minutes == total_minutes
        assert reported_under.min_total_minutes == nurse.min_total_minutes
        assert reported_under.under_total_minutes == expected_under_total

        for week_start in range(0, instance.horizon, 7):
            week_end = min(
                week_start + 7,
                instance.horizon,
            )

            week_shifts = nurse_schedule.shifts[week_start:week_end]

            total_week_minutes = sum(
                durations[s]
                for s in week_shifts
            )

            assert total_week_minutes <= nurse.max_weekly_minutes

            expected_under_weekly = max(
                0,
                nurse.min_weekly_minutes - total_week_minutes,
            )

            reported_week = next(
                item
                for item in reported_under.weekly
                if item.week_start_day == week_start
            )

            assert reported_week.assigned_minutes == total_week_minutes
            assert reported_week.min_weekly_minutes == nurse.min_weekly_minutes
            assert reported_week.under_weekly_minutes == expected_under_weekly


def assert_min_max_consecutive_shifts_and_days_off(
    instance: Instance,
    solution: Solution,
):
    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(
            nurse.employee_id,
            solution,
        )

        assert nurse_schedule is not None

        max_consecutive_shifts = 0
        consecutive_shifts = 0

        for day in range(instance.horizon):
            if nurse_schedule.shifts[day] == FREE:
                consecutive_shifts = 0
            else:
                consecutive_shifts += 1
                max_consecutive_shifts = max(
                    max_consecutive_shifts,
                    consecutive_shifts,
                )

        assert max_consecutive_shifts <= nurse.max_consecutive_shifts

        for day in range(1, instance.horizon):
            if (
                nurse_schedule.shifts[day - 1] == FREE
                and nurse_schedule.shifts[day] != FREE
            ):
                assert (
                    FREE
                    not in nurse_schedule.shifts[
                        day: day + nurse.min_consecutive_shifts
                    ]
                )

                assert (
                    len(
                        list(
                            filter(
                                lambda s: s != FREE,
                                nurse_schedule.shifts[
                                    max(
                                        0,
                                        day - nurse.min_consecutive_days_off,
                                    ): day
                                ],
                            )
                        )
                    )
                    == 0
                )


def assert_max_weekends(
    instance: Instance,
    solution: Solution,
):
    start_date = datetime.strptime(
        instance.start_date,
        "%Y-%m-%d",
    )

    weekend_pairs = []

    for day in range(instance.horizon):
        current_date = start_date + timedelta(days=day)

        if current_date.weekday() == 5:
            sunday = day + 1

            if sunday < instance.horizon:
                sunday_date = start_date + timedelta(days=sunday)

                if sunday_date.weekday() == 6:
                    weekend_pairs.append(
                        (day, sunday)
                    )

    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(
            nurse.employee_id,
            solution,
        )

        assert nurse_schedule is not None

        working_weekends = 0

        for saturday, sunday in weekend_pairs:
            if (
                nurse_schedule.shifts[saturday] != FREE
                or nurse_schedule.shifts[sunday] != FREE
            ):
                working_weekends += 1

        assert working_weekends <= nurse.max_weekends


def assert_stress_threshold(
    instance: Instance,
    solution: Solution,
):
    for nurse in instance.staff:
        nurse_schedule = nurse_scheduled_shifts(
            nurse.employee_id,
            solution,
        )

        assert nurse_schedule is not None

        if nurse.stress_level >= instance.stress_threshold:
            assert all(
                shift == FREE
                for shift in nurse_schedule.shifts
            )
        else:
            shifts = {
                s.shift_id: s
                for s in instance.shifts
            }

            accumulated_stress = nurse.stress_level

            for shift in nurse_schedule.shifts:
                if shift != FREE:
                    accumulated_stress += shifts[shift].stress_weight

            assert accumulated_stress < instance.stress_threshold


def assert_days_off(
    instance: Instance,
    solution: Solution,
):
    for days_off in instance.days_off:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == days_off.employee_id:
                for day in days_off.day_indexes:
                    assert shifts.shifts[day] == FREE


def assert_blocked_weekdays(
    instance: Instance,
    solution: Solution,
):
    start_date = datetime.strptime(
        instance.start_date,
        "%Y-%m-%d",
    )

    for blocked in instance.blocked_weekdays:
        for day in range(instance.horizon):
            current_date = start_date + timedelta(days=day)

            if current_date.weekday() != blocked.weekday:
                continue

            for nurse_schedule in solution.shift_schedule:
                assert nurse_schedule.shifts[day] not in blocked.shift_ids


def assert_role_cover(
    instance: Instance,
    solution: Solution,
):
    """
    Cover is now hard and role-aware.

    For each day, shift, and role:
        assigned nurses with that role must equal requirement exactly.

    This also verifies requirement=0 produces zero allocation.
    """

    staff_role_by_id = {
        nurse.employee_id: nurse.role_id
        for nurse in instance.staff
    }

    for cover in instance.cover:
        for role_id, requirement in cover.role_requirements.items():
            assigned = 0

            for nurse_schedule in solution.shift_schedule:
                nurse_role = staff_role_by_id[nurse_schedule.employee_id]

                if nurse_role != role_id:
                    continue

                if nurse_schedule.shifts[cover.day] == cover.shift_id:
                    assigned += 1

            assert assigned == requirement


def assert_shift_on(
    requests: List[ShiftRequest],
    solution: Solution,
):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == FREE
                    or shifts.shifts[request.day] == request.shift_id
                )


def assert_shift_off(
    requests: List[ShiftRequest],
    solution: Solution,
):
    for request in requests:
        for shifts in solution.shift_schedule:
            if shifts.employee_id == request.employee_id:
                assert (
                    shifts.shifts[request.day] == FREE
                    or shifts.shifts[request.day] != request.shift_id
                )


@pytest.mark.parametrize("instance", list(range(1, 11)))
def test_instance(instance: int):
    instance, solution, objective_value = solve_instance(instance, time_limit=60) # type: ignore

    assert_cannot_follow(instance, solution) # type: ignore
    assert_max_shifts(instance, solution) # type: ignore
    assert_total_and_weekly_minutes(instance, solution) # type: ignore
    assert_min_max_consecutive_shifts_and_days_off(instance, solution) # type: ignore
    assert_max_weekends(instance, solution) # type: ignore
    assert_stress_threshold(instance, solution) # type: ignore
    assert_days_off(instance, solution) # type: ignore
    assert_blocked_weekdays(instance, solution) # type: ignore
    assert_role_cover(instance, solution) # type: ignore


def test_instance0():
    instance, solution, objective_value = solve_instance(0)

    assert_shift_on(
        instance.shift_on_requests,
        solution,
    )

    assert_shift_off(
        instance.shift_off_requests,
        solution,
    )

    assert_role_cover(
        instance,
        solution,
    )

    assert_total_and_weekly_minutes(
        instance,
        solution,
    )


def test_unspecified_cover_is_zero():
    """
    Roles not listed in role_requirements, and days/shifts without any
    cover entry, are treated as a requirement of 0.
    """

    instance_dict = load_instance_dict(1)

    cover = instance_dict["cover"]
    day0_morning = next(
        c for c in cover if c["day"] == 0 and c["shift_id"] == "morning"
    )
    assert day0_morning["role_requirements"]["assistant"] > 0
    del day0_morning["role_requirements"]["assistant"]

    instance_dict["cover"] = [
        c for c in cover if not (c["day"] == 1 and c["shift_id"] == "night")
    ]

    instance: Instance = Instance.from_dict(instance_dict)  # type: ignore
    instance, solution, objective_value = solve_instance_obj(instance, time_limit=60)

    staff_role_by_id = {
        nurse.employee_id: nurse.role_id
        for nurse in instance.staff
    }

    for nurse_schedule in solution.shift_schedule:
        if staff_role_by_id[nurse_schedule.employee_id] == "assistant":
            assert nurse_schedule.shifts[0] != "morning"

        assert nurse_schedule.shifts[1] != "night"

    assert_role_cover(instance, solution)


def test_cover_weights_are_optional():
    """
    weight_for_under and weight_for_over are deprecated: they can be
    omitted, and a warning is emitted when they are given.
    """

    instance_dict = load_instance_dict(1)

    for cover in instance_dict["cover"]:
        del cover["weight_for_under"]
        del cover["weight_for_over"]

    instance: Instance = Instance.from_dict(instance_dict)  # type: ignore
    instance, solution, objective_value = solve_instance_obj(instance, time_limit=60)

    assert_role_cover(instance, solution)

    with pytest.warns(DeprecationWarning):
        Instance.from_dict(load_instance_dict(1))
