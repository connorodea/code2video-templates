# varg previz

![three.js grey-box previz (left of each pair) and the Seedance 2.5 video-to-video result made from it](https://s3.varg.ai/files/194b94d0-58ff-4e8b-91de-4f1959d04013/file_3a16e502c737.gif)

Plan and pre-visualise a multi-shot AI video before spending credits: write the story, lock character / vehicle /
location sheets, group shots into master scenes, block every camera in a **three.js grey-box previz** on the
timeline, then export clean previz clips as `@video1` references for **Seedance 2.5 video-to-video** and generate
one short run per scene. Built on a 36-shot, 99 s anime music video and tested on a 6-shot product ad. The agent
skill is maintained in [vargHQ/skills](https://github.com/vargHQ/skills/tree/main/varg-previz)
(`npx skills add vargHQ/skills --skill varg-previz`); this folder holds the previz app and a snapshot of the references.

| path | what |
|---|---|
| `SKILL.md` | a pointer to the maintained skill in vargHQ/skills + how to run the app |
| `references/story-structure.md` | Hero's Journey, hook-problem-payoff, 3-act mapped onto song sections or seconds |
| `references/character-sheets.md` | character / product / vehicle sheets, master plates from previz renders, still QA |
| `references/scene-grouping.md` | grouping shots by location into 4–11 s runs, naming, the scene table |
| `references/threejs-previz.md` | the app: storyboard schema, auto cameras from words ("MCU, 3/4 left, push in"), sets, editing, headless checks |
| `references/seedance-v2v.md` | what v2v copies and what it does not, the prompt template, pricing, the pass-through check |
| `scripts/new_previz.py` | sets the app up in a project (`--aspect 16:9`, `--bpm`, `--audio`) |
| `templates/previz/` | the app: `index.html`, `js/` (sets, shots, props with a posable mannequin, auto cameras), `serve.py`, vendored three.js r169, `seedance/tools/` (frame capture + pack builder), a sample storyboard and the space-opera example sets |

## Quick start

```bash
python3 scripts/new_previz.py ~/videos/my-ad --aspect 9:16 --bpm 120 --audio assets/track.mp3
python3 ~/videos/my-ad/previz/serve.py          # http://localhost:8765/previz/
```

No storyboard yet → a 6-shot sample opens at once. With your `storyboard.json`, every shot gets an auto camera from
its `camera` words; fix the bad ones in the UI (`1`/`2` to frame START/END, `⌘S` to save) and export the camera
plan. Then build the Seedance pack:

```bash
cd ~/videos/my-ad/previz/seedance
python3 tools/build_pack.py --check
bun tools/capture.mjs frames "$(python3 tools/build_pack.py --plan)"   # needs playwright-core + Chrome
python3 tools/build_pack.py frames                                       # video/, requests.json, PROMPTS.md, index.html board
```

Requirements: Python 3 and a browser for the app (no npm, no build step); bun + playwright-core + Chrome for clip
capture; ffmpeg for the pack; the varg MCP or a `VARG_API_KEY` for generation (~16 credits/s at 480p).

Related: [`varg-music-video`](../varg-music-video/) (the simple path from a song to a finished clip),
[`anime-jp-subtitles`](../anime-jp-subtitles/), [`anime-triple-split`](../anime-triple-split/).
