---
name: ui-interaction-design
description: Design interfaces that feel obvious - hierarchy, spacing, motion, feedback, keyboard flow and the small interactions users judge in the first five seconds.
order: 21
---

# UI and interaction design

A user does not read an interface. They scan it, guess, and click. Design for
the guess.

## Hierarchy

- One primary action per screen. Everything else is secondary or hidden.
- Size, weight and contrast rank importance. Do not rank with colour alone.
- If everything is bold, nothing is.
- Group by meaning, not by shape. Spacing between groups is larger than
  spacing inside a group - at least double.

## Layout

- Use a 4 or 8 pixel scale. Arbitrary values produce drift.
- Align edges. A single misaligned edge reads as broken even when the user
  cannot name why.
- Line length 45 to 75 characters for body text.
- Touch targets at least 44 by 44 pixels. Desktop click targets at least
  32 by 32.

## Feedback

- Every action answers within 100 ms: a pressed state, a spinner, a change.
  Silence reads as a broken click.
- Long work shows progress and stays cancellable.
- Errors say what happened, what it means, and what to do next. Never only
  "Something went wrong".
- Success is visible and specific: "Saved to Notes", not "OK".

## Motion

- Motion explains a change of state or place. If it explains nothing, remove it.
- 150 to 250 ms for UI transitions. Longer feels sluggish, shorter feels broken.
- Respect reduced-motion settings.
- Never animate on a path the user repeats dozens of times a day.

## Keyboard

- Tab order follows visual order.
- Enter submits, Escape cancels, arrows move within a group.
- Shortcuts are discoverable in the UI, not only in documentation.

## Empty and first-run states

- An empty screen teaches the next action. It is never a blank box with
  "No data".
- First run shows the smallest useful thing the user can complete in a minute.

## Review checklist

1. Can a new user find the primary action in two seconds?
2. Does every state have a designed appearance?
3. Does every click produce feedback?
4. Does the keyboard reach everything the mouse can?
5. Would removing any element break the job? If not, remove it.
