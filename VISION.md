# Vision

basecamp-mate is a thin, reliable connection between firstmate and Basecamp. It makes sure firstmate sees everything meant for it and can answer in the right place. It does not decide how firstmate works.

## Who it is for

Any firstmate user on Basecamp, whatever their projects, lists and card tables look like.

## Principles

1. **Reliability is the product.** Every assignment, check-in, comment, chat line and card meant for firstmate reaches it once, at the right time, in the right format: nothing missed, nothing doubled.
2. **No fixed layout.** It works with any project, to-do list or card table. It never requires a particular project, list or pattern, such as every decision becoming a to-do in one project.
3. **Sensible defaults, changed by asking.** It ships with defaults that the user changes by asking firstmate, per list where that makes sense:
   - An assigned task with a due date: firstmate comments to ask whether to do it on the due date or before, then remembers the answer.
   - A recurring assigned task: firstmate does it on the due date.
   - A decision needed on a task or card: firstmate comments there and adds a step assigned to the person who has to decide.
4. **Plain language in the user's local time** in everything it writes.
5. **Who it listens to is explicit, and enforced before firstmate.** Only people on its allow lists get through: account-wide, per project, or a trusted group for risky actions. A message from anyone else never reaches firstmate; basecamp-mate blocks it and posts a short automatic reply saying it cannot act on the request. The default is only the account owner for a personal account and everyone in the company for a team account, and both change by asking firstmate.

It builds on [basecamp-axi](https://github.com/calebl/basecamp-axi) for talking to Basecamp.

## Non-goals

- Deciding firstmate's workflow.
- Requiring set projects, lists or card tables.
- General Basecamp automation.
