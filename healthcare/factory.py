import cpmpy as cp
from cpmpy.transformations.normalize import toplevel_list
from datetime import datetime, timedelta
from typing import Any, Optional

from .scheduling_problem import SchedulingProblem

FREE = 0


class NurseSchedulingFactory:
    def __init__(self, data: SchedulingProblem):

        self.data = data
        self.n_types = len(data.shifts)
        self.n_nurses = len(data.staff)

        self.start_date = datetime.strptime(data.start_date, "%Y-%m-%d")

        self.index_to_date = {
            i: self.start_date + timedelta(days=i)
            for i in range(data.horizon)
        }

        self.date_to_index = {
            date.strftime("%Y-%m-%d"): idx
            for idx, date in self.index_to_date.items()
        }

        self.weekends = self._build_weekends()

        self.shift_name_to_idx = {
            name: idx + 1
            for idx, (name, _) in enumerate(data.shifts.iterrows())
        }

        self.idx_to_name = ["-"] + [key for key in self.shift_name_to_idx]
        self.shift_name_to_idx.update({"-": 0})

        self.high_stress_nurses = set(
            data.staff.index[
                data.staff["StressLevel"] >= data.stress_threshold
            ]
        )

        self.nurse_map = list(self.data.staff["# ID"])

        self.days = [
            self.index_to_date[i].strftime("%a %Y-%m-%d")
            for i in range(data.horizon)
        ]

        self.nurse_view: Any = cp.intvar(
            0,
            self.n_types,
            shape=(self.n_nurses, data.horizon),  # type: ignore[arg-type]
            name="roster",
        )

        self.day_off_color = "lightgreen"
        self.on_request_color = (183, 119, 41)
        self.off_request_color = (212, 175, 55)

    def _describe(self, constraint: Any, description: str):
        if hasattr(constraint, "set_description"):
            constraint.set_description(description)

    def _visualize(self, constraint: Any, visualizer):
        setattr(constraint, "visualize", visualizer)

    def _noop_visualizer(self, style):
        return None

    def _build_weekends(self):
        """
        Weekends as tuples of the Saturday/Sunday indexes inside the horizon.
        A weekend cut by the horizon (starting on Sunday or ending on Saturday)
        is kept with its only day.
        """
        weekends = {}

        for i, current_date in self.index_to_date.items():
            weekday = current_date.weekday()

            if weekday >= 5:
                saturday_idx = i - (weekday - 5)
                weekends.setdefault(saturday_idx, []).append(i)

        return [tuple(days) for _, days in sorted(weekends.items())]

    def week_blocks(self):
        """
        Planning weeks as (start, end) blocks of 7 days from the first day
        of the horizon; the last block may be shorter.
        """
        return [
            (start, min(start + 7, self.data.horizon))
            for start in range(0, self.data.horizon, 7)
        ]

    def prorated_min_weekly(self, min_weekly, start, end):
        """
        Weekly minimum for the block [start, end), prorated by the number of
        days when the block is shorter than a week.
        """
        return int(min_weekly) * (end - start) // 7

    def get_day_indexes_for_weekday(self, weekday: int):
        return [
            idx
            for idx, date in self.index_to_date.items()
            if date.weekday() == weekday
        ]

    def get_day_indexes_for_dates(self, dates):
        return [
            self.date_to_index[date]
            for date in dates
            if date in self.date_to_index
        ]

    def get_hard_constraints(self):
        model = cp.Model()

        model += self.shift_rotation()
        model += self.max_shifts()
        model += self.max_minutes()

        # Min workload is now soft.
        # Do not include:
        # model += self.min_minutes()

        model += self.max_weekly_minutes()

        # Min weekly workload is now soft.
        # Do not include:
        # model += self.min_weekly_minutes()

        model += self.max_consecutive()
        model += self.min_consecutive()
        model += self.weekend_shifts()
        model += self.days_off()
        model += self.min_consecutive_off()
        model += self.blocked_weekdays()

        return model

    def get_optimization_model(self):
        cons_on, penalty_on = self.shift_on_requests(formulation="soft")
        cons_off, penalty_off = self.shift_off_requests(formulation="soft")

        # Cover is now HARD.
        # requirement = 0 means exactly zero assigned nurses.
        cons_cover, penalty_cover = self.cover(formulation="hard")

        # Minimum workload is now SOFT.
        cons_min_total, penalty_min_total = self.min_minutes_soft()
        cons_min_weekly, penalty_min_weekly = self.min_weekly_minutes_soft()

        cons_stress, penalty_stress = self.stress()

        model = self.get_hard_constraints()

        model += [
            cons_on,
            cons_off,
            cons_cover,
            cons_min_total,
            cons_min_weekly,
            cons_stress,
        ]

        obj_func = (
            penalty_on
            + penalty_off
            + penalty_cover
            + penalty_min_total
            + penalty_min_weekly
            + penalty_stress
        )

        model.minimize(obj_func)
        model.constraints = toplevel_list(model.constraints, merge_and=False)

        return model, self.nurse_view

    def get_multi_objective_model(self):
        cons_on, penalty_on = self.shift_on_requests(formulation="soft")
        cons_off, penalty_off = self.shift_off_requests(formulation="soft")

        cons_cover, penalty_cover = self.cover(formulation="hard")
        cons_min_total, penalty_min_total = self.min_minutes_soft()
        cons_min_weekly, penalty_min_weekly = self.min_weekly_minutes_soft()

        model = self.get_hard_constraints()

        model += [
            cons_on,
            cons_off,
            cons_cover,
            cons_min_total,
            cons_min_weekly,
        ]

        obj_func = (
            penalty_on
            + penalty_off
            + penalty_cover
            + penalty_min_total
            + penalty_min_weekly
        )

        model.minimize(obj_func)
        model.constraints = toplevel_list(model.constraints, merge_and=False)

        return (
            model,
            self.nurse_view,
            penalty_on,
            penalty_off,
            penalty_cover,
            penalty_min_total,
            penalty_min_weekly,
        )

    def get_decision_model(self):
        model = self.get_hard_constraints()

        cons_on, penalty_on = self.shift_on_requests(formulation="hard")
        cons_off, penalty_off = self.shift_off_requests(formulation="hard")
        cons_cover, penalty_cover = self.cover(formulation="hard")

        model += [cons_on, cons_off, cons_cover]

        obj_func = penalty_on + penalty_off + penalty_cover
        model.minimize(obj_func)

        model.constraints = toplevel_list(model.constraints, merge_and=False)

        return model, self.nurse_view

    def get_slack_model(self):
        model = self.get_hard_constraints()

        cons_on, penalty_on = self.shift_on_requests(formulation="hard")
        cons_off, penalty_off = self.shift_off_requests(formulation="hard")
        cons_cover, penalty_cover = self.cover(formulation="hard")
        cons_min_total, penalty_min_total = self.min_minutes_soft()
        cons_min_weekly, penalty_min_weekly = self.min_weekly_minutes_soft()

        model += [
            cons_on,
            cons_off,
            cons_cover,
            cons_min_total,
            cons_min_weekly,
        ]

        model.constraints = toplevel_list(model.constraints, merge_and=False)

        return model, self.nurse_view, None, None

    def shift_rotation(self):
        constraints = []

        for t, (_, shift) in enumerate(self.data.shifts.iterrows()):
            cannot_follow = [
                self.shift_name_to_idx[name]
                for name in shift["cannot follow"]
                if name != ""
            ]

            for other_shift in cannot_follow:
                for n in range(self.n_nurses):

                    if n in self.high_stress_nurses:
                        continue

                    for d in range(self.data.horizon - 1):
                        cons = (self.nurse_view[n, d] == t + 1).implies(
                            self.nurse_view[n, d + 1] != other_shift
                        )

                        self._describe(
                            cons,
                            f"None of {shift['cannot follow']} can follow "
                            f"shift {self.idx_to_name[t + 1]} for "
                            f"{self.data.staff.iloc[n]['name']}",
                        )
                        self._visualize(cons, self._noop_visualizer)
                        constraints.append(cons)

        return constraints

    def max_shifts(self):

        def get_visualizer(nurse_idx, shift_id):
            def visualize(styler):
                styler[("#Shifts", shift_id)].iloc[nurse_idx] += (
                    "border: 5px dotted red;"
                )

            return visualize

        constraints = []

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            for shift_id, _ in self.data.shifts.iterrows():
                n_shifts = cp.Count(
                    self.nurse_view[n],
                    self.shift_name_to_idx[shift_id],
                )

                max_shifts = nurse[f"max_shifts_{shift_id}"]
                cons = n_shifts <= max_shifts

                self._describe(
                    cons,
                    f"{nurse['name']} can work at most "
                    f"{max_shifts} {shift_id}-shifts",
                )
                self._visualize(cons, get_visualizer(n, shift_id))
                constraints.append(cons)

        return constraints

    def max_minutes(self):

        def get_visualizer(nurse_idx):
            def visualize(styler):
                styler.iloc[nurse_idx, -1] += "border: 5px dotted red;"

            return visualize

        constraints = []
        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            time_worked = cp.sum(
                shift_length[t]
                for t in self.nurse_view[n]
            )

            constraint = time_worked <= nurse["MaxTotalMinutes"]

            self._describe(
                constraint,
                f"{nurse['name']} cannot work more than "
                f"{nurse['MaxTotalMinutes']}min",
            )
            self._visualize(constraint, get_visualizer(n))
            constraints.append(constraint)

        return constraints

    def min_minutes(self):
        """
        Hard version kept for compatibility/debugging.
        It is no longer included in get_hard_constraints().
        Use min_minutes_soft() in the optimization model.
        """

        def get_visualizer(nurse_idx):
            def visualize(styler):
                styler.iloc[nurse_idx, -1] += "border: 5px dotted green;"

            return visualize

        constraints = []
        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            time_worked = cp.sum(
                shift_length[t]
                for t in self.nurse_view[n]
            )

            constraint = time_worked >= nurse["MinTotalMinutes"]

            self._describe(
                constraint,
                f"{nurse['name']} should work at least "
                f"{nurse['MinTotalMinutes']}min",
            )
            self._visualize(constraint, get_visualizer(n))
            constraints.append(constraint)

        return constraints

    def min_minutes_soft(self, penalty_weight: Optional[int] = None):
        if penalty_weight is None:
            penalty_weight = self.data.underallocation_weight_total

        constraints = []
        penalties = []

        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            min_total = int(nurse["MinTotalMinutes"])

            time_worked = cp.sum(
                shift_length[t]
                for t in self.nurse_view[n]
            )

            shortage = cp.intvar(
                0,
                min_total,
                name=f"under_total_minutes_{nurse['# ID']}",
            )

            constraint = time_worked + shortage >= min_total

            self._describe(
                constraint,
                f"{nurse['name']} may be underallocated against "
                f"MinTotalMinutes={min_total}",
            )
            self._visualize(constraint, self._noop_visualizer)

            constraints.append(constraint)
            penalties.append(penalty_weight * shortage)

        return constraints, cp.sum(penalties)

    def max_weekly_minutes(self):
        constraints = []
        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            for i, week_end in self.week_blocks():
                window = self.nurse_view[n][i:week_end]

                time_worked = cp.sum(
                    shift_length[t]
                    for t in window
                )

                constraint = time_worked <= nurse["MaxWeeklyMinutes"]

                self._describe(
                    constraint,
                    f"{nurse['name']} cannot work more than "
                    f"{nurse['MaxWeeklyMinutes']}min in planning week starting "
                    f"{self.days[i]}",
                )
                self._visualize(constraint, self._noop_visualizer)
                constraints.append(constraint)

        return constraints

    def min_weekly_minutes(self):
        """
        Hard version kept for compatibility/debugging.
        It is no longer included in get_hard_constraints().
        Use min_weekly_minutes_soft() in the optimization model.
        """

        constraints = []
        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            for i, week_end in self.week_blocks():
                window = self.nurse_view[n][i:week_end]
                min_weekly = self.prorated_min_weekly(
                    nurse["MinWeeklyMinutes"], i, week_end
                )

                time_worked = cp.sum(
                    shift_length[t]
                    for t in window
                )

                constraint = time_worked >= min_weekly

                self._describe(
                    constraint,
                    f"{nurse['name']} should work at least "
                    f"{min_weekly}min in planning week starting "
                    f"{self.days[i]}",
                )
                self._visualize(constraint, self._noop_visualizer)
                constraints.append(constraint)

        return constraints

    def min_weekly_minutes_soft(self, penalty_weight: Optional[int] = None):
        if penalty_weight is None:
            penalty_weight = self.data.underallocation_weight_weekly

        constraints = []
        penalties = []

        shift_length = cp.cpm_array([0] + [l for l in self.data.shifts.Length])

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            for i, week_end in self.week_blocks():
                window = self.nurse_view[n][i:week_end]
                min_weekly = self.prorated_min_weekly(
                    nurse["MinWeeklyMinutes"], i, week_end
                )

                time_worked = cp.sum(
                    shift_length[t]
                    for t in window
                )

                shortage = cp.intvar(
                    0,
                    min_weekly,
                    name=f"under_weekly_minutes_{nurse['# ID']}_start_{i}",
                )

                constraint = time_worked + shortage >= min_weekly

                self._describe(
                    constraint,
                    f"{nurse['name']} may be underallocated against "
                    f"MinWeeklyMinutes={min_weekly} for planning week "
                    f"starting {self.days[i]}",
                )
                self._visualize(constraint, self._noop_visualizer)

                constraints.append(constraint)
                penalties.append(penalty_weight * shortage)

        return constraints, cp.sum(penalties)

    def max_consecutive(self):

        def get_visualizer(nurse_idx, window):
            def visualize(styler):
                styler.iloc[nurse_idx, window[0]] += (
                    "border-left: 5px solid red;"
                )
                styler.iloc[nurse_idx, window[-1]] += (
                    "border-right: 5px solid red;"
                )

                for day in window:
                    styler.iloc[nurse_idx, day] += (
                        "border-top: 5px solid red; "
                        "border-bottom: 5px solid red;"
                    )

            return visualize

        constraints = []

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            max_days = nurse["MaxConsecutiveShifts"]

            for i in range(self.data.horizon - max_days):
                window_indexes = list(range(i, i + max_days + 1))
                window = self.nurse_view[n][i: i + max_days + 1]

                constraint = cp.Count(window, FREE) >= 1

                self._describe(
                    constraint,
                    f"{nurse['name']} can work at most {max_days} days "
                    f"before having a day off",
                )
                self._visualize(
                    constraint,
                    get_visualizer(n, window_indexes),
                )
                constraints.append(constraint)

        return constraints

    def min_consecutive(self):

        def get_visualizer(nurse_idx, window):
            def visualize(styler):
                styler.iloc[nurse_idx, window[0]] += (
                    "border-left: 5px dotted teal;"
                )
                styler.iloc[nurse_idx, window[-1]] += (
                    "border-right: 5px dotted teal;"
                )

                for day in window:
                    styler.iloc[nurse_idx, day] += (
                        "border-top: 5px dotted teal; "
                        "border-bottom: 5px dotted teal;"
                    )

            return visualize

        constraints = []

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            min_days = nurse["MinConsecutiveShifts"]
            nurse_shifts = self.nurse_view[n]

            for i in range(self.data.horizon):
                if i == 0:
                    continue

                end = min(i + min_days, self.data.horizon)

                if end - i < min_days:
                    continue

                is_start_of_working_period = (
                    (nurse_shifts[i] != FREE)
                    & (nurse_shifts[i - 1] == FREE)
                )

                constraint = is_start_of_working_period.implies(
                    cp.all(
                        [
                            nurse_shifts[d] != FREE
                            for d in range(i, end)
                        ]
                    )
                )

                self._describe(
                    constraint,
                    f"{nurse['name']} should work at least {min_days} days "
                    f"before having a day off",
                )
                self._visualize(
                    constraint,
                    get_visualizer(n, list(range(i, end))),
                )
                constraints.append(constraint)

        return constraints

    def weekend_shifts(self):

        def get_visualizer(nurse_idx):
            def visualize(styler):
                for weekend in self.weekends:
                    styler.iloc[nurse_idx, weekend[0]] += (
                        "border-left: 5px solid indigo;"
                    )
                    styler.iloc[nurse_idx, weekend[-1]] += (
                        "border-right: 5px solid indigo;"
                    )

                    for day in weekend:
                        styler.iloc[nurse_idx, day] += (
                            "border-top: 5px solid indigo; "
                            "border-bottom: 5px solid indigo;"
                        )

            return visualize

        constraints = []

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            max_weekends = nurse["MaxWeekends"]
            shifts = self.nurse_view[n]

            n_weekends = cp.sum(
                [
                    cp.any([shifts[day] != FREE for day in weekend])
                    for weekend in self.weekends
                ]
            )

            constraint = n_weekends <= max_weekends

            self._describe(
                constraint,
                f"{nurse['name']} should work at most {max_weekends} weekends",
            )
            self._visualize(constraint, get_visualizer(n))
            constraints.append(constraint)

        return constraints

    def days_off(self):

        def get_visualizer(nurse_idx, day):
            def visualize(styler):
                styler.iloc[nurse_idx, day] += "background-color:lightgreen;"

            return visualize

        constraints = []

        if self.data.days_off is None or self.data.days_off.empty:
            return constraints

        for _, holiday in self.data.days_off.iterrows():
            n = self.nurse_map.index(holiday["EmployeeID"])

            if n in self.high_stress_nurses:
                continue

            day = int(holiday["DayIndex"])

            constraint = self.nurse_view[n, day] == FREE

            self._describe(
                constraint,
                f"{self.data.staff.iloc[n]['name']} has a day off on "
                f"{self.days[day]}",
            )
            self._visualize(constraint, get_visualizer(n, day))
            constraints.append(constraint)

        return constraints

    def blocked_weekdays(self):
        constraints = []

        if (
            not hasattr(self.data, "blocked_weekdays")
            or self.data.blocked_weekdays is None
            or self.data.blocked_weekdays.empty
        ):
            return constraints

        for _, blocked in self.data.blocked_weekdays.iterrows():
            weekday = int(blocked["weekday"])
            shift_ids = blocked["shift_ids"]
            day_indexes = self.get_day_indexes_for_weekday(weekday)

            for day in day_indexes:
                for shift_id in shift_ids:
                    shift_idx = self.shift_name_to_idx[shift_id]

                    expr = cp.Count(
                        [
                            self.nurse_view[n, day]
                            for n in range(self.n_nurses)
                        ],
                        shift_idx,
                    ) == 0

                    self._describe(
                        expr,
                        f"Shift {shift_id} is forbidden on {self.days[day]}",
                    )
                    self._visualize(expr, self._noop_visualizer)
                    constraints.append(expr)

        return constraints

    def min_consecutive_off(self):

        def get_visualizer(nurse_idx, window):
            def visualize(styler):
                styler.iloc[nurse_idx, window[0]] += (
                    "border-left: 5px dotted lightgreen;"
                )
                styler.iloc[nurse_idx, window[-1]] += (
                    "border-right: 5px dotted lightgreen;"
                )

                for day in window:
                    styler.iloc[nurse_idx, day] += (
                        "border-top: 5px dotted lightgreen; "
                        "border-bottom: 5px dotted lightgreen;"
                    )

            return visualize

        constraints = []

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])

            if n in self.high_stress_nurses:
                continue

            min_days = nurse["MinConsecutiveDaysOff"]
            nurse_shifts = self.nurse_view[n]

            for i in range(self.data.horizon):
                if i == 0:
                    continue

                end = min(i + min_days, self.data.horizon)

                if end - i < min_days:
                    continue

                is_start_of_free_period = (
                    (nurse_shifts[i] == FREE)
                    & (nurse_shifts[i - 1] != FREE)
                )

                constraint = is_start_of_free_period.implies(
                    cp.all(
                        [
                            nurse_shifts[d] == FREE
                            for d in range(i, end)
                        ]
                    )
                )

                self._describe(
                    constraint,
                    f"{nurse['name']} should have at least {min_days} "
                    f"consecutive days off",
                )
                self._visualize(
                    constraint,
                    get_visualizer(n, list(range(i, end))),
                )
                constraints.append(constraint)

        return constraints

    def shift_on_requests(self, formulation="soft"):

        def get_visualizer(nurse_idx, day):
            def visualize(styler):
                styler.iloc[nurse_idx, day] += (
                    "background-color:rgb(183, 119, 41);"
                )

            return visualize

        constraints = []
        penalty = []

        if self.data.shift_on is None or self.data.shift_on.empty:
            return constraints, cp.sum(penalty)

        for _, request in self.data.shift_on.iterrows():
            n = self.nurse_map.index(request["# EmployeeID"])

            if n in self.high_stress_nurses:
                continue

            shift = self.shift_name_to_idx[request["ShiftID"]]
            day = int(request["Day"])

            if formulation == "hard":
                constraint = self.nurse_view[n, day] == shift

                self._describe(
                    constraint,
                    f"{self.data.staff.iloc[n]['name']} requests to work shift "
                    f"{self.idx_to_name[shift]} on {self.days[day]}",
                )
                self._visualize(constraint, get_visualizer(n, day))
                constraints.append(constraint)
            else:
                expr = self.nurse_view[n, day] != shift

                self._describe(
                    expr,
                    f"Deny {self.data.staff.iloc[n]['name']}'s request to work "
                    f"shift {self.idx_to_name[shift]} on {self.days[day]}",
                )
                penalty.append(request["Weight"] * expr)

        return constraints, cp.sum(penalty)

    def shift_off_requests(self, formulation="soft"):

        def get_visualizer(nurse_idx, day):
            def visualize(styler):
                styler.iloc[nurse_idx, day] += (
                    "background-color: rgb(212,175,55);"
                )

            return visualize

        constraints = []
        penalty = []

        if self.data.shift_off is None or self.data.shift_off.empty:
            return constraints, cp.sum(penalty)

        for _, request in self.data.shift_off.iterrows():
            n = self.nurse_map.index(request["# EmployeeID"])

            if n in self.high_stress_nurses:
                continue

            shift = self.shift_name_to_idx[request["ShiftID"]]
            day = int(request["Day"])

            if formulation == "hard":
                constraint = self.nurse_view[n, day] != shift

                self._describe(
                    constraint,
                    f"{self.data.staff.iloc[n]['name']} requests not to work "
                    f"shift {self.idx_to_name[shift]} on {self.days[day]}",
                )
                self._visualize(constraint, get_visualizer(n, day))
                constraints.append(constraint)
            else:
                expr = self.nurse_view[n, day] == shift

                self._describe(
                    expr,
                    f"Deny {self.data.staff.iloc[n]['name']}'s request not to work "
                    f"shift {self.idx_to_name[shift]} on {self.days[day]}",
                )
                penalty.append(request["Weight"] * expr)

        return constraints, cp.sum(penalty)

    def cover(self, formulation="hard"):

        def get_visualizer(day, shift):
            def visualize(styler):
                styler.iloc[0, day] += "border-top: 5px solid red;"

                for n in range(self.n_nurses):
                    styler.iloc[n, day] += (
                        "border-left: 5px solid red; "
                        "border-right: 5px solid red;"
                    )

                styler.iloc[n, day] += "border-bottom: 5px solid red;"
                styler.iloc[n + shift, day] += "border: 5px solid red;"

            return visualize

        constraints = []
        penalties = []

        if formulation != "hard":
            raise ValueError(
                "Cover must now be a hard constraint. "
                "Use soft MinTotalMinutes and MinWeeklyMinutes constraints "
                "to allow nurses to be underallocated."
            )

        def exact_cover(day, shift_id, role_id, requirement, description):
            shift = self.shift_name_to_idx[shift_id]

            eligible_nurses = [
                n
                for n, nurse in self.data.staff.iterrows()
                if nurse["RoleID"] == role_id
            ]

            nb_nurses = cp.sum(
                [
                    self.nurse_view[n, day] == shift
                    for n in eligible_nurses
                ]
            )

            # Hard exact cover:
            # requirement = 0 means exactly zero nurses assigned.
            expr = nb_nurses == requirement

            self._describe(expr, description)
            self._visualize(expr, get_visualizer(day, shift))
            constraints.append(expr)

        covered = set()
        cover_rows = (
            self.data.cover.iterrows() if self.data.cover is not None else []
        )

        for _, cover in cover_rows:
            shift_id = cover["ShiftID"]
            requirement = int(cover["Requirement"])
            day = int(cover["# Day"])
            role_id = cover["RoleID"]

            covered.add((day, shift_id, role_id))
            exact_cover(
                day,
                shift_id,
                role_id,
                requirement,
                f"Shift {shift_id} on {self.days[day]} requires exactly "
                f"{requirement} nurse(s) with role {role_id}",
            )

        # Roles not listed in the cover of a day/shift, and days/shifts without
        # any cover entry, are treated as a requirement of 0.
        for day in range(self.data.horizon):
            for shift_id in self.data.shifts.index:
                for role_id in self.data.staff["RoleID"].unique():
                    if (day, shift_id, role_id) in covered:
                        continue

                    exact_cover(
                        day,
                        shift_id,
                        role_id,
                        0,
                        f"Shift {shift_id} on {self.days[day]} requires no "
                        f"nurse with role {role_id} (not specified in cover)",
                    )

        return constraints, cp.sum(penalties)

    def stress(self):
        constraints = []
        penalties = []

        shifts_stress_weights = [0] * len(self.shift_name_to_idx)

        for shift_id, shift in self.data.shifts.iterrows():
            shifts_stress_weights[self.shift_name_to_idx[shift_id]] = int(
                shift["StressWeight"] * 10
            )

        for _, nurse in self.data.staff.iterrows():
            n = self.nurse_map.index(nurse["# ID"])
            nurse_shifts = self.nurse_view[n]

            if n in self.high_stress_nurses:
                for day in range(self.data.horizon):
                    constraints.append(nurse_shifts[day] == FREE)
                continue

            accumulated_stress = [nurse["StressLevel"] * 10]

            for day in range(self.data.horizon):
                for shift in self.shift_name_to_idx.values():
                    if shifts_stress_weights[shift] == 0:
                        continue

                    accumulated_stress.append(
                        (nurse_shifts[day] == shift)
                        * shifts_stress_weights[shift]
                    )

            expr = sum(accumulated_stress) < self.data.stress_threshold * 10
            constraints.append(expr)

        return constraints, cp.sum(penalties)


def is_not_none(*args):
    return not any(a is None for a in args)