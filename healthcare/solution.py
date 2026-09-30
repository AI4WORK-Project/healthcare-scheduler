import dataclasses
import dataclasses_json
from typing import List
import numpy as np

from .factory import NurseSchedulingFactory


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class EmployeeShifts:
    employee_id: str
    shifts: List[str]


@dataclasses_json.dataclass_json
@dataclasses.dataclass
class Solution:
    shift_schedule: List[EmployeeShifts]

    @staticmethod
    def from_nurse_view(sol: np.ndarray, factory: NurseSchedulingFactory):
        shift_schedule = []

        for i, employee_id in enumerate(factory.data.staff["name"].tolist()):
            shift_schedule.append(
                EmployeeShifts(
                    employee_id=employee_id,
                    shifts=list(
                        map(
                            lambda s: factory.idx_to_name[s],
                            sol[i],
                        )
                    ),
                )
            )

        return Solution(shift_schedule)