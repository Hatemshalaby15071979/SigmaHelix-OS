---
name: frontend-webapp
description: Build and review frontend web apps that actually run - structure, state, data flow, accessibility, performance and the build/release path.
order: 20
---

# Frontend and web app engineering

You build interfaces that run, not demos that look right in a screenshot.

## Decide the shape before writing code

1. Name the single user job the screen exists for. If you cannot state it in
   one sentence, the screen is two screens.
2. List the states it must render: empty, loading, error, partial, full,
   offline. Every one of them is a real screen.
3. Name the data source and who owns it. If the answer is "the component",
   move it up.

## Structure

- One route or view per user job. Nested views are for nested data, never for
  hiding complexity.
- Separate fetching, transformation and rendering. A component that does all
  three cannot be tested.
- Keep derived state derived. If a value can be computed from props or store,
  never store it again.
- Server state and UI state are different problems. Server state needs cache,
  revalidation and staleness rules; UI state needs none of that.

## Implementation rules

- Prefer the platform: native form validation, native dialogs, native
  scrolling. Add a library only when it removes more code than it adds.
- Every async call has a timeout, an error branch and a cancel path.
- Never block the first paint on a network call that is not required to render
  the shell.
- Tables virtualise past 200 rows. Lists paginate past 100.
- Images declare width and height so layout does not jump.
- No inline styles except computed values.

## Accessibility is not optional

- Every interactive element is reachable by keyboard and has a visible focus
  ring.
- Every input has a label tied by `for`/`id`, not placeholder text.
- Colour is never the only carrier of meaning.
- Contrast meets 4.5:1 for body text.

## Performance

- Measure before optimising. Record the metric, the tool and the number.
- Ship the smallest bundle that renders the first screen; split the rest.
- A list item that re-renders on every keystroke is a bug, not a tuning issue.

## Release path

- The build command is written down and runs from a clean checkout.
- Environment values come from the environment, never from source.
- A build that only works on your machine is not built.
- State the exact command that proves the app starts, and run it.
