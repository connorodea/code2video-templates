---
name: signature-motion
description: Render six local motion templates from validated JSON, including kinetic type, source excerpts, numeric trends, workflow transformations, dimensional panels and iris titles. Use when an agent needs reusable full-frame video scenes or editable branded short videos. Not for generating footage, transcribing speech, automatic beat sync, alpha overlays or publishing a finished campaign.
---

# Signature Motion

Read `templates.json` and choose by the scene's narrative purpose. Read the selected example and `schema.json` before creating inputs. Use `CONCEPTS.md` only when proposing additional designs; its twelve future concepts are not executable templates.

For reference-led planning, read `REVERSE-ENGINEERING.md` and `motion-recipes.json`. All seven advanced recipes are design-only. `references.json` records the evidence and inspection limits. `inspect_reference.py` can sample an already-local video into timestamped frames; it does not establish cut boundaries, sound design, or causal performance.

## Render

1. Keep each request in its own job directory. Copy the relevant example, then fill its fields from the user's actual brief and authorized assets. Follow schema limits; do not silently truncate text or fabricate evidence.
2. Preserve `demo: true` for synthetic example content. For real Redline/Signal material, supply the source label and URL and independently verify that the excerpt/series and conclusion match that source. A URL passing validation is not factual verification.
3. Use `python3 render.py --config /absolute/path/request.json --validate`. Fix input errors before starting the render. Resolve Prism image paths relative to the config file; images must already exist locally.
4. Render a still with `--still /absolute/path/frame.png --time 5`. For motion review, use the preview option shown by `python3 render.py --help`. Inspect actual readable states and transitions; check the final target aspect ratio.
5. Run `python3 render.py --config /absolute/path/request.json --out /absolute/path/video.mp4` in the parent's background render worker. Do not block the user's interaction during a long render. Supply `--audio /absolute/path/track.wav` only for an authorized track; otherwise leave audio to the parent editor.
6. Require a successful process exit and the actual completed MP4 before declaring success. Preserve the adjacent result JSON. Report the output location, dimensions, duration and any limitation relevant to the requested edit.

Use the existing local font and its OFL notice. For a custom font, set `SIGNATURE_MOTION_FONT` to its local file and retain its license. Never commit generated media or caches.

## Integration boundaries

Use a fixed CLI argv list or the frame function documented in README. Agents edit validated JSON; they do not generate arbitrary executable code for routine variations. The six templates render clips; they do not connect themselves to an external editing application.

Keep dialogue at its intended speed and integrate captions upstream. The current renderer scales each built-in choreography to the clip duration. Phrase/beat cue overrides, transparent output, video-backed panels and native editor projects are not implemented. See `INTEGRATION.md` for timing, source semantics and runtime pinning.
