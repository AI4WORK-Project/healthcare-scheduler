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

    def __init__(self, sol: np.ndarray, factory: NurseSchedulingFactory):
        self.shift_schedule = []
        for i, employee_id in enumerate(factory.data.staff["name"].tolist()):
            self.shift_schedule.append(
                EmployeeShifts(
                    employee_id, list(map(lambda s: factory.idx_to_name[s], sol[i]))
                )
            )
