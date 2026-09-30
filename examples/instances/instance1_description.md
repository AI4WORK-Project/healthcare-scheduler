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

- **LM**: Lead Nurse, Morning
- **LA**: Lead Nurse, Afternoon
- **LN**: Lead Nurse, Night
- **RM**: Registered Nurse, Morning
- **RA**: Registered Nurse, Afternoon
- **RN**: Registered Nurse, Night
- **AM**: Assistant Nurse, Morning
- **AA**: Assistant Nurse, Afternoon
- **AN**: Assistant Nurse, Night 

Each shift lasts 480 minutes (8 hours).
The `stress_weight` field indicates how much each shift contributes to the nurse's overall stress.

## Staff

The staff comprises:  

- 4 lead nurses  
- 6 registered nurses  
- 8 assistant nurses  

### Example

Megan is a lead nurse with the following constraints and preferences:

- The `max_shifts` field specifies the shifts she can perform (i.e., **LM**, **LA**, **LN**) and the maximum number of each.  
- Megan works exactly 9600 minutes (20 shifts) over the 28-day period and 2400 minutes (5 shifts) per week.
- The `max_consecutive_shifts` field is set to 10, indicating that Megan can work up to 10 consecutive days.  
- The `min_consecutive_shifts` field is set to 1.
- The `min_consecutive_days_off` field is set to 1.
- The `max_weekends` field is set to 4, so this constraint is always satisfied.
- The `stress_level` field represents Megan's current stress level

```json
{
    "employee_id": "Megan",
    "max_shifts": [
        {
            "shift_id": "LM",
            "max_shifts": 20
        },
        {
            "shift_id": "LA",
            "max_shifts": 20
        },
        {
            "shift_id": "LN",
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
    "shift_id": "LM",
    "weight": 1
}
```

To indicate Megan's preference for the morning shift every day, this entry is repeated for all 28 days.

## Shift Off Requests

The `shift_off_requests` section specifies the shifts an employee prefers not to work. It is similar to the "Shift On Requests" section.

## Cover

The `cover` section defines the required number of nurses for each shift each day.

- If the number assigned (x) is below the required number then the solution's penalty is `(requirement - x) * weight_for_under`
- If the total number assigned is more than the required number then the solution's penalty is `(x - requirement) * weight_for_over`

### Example

```json
{
    "day": 0,
    "shift_id": "LM",
    "requirement": 1,
    "weight_for_under": 100,
    "weight_for_over": 1
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
        "LN",
        "RN",
        "AN"
    ]
}
```

## Stress threshold

The `stress_threshold` field specifies the maximum stress level a nurse is required to stay below.
A nurse's final stress is calculated as their initial stress level plus the sum of the `stress_weight` values for all assigned shifts. The final stress must not exceed the `stress_threshold`.

## Use Case Specific Constraints

### shiftPreferencesSatisfaction

To specify that a nurse desires to work a specific shift every day (e.g., morning shifts), repeat the preference in the `shift_on_requests` section for all 28 days.

### healthRestrictions

To ensure nurses with health restrictions are not scheduled for inappropriate shifts, define these shifts in the `shift_off_requests` section.

### restPeriodCompliance

To ensure that the required rest period (11 hours) between shifts is met, the afternoon shift cannot be followed by the morning shift the next day, and the night shift cannot be followed by the morning or afternoon shifts the next day.

Since each nurse is limited to one shift per day, restrictions for shifts on the same day must not be defined.

For example:
- Shift `LA` (Lead Nurse, Afternoon) cannot be followed by shift `LM` (Lead Nurse, Morning) the next day. It is important not to include `LN` (Lead Nurse, Night) in the `cannot_follow` field, as it would incorrectly refer to the night shift of the following day.
- Shift `LN` (Lead Nurse, Night) cannot be followed by shifts `LM` (Lead Nurse, Morning) or `LA` (Lead Nurse, Afternoon) the next day.

```json
{
    "shift_id": "LA",
    "length": 480,
    "cannot_follow": [
        "LM"
    ]
},
{
    "shift_id": "LN",
    "length": 480,
    "cannot_follow": [
        "LM",
        "LA"
    ]
}
```

