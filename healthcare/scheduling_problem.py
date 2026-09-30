from dataclasses import dataclass
import pandas as pd


@dataclass
class SchedulingProblem:
    horizon: int = 0
    start_date: str = "1970-01-05"

    shifts: pd.DataFrame = None  # type: ignore
    staff: pd.DataFrame = None  # type: ignore
    days_off: pd.DataFrame = None  # type: ignore
    shift_on: pd.DataFrame = None  # type: ignore
    shift_off: pd.DataFrame = None  # type: ignore
    cover: pd.DataFrame = None  # type: ignore
    blocked_weekdays: pd.DataFrame = None  # type: ignore

    stress_threshold: int = 0