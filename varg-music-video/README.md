# varg music video

![Highlights of "I Don't Wanna Pick" (99 s, 9:16), made with this workflow](https://s3.varg.ai/files/194b94d0-58ff-4e8b-91de-4f1959d04013/file_5e78548332d5.gif)

How to make an AI music video with varg, from a song to a finished 9:16 clip: song map → story → storyboard on
the beat grid → character/vehicle/location anchors → short Seedance scenes → QA → frame-exact cut on the song →
lyrics and graphics in HyperFrames → director rounds → export. Written from a 99 s, 36-shot anime music video
(133.8 BPM, nine rounds of director notes). This folder holds four scripts; the agent skill is maintained in
[vargHQ/skills](https://github.com/vargHQ/skills/tree/main/varg-music-video)
(`npx skills add vargHQ/skills --skill varg-music-video`), with this video as its `references/anime-case-study.md`.

| file | what |
|---|---|
| `SKILL.md` | a pointer to the maintained skill in vargHQ/skills + how to run the scripts |
| `scripts/songmap.py` | song → `songmap.json` (tempo + phase fit per 8 s window, beat_track, downbeats, optional faster-whisper words) |
| `scripts/rough_cut.py` | storyboard + `place.json` → frame-exact cut with the song (segments, slow-mo, freeze frames, tints; warns when a clip is too short) |
| `scripts/contact_sheet.sh` | timestamped contact sheet for QA of every generation and render |
| `scripts/tg_export.sh` | small H.264 copy for Telegram (99 s 1080×1920 ≈ 38 MB; `720` ≈ 15–18 MB) |

## Quick start

```bash
python3 scripts/songmap.py assets/song.mp3 --lyrics lyrics.txt --out songmap.json   # needs librosa (+ faster-whisper for words)
# write storyboard.json (shots on the grid), generate scenes with varg, then:
python3 scripts/rough_cut.py storyboard.json place.json renders/cut.mp4 --clips out/ --audio assets/song.mp3
bash scripts/contact_sheet.sh renders/cut.mp4 qa/cut.jpg 2
bash scripts/tg_export.sh renders/final_v1.mp4
```

If the music generator tells you the BPM, pass `--bpm` to `songmap.py`: only the phase is fitted then.

Related templates: [`anime-jp-subtitles`](../anime-jp-subtitles/) (Japanese captions, telop, katakana SFX) and
[`anime-triple-split`](../anime-triple-split/) (manga three-panel split). For a 3D grey-box previz and Seedance
video-to-video packs, see the `varg-previz` skill.
