# Date-based recurrence rules

`RecurrenceRule` is a pure all-day date rule anchored to a start date. Daily rules apply `interval` days; weekday filters then select allowed weekdays. Weekly rules apply `interval` weeks and select the supplied weekdays, defaulting to the anchor weekday. Monthly rules apply `interval` months and use either `day_of_month` or the anchor day. A requested day that is absent from a month clamps to that month's final day, so a day-31 rule occurs on February's last day and April 30.

`count` limits the total occurrences from the anchor; `end_date` is inclusive. Expansion uses an inclusive `through` bound, an exclusive optional `after` cursor, and a positive result limit. Rules use calendar dates only; timezone and daylight-saving scheduling belong to the later scheduler task.
