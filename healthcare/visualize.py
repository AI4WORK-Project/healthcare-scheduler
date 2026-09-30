import pandas as pd
import numpy as np
from healthcare import SchedulingProblem, Solution

import matplotlib.pyplot as plt
from datetime import datetime, timedelta


def _build_day_columns(problem: SchedulingProblem):
    start_date = datetime.strptime(problem.start_date, "%Y-%m-%d")
    weeks = []
    days = []

    for i in range(problem.horizon):
        current_date = start_date + timedelta(days=i)

        weeks.append(f"Week {(i // 7) + 1}")
        days.append(current_date.strftime("%a %Y-%m-%d"))

    return pd.MultiIndex.from_arrays(
        [weeks, days],
        names=("Week", "Day")
    )


def visualize(problem: SchedulingProblem, solution: Solution):
    day_columns = _build_day_columns(problem)

    shift_name_to_idx = { name: idx + 1 for idx, (name, _) in enumerate(problem.shifts.iterrows()) }
    idx_to_name = ["-"] + [key for key in shift_name_to_idx]
    shift_name_to_idx.update({"-": 0})

    sol = []

    for i, employee_id in enumerate(problem.staff["name"].tolist()):
        assert solution.shift_schedule[i].employee_id == employee_id
        sol.append( list( map( lambda s: shift_name_to_idx[s], solution.shift_schedule[i].shifts ) ) )

    
    df = pd.DataFrame(sol, columns=day_columns, index=problem.staff.name)

    total_minutes = (
        df.map(
            lambda i: (
                ([0] + list(problem.shifts.Length))[i]
                if i is not None
                else 0
            )
        )
        .sum(axis=1)
        .astype(int)
    )

    df = df.map(lambda v: idx_to_name[v] if v is not None else "")

    real_shifts = sorted(set(shift_name_to_idx) - {"-"}) # type: ignore
    total_shifts = pd.DataFrame(
        columns=pd.MultiIndex.from_product(
            [["#Shifts"], real_shifts]
        ),
        index=df.index,
    )

    for shift_type in real_shifts:
        total_shifts[("#Shifts", shift_type)] = (df == shift_type).sum(axis=1)

    for shift_type in real_shifts:
        sums = (df == shift_type).sum()

        req = problem.cover["Requirement"][problem.cover["ShiftID"] == shift_type]
        req.index = sums.index[: len(req)]

        df.loc[f"Cover {shift_type}"] = ( sums.astype(str) + "/" + req.astype(str) )

    shifts_stress_weights = {
        shift_name: shift["StressWeight"]
        for shift_name, shift in problem.shifts.iterrows()
    }

    stress = [0] * len(df)

    for i, (_, nurse) in enumerate(problem.staff.iterrows()):
        stress[i] = nurse["StressLevel"] + sum(
            [
                shifts_stress_weights[s]
                for s in solution.shift_schedule[i].shifts
                if s != "-"
            ]
        )

    df = pd.concat([df, total_shifts], axis=1)
    df["#Minutes"] = total_minutes
    df["Stress"] = stress
    df = df.fillna(0)

    df["#Shifts"] = df["#Shifts"].astype(int)
    df["#Minutes"] = df["#Minutes"].astype(int)

    subset = (
        df.index.tolist()[: -len(problem.shifts)],
        df.columns[: problem.horizon],
    )

    style = df.style.set_table_styles(
        [
            {"selector": ".data", "props": [("text-align", "center")]},
            {"selector": ".col_heading", "props": [("text-align", "center")]},
        ]
    )

    style = style.map(lambda v: "border: 1px solid black", subset=subset)

    style = style.map(color_shift, shift_name_to_idx=shift_name_to_idx, subset=subset)

    return style


def color_shift(shift, shift_name_to_idx):
    cmap = plt.get_cmap("Set3")

    if shift is None or shift == "" or shift == "-":
        return "background-color: white"

    r, g, b = (
        round(255 * val)
        for val in cmap.colors[shift_name_to_idx[shift]] # type: ignore
    )

    return f"background-color: rgb({r},{g},{b})"


def highlight_changes(new_sol, old_sol, factory):

    style = visualize(new_sol, factory)
    shape = style.data.shape

    neq = new_sol != old_sol
    diff0 = shape[0] - neq.shape[0]
    diff1 = shape[1] - neq.shape[1]
    neq = np.pad(neq, ((0, diff0), (0, diff1)), constant_values=False)

    df_css = pd.DataFrame(neq)
    df_css.index = style.index
    df_css.columns = style.columns

    df_css = df_css.map( lambda x: "border: 5px solid lawngreen" if x else "")

    return style.apply(apply_styles, styles=df_css, axis=None)


def apply_styles(x, styles):
    return styles


def visualize_constraints(constraints, nurse_view, factory, do_clear=True):
    if do_clear:
        nurse_view.clear()

    style = visualize(factory.data, Solution.from_nurse_view(nurse_view.value(), factory))
    df_css = pd.DataFrame(index=style.data.index, columns=style.data.columns)
    df_css.fillna("", inplace=True)

    for cons in constraints:
        if hasattr(cons, "visualize"):
            cons.visualize(df_css)

    return style.apply(apply_styles, styles=df_css, axis=None)


def visualize_step(step, nurse_view, factory):
    E, S, N = step
    print(f"Propagating constraint: {next(iter(S))}")

    if any(len(vals) == 0 for vals in N.values()):
        return visualize_constraints(S, nurse_view, factory=factory, do_clear=False)

    for v in E:
        if E[v] > N[v]:
            assert len(N[v]) <= 1, ("Only allow assignments here.")
            r = int(v.name.split(",")[0].split("[")[1])
            c = int(v.name.split(",")[1].split("]")[0])
            nurse_view[r, c]._value = next(iter(N[v]))

    return visualize_constraints(S, nurse_view, factory=factory, do_clear=False)