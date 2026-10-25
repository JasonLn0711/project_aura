# AURA C4 architecture packet

This packet contains rendered architecture documentation, not a new ASR
experiment. The [English guide](../../docs/architecture/c4/README.md) explains
browsing, rebuilding and runtime boundaries; the
[view catalog](../../docs/architecture/c4/view-catalog.md) links every SVG/PNG.

The [source and closeout record](../../docs/audit-events/2026-10-18-c4-architecture/audit-event.md)
connects the original request, selected decisions, FIRST PRINCIPLE ownership
and Planning publication receipt. [Publication checks](publication-checks.json)
verify the refreshed render and preserve references to the original packet in
Git. The manifest's `source_revision` identifies the checked-out commit at build
time; `architecture_sources` seals the actual model and tool inputs rendered from
that working tree. The Planning day receipt identifies the source-publication
commits. Browser/publication receipts are produced after rendering and remain
separate from the rendered-output hash seal.

- `images/`: complete C1–C4, dynamic and deployment images, plus renderer keys.
- `workspace.json`: parsed Structurizr model with generated layouts and code views.
- `source-coverage.json`: complete application/native/resource ownership and
  supporting setup, packaging and CI files.
- `manifest.json`: source revision, architecture/application source hashes,
  tool versions, view inventory and output hashes.
- `validation.json`: actual source, browser, documentation and regression checks.
- `site/`: generated, ignored, portable interactive viewer with local assets.

Run `make architecture-build` to regenerate the viewer and
`make architecture-serve` to browse it at `http://127.0.0.1:18080/`. The portable
ZIP is written to ignored `dist/aura-c4-architecture.zip`.

Coverage and code declarations come from syntax inspection without importing
AURA or loading models. Browser tests exercise all views, zoom, drill-down,
quick navigation, nonlocal-request rejection and foreground-server shutdown.
Visual review is recorded separately in the validation receipt.

The runtime claims still belong to the
[RE-USE availability packet](../reuse-speech-guard-2026-10-18/README.md).
Architecture render success establishes documentation/tool availability only.
Private audio, transcripts, connection credentials, model weights, downloaded
binaries and detailed tool logs are not included in this tracked packet.

## October 25 Nemotron integration refresh

The current render includes default-on Nemotron and 77 mapped source files
across 30 views. The October 18 validation and publication-check JSON files remain
historical receipts; the current source seal and browser check are in
`manifest.json` and `browser-validation.json`. The [Nemotron publication checks](../nemotron/README.md#combined-code-checks)
record combined-code regression and the distinction between measured runtime and
pending combined RE-USE/Nemotron live acceptance.
