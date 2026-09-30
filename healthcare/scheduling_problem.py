from dataclasses import dataclass
import pandas as pd


@dataclass
class SchedulingProblem:
    horizon: int = 0
    start_date: str = "1970-01-05"

    shifts: pd.DataFrame = None           # pyright: ignore[reportAssignmentType]
    staff: pd.DataFrame = None            # pyright: ignore[reportAssignmentType]
    days_off: pd.DataFrame = None         # pyright: ignore[reportAssignmentType]
    shift_on: pd.DataFrame = None         # pyright: ignore[reportAssignmentType]
    shift_off: pd.DataFrame = None        # pyright: ignore[reportAssignmentType]
    cover: pd.DataFrame = None            # pyright: ignore[reportAssignmentType]
    blocked_weekdays: pd.DataFrame = None # pyright: ignore[reportAssignmentType]
    stress_threshold: int = 0