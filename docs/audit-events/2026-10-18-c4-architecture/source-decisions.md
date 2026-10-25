# Complete C4 architecture: supplied requests and selected decisions

Recorded October 18, 2026 (Asia/Taipei). This is the source layer for the
[architecture publication closeout](audit-event.md). It continues the
[streaming repair thread](../2026-10-18-reuse-speech-guard/source-decisions.md)
with a distinct architecture-documentation deliverable.

## Original requests

> 請利用 Structurizr 等開源工具等等，來繪製這個專案的完整 C4 model。

The user selected these choices in the planning conversation:

- Scope: `目前實作全貌 (Recommended)`.
- Delivery: `互動瀏覽＋SVG／PNG (Recommended)`.
- Language: `全英文`.
- Code-level depth: `Key components + full source map (Recommended)`.

The implementation instruction was:

> Implement the plan.

The subsequent record and publication request was:

> Using FIRST PRINCIPLE, and please take notes on my day note in the `planning-everything-track` repo, and update the relevant docs, files, and contents for it.
> Please update all the commits separately on git, and push this branch to the remote main branch of the github repo. (If there were conflict among commits, i would like to keep both local commits and remote commits.)
> And build strong connection with all other relevant files, docs, and contents.

## Adopted interpretation

Create one current-implementation C4 model with C1/C2, focused C3/C4, dynamic
flows, deployment gates and complete source ownership. Use Structurizr and
PlantUML locally; retain rebuildable model sources, interactive browsing and
SVG/PNG. English governs diagrams, guides and new closeout text. Future Agent
and MCP designs remain outside the current model.

AURA owns the detailed source, implementation, rendered packet and validation.
Planning owns the day/project/week/integration locators, capacity, publication
and next maintenance action. Publication uses separate logical commits to
each repository's remote `main`, preserving local and remote history.

Architecture checks and publication do not activate audio experiments,
production restarts, public hosting, release tags or new learning blocks.
Existing private audio and runtime credentials remain in their original custody.
