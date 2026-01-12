from dataclasses import dataclass
from dataclasses_json import dataclass_json
import pandas as pd
from typing import List

from .scheduling_problem import SchedulingProblem


@dataclass_json
@dataclass
class Shift:
    shift_id: str
    length: int
    cannot_follow: List[str]
    stress_weight: float

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.length > 0, "Shift length must be greater than 0"
        assert (
            self.stress_weight >= 0
        ), "Stress weight must be greater than or equal to 0"


@dataclass_json
@dataclass
class MaxShifts:
    shift_id: str
    max_shifts: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.max_shifts >= 0, "Max shifts must be greater than or equal to 0"


@dataclass_json
@dataclass
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
    stress_level: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert (
            self.max_total_minutes >= 0
        ), "Max total minutes must be greater than or equal to 0"
        assert (
            self.min_total_minutes >= 0
        ), "Min total minutes must be greater than or equal to 0"
        assert (
            self.max_total_minutes >= self.min_total_minutes
        ), "Max total minutes must be greater than or equal to min total minutes"

        assert (
            self.max_weekly_minutes >= 0
        ), "Max weekly minutes must be greater than or equal to 0"
        assert (
            self.min_weekly_minutes >= 0
        ), "Min weekly minutes must be greater than or equal to 0"
        assert (
            self.max_weekly_minutes >= self.min_weekly_minutes
        ), "Max weekly minutes must be greater than or equal to min weekly minutes"

        assert (
            self.max_total_minutes >= self.max_weekly_minutes
        ), "Max total minutes must be greater than or equal to max weekly minutes"
        assert (
            self.min_total_minutes >= self.min_weekly_minutes
        ), "Min total minutes must be greater than or equal to min weekly minutes"

        assert (
            self.max_consecutive_shifts >= 0
        ), "Max consecutive shifts must be greater than or equal to 0"
        assert (
            self.min_consecutive_shifts >= 0
        ), "Min consecutive shifts must be greater than or equal to 0"
        assert (
            self.max_consecutive_shifts >= self.min_consecutive_shifts
        ), "Max consecutive shifts must be greater than or equal to min consecutive shifts"

        assert (
            self.min_consecutive_days_off >= 0
        ), "Min consecutive days off must be greater than or equal to 0"
        assert self.max_weekends >= 0, "Max weekends must be greater than or equal to 0"

        assert self.stress_level >= 0, "Stress level must be greater than or equal to 0"


@dataclass_json
@dataclass
class DaysOff:
    employee_id: str
    day_indexes: List[int]


@dataclass_json
@dataclass
class ShiftRequest:
    employee_id: str
    day: int
    shift_id: str
    weight: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.weight >= 0, "Weight must be greater than or equal to 0"


@dataclass_json
@dataclass
class Cover:
    day: int
    shift_id: str
    requirement: int
    weight_for_under: int
    weight_for_over: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.requirement >= 0, "Requirement must be greater than or equal to 0"
        assert (
            self.weight_for_under >= 0
        ), "Weight for under must be greater than or equal to 0"
        assert (
            self.weight_for_over >= 0
        ), "Weight for over must be greater than or equal to 0"


@dataclass_json
@dataclass
class Instance:
    horizon: int
    shifts: List[Shift]
    staff: List[Staff]
    days_off: List[DaysOff]
    shift_on_requests: List[ShiftRequest]
    shift_off_requests: List[ShiftRequest]
    cover: List[Cover]
    stress_threshold: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.horizon > 0, "The horizon must be greater than 0"

        shifts = set(shift.shift_id for shift in self.shifts)
        assert len(shifts) == len(self.shifts), "Shift IDs must be unique"
        assert all(
            set(shift.cannot_follow).issubset(shifts) for shift in self.shifts
        ), "Cannot follow shifts must contain valid shift IDs"

        nurses = set(nurse.employee_id for nurse in self.staff)
        assert len(nurses) == len(self.staff), "Nurse IDs must be unique"

        for nurse in self.staff:
            for max_shift in nurse.max_shifts:
                assert max_shift.shift_id in shifts, "Max shift IDs must be valid"

        assert len(set(day_off.employee_id for day_off in self.days_off)) == len(
            self.days_off
        ), "Days off nurse IDs must be unique"

        for day_off in self.days_off:
            assert day_off.employee_id in nurses, "Days off nurse IDs must be valid"
            for day in day_off.day_indexes:
                assert 0 <= day < self.horizon, "Days off must be within the horizon"

        for request in self.shift_on_requests + self.shift_off_requests:
            assert (
                request.employee_id in nurses
            ), "Shift on requests nurse IDs must be valid"

            assert (
                0 <= request.day < self.horizon
            ), "Shift on requests days must be within the horizon"

            assert (
                request.shift_id in shifts
            ), "Shift on requests shift IDs must be valid"

        for cover in self.cover:
            assert (
                0 <= cover.day < self.horizon
            ), "Cover days must be within the horizon"
            assert cover.shift_id in shifts, "Cover shift IDs must be valid"

        assert self.stress_threshold > 0, "The stress threshold must be greater than 0"

    def scheduling_problem(self) -> SchedulingProblem:
        problem = SchedulingProblem()
        problem.horizon = self.horizon

        problem.shifts = pd.DataFrame(self.shifts)
        names_mapping = {
            "shift_id": "ShiftID",
            "length": "Length",
            "cannot_follow": "cannot follow",
            "stress_weight": "StressWeight",
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
            "stress_level": "StressLevel",
        }
        problem.staff.rename(columns=lambda x: names_mapping[x], inplace=True)
        problem.staff["name"] = problem.staff["# ID"]
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
        problem.shift_off = pd.DataFrame(self.shift_off_requests)
        names_mapping = {
            "employee_id": "# EmployeeID",
            "day": "Day",
            "shift_id": "ShiftID",
            "weight": "Weight",
        }
        problem.shift_on.rename(columns=lambda x: names_mapping[x], inplace=True)
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

        problem.stress_threshold = self.stress_threshold

        return problem
