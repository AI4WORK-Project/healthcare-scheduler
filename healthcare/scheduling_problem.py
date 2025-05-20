from dataclasses import dataclass
import pandas as pd


@dataclass
class SchedulingProblem:
    horizon: int = 0
    shifts: pd.DataFrame = None
    staff: pd.DataFrame = None
    days_off: pd.DataFrame = None
    shift_on: pd.DataFrame = None
    shift_off: pd.DataFrame = None
    cover: pd.DataFrame = None
