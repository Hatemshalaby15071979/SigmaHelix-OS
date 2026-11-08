---
name: prompt-engineering
description: Write prompts that produce reliable, checkable output - role, task, constraints, examples, output contract, failure handling and evaluation.
order: 23
---

# Prompt engineering

A prompt is a specification. If two competent readers would produce different
outputs from it, it is under-specified.

## Structure

1. **Role and scope** - who the model is, what it owns, what it must not touch.
2. **Task** - one imperative sentence. If there are two tasks, write two prompts.
3. **Context** - the facts the model needs, each labelled. Never rely on it
   knowing your project.
4. **Constraints** - what to include, exclude, and refuse.
5. **Output contract** - exact shape: JSON keys, ordering, length, format.
6. **Failure behaviour** - what to say when input is missing or ambiguous.

## Rules that change results

- Be concrete. "Short" is a guess; "under 60 words" is a requirement.
- Show one good example and one bad example. Examples beat adjectives.
- Ask for the answer first, reasoning second. Long reasoning before the answer
  invites drift.
- Give the model an explicit way to say "I don't know". Otherwise it invents.
- Put the most important constraint last; long prompts lose the middle.
- State the unit and the scale for every number you ask for.
- Never ask two questions in one sentence.

## Structured output

- Demand JSON only, with the exact keys.
- Make one key mandatory for the answer so the reply cannot be empty.
- Validate the output and retry once with the validation error attached.
- Treat model output as untrusted input: parse, validate, then use.

## Reliability

- Temperature 0 to 0.3 for extraction, classification and code.
- Higher temperature only for brainstorming, and say so.
- Same input, same output: seed or temperature 0, and record which.
- Keep a small set of fixed test inputs. Change the prompt, rerun the set,
  compare. A prompt change without a rerun is a guess.

## Evaluation

- Write the accept and reject rule before running the prompt.
- Score on data you did not tune on.
- Report the failure cases, not only the average.
- A prompt that works on one example is not tested; it is observed once.

## Anti-patterns

- Piling on rules until they contradict each other.
- Hiding the real requirement in a polite paragraph.
- Asking for "high quality" instead of defining what good looks like.
- Assuming the model remembers the previous session.
