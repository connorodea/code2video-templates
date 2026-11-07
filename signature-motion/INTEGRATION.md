# Integrating Signature Motion with an agentic editor

## What is available now

The package provides six local scene renderers, a discovery registry, a JSON Schema, input validation, example payloads, still previews, MP4 export, and an adjacent render result. The application adapter remains a separate integration step in your existing editor.

The original repository supports several rendering stacks and already includes Python templates. This pack follows that existing local-render path; it does not require adopting a second paid generation service. The root Varg `manifest.json` is left intact because it describes a different SDK/template contract.

## Choose by the job of the scene

| Scene intent | Template | Input the agent must have |
|---|---|---|
| Hook or strong position | `type-impact` | Two or three short headline lines, subhead, CTA |
| Evidence or quotation | `redline` | Excerpt, source label, source URL for production, supported conclusion |
| Numeric trend | `signal` | Ordered labeled values, unit, source URL for production, supported takeaway |
| Process transformation | `flow-state` | Three or four ordered steps and accurate before/after labels |
| Visual showcase | `prism` | Three labels, optionally three local images, headline and subhead |
| Title or branded interlude | `after-hours` | Two title lines, subtitle, badge and CTA |

Do not select solely from adjectives such as "premium" or "cinematic". Determine the narrative purpose and the available evidence first; then choose the visual treatment. Retain a consistent palette and brand within one film even when it uses multiple scenes.

## Suggested worker sequence

1. **Discover.** Read `templates.json` or invoke `render.py --list`. Filter by story role, required assets, aspect and available content.
2. **Populate.** Produce a complete JSON object conforming to `schema.json`. Keep text, numeric observations and source references separate from code.
3. **Validate.** Run `render.py --config request.json --validate`. Reject invalid fields and missing assets before rendering.
4. **Preview.** Render settled stills plus a reduced-size MP4. Stills catch layout defects; motion review catches late reveals, poor reading holds and awkward handoffs.
5. **Render.** Submit the CLI command to the existing background worker/queue. The renderer's stdout is machine-readable; progress and failures belong on stderr.
6. **Assemble.** Read the adjacent result JSON, then place the returned MP4 on the editor timeline. Add the parent narration, captions and licensed soundtrack in that editor.

The names `template.list`, `template.validate`, `template.preview` and `template.render` are suggested application tool names, not HTTP endpoints implemented by this repository. Bind them to the CLI inside your existing LangGraph, task queue, or other orchestration layer. Do not expose arbitrary shell text as an agent tool argument; the application should construct a fixed argv list.

## Timing and composition

Each template has its own fixed choreography scaled across the requested duration. The current input contract is not an audio cue sheet. It supports a bounded duration and integer frame rate, not automatic word alignment, beat detection or individual cue overrides. For narrated content, choose the segment length from the actual final audio, render that duration, and verify the meaningful reveal against the spoken phrase. If phrase-level alignment is required, add explicit named cue fields and validate them before promising automatic sync.

Generated clips use ordinary full-frame RGB/H.264 output. They can be placed in an editor that accepts MP4 regardless of its UI framework. The engine is Python; the React frontend can edit schema-derived controls and call a render worker. A direct React/Remotion component adapter is not included. A true alpha-overlay path needs a separate RGBA renderer and an alpha-capable codec.

There is no full-project assembly service here. Use an editorial sequence such as Type Impact → Signal → Redline → Flow State → Prism → Type Impact only when that order supports the story. A complete film should share typography and color decisions instead of alternating all six demonstration palettes.

## Evidence and assets

`demo: true` is appropriate for synthetic example copy and data and keeps a visible demo marker. For production `redline` and `signal` requests, a source label and source URL are required. Validation establishes that references are present; it cannot establish that a quotation is accurate, a numeric series is authentic, or a conclusion is supported. Perform that check upstream and retain the research record.

Signal uses a zero-based numeric axis and proportional geometry. It preserves the order of supplied observations. Equal spacing represents observation order, not elapsed time; the initial schema does not accept timestamps. Label the x-axis appropriately, or implement a separate time-aware chart when interval length matters. The same unit must apply throughout one series. The renderer does not infer statistical significance or causality.

Prism accepts local raster images. Resolve and download authorized assets through the application's existing asset service, validate their MIME type and size, and then hand the worker local paths. The renderer does not fetch URLs. Three flat images produce a 2.5D panel treatment, not new views of a real 3D object. The asset-free variant uses intentional typographic specimens.

## Reproducibility and caching

Cache by the complete validated config, referenced asset bytes, font bytes, engine revision and rendering runtime. Keep source IDs and the originating research revision alongside the edit plan. A mutable image filename or a changing URL is insufficient as a cache key. Preserve the current renderer's result metadata instead of rebuilding provenance from a display title.

Pure frame evaluation makes seeking deterministic within a pinned runtime. Cross-machine H.264 file identity additionally depends on FFmpeg build, encoder flags, font rendering and dependency versions. Pin your production container. Do not describe every render on every computer as byte-identical.

Concurrent jobs must use unique job directories or output paths. Let the parent scheduler enforce CPU/memory/concurrency quotas and cancellation. A canceled process should not publish its temporary output as a completed job. Only attach the result after the renderer has exited successfully and the final file exists.

## Production work to add in the application

The reference-led layer is documented in `REVERSE-ENGINEERING.md` and `motion-recipes.json`. Those seven recipes are explicitly design-only and must not be advertised by the live renderer registry. They add shot roles, asset matching, focal regions, continuity and reveal timing to the six implemented primitives. Preserve this distinction in the UI: executable templates can render now; design recipes require the stated capabilities and suitable assets.

The concrete next integration is a template picker, a schema-driven property form, a queued worker invocation and a preview attached to the edit timeline. Reuse the current project asset registry, authorization, job ledger and caption/audio pipeline. That gives these templates a place in the editing product without creating another project system.

Useful subsequent capabilities are explicit narration/beat cues, variable-font and multilingual layout tests, per-platform masks, video input for Prism, transparent overlays, reusable source mappings, and automatic readable-hold checks. These are proposed next steps, not shipped features.
