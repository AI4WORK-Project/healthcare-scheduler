# Instance1

This document describes the problem defined by the `instance1.json` file.

## Horizon

The scheduling horizon is 28 days (4 weeks).

## Start Date

The `start_date` field (format `YYYY-MM-DD`) is the date of the first day of the horizon (day index 0).
It is used to compute the weekday of each day, and therefore the weekends and the blocked weekdays.
In this instance the horizon starts on Monday 2026-06-01.
The field is optional and defaults to `1970-01-05` (a Monday).

## Shifts

The available shifts are:

- **morning**
- **evening**
- **night**

Shifts are independent of the nurse's professional role: the role is a property of the nurse (see `role_id` below), and the cover defines how many nurses of each role are required on each shift.

Each shift lasts 480 minutes (8 hours).
The `stress_weight` field indicates how much each shift contributes to the nurse's overall stress.

## Staff

Each nurse has a `role_id`. The staff comprises:  

- 4 lead nurses (`lead`)  
- 6 registered nurses (`registered`)  
- 9 assistant nurses (`assistant`)  

### Example

Megan is a lead nurse with the following constraints and preferences:

- The `role_id` field is set to `lead`.
- The `max_shifts` field specifies the shifts she can perform (i.e., **morning**, **evening**, **night**) and the maximum number of each.  
- Megan can work at most 9600 minutes (20 shifts) over the 28-day period and 2400 minutes (5 shifts) per week.
- The minimum total and weekly minutes (also 9600 and 2400) are soft targets: if needed to satisfy the cover, the solver may assign her less work, minimising the shortage. The shortage is penalised in the objective according to the `underallocation_weights` (see below).
- Weekly minutes are checked on planning weeks of 7 days counted from `start_date`, not on calendar weeks. If the horizon ends with a partial week, its minimum is prorated by the number of days (e.g. a final 3-day block requires 2400 * 3 / 7 = 1028 minutes, rounded down).
- The `max_consecutive_shifts` field is set to 10, indicating that Megan can work up to 10 consecutive days.  
- The `min_consecutive_shifts` field is set to 1.
- The `min_consecutive_days_off` field is set to 1.
- The `max_weekends` field is set to 4, so this constraint is always satisfied. A weekend is considered worked if she is assigned a shift on the Saturday or on the Sunday; a Saturday or Sunday at the edge of the horizon counts as a weekend on its own.
- The `stress_level` field represents Megan's current stress level

```json
{
    "employee_id": "Megan",
    "role_id": "lead",
    "max_shifts": [
        {
            "shift_id": "morning",
            "max_shifts": 20
        },
        {
            "shift_id": "evening",
            "max_shifts": 20
        },
        {
            "shift_id": "night",
            "max_shifts": 20
        }
    ],
    "max_total_minutes": 9600,
    "min_total_minutes": 9600,
    "max_weekly_minutes": 2400,
    "min_weekly_minutes": 2400,
    "max_consecutive_shifts": 10,
    "min_consecutive_shifts": 1,
    "min_consecutive_days_off": 1,
    "max_weekends": 4,
    "stress_level": 10
}
```

## Days Off

This section defines which shifts must not be assigned to the specified employee on the specified days.

### Example

Robert is unavailable on the 4th, 5th, and 8th days (day indexes start at zero):

```json
{
    "employee_id": "Robert",
    "day_indexes": [
        3,
        4,
        7
    ]
}
```

## Shift On Requests

The `shift_on_requests` section defines the shifts each nurse prefers to work. If the specified shift is not assigned to the employee on the specified day, a penalty is applied based on the weight.

### Example

Megan prefers to work the morning shift on the first day. If this shift is not assigned, a penalty of 1 is applied:

```json
{
    "employee_id": "Megan",
    "day": 0,
    "shift_id": "morning",
    "weight": 1
}
```

To indicate Megan's preference for the morning shift every day, this entry is repeated for all 28 days.

## Shift Off Requests

The `shift_off_requests` section specifies the shifts an employee prefers not to work. It is similar to the "Shift On Requests" section.

## Cover

The `cover` section defines, for each day and shift, the required number of nurses of each role (`role_requirements`).

Cover is a hard constraint: the schedule must contain exactly the required number of nurses for each role and shift.
A requirement of 0 explicitly prevents nurses of that role from being assigned to the shift.
Roles not listed in `role_requirements`, and days/shifts without a cover entry, are treated as a requirement of 0: no nurse of that role (or no nurse at all) can be assigned.
The `weight_for_under` and `weight_for_over` fields are deprecated: they are optional and ignored by the solver.

### Example

On the first day, the morning shift requires exactly 1 lead nurse, 2 registered nurses and 3 assistant nurses:

```json
{
    "day": 0,
    "shift_id": "morning",
    "role_requirements": {
        "lead": 1,
        "registered": 2,
        "assistant": 3
    }
}
```

## Blocked Weekdays

The `blocked_weekdays` section defines shifts that must not be assigned to any employee on a given weekday (Monday = 0, ..., Sunday = 6).
The section is optional; this instance does not block any weekday.

### Example

No night shift is assigned on Sundays:

```json
{
    "weekday": 6,
    "shift_ids": [
        "night"
    ]
}
```

## Stress threshold

The `stress_threshold` field specifies the maximum stress level a nurse is required to stay below.
A nurse's final stress is calculated as their initial stress level plus the sum of the `stress_weight` values for all assigned shifts. The final stress must not exceed the `stress_threshold`.
Nurses whose initial stress level has already reached the threshold (e.g., Rachel) are not assigned any shift.

## Underallocation Weights

The `underallocation_weights` field sets how much the shortage against the soft minimum workload costs in the objective:

- `total`: cost per minute missing from `min_total_minutes`;
- `weekly`: cost per minute missing from the minimum of each planning week.

The field is optional and both weights default to 1; this instance does not set it.
The weights are compared with the `weight` of the shift requests: with the defaults, one missing 480-minute shift costs 480 (total) + 480 (weekly) = 960, while an ignored request costs its `weight`.

### Example

```json
"underallocation_weights": {
    "total": 1,
    "weekly": 1
}
```

## Use Case Specific Constraints

### shiftPreferencesSatisfaction

To specify that a nurse desires to work a specific shift every day (e.g., morning shifts), repeat the preference in the `shift_on_requests` section for all 28 days.

### healthRestrictions

To ensure nurses with health restrictions are not scheduled for inappropriate shifts, define these shifts in the `shift_off_requests` section.

### restPeriodCompliance

To ensure that the required rest period (11 hours) between shifts is met, the evening shift cannot be followed by the morning shift the next day, and the night shift cannot be followed by the morning or evening shifts the next day.

Since each nurse is limited to one shift per day, restrictions for shifts on the same day must not be defined.

For example:
- Shift `evening` cannot be followed by shift `morning` the next day. It is important not to include `night` in the `cannot_follow` field, as it would incorrectly refer to the night shift of the following day.
- Shift `night` cannot be followed by shifts `morning` or `evening` the next day.

```json
{
    "shift_id": "evening",
    "length": 480,
    "cannot_follow": [
        "morning"
    ]
},
{
    "shift_id": "night",
    "length": 480,
    "cannot_follow": [
        "morning",
        "evening"
    ]
}
```

