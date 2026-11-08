"""Deterministic local graphics for the GTA production pilot.

All pixels are procedural or drawn with licensed local fonts. Scene copy, palette,
font paths, frame rate and layout come from the validated JSON specification.
RGB footage and straight-alpha graphics are deliberately rendered separately.
"""
from __future__ import annotations

from bisect import bisect_right
from functools import lru_cache
from pathlib import Path
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from captions import chunk_words


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def _ease(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return 1 - (1 - value) ** 3


def _groups(words, max_words, gap_seconds):
    """Use the same phrase boundaries as the editable SRT sidecar."""
    if not words:
        return []
    return [cue["words"] for cue in chunk_words(words, max_words, gap_seconds)]


class FrameRenderer:
    """Reusable PIL renderer. Each method returns an independent image."""

    def __init__(self, spec: dict, config_dir: Path):
        self.spec = spec
        self.config_dir = Path(config_dir)
        video, style = spec["video"], spec["style"]
        self.w, self.h = int(video["width"]), int(video["height"])
        self.fps = int(video["fps"])
        self.duration = int(video["duration_frames"])
        self.portrait = self.h > self.w
        self.s = min(self.w, self.h) / 1080
        self.margin = float(style.get("safe_margin", .055))
        self.mx, self.my = round(self.w * self.margin), round(self.h * self.margin)
        self.bg = _rgb(style["background"])
        self.fg = _rgb(style["foreground"])
        self.accent = _rgb(style["accent"])
        self.secondary = _rgb(style["secondary"])
        self.muted = _rgb(style["muted"])
        self.scenes = spec["scenes"]
        self.starts = [scene["start_frame"] for scene in self.scenes]
        self.font_paths = {}
        for name, filename in (("regular", "DejaVuSans.ttf"), ("bold", "DejaVuSans-Bold.ttf")):
            supplied = style.get("font_" + name)
            path = (self.config_dir / supplied).resolve() if supplied else Path("/usr/share/fonts/truetype/dejavu") / filename
            if not path.is_file():
                raise ValueError(f"Font not found: {path}; set style.font_{name} to a local TTF/OTF file")
            self.font_paths[name] = str(path)
        self._measure = ImageDraw.Draw(Image.new("L", (1, 1)))
        self._layouts = [self._scene_layout(scene) for scene in self.scenes]
        self._background = self._build_background()
        self._caption_source = None
        self._caption_groups = []
        self._caption_starts = []
        self._last_frame = None
        self._last_graphics = None

    @lru_cache(maxsize=96)
    def _font(self, size: int, bold: bool = False):
        return ImageFont.truetype(self.font_paths["bold" if bold else "regular"], max(7, size))

    def _px(self, value: float) -> int:
        return max(1, round(value * self.s))

    def _text_width(self, text: str, font) -> float:
        return self._measure.textlength(text, font=font)

    def _wrap(self, text: str, font, width: float) -> list[str]:
        lines = []
        for paragraph in str(text).split("\n"):
            current = ""
            for word in paragraph.split():
                if self._text_width(word, font) > width:
                    raise ValueError(f"Text contains a word wider than its safe area: {word!r}")
                candidate = f"{current} {word}" if current else word
                if current and self._text_width(candidate, font) > width:
                    lines.append(current)
                    current = word
                else:
                    current = candidate
            lines.append(current)
        return lines

    def _fit(self, text, size, width, max_lines, min_size):
        # Prefer the author's explicit line breaks; only add a line when even
        # the minimum readable size cannot preserve that composition.
        preferred = min(max_lines, max(2, len(str(text).split("\n"))))
        for allowed_lines in range(preferred, max_lines + 1):
            for candidate in range(round(size), round(min_size) - 1, -1):
                font = self._font(candidate, True)
                try:
                    lines = self._wrap(text, font, width)
                except ValueError:
                    continue
                if len(lines) <= allowed_lines:
                    return font, lines, candidate
        raise ValueError(f"Title cannot fit in {max_lines} safe lines: {text!r}")

    def _scene_layout(self, scene):
        x = self.mx
        top = round(self.h * (.185 if self.portrait else .22))
        width = self.w - 2 * self.mx if self.portrait else self.w * .45
        title_size = self._px(124 if self.portrait else 140)
        font, lines, title_size = self._fit(scene["title"], title_size, width, 3, self._px(68))
        leading = round(title_size * 1.05)
        title_end = top + leading * len(lines)
        subtitle_font = self._font(self._px(28 if self.portrait else 27))
        subtitles = self._wrap(scene.get("subtitle", ""), subtitle_font, width * .98)
        subtitle_y = title_end + self._px(33)
        subtitle_end = subtitle_y + len(subtitles) * self._px(40)
        title_limit = self.h * (.425 if self.portrait else .72)
        if subtitle_end > title_limit:
            raise ValueError(f"Scene {scene['id']!r} title/subtitle exceeds the safe title area; shorten the copy")
        kicker_font = self._font(self._px(18), True)
        kicker = str(scene.get("kicker", ""))
        if self._text_width(kicker, kicker_font) > width:
            raise ValueError(f"Scene {scene['id']!r} kicker exceeds the safe title area")
        if self.portrait:
            card = (self.mx, round(self.h * .48), self.w - self.mx, round(self.h * .745))
        else:
            card = (round(self.w * .545), round(self.h * .215), self.w - self.mx, round(self.h * .745))
        return dict(x=x, top=top, width=width, font=font, lines=lines,
                    leading=leading, subtitle_font=subtitle_font, subtitles=subtitles,
                    subtitle_y=subtitle_y, kicker_font=kicker_font, card=card)

    def _check_frame(self, frame):
        if not isinstance(frame, int) or frame < 0 or frame >= self.duration:
            raise ValueError(f"Frame must be an integer in [0, {self.duration - 1}]")

    def _scene_index(self, frame):
        return max(0, bisect_right(self.starts, frame) - 1)

    def _build_background(self):
        """Cache the original skyline and lighting; moving road is added per frame."""
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        nx, ny = xx / self.w, yy / self.h
        glow = np.exp(-(((nx - .77) / .39) ** 2 + ((ny - .46) / .23) ** 2)) * .23
        darken = .78 + .22 * nx
        arr = np.empty((self.h, self.w, 3), dtype=np.uint8)
        for c in range(3):
            arr[:, :, c] = np.clip(self.bg[c] * darken + self.accent[c] * glow, 0, 255)
        base = Image.fromarray(arr)
        draw = ImageDraw.Draw(base)
        horizon = round(self.h * (.57 if self.portrait else .54))
        vx = round(self.w * (.62 if self.portrait else .75))
        rng = random.Random(int(self.spec["project"].get("seed", 7)))
        # The grid and silhouetted block forms intentionally read as a synthetic set.
        for layer in range(3):
            x = -self._px(40)
            while x < self.w + self._px(80):
                bw = self._px(rng.randrange(35, 104))
                bh = self._px(rng.randrange(60, 255)) * (.55 + .22 * layer)
                y = horizon - round(bh)
                fill = _mix(self.bg, self.accent, .025 + .018 * layer)
                edge = _mix(self.bg, self.accent, .07 + .028 * layer)
                draw.rectangle((x, y, x + bw, horizon), fill=fill)
                draw.line((x, horizon, x, y, x + bw, y), fill=edge, width=self._px(1))
                if layer == 2:
                    for wy in range(y + self._px(16), horizon - self._px(12), self._px(21)):
                        for wx in range(x + self._px(12), x + bw - self._px(8), self._px(17)):
                            if rng.random() > .64:
                                draw.rectangle((wx, wy, wx + self._px(3), wy + self._px(5)), fill=_mix(self.bg, self.secondary, rng.uniform(.16, .33)))
                x += bw + self._px(rng.randrange(8, 24))
        ground = _mix(self.bg, (0, 0, 0), .12)
        draw.rectangle((0, horizon, self.w, self.h), fill=ground)
        # Road fans out from the vanishing point; teal edge lights echo route graphics.
        road_l, road_r = self.w * .31, self.w * 1.18
        draw.polygon([(vx - self._px(11), horizon), (vx + self._px(11), horizon), (road_r, self.h), (road_l, self.h)], fill=_mix(self.bg, (0, 0, 0), .37))
        for endpoint in (road_l, road_l - self.w * .035, road_r, road_r + self.w * .035):
            draw.line((vx, horizon, endpoint, self.h), fill=_mix(self.bg, self.accent, .16), width=self._px(2))
        # Architectural side-grid, drawn as deliberately abstract design geometry.
        for k in range(13):
            endpoint = -self.w * .9 + k * self.w * .24
            draw.line((vx, horizon, endpoint, self.h), fill=_mix(self.bg, self.accent, .055), width=self._px(1))
        # Fade the left side to give type and externally supplied media clear contrast.
        shade = Image.new("RGBA", (self.w, self.h))
        alpha = np.clip((1 - nx) ** 1.8 * (85 if not self.portrait else 32), 0, 255).astype(np.uint8)
        shade.putalpha(Image.fromarray(alpha))
        return Image.alpha_composite(base.convert("RGBA"), shade).convert("RGB")

    def render_background(self, frame_index: int) -> Image.Image:
        self._check_frame(frame_index)
        image = self._background.copy()
        draw = ImageDraw.Draw(image)
        t = frame_index / self.fps
        horizon = self.h * (.57 if self.portrait else .54)
        vx = self.w * (.62 if self.portrait else .75)
        # Perspective motion is continuous across scenes, with no hidden random state.
        for k in range(17):
            depth = ((k / 17 + t * .18) % 1) ** 2
            y = horizon + depth * (self.h - horizon)
            draw.line((0, y, self.w, y), fill=_mix(self.bg, self.accent, .035 + depth * .07), width=self._px(1))
        for lane in (.53, .75, .97):
            for k in range(11):
                d0 = (k / 11 + t * .25) % 1
                d1 = min(1.0, d0 + .033)
                p0, p1 = d0 ** 2, d1 ** 2
                x0, x1 = vx + (self.w * lane - vx) * p0, vx + (self.w * lane - vx) * p1
                y0, y1 = horizon + (self.h - horizon) * p0, horizon + (self.h - horizon) * p1
                draw.line((x0, y0, x1, y1), fill=_mix(self.bg, self.fg, .12 + p0 * .12), width=max(1, round(3 * self.s * p0)))
        for k, lane in enumerate((.42, .63, .86, 1.08)):
            depth = (.23 + (k * .231 + t * .052) % .7) ** 1.65
            cx = vx + (self.w * lane - vx) * depth
            cy = horizon + (self.h - horizon) * depth
            car_w, car_h = max(3, self._px(57) * depth), max(5, self._px(100) * depth)
            draw.rounded_rectangle((cx - car_w / 2, cy - car_h, cx + car_w / 2, cy), radius=max(1, car_w * .16), fill=_mix(self.bg, self.fg, .11), outline=_mix(self.bg, self.accent, .25), width=1)
            draw.line((cx - car_w * .34, cy - car_h * .12, cx - car_w * .1, cy - car_h * .12), fill=self.secondary, width=max(1, round(self.s * depth * 4)))
            draw.line((cx + car_w * .1, cy - car_h * .12, cx + car_w * .34, cy - car_h * .12), fill=self.secondary, width=max(1, round(self.s * depth * 4)))
        return image

    def _text(self, draw, xy, text, font, fill):
        # 'lt' anchors ink, avoiding font-specific ascender offsets in safe-zone math.
        draw.text((round(xy[0]), round(xy[1])), text, font=font, fill=fill, anchor="lt")

    def _card(self, draw, box):
        x0, y0, x1, y1 = box
        draw.rounded_rectangle(box, radius=self._px(22), fill=(*self.bg, 215), outline=(*self.muted, 52), width=self._px(1))
        draw.line((x0 + self._px(25), y0 + self._px(2), x0 + self._px(115), y0 + self._px(2)), fill=(*self.accent, 255), width=self._px(3))

    def _route(self, draw, box, progress, points):
        self._card(draw, box)
        x0, y0, x1, y1 = box
        pad = self._px(43)
        self._text(draw, (x0 + pad, y0 + self._px(30)), "ROUTE / CONCEPT MAP", self._font(self._px(17), True), self.muted)
        top, bottom = y0 + self._px(92), y1 - self._px(65)
        left, right = x0 + pad, x1 - pad
        for k in range(9):
            x = left + (right - left) * k / 8
            draw.line((x, top, x, bottom), fill=(*self.muted, 30), width=self._px(1))
        for k in range(6):
            y = top + (bottom - top) * k / 5
            draw.line((left, y, right, y), fill=(*self.muted, 30), width=self._px(1))
        pts = [(left + p[0] * (right - left), top + p[1] * (bottom - top)) for p in points]
        draw.line(pts, fill=(*self.muted, 80), width=self._px(6), joint="curve")
        lengths = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
        remaining = sum(lengths) * min(1.0, max(0.0, progress))
        cursor = pts[0]
        for a, b, length in zip(pts, pts[1:], lengths):
            amount = min(1.0, remaining / length) if length else 1
            cursor = (a[0] + (b[0] - a[0]) * amount, a[1] + (b[1] - a[1]) * amount)
            if amount > 0:
                draw.line((a, cursor), fill=(*self.accent, 255), width=self._px(6))
            remaining -= length
            if remaining <= 0:
                break
        for i, (x, y) in enumerate((pts[0], pts[-1])):
            r = self._px(9)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(*self.bg, 255), outline=(*(self.accent if i == 0 else self.secondary), 255), width=self._px(3))
        r = self._px(7)
        draw.ellipse((cursor[0] - r, cursor[1] - r, cursor[0] + r, cursor[1] + r), fill=(*self.fg, 255))
        self._text(draw, (left, y1 - self._px(39)), "A  /  START", self._font(self._px(15), True), self.accent)
        end_label = "B  /  NEXT TURN"
        self._text(draw, (right - self._text_width(end_label, self._font(self._px(15), True)), y1 - self._px(39)), end_label, self._font(self._px(15), True), self.secondary)

    def _telemetry(self, draw, box, progress, metrics, frame):
        self._card(draw, box)
        x0, y0, x1, y1 = box
        pad = self._px(38)
        width = x1 - x0 - 2 * pad
        self._text(draw, (x0 + pad, y0 + self._px(30)), "SIGNAL / DEMONSTRATION DATA", self._font(self._px(16), True), self.muted)
        row_y = y0 + self._px(100)
        cell_w = width / max(1, len(metrics))
        for i, metric in enumerate(metrics):
            x = x0 + pad + i * cell_w
            value = metric["value"]
            if isinstance(value, (int, float)):
                number = value * _ease(progress * 2.8)
                text = f"{number:.1f}" if isinstance(value, float) and not value.is_integer() else f"{round(number):d}"
            else:
                text = str(value)
            font = self._font(self._px(64 if len(metrics) <= 3 else 45), True)
            self._text(draw, (x, row_y), text, font, self.fg)
            self._text(draw, (x, row_y + self._px(82)), str(metric.get("unit", "")), self._font(self._px(20), True), self.accent)
            label_font = self._font(self._px(13), True)
            labels = self._wrap(str(metric["label"]), label_font, cell_w - self._px(10))
            for j, label in enumerate(labels):
                self._text(draw, (x, row_y + self._px(122 + 18 * j)), label, label_font, self.muted)
        wave_top = row_y + self._px(194)
        wave_bottom = y1 - self._px(49)
        if wave_bottom > wave_top:
            mid = (wave_top + wave_bottom) / 2
            for k in range(4):
                y = wave_top + (wave_bottom - wave_top) * k / 3
                draw.line((x0 + pad, y, x1 - pad, y), fill=(*self.muted, 32), width=self._px(1))
            points = []
            for k in range(121):
                phase = k / 120
                signal = math.sin(phase * 22 - frame * .07) * .51 + math.sin(phase * 47 + frame * .035) * .23
                points.append((x0 + pad + width * phase, mid + signal * (wave_bottom - wave_top) * .46))
            draw.line(points, fill=(*self.accent, 255), width=self._px(3), joint="curve")

    def _orbital(self, draw, box, progress, frame, outro=False):
        x0, y0, x1, y1 = box
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        radius = min(x1 - x0, y1 - y0) * .37
        for i in range(4):
            r = radius * (.48 + i * .19)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(*self.muted, 34 + i * 8), width=self._px(1))
        start = -90 + frame * .12
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=start, end=start + 260 * _ease(progress * 2), fill=(*self.accent, 255), width=self._px(4))
        inner = radius * .67
        draw.arc((cx - inner, cy - inner, cx + inner, cy + inner), start=180 - start, end=350 - start, fill=(*self.secondary, 220), width=self._px(2))
        for angle in range(0, 360, 15):
            a = math.radians(angle)
            r0 = radius * 1.12
            r1 = radius * (1.19 if angle % 45 == 0 else 1.15)
            draw.line((cx + math.cos(a) * r0, cy + math.sin(a) * r0, cx + math.cos(a) * r1, cy + math.sin(a) * r1), fill=(*self.muted, 110), width=self._px(1))
        r = radius * .34
        draw.polygon([(cx - r * .62, cy - r), (cx + r, cy), (cx - r * .62, cy + r)], outline=(*self.fg, 240), width=self._px(3))
        if outro:
            draw.line((cx - radius * .9, cy + radius * 1.34, cx + radius * .9, cy + radius * 1.34), fill=(*self.accent, 210), width=self._px(2))

    def _scene_graphics(self, scene_index, frame):
        scene, layout = self.scenes[scene_index], self._layouts[scene_index]
        image = Image.new("RGBA", (self.w, self.h))
        draw = ImageDraw.Draw(image)
        local = max(0, frame - scene["start_frame"])
        progress = local / max(1, scene["duration_frames"] - 1)
        entrance = _ease(local / max(1, round(self.fps * .65)))
        dx = round((1 - entrance) * self._px(-36))
        # A light scrim supports legibility when a real gameplay clip is substituted.
        if self.portrait:
            draw.rounded_rectangle((self.mx - self._px(22), layout["top"] - self._px(77), self.w - self.mx + self._px(22), layout["subtitle_y"] + len(layout["subtitles"]) * self._px(40) + self._px(18)), radius=self._px(12), fill=(*self.bg, 155))
        else:
            draw.rounded_rectangle((self.mx - self._px(24), layout["top"] - self._px(74), layout["x"] + layout["width"] + self._px(16), layout["subtitle_y"] + len(layout["subtitles"]) * self._px(40) + self._px(20)), radius=self._px(12), fill=(*self.bg, 155))
        x, y = layout["x"] + dx, layout["top"]
        self._text(draw, (x, y - self._px(58)), scene.get("kicker", ""), layout["kicker_font"], self.accent)
        for i, line in enumerate(layout["lines"]):
            line_shift = round((1 - _ease(max(0, local - i * 3) / max(1, self.fps * .55))) * self._px(20))
            color = self.fg if i == 0 else self.accent
            self._text(draw, (x, y + i * layout["leading"] + line_shift), line, layout["font"], color)
        for i, line in enumerate(layout["subtitles"]):
            self._text(draw, (x, layout["subtitle_y"] + i * self._px(40)), line, layout["subtitle_font"], self.muted)
        if scene["kind"] == "route":
            self._route(draw, layout["card"], _ease(progress * 1.12), scene["route"])
        elif scene["kind"] == "telemetry":
            self._telemetry(draw, layout["card"], progress, scene.get("metrics", []), frame)
        else:
            self._orbital(draw, layout["card"], progress, frame, scene["kind"] == "outro")
        return image

    def _chrome(self, image, frame):
        draw = ImageDraw.Draw(image)
        small = self._font(self._px(15), True)
        top = self.my
        label = "DEMONSTRATION / CONCEPT" if self.spec["project"].get("demo", False) else self.spec["project"]["title"]
        self._text(draw, (self.mx, top), label, small, self.muted)
        right = f"{self.w} × {self.h}  /  {self.fps} FPS"
        self._text(draw, (self.w - self.mx - self._text_width(right, small), top), right, small, self.muted)
        # Quiet editorial frame lines; progress uses the exact integer timeline.
        y = self.h - self.my
        draw.line((self.mx, y, self.w - self.mx, y), fill=(*self.muted, 65), width=self._px(1))
        length = self.w - 2 * self.mx
        draw.line((self.mx, y, self.mx + length * ((frame + 1) / self.duration), y), fill=(*self.accent, 255), width=self._px(3))
        footer_font = self._font(self._px(14), True)
        count = self._scene_index(frame)
        left = f"{count + 1:02d} / {len(self.scenes):02d}"
        self._text(draw, (self.mx, y - self._px(30)), left, footer_font, self.muted)
        timecode = f"{frame // (self.fps * 60):02d}:{(frame // self.fps) % 60:02d}:{frame % self.fps:02d}"
        self._text(draw, (self.w - self.mx - self._text_width(timecode, footer_font), y - self._px(30)), timecode, footer_font, self.muted)

    def _prepare_captions(self, words):
        if words is self._caption_source:
            return
        self._caption_source = words
        options = self.spec.get("captions", {})
        self._caption_groups = _groups(words, int(options.get("max_words", 4)), float(options.get("gap_seconds", .45)))
        self._caption_starts = [float(group[0]["start"]) for group in self._caption_groups]

    def _caption_layout(self, group):
        font = self._font(self._px(39 if self.portrait else 37), True)
        space = self._text_width(" ", font)
        width = self.w - 2 * self.mx - self._px(46)
        lines, current, current_width = [], [], 0.0
        for word in group:
            measured = self._text_width(str(word["word"]), font)
            if measured > width:
                raise ValueError(f"Caption word exceeds safe area: {word['word']!r}")
            total = current_width + (space if current else 0) + measured
            if current and total > width:
                lines.append((current, current_width))
                current, current_width = [], 0.0
            if current:
                current_width += space
            current.append((word, measured))
            current_width += measured
        if current:
            lines.append((current, current_width))
        max_lines = int(self.spec.get("captions", {}).get("max_lines", 2))
        if len(lines) > max_lines:
            raise ValueError(f"Caption phrase exceeds {max_lines} safe lines: {' '.join(str(w['word']) for w in group)!r}")
        return font, space, lines

    def _captions(self, image, frame, words):
        self._prepare_captions(words)
        if not self._caption_groups:
            return
        t = frame / self.fps
        index = bisect_right(self._caption_starts, t) - 1
        if index < 0:
            return
        group = self._caption_groups[index]
        # Hold the phrase through its short interword pauses, without highlighting
        # a word during silence. Long pauses split cues in captions.chunk_words.
        # Half-open intervals keep cue and highlight endpoints frame-accurate.
        if not float(group[0]["start"]) <= t < float(group[-1]["end"]):
            return
        font, space, lines = self._caption_layout(group)
        draw = ImageDraw.Draw(image)
        leading = self._px(57)
        center = self.h * float(self.spec["style"].get("caption_y", .84))
        y = round(center - (len(lines) * leading) / 2)
        for entries, width in lines:
            x = round((self.w - width) / 2)
            pad = self._px(18)
            draw.rounded_rectangle((x - pad, y - self._px(11), x + width + pad, y + self._px(45)), radius=self._px(10), fill=(*self.bg, 240))
            for word, word_width in entries:
                active = float(word["start"]) <= t < float(word["end"])
                self._text(draw, (x, y), str(word["word"]), font, self.accent if active else self.fg)
                x += word_width + space
            y += leading

    def render_graphics(self, frame_index: int, words: list, include_captions: bool = True) -> Image.Image:
        self._check_frame(frame_index)
        if frame_index != self._last_frame:
            index = self._scene_index(frame_index)
            scene = self.scenes[index]
            current = self._scene_graphics(index, frame_index)
            local = frame_index - scene["start_frame"]
            transition_frames = scene.get("transition_frames", 0)
            if index and transition_frames and local < transition_frames:
                previous = self._scene_graphics(index - 1, scene["start_frame"] - 1)
                amount = (local + 1) / transition_frames
                if scene.get("transition_in") == "dissolve":
                    current = Image.blend(previous, current, _ease(amount))
                elif scene.get("transition_in") == "wipe":
                    cut = round(self.w * _ease(amount))
                    previous.paste(current.crop((0, 0, cut, self.h)), (0, 0))
                    draw = ImageDraw.Draw(previous)
                    if cut < self.w:
                        draw.rectangle((max(0, cut - self._px(4)), 0, cut, self.h), fill=(*self.accent, 255))
                    current = previous
            self._chrome(current, frame_index)
            self._last_graphics = current
            self._last_frame = frame_index
        result = self._last_graphics.copy()
        if include_captions:
            self._captions(result, frame_index, words)
        return result

    def validate_layout(self, words: list) -> list[str]:
        """Fail visibly on unsupported text, rather than silently clipping an export."""
        self._prepare_captions(words)
        caption_y = self.h * float(self.spec["style"].get("caption_y", .84))
        for group in self._caption_groups:
            _, _, lines = self._caption_layout(group)
            half_height = len(lines) * self._px(57) / 2 + self._px(16)
            if caption_y - half_height < self.my or caption_y + half_height > self.h - self.my - self._px(42):
                raise ValueError("Caption position or phrase height overlaps the frame/footer safe area")
        small = self._font(self._px(15), True)
        metadata = "DEMONSTRATION / CONCEPT" if self.spec["project"].get("demo", False) else self.spec["project"]["title"]
        right = f"{self.w} × {self.h}  /  {self.fps} FPS"
        if self._text_width(metadata, small) + self._text_width(right, small) + self._px(30) > self.w - 2 * self.mx:
            raise ValueError("Project title is too long for the metadata safe area")
        for scene, layout in zip(self.scenes, self._layouts):
            if scene["kind"] == "telemetry":
                metrics = scene.get("metrics", [])
                width = layout["card"][2] - layout["card"][0] - self._px(76)
                cell = width / max(1, len(metrics)) - self._px(10)
                for metric in metrics:
                    value_font = self._font(self._px(64 if len(metrics) <= 3 else 45), True)
                    if self._text_width(str(metric["value"]), value_font) > cell:
                        raise ValueError(f"Telemetry value does not fit: {metric['value']!r}")
                    if self._text_width(str(metric.get("unit", "")), self._font(self._px(20), True)) > cell:
                        raise ValueError(f"Telemetry unit does not fit: {metric.get('unit')!r}")
                    lines = self._wrap(str(metric["label"]), self._font(self._px(13), True), cell)
                    if len(lines) > 2:
                        raise ValueError(f"Telemetry label needs more than two lines: {metric['label']!r}")
        return [f"Validated {len(self.scenes)} scene layouts and {len(self._caption_groups)} caption phrases at {self.w}x{self.h}"]
