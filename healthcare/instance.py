from dataclasses import dataclass, field
from dataclasses_json import dataclass_json
import pandas as pd
import warnings
from typing import Dict, List, Optional
from datetime import datetime

from .scheduling_problem import SchedulingProblem


@dataclass_json
@dataclass
class Shift:
    shift_id: str
    length: int
    cannot_follow: List[str]
    workload_weight: float

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.shift_id != "", "Shift ID must not be empty"
        assert self.length > 0, "Shift length must be greater than 0"
        assert self.workload_weight >= 0, (
            "Workload weight must be greater than or equal to 0"
        )


@dataclass_json
@dataclass
class MaxShifts:
    shift_id: str
    max_shifts: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.shift_id != "", "Shift ID must not be empty"
        assert self.max_shifts >= 0, (
            "Max shifts must be greater than or equal to 0"
        )


@dataclass_json
@dataclass
class Staff:
    employee_id: str
    role_id: str
    max_shifts: List[MaxShifts]
    max_total_minutes: int
    min_total_minutes: int
    max_weekly_minutes: int
    min_weekly_minutes: int
    max_consecutive_shifts: int
    min_consecutive_shifts: int
    min_consecutive_days_off: int
    max_weekends: int
    workload_level: int

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.employee_id != "", "Employee ID must not be empty"
        assert self.role_id != "", "Role ID must not be empty"

        assert self.max_total_minutes >= 0, (
            "Max total minutes must be greater than or equal to 0"
        )
        assert self.min_total_minutes >= 0, (
            "Min total minutes must be greater than or equal to 0"
        )
        assert self.max_total_minutes >= self.min_total_minutes, (
            "Max total minutes must be greater than or equal to min total minutes"
        )

        assert self.max_weekly_minutes >= 0, (
            "Max weekly minutes must be greater than or equal to 0"
        )
        assert self.min_weekly_minutes >= 0, (
            "Min weekly minutes must be greater than or equal to 0"
        )
        assert self.max_weekly_minutes >= self.min_weekly_minutes, (
            "Max weekly minutes must be greater than or equal to min weekly minutes"
        )

        assert self.max_total_minutes >= self.max_weekly_minutes, (
            "Max total minutes must be greater than or equal to max weekly minutes"
        )
        assert self.min_total_minutes >= self.min_weekly_minutes, (
            "Min total minutes must be greater than or equal to min weekly minutes"
        )

        assert self.max_consecutive_shifts >= 0, (
            "Max consecutive shifts must be greater than or equal to 0"
        )
        assert self.min_consecutive_shifts >= 0, (
            "Min consecutive shifts must be greater than or equal to 0"
        )
        assert self.max_consecutive_shifts >= self.min_consecutive_shifts, (
            "Max consecutive shifts must be greater than or equal to min consecutive shifts"
        )

        assert self.min_consecutive_days_off >= 0, (
            "Min consecutive days off must be greater than or equal to 0"
        )
        assert self.max_weekends >= 0, (
            "Max weekends must be greater than or equal to 0"
        )
        assert self.workload_level >= 0, (
            "Workload level must be greater than or equal to 0"
        )


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
        assert self.employee_id != "", "Employee ID must not be empty"
        assert self.shift_id != "", "Shift ID must not be empty"
        assert self.weight >= 0, "Weight must be greater than or equal to 0"


@dataclass_json
@dataclass
class Cover:
    day: int
    shift_id: str
    role_requirements: Dict[str, int]

    # Deprecated: not used since cover is exact (hard)
    weight_for_under: Optional[int] = None
    weight_for_over: Optional[int] = None

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.shift_id != "", "Shift ID must not be empty"
        assert self.role_requirements is not None
        assert len(self.role_requirements) > 0

        for role_id, requirement in self.role_requirements.items():
            assert role_id != "", "Role ID must not be empty"
            assert requirement >= 0, (
                "Role requirement must be greater than or equal to 0"
            )

        for name in ("weight_for_under", "weight_for_over"):
            weight = getattr(self, name)
            assert weight is None or weight >= 0, (
                f"{name} must be greater than or equal to 0"
            )


