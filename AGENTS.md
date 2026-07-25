# Project AURA Agent Instructions

## README Contract

- Treat the root `README.md` as a comprehensive product and operator entry
  point. Preserve enough detail for a new user to understand the product,
  install it, operate it, inspect its artifacts, verify its claims, and find
  deeper documentation.
- Write every rendered README heading, paragraph, table label, image alt text,
  and figure caption in English. Preserve exact commands, identifiers, model
  tags, file names, and source quotations when precision requires them.
- Place a concise italicized caption immediately after every product
  screenshot, diagram, or illustration. State what the figure shows and why it
  matters to the user.
- Use a confident, generous, affirmative release voice. Organize prose around
  capability, evidence, ownership, active operating scope, stewardship, and
  the next validation layer.
- Present scope boundaries as supported runtime contracts, activation gates,
  validation paths, and future work packages. Keep exact safety, privacy,
  credential, and runtime status language wherever precision controls risk.
- Optimize duplication and chronology while retaining operational depth.
  Release history belongs in GitHub Releases, design rationale belongs in
  `docs/`, and measured runtime evidence belongs in `artifacts/`; the README
  links each source from the relevant product section.
- Keep the stable section order declared in the README source comment. Add a
  section only when the new content has durable user or maintainer value.
- Preserve these exact release synchronization surfaces:
  `Refactor Version`, `Latest Published Tag`, `Next Release Candidate`, and
  `## Latest Update — vX.Y.Z (YYYY-MM-DD)`.
- Validate every relative link and image path from the repository root after
  each README edit.

## Claim And Validation Contract

- Separate implemented capability, live runtime evidence, release status, and
  next-stage validation.
- Use measured counts and runtime classifications from the canonical packet in
  `artifacts/`; refresh drift-prone status before publication.
- Run `git diff --check`, the focused versioning tests, README link and image
  checks, and the full regression suite after a material README revision.
- Preserve unrelated working-tree changes and generated local data.
