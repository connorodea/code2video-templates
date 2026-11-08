# Asset provenance and dependencies

## Demonstration content

The example's city backgrounds, route diagrams, telemetry, transitions, music
and effects are generated locally from the template's code and seed. Narration
text is original demonstration copy, voiced with the installed Flite SLT voice.
No downloaded gameplay, Rockstar logos, soundtrack recordings, stock footage,
or reference-video material is bundled. GTA identifies the intended subject of
the future channel; this template does not imply endorsement by Rockstar Games.

Routes, distances, signal levels and checkpoints in the example are synthetic
demonstration values. They are not measurements or claims about a GTA game.

This template uses the repository's template/agent conventions. It does not
copy the Cut30 style-kit assets from `agent-video-style-kit/`; that template's
separate attribution and license remain with its own files.

The template source and documentation follow the repository's root
[`LICENSE`](../LICENSE). External software and fonts retain their own terms.

## Locally installed dependencies

Dependencies and font binaries are not redistributed in this template. The
following upstream notices identify the components used by the local render:

| Component | Use | Upstream notice |
| --- | --- | --- |
| Python | Renderer and handoff CLI | [Python license](https://docs.python.org/3/license.html) |
| Pillow | Images, typography and compositing | [Pillow license](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| NumPy | Local signal generation and image/audio measurements | [NumPy license](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| jsonschema | Structured input validation | [jsonschema license](https://github.com/python-jsonschema/jsonschema/blob/main/COPYING) |
| FFmpeg | Encoding, decoding, probing and audio conversion | [FFmpeg legal and build license information](https://ffmpeg.org/legal.html) |
| Flite / SLT | Local demonstration narration and native speech timing | [Flite notices](https://github.com/festvox/flite/blob/master/COPYING) |
| DejaVu Sans | Default regular and bold fonts | [DejaVu font notices](https://dejavu-fonts.github.io/License.html) |

FFmpeg's applicable terms depend on its build configuration. Font and Flite
libraries are discovered on the rendering computer; retain their upstream
notices when redistributing those dependencies. The manifest records the fonts
and software versions actually used in a completed render.

## User-supplied assets

Each external background and narration input requires `license` and `credit`
fields in the scene specification. These fields document the user's statement;
the renderer does not independently verify ownership or grant rights. Use
synthetic inputs until appropriate footage and narration have been supplied.
Do not insert third-party music or reference-video clips merely because they
are publicly viewable. Source paths and hashes are recorded in the manifest.

Deepgram and Claude are integration boundaries: this pilot reads a local JSON
specification and local timestamp data. No response, voice, or media is fetched
from either service by the renderer.

## Interchange references

The handoff writer follows the documented Final Cut Pro 7 XML structure and
provides local media for editing in DaVinci Resolve:

- [Apple FCP7 XML element catalog](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/Elements/Elements.html)
- [Apple FCP7 XML DTD reference](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/FinalCutPro_XML/DTD/DTD.html)
- [Blackmagic Resolve Colorist Guide](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Colorist-Guide.pdf), “Conforming an XML Timeline”
- [Blackmagic Resolve editing and subtitle features](https://www.blackmagicdesign.com/products/davinciresolve/edit)

These are implementation references, not a claim that the generated timeline
has been imported or certified in Resolve. A completed application import must
be verified separately.