@dataclass_json
@dataclass
class BlockedWeekday:
    weekday: int
    shift_ids: List[str]

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert 0 <= self.weekday <= 6, (
            "Weekday must be between 0 and 6"
        )

        assert self.shift_ids is not None
        assert len(self.shift_ids) > 0, (
            "Blocked weekday must contain at least one shift ID"
        )

        for shift_id in self.shift_ids:
            assert shift_id != "", "Blocked shift ID must not be empty"


@dataclass_json
@dataclass
class UnderallocationWeights:
    # cost per missing minute against min_total_minutes
    total: int = 1
    # cost per missing minute against the (prorated) min_weekly_minutes
    weekly: int = 1

    def __post_init__(self):
        self.validate()

    def validate(self):
        for name in ("total", "weekly"):
            value = getattr(self, name)

            assert isinstance(value, int) and not isinstance(value, bool), (
                f"{name.capitalize()} underallocation weight must be an integer"
            )
            assert value >= 0, (
                f"{name.capitalize()} underallocation weight must be greater "
                "than or equal to 0"
            )


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
    workload_threshold: int

    start_date: str = "1970-01-05"
    blocked_weekdays: List[BlockedWeekday] = field(default_factory=list)
    underallocation_weights: UnderallocationWeights = field(
        default_factory=UnderallocationWeights
    )

    def __post_init__(self):
        self.validate()

    def validate(self):
        assert self.horizon > 0, "The horizon must be greater than 0"

        try:
            datetime.strptime(self.start_date, "%Y-%m-%d")
        except ValueError:
            raise AssertionError("start_date must follow format YYYY-MM-DD")

        shifts = set(shift.shift_id for shift in self.shifts)
        assert len(shifts) == len(self.shifts), "Shift IDs must be unique"

        assert all(
            set(shift.cannot_follow).issubset(shifts)
            for shift in self.shifts
        ), "Cannot follow shifts must contain valid shift IDs"

        nurses = set(nurse.employee_id for nurse in self.staff)
        assert len(nurses) == len(self.staff), "Nurse IDs must be unique"

        roles = set(nurse.role_id for nurse in self.staff)
        assert len(roles) > 0, "At least one nurse role must exist"

        for nurse in self.staff:
            for max_shift in nurse.max_shifts:
                assert max_shift.shift_id in shifts, (
                    "Max shift IDs must be valid"
                )

        assert len(set(day_off.employee_id for day_off in self.days_off)) == len(
            self.days_off
        ), "Days off nurse IDs must be unique"

        for day_off in self.days_off:
            assert day_off.employee_id in nurses, (
                "Days off nurse IDs must be valid"
            )

            for day in day_off.day_indexes:
                assert 0 <= day < self.horizon, (
                    "Days off must be within the horizon"
                )

        for request in self.shift_on_requests + self.shift_off_requests:
            assert request.employee_id in nurses, (
                "Shift request nurse IDs must be valid"
            )
            assert 0 <= request.day < self.horizon, (
                "Shift request days must be within the horizon"
            )
            assert request.shift_id in shifts, (
                "Shift request shift IDs must be valid"
            )

        for cover in self.cover:
            assert 0 <= cover.day < self.horizon, (
                "Cover days must be within horizon"
            )
            assert cover.shift_id in shifts, (
                "Cover shift IDs must be valid"
            )

            for role_id, requirement in cover.role_requirements.items():
                assert role_id in roles, (
                    f"Cover role '{role_id}' does not exist in staff roles"
                )
                assert requirement >= 0

        if any(
            cover.weight_for_under is not None
            or cover.weight_for_over is not None
            for cover in self.cover
        ):
            warnings.warn(
                "Cover fields 'weight_for_under' and 'weight_for_over' "
                "are deprecated and ignored",
                DeprecationWarning,
            )

        for blocked in self.blocked_weekdays:
            assert 0 <= blocked.weekday <= 6

            for shift_id in blocked.shift_ids:
                assert shift_id in shifts, (
                    "Blocked weekday shift IDs must be valid"
                )

        assert self.workload_threshold > 0, (
            "Workload threshold must be greater than 0"
        )

    def scheduling_problem(self) -> SchedulingProblem:
        problem = SchedulingProblem()
        problem.horizon = self.horizon
        problem.start_date = self.start_date

        problem.shifts = pd.DataFrame(self.shifts)
        problem.shifts.rename(
            columns={
                "shift_id": "ShiftID",
                "length": "Length",
                "cannot_follow": "cannot follow",
                "workload_weight": "WorkloadWeight",
            },
            inplace=True,
        )
        problem.shifts.set_index("ShiftID", inplace=True)

        problem.staff = pd.DataFrame(self.staff)
        problem.staff.rename(
            columns={
                "employee_id": "# ID",
                "role_id": "RoleID",
                "max_shifts": "MaxShifts",
                "max_total_minutes": "MaxTotalMinutes",
                "min_total_minutes": "MinTotalMinutes",
                "max_weekly_minutes": "MaxWeeklyMinutes",
                "min_weekly_minutes": "MinWeeklyMinutes",
                "max_consecutive_shifts": "MaxConsecutiveShifts",
                "min_consecutive_shifts": "MinConsecutiveShifts",
                "min_consecutive_days_off": "MinConsecutiveDaysOff",
                "max_weekends": "MaxWeekends",
                "workload_level": "WorkloadLevel",
            },
            inplace=True,
        )
        problem.staff["name"] = problem.staff["# ID"]

        maxes = dict((shift_id, []) for shift_id in problem.shifts.index)

        for nurse_max_shifts in problem.staff["MaxShifts"]:
            for shift_id in problem.shifts.index:
                maxes[shift_id].append(0)

            for max_shift in nurse_max_shifts:
                shift_id = max_shift["shift_id"]
                maxes[shift_id][-1] = max_shift["max_shifts"]

        for shift_id in problem.shifts.index:
            problem.staff[f"max_shifts_{shift_id}"] = maxes[shift_id]

        days_off = []

        for nurse_days_off in self.days_off:
            for day_idx in nurse_days_off.day_indexes:
                days_off.append(
                    {
                        "EmployeeID": nurse_days_off.employee_id,
                        "DayIndex": day_idx,
                    }
                )

        problem.days_off = pd.DataFrame(
            days_off,
            columns=["EmployeeID", "DayIndex"],
        )

        problem.shift_on = pd.DataFrame(
            self.shift_on_requests,
            columns=["employee_id", "day", "shift_id", "weight"],
        )

        problem.shift_off = pd.DataFrame(
            self.shift_off_requests,
            columns=["employee_id", "day", "shift_id", "weight"],
        )

        request_mapping = {
            "employee_id": "# EmployeeID",
            "day": "Day",
            "shift_id": "ShiftID",
            "weight": "Weight",
        }

        problem.shift_on.rename(columns=request_mapping, inplace=True)
        problem.shift_off.rename(columns=request_mapping, inplace=True)

        cover_rows = []

        for cover in self.cover:
            for role_id, requirement in cover.role_requirements.items():
                cover_rows.append(
                    {
                        "# Day": cover.day,
                        "ShiftID": cover.shift_id,
                        "RoleID": role_id,
                        "Requirement": requirement,
                    }
                )

        problem.cover = pd.DataFrame(
            cover_rows,
            columns=[
                "# Day",
                "ShiftID",
                "RoleID",
                "Requirement",
            ],
        )

        problem.blocked_weekdays = pd.DataFrame(
            self.blocked_weekdays,
            columns=["weekday", "shift_ids"],
        )

        problem.workload_threshold = self.workload_threshold

        problem.underallocation_weight_total = self.underallocation_weights.total
        problem.underallocation_weight_weekly = self.underallocation_weights.weekly

        return problem