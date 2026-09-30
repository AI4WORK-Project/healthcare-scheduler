import dataclasses
import dataclasses_json
from typing import List
import math
import numpy as np

from .factory import NurseSchedulingFactory


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class EmployeeShifts:
    employee_id: str
    shifts: List[str]


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class WeeklyUnderAllocation:
    week_start_day: int
    week_start_label: str
    assigned_minutes: int
    min_weekly_minutes: int
    under_weekly_minutes: int
    under_weekly_shifts: int


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class NurseUnderAllocation:
    employee_id: str
    assigned_minutes: int
    min_total_minutes: int
    under_total_minutes: int
    under_total_shifts: int
    weekly: List[WeeklyUnderAllocation]


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Solution:
    shift_schedule: List[EmployeeShifts]
    underallocations: List[NurseUnderAllocation] = dataclasses.field(
        default_factory=list
    )

    @staticmethod
    def from_nurse_view(sol: np.ndarray, factory: NurseSchedulingFactory):
        shift_schedule = []
        underallocations = []

        shift_lengths = {
            shift_id: int(shift["Length"])
            for shift_id, shift in factory.data.shifts.iterrows()
        }

        positive_shift_lengths = [
            length
            for length in shift_lengths.values()
            if length > 0
        ]

        default_shift_length = (
            min(positive_shift_lengths)
            if len(positive_shift_lengths) > 0
            else 480
        )

        for i, employee_id in enumerate(factory.data.staff["name"].tolist()):
            shifts = list(
                map(
                    lambda s: factory.idx_to_name[s],
                    sol[i],
                )
            )

            shift_schedule.append(
                EmployeeShifts(
                    employee_id=employee_id,
                    shifts=shifts,
                )
            )

            nurse = factory.data.staff.iloc[i]

            assigned_minutes = sum(
                shift_lengths.get(shift_id, 0)
                for shift_id in shifts
                if shift_id != "-"
            )

            min_total_minutes = int(nurse["MinTotalMinutes"])
            under_total_minutes = max(
                0,
                min_total_minutes - assigned_minutes,
            )

            under_total_shifts = (
                math.ceil(under_total_minutes / default_shift_length)
                if under_total_minutes > 0
                else 0
            )

            weekly_underallocations = []

            for week_start in range(0, factory.data.horizon, 7):
                week_end = min(week_start + 7, factory.data.horizon)
                week_shifts = shifts[week_start:week_end]

                week_assigned_minutes = sum(
                    shift_lengths.get(shift_id, 0)
                    for shift_id in week_shifts
                    if shift_id != "-"
                )

                min_weekly_minutes = int(nurse["MinWeeklyMinutes"])

                under_weekly_minutes = max(
                    0,
                    min_weekly_minutes - week_assigned_minutes,
                )

                under_weekly_shifts = (
                    math.ceil(under_weekly_minutes / default_shift_length)
                    if under_weekly_minutes > 0
                    else 0
                )

                weekly_underallocations.append(
                    WeeklyUnderAllocation(
                        week_start_day=week_start,
                        week_start_label=factory.days[week_start],
                        assigned_minutes=week_assigned_minutes,
                        min_weekly_minutes=min_weekly_minutes,
                        under_weekly_minutes=under_weekly_minutes,
                        under_weekly_shifts=under_weekly_shifts,
                    )
                )

            underallocations.append(
                NurseUnderAllocation(
                    employee_id=employee_id,
                    assigned_minutes=assigned_minutes,
                    min_total_minutes=min_total_minutes,
                    under_total_minutes=under_total_minutes,
                    under_total_shifts=under_total_shifts,
                    weekly=weekly_underallocations,
                )
            )

        return Solution(
            shift_schedule=shift_schedule,
            underallocations=underallocations,
        )