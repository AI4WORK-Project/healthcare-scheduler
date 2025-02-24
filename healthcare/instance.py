import dataclasses
import dataclasses_json
import pandas as pd
from faker import Faker
from typing import List

from .read_data import SchedulingProblem


fake = Faker()
fake.seed_instance(0)


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Shift:
    shift_id: str
    length: int
    cannot_follow: List[str]


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class MaxShifts:
    shift_id: str
    max_shifts: int


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Staff:
    employee_id: str
    max_shifts: List[MaxShifts]
    max_total_minutes: int
    min_total_minutes: int
    max_weekly_minutes: int
    min_weekly_minutes: int
    max_consecutive_shifts: int
    min_consecutive_shifts: int
    min_consecutive_days_off: int
    max_weekends: int


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class DaysOff:
    employee_id: str
    day_indexes: List[int]


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class ShiftRequest:
    employee_id: str
    day: int
    shift_id: str
    weight: int


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Cover:
    day: int
    shift_id: str
    requirement: int
    weight_for_under: int
    weight_for_over: int


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Instance:
    horizon: int
    shifts: List[Shift]
    staff: List[Staff]
    days_off: List[DaysOff]
    shift_on_requests: List[ShiftRequest]
    shift_off_requests: List[ShiftRequest]
    cover: List[Cover]

    def scheduling_problem(self) -> SchedulingProblem:
        problem = SchedulingProblem()
        problem.horizon = self.horizon

        problem.shifts = pd.DataFrame(self.shifts)
        names_mapping = {
            "shift_id": "ShiftID",
            "length": "Length",
            "cannot_follow": "cannot follow",
        }
        problem.shifts.rename(columns=lambda x: names_mapping[x], inplace=True)
        problem.shifts.set_index("ShiftID", inplace=True)

        problem.staff = pd.DataFrame(self.staff)
        names_mapping = {
            "employee_id": "# ID",
            "max_shifts": "MaxShifts",
            "max_total_minutes": "MaxTotalMinutes",
            "min_total_minutes": "MinTotalMinutes",
            "max_weekly_minutes": "MaxWeeklyMinutes",
            "min_weekly_minutes": "MinWeeklyMinutes",
            "max_consecutive_shifts": "MaxConsecutiveShifts",
            "min_consecutive_shifts": "MinConsecutiveShifts",
            "min_consecutive_days_off": "MinConsecutiveDaysOff",
            "max_weekends": "MaxWeekends",
        }
        problem.staff.rename(columns=lambda x: names_mapping[x], inplace=True)
        problem.staff["name"] = problem.staff["# ID"]
        # problem.staff["name"] = [fake.unique.first_name() for _ in problem.staff.index]
        maxes = dict((shift_id, []) for shift_id in problem.shifts.index)
        for nurse_max_shifts in problem.staff["MaxShifts"]:
            for shift_id in problem.shifts.index:
                maxes[shift_id].append(0)
            for max_shifts in nurse_max_shifts:
                shift_id = max_shifts["shift_id"]
                maxes[shift_id][-1] = max_shifts["max_shifts"]
        for shift_id in problem.shifts.index:
            problem.staff[f"max_shifts_{shift_id}"] = maxes[shift_id]

        days_off = []
        for nurse_days_off in self.days_off:
            employee_id = nurse_days_off.employee_id
            for day_idx in nurse_days_off.day_indexes:
                days_off.append({"EmployeeID": employee_id, "DayIndex": day_idx})
        problem.days_off = pd.DataFrame(days_off)

        problem.shift_on = pd.DataFrame(self.shift_on_requests)
        names_mapping = {
            "employee_id": "# EmployeeID",
            "day": "Day",
            "shift_id": "ShiftID",
            "weight": "Weight",
        }
        problem.shift_on.rename(columns=lambda x: names_mapping[x], inplace=True)

        problem.shift_off = pd.DataFrame(self.shift_off_requests)
        problem.shift_off.rename(columns=lambda x: names_mapping[x], inplace=True)

        problem.cover = pd.DataFrame(self.cover)
        names_mapping = {
            "day": "# Day",
            "shift_id": "ShiftID",
            "requirement": "Requirement",
            "weight_for_under": "Weight for under",
            "weight_for_over": "Weight for over",
        }
        problem.cover.rename(columns=lambda x: names_mapping[x], inplace=True)

        return problem
