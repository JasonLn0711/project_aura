# Versioning Rule

Project AURA uses strict semantic versioning for release tags and package metadata.

## Canonical Version Format

- Use `MAJOR.MINOR.PATCH` inside source files, for example `1.5.0`.
- Use `vMAJOR.MINOR.PATCH` only for Git tags and GitHub release names, for example `v1.5.0`.
- Never put the leading `v` inside `pyproject.toml` or `src/aura/metadata.py`.

## Required Files For Every Version Bump

Every runtime version bump must update these files together so local audit and
diagnostic provenance stay accurate:

- `pyproject.toml`: `[project].version`
- `src/aura/metadata.py`: `__version__`
- `src/aura/metadata.py`: `__date__`, using the release update date
- `uv.lock`: editable `project-aura-refactor` package version
- `README.md`: `Refactor Version` table row
- `README.md`: `Next Release Candidate` table row, using the leading-`v` form
- `README.md`: `Latest Update` heading, including version and release date

`Latest Published Tag` records the latest tag that actually exists. A prepared
working tree may therefore report a newer runtime/package version while
retaining the previous published tag; update that row only when the new tag is
created.

## Release Commit Rule

Use one dedicated version commit after all feature/fix commits are already merged:

```bash
git status --short --branch
make check PYTHON=/path/to/python
make build UV=/path/to/uv
```

Then update the required version files with the repository helper and commit:

```bash
make bump-version VERSION=X.Y.Z RELEASE_DATE=YYYY-MM-DD PYTHON=/path/to/python
git add pyproject.toml src/aura/metadata.py README.md
git commit -m "bump version to vX.Y.Z"
```

For the next semantic version, let the helper calculate the number:

```bash
make bump-version BUMP=patch RELEASE_DATE=YYYY-MM-DD PYTHON=/path/to/python
make bump-version BUMP=minor RELEASE_DATE=YYYY-MM-DD PYTHON=/path/to/python
make bump-version BUMP=major RELEASE_DATE=YYYY-MM-DD PYTHON=/path/to/python
```

`make check` validates that package metadata, runtime metadata, README release
rows, the latest-update heading, and the application footer remain synchronized.

If `RELEASE_DATE` is omitted, `scripts/bump_version.py` uses the current local date. Passing the date explicitly is preferred for reproducible release commits.

The commit message must use the tagged form, for example:

```text
bump version to v1.5.0
```

## Tagging Rule

Create the Git tag only after the version commit passes checks:

```bash
make check PYTHON=/path/to/python
make build UV=/path/to/uv
git tag -a vX.Y.Z -m "Project AURA vX.Y.Z"
git push origin main
git push origin vX.Y.Z
```

Never tag a dirty working tree. Never reuse an existing version tag.

## Version Increment Rule

- Patch bump, for example `v1.5.0` to `v1.5.1`: bug fixes, docs corrections, test-only improvements, packaging fixes.
- Minor bump, for example `v1.5.0` to `v1.6.0`: new user-visible features, new UI controls, new runtime configuration behavior.
- Major bump, for example `v1.5.0` to `v2.0.0`: incompatible workflow changes, removed features, changed output formats, or migration-required architecture changes.

When unsure, choose the smaller valid bump only if the user workflow remains compatible.
