"""Three original, frame-pure motion directions.

Only the supplied frame index changes a composition. Static surfaces are cached;
the cache is an optimization and never holds animation state. Asset paths are
resolved and checked at the worker boundary in validation.py.
"""
from __future__ import annotations

from functools import lru_cache
import math

from PIL import Image, ImageDraw, ImageOps

from .style import clamp, ease, font, footer, mix, rgb, text, wrap


def _color_mix(first, second, amount):
    a = rgb(first) if isinstance(first, str) else first
    b = rgb(second) if isinstance(second, str) else second
    return tuple(round(mix(x, y, clamp(amount))) for x, y in zip(a, b))


def _progress(config, frame_index):
    return frame_index / (config["fps"] * config["duration"])


def _fit_size(draw, values, size, width, weight=800):
    chosen = max(6, round(size))
    while chosen > 6 and any(
        draw.textlength(line, font=font(chosen, weight)) > width for line in values
    ):
        chosen -= 1
    return chosen


def _paragraph(draw, value, xy, width, size, fill, weight=500,
               max_lines=3, leading=1.25, max_height=None):
    """Fit complete copy; never truncate a configured sentence."""
    chosen = max(6, round(size))
    lines = wrap(value, width, chosen, weight)
    while chosen > 6 and (
        len(lines) > max_lines or
        (max_height is not None and len(lines) * chosen * leading > max_height) or any(
            draw.textlength(line, font=font(chosen, weight)) > width for line in lines
        )
    ):
        chosen -= 1
        lines = wrap(value, width, chosen, weight)
    for index, line in enumerate(lines):
        text(draw, (xy[0], xy[1] + index * chosen * leading), line,
             chosen, fill, weight=weight)
    return len(lines) * chosen * leading


def _line_group(draw, values, xy, size, width, fill, leading=1.02, weight=850):
    chosen = _fit_size(draw, values, size, width, weight)
    for index, line in enumerate(values):
        text(draw, (xy[0], xy[1] + index * chosen * leading), line,
             chosen, fill, weight=weight)
    return chosen * leading * len(values)


@lru_cache(maxsize=40)
def _step_surface(width, height, index, value, face, ink, accent, is_last, tall):
    surface = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(surface)
    radius = max(2, round(min(width, height) * .045))
    draw.rounded_rectangle((0, 0, width - 1, height - 1), radius,
                           fill=accent if is_last else face)
    if tall:
        pad = width * .11
        number_size = height * .26
        text(draw, (pad, height * .11), f"{index + 1:02}", number_size,
             ink, weight=800)
        draw.line((pad, height * .51, width - pad, height * .51),
                  fill=_color_mix(accent if is_last else face, ink, .24),
                  width=max(1, round(width * .006)))
        _paragraph(draw, value, (pad, height * .62), width - 2 * pad,
                   height * .092, ink, weight=700, max_lines=3, leading=1.16)
    else:
        pad = width * .055
        text(draw, (pad, height * .28), f"{index + 1:02}", height * .39,
             ink, weight=800)
        divider = width * .205
        draw.line((divider, height * .22, divider, height * .78),
                  fill=_color_mix(accent if is_last else face, ink, .28),
                  width=max(1, round(height * .012)))
        text(draw, (width * .25, height * .34), value, height * .255,
             ink, weight=650, max_width=width * .69)
    return surface


def flow_state(config, frame_index):
    """A scattered stack becomes a readable, ordered workflow."""
    w, h = config["width"], config["height"]
    s = min(w, h)
    t = _progress(config, frame_index)
    p = config["palette"]
    bg, ink, accent = p["background"], p["foreground"], p["accent"]
    copy = config["content"]
    image = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(image)
    landscape = w > h * 1.25
    margin = w * .075
    muted = _color_mix(bg, ink, .56)

    # The route is deliberately absent while the tasks are unordered.
    aligned = ease((t - .24) / .34)
    entrance = ease(t / .15)
    draw.line((margin, h * .105, margin + s * .065, h * .105),
              fill=accent, width=max(2, round(s * .006)))
    text(draw, (margin + s * .087, h * .096), "FLOW STATE", s * .019,
         ink, weight=650)
    square = not landscape and h <= w * 1.25
    headline_size = s * (.065 if square else .072 if landscape else .078)
    headline_parts = copy["headline"].split(". ")
    if len(headline_parts) == 2 and not landscape:
        _line_group(draw, [headline_parts[0] + ".", headline_parts[1]],
                    (margin, h * .157), headline_size, w * .85,
                    ink, leading=1.08)
    else:
        _paragraph(draw, copy["headline"], (margin, h * .157), w * .85,
                   headline_size, ink, weight=850, max_lines=2, leading=1.08)

    # Copy follows the structural change instead of claiming measured savings.
    state = copy["before_label"] if t < .42 else copy["after_label"]
    state_opacity = clamp(abs(t - .42) / .06)
    state_color = _color_mix(bg, accent, state_opacity)
    state_y = h * (.34 if landscape or square else .32)
    text(draw, (margin, state_y), state.upper(), s * .021, state_color,
         weight=650, max_width=w * .84)

    steps = copy["steps"]
    count = len(steps)
    if landscape:
        gap = w * .017
        card_w = round((w * .85 - gap * (count - 1)) / count)
        card_h = round(h * .355)
        final_y = h * .57
        targets = [(margin + card_w / 2 + i * (card_w + gap), final_y)
                   for i in range(count)]
        initial = [(w * (.39 + i * .067), h * (.59 + (i % 2) * .025))
                   for i in range(count)]
    else:
        card_w = round(w * .85)
        gap = h * .014
        total = h * .39
        card_h = round((total - gap * (count - 1)) / count)
        first_y = h * .397 + card_h / 2
        targets = [(w / 2, first_y + i * (card_h + gap)) for i in range(count)]
        initial = [(w * (.47 + .035 * (i % 2)), h * (.55 + i * .025))
                   for i in range(count)]

    # A single path only appears once its sequence has a readable spatial order.
    if aligned > .82:
        connector_color = _color_mix(bg, accent, (aligned - .82) / .18)
        for left, right in zip(targets, targets[1:]):
            if landscape:
                x1, x2 = left[0] + card_w / 2, right[0] - card_w / 2
                yy = left[1]
                draw.line((x1, yy, x2, yy), fill=connector_color,
                          width=max(2, round(s * .004)))
                a = s * .008
                draw.polygon(((x2 - a, yy - a), (x2, yy), (x2 - a, yy + a)),
                             fill=connector_color)
            else:
                x = left[0]
                y1, y2 = left[1] + card_h / 2, right[1] - card_h / 2
                draw.line((x, y1, x, y2), fill=connector_color,
                          width=max(2, round(s * .004)))

    angles = (-12, 8, -6, 11)
    for index, value in enumerate(steps):
        px = mix(initial[index][0], targets[index][0], aligned)
        py = mix(initial[index][1], targets[index][1], aligned)
        py += h * .10 * (1 - entrance)
        angle = angles[index] * (1 - aligned)
        surface = _step_surface(card_w, card_h, index, value,
                                ink, bg, accent, index == count - 1, landscape)
        rotated = surface.rotate(angle, Image.Resampling.BICUBIC, expand=True)
        # Tight, graphic shadows are intentional: no per-frame blur or drift.
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 0))
        shadow.putalpha(rotated.getchannel("A").point(lambda a: round(a * .24)))
        place = (round(px - rotated.width / 2), round(py - rotated.height / 2))
        image.paste(shadow, (place[0] + round(s * .009),
                             place[1] + round(s * .015)), shadow)
        image.paste(rotated, place, rotated)

    draw = ImageDraw.Draw(image)
    if t > .56:
        copy_ink = _color_mix(bg, muted, ease((t - .56) / .11))
        _paragraph(draw, copy["subhead"], (margin, h * .812), w * .82,
                   s * .025, copy_ink, max_lines=2, leading=1.2)
    footer(draw, config)
    return image


def _linear_system(rows, values):
    """Solve the small, well-conditioned projective mapping with pivoting."""
    matrix = [list(map(float, row)) + [float(value)]
              for row, value in zip(rows, values)]
    for col in range(len(values)):
        pivot = max(range(col, len(values)), key=lambda i: abs(matrix[i][col]))
        if abs(matrix[pivot][col]) < 1e-10:
            raise ValueError("Degenerate projected panel")
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        scale = matrix[col][col]
        matrix[col] = [value / scale for value in matrix[col]]
        for row in range(len(values)):
            if row == col:
                continue
            scale = matrix[row][col]
            matrix[row] = [v - scale * p for v, p in zip(matrix[row], matrix[col])]
    return [matrix[i][-1] for i in range(len(values))]


def _warp_panel(image, surface, corners, shadow_ink, shadow_offset):
    """Project an RGBA surface into a bounded quadrilateral, avoiding full-frame warps."""
    left = math.floor(min(point[0] for point in corners)) - 2
    top = math.floor(min(point[1] for point in corners)) - 2
    right = math.ceil(max(point[0] for point in corners)) + 2
    bottom = math.ceil(max(point[1] for point in corners)) + 2
    target = [(x - left, y - top) for x, y in corners]
    src = [(0, 0), (surface.width, 0),
           (surface.width, surface.height), (0, surface.height)]
    equations, answers = [], []
    for (x, y), (u, v) in zip(target, src):
        equations.extend(((x, y, 1, 0, 0, 0, -u * x, -u * y),
                          (0, 0, 0, x, y, 1, -v * x, -v * y)))
        answers.extend((u, v))
    coefficients = _linear_system(equations, answers)
    warped = surface.transform((right - left, bottom - top),
                               Image.Transform.PERSPECTIVE, coefficients,
                               Image.Resampling.BICUBIC)
    draw = ImageDraw.Draw(image)
    draw.polygon([(x + shadow_offset, y + shadow_offset * 1.5) for x, y in corners],
                 fill=shadow_ink)
    image.paste(warped, (left, top), warped)


def _corners(pw, ph, cx, cy, yaw, roll, focal, depth=0):
    yaw, roll = math.radians(yaw), math.radians(roll)
    points = []
    for x, y in ((-pw / 2, -ph / 2), (pw / 2, -ph / 2),
                 (pw / 2, ph / 2), (-pw / 2, ph / 2)):
        xx = x * math.cos(yaw)
        zz = -x * math.sin(yaw) + depth
        xp = xx * math.cos(roll) - y * math.sin(roll)
        yp = xx * math.sin(roll) + y * math.cos(roll)
        scale = focal / (focal + zz)
        points.append((cx + xp * scale, cy + yp * scale))
    return points


@lru_cache(maxsize=24)
def _poster_surface(width, height, index, name, background, foreground, accent, asset):
    fills = (background, foreground, accent)
    inks = (foreground, background, foreground)
    face, ink = fills[index], inks[index]
    image = Image.new("RGBA", (width, height), face)
    draw = ImageDraw.Draw(image)
    pad = width * .078
    small = width * .045
    text(draw, (pad, height * .05), f"{index + 1:02} / {name.upper()}",
         small, ink, weight=650, max_width=width - 2 * pad)
    draw.line((pad, height * .111, width - pad, height * .111),
              fill=_color_mix(face, ink, .33), width=max(1, round(width * .003)))
    if asset:
        # Screenshots keep their full bounds; transparent/image gutters are explicit.
        with Image.open(asset) as source:
            fitted = ImageOps.contain(source.convert("RGBA"),
                                     (round(width - 2 * pad), round(height * .70)),
                                     Image.Resampling.LANCZOS)
        image.alpha_composite(fitted, (round((width - fitted.width) / 2),
                                        round(height * .16 + (height * .70 - fitted.height) / 2)))
        text(draw, (pad, height * .915), "SOURCE CAPTURE", small * .83,
             ink, weight=550)
    else:
        # A typographic specimen is visibly a layout demonstration, never fabricated UI.
        if index == 0:
            large = width * .78
            text(draw, (width * .50, height * .23), "01", large,
                 ink, weight=850, anchor="mt", max_width=width * .95)
            draw.rectangle((pad, height * .65, width - pad, height * .685), fill=accent)
            _paragraph(draw, name.upper(), (pad, height * .74), width - 2 * pad,
                       width * .15, ink, weight=800, max_lines=2, max_height=height * .16)
        elif index == 1:
            cx, cy = width * .5, height * .46
            outer = width * .35
            for ring in range(5):
                radius = outer * (1 - ring * .16)
                draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                             outline=accent, width=max(2, round(width * .014)))
            draw.rectangle((width * .50, height * .17, width * .515, height * .73),
                           fill=face)
            _paragraph(draw, name.upper(), (pad, height * .74), width - 2 * pad,
                       width * .16, ink, weight=800, max_lines=2, max_height=height * .16)
        else:
            top = height * .22
            stripe_h = height * .075
            for stripe in range(5):
                draw.polygon(((pad, top + stripe * stripe_h),
                              (width - pad, top + stripe * stripe_h - height * .05),
                              (width - pad, top + stripe * stripe_h + stripe_h * .47),
                              (pad, top + stripe * stripe_h + stripe_h * .47 + height * .05)),
                             fill=ink)
            _paragraph(draw, name.upper(), (pad, height * .74), width - 2 * pad,
                       width * .15, ink, weight=800, max_lines=2, max_height=height * .16)
        text(draw, (pad, height * .927), "LAYOUT DEMO", small * .75, ink, weight=600)
    return image


def prism(config, frame_index):
    """A fan of editorial planes opens into one dimensional product showcase."""
    w, h = config["width"], config["height"]
    s = min(w, h)
    p, copy = config["palette"], config["content"]
    bg, ink, accent = p["background"], p["foreground"], p["accent"]
    t = _progress(config, frame_index)
    image = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(image)
    landscape = w > h * 1.25
    portrait = h > w * 1.25
    margin = w * .075
    muted = _color_mix(bg, ink, .55)

    text(draw, (margin, h * .096), "PRISM / DIMENSION STUDY", s * .019,
         ink, weight=650, max_width=w * .8)
    if landscape:
        _line_group(draw, copy["headline"], (margin, h * .24),
                    s * .112, w * .39, ink, leading=1.04)
        _paragraph(draw, copy["subhead"], (margin, h * .665), w * .33,
                   s * .028, muted, max_lines=3)
        panel_w, panel_h = round(w * .225), round(h * .61)
        centers = [(w * .585, h * .55), (w * .73, h * .53), (w * .86, h * .55)]
        origin_x, origin_y = w * .735, h * .57
    else:
        title_y = h * (.16 if portrait else .14)
        _line_group(draw, copy["headline"], (margin, title_y),
                    s * .112, w * .85, ink, leading=1.03)
        panel_w = round(w * (.52 if portrait else .29))
        panel_h = round(h * (.345 if portrait else .39))
        cy = h * (.595 if portrait else .56)
        side_x = .265 if portrait else .30
        centers = [(w * side_x, cy + h * .018), (w * .5, cy),
                   (w * (1 - side_x), cy + h * .018)]
        origin_x, origin_y = w * .5, cy + h * .04
        _paragraph(draw, copy["subhead"], (margin, h * .812), w * .85,
                   s * .026, muted, max_lines=2)

    opening = ease(t / .20)
    fan = ease((t - .16) / .34)
    # The back planes remain visible during the final hold, preserving context.
    assets = copy.get("assets") or [None, None, None]
    order = (0, 2, 1)
    for index in order:
        surface = _poster_surface(panel_w, panel_h, index, copy["cards"][index],
                                  bg, ink, accent, assets[index])
        cx = mix(origin_x + (index - 1) * s * .045, centers[index][0], fan)
        cy = mix(origin_y, centers[index][1], fan) + h * .12 * (1 - opening)
        yaw = mix((-48, 9, 48)[index], (-28, 0, 28)[index], fan)
        roll = mix((-9, 3, 9)[index], (-5, 0, 5)[index], fan)
        depth = s * (.055 if index != 1 else -.025) * fan
        corners = _corners(panel_w, panel_h, cx, cy, yaw, roll, s * 2.8, depth)
        shadow = _color_mix(bg, ink, .16 if index != 1 else .23)
        _warp_panel(image, surface, corners, shadow, s * .012)

    draw = ImageDraw.Draw(image)
    footer(draw, config)
    return image


@lru_cache(maxsize=12)
def _after_hours_base(w, h, background, foreground, accent):
    """Cache a very restrained vignette; no noisy, flickering particle texture."""
    image = Image.new("RGB", (w, h), background)
    draw = ImageDraw.Draw(image)
    # A single quiet color field creates depth while the live arcs own movement.
    s = min(w, h)
    cx, cy = (w * .72, h * .49) if w > h * 1.25 else (w * .56, h * .49)
    for index in range(28, 0, -1):
        radius = s * (.46 + index * .013)
        amount = (1 - index / 29) * .11
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                     fill=_color_mix(background, accent, amount))
    return image


def after_hours(config, frame_index):
    """Loopable event/brand poster: a moving iris behind stable, oversized type."""
    w, h = config["width"], config["height"]
    s = min(w, h)
    p, copy = config["palette"], config["content"]
    bg, ink, accent = p["background"], p["foreground"], p["accent"]
    t = _progress(config, frame_index)
    image = _after_hours_base(w, h, bg, ink, accent).copy()
    draw = ImageDraw.Draw(image)
    landscape = w > h * 1.25
    portrait = h > w * 1.25
    phase = 2 * math.pi * t
    cx = w * (.735 if landscape else .56)
    cy = h * (.49 if landscape else .50 if portrait else .46)
    radius = s * (.45 if landscape else .425 if portrait else .30)
    # Every animated property is periodic; adjacent loop endpoints are continuous.
    breathing = 1 + .025 * math.sin(phase)
    spin = 18 * math.sin(phase)
    for index in range(12):
        r = radius * (1 - index * .059) * breathing
        line_w = max(2, round(s * (.011 + index * .0003)))
        stroke = _color_mix(accent, ink, index * .018)
        start = 24 + index * 9 + spin
        end = 324 + index * 9 + spin
        draw.arc((cx - r, cy - r, cx + r, cy + r), start, end,
                 fill=stroke, width=line_w)
    # The aperture's center stays quiet, letting the type and arc edge read cleanly.
    inner = radius * .25
    draw.ellipse((cx - inner, cy - inner, cx + inner, cy + inner), fill=bg)
    dot_angle = phase - math.pi / 3
    dot_r = radius * 1.06
    dot_x, dot_y = cx + math.cos(dot_angle) * dot_r, cy + math.sin(dot_angle) * dot_r
    dot_size = s * .009
    draw.ellipse((dot_x - dot_size, dot_y - dot_size, dot_x + dot_size, dot_y + dot_size),
                 fill=ink)

    margin = w * .075
    text(draw, (margin, h * .096), copy["badge"].upper(), s * .021,
         accent, weight=650, max_width=w * .80)
    if landscape:
        size = _fit_size(draw, copy["title"], s * .205, w * .67, 880)
        for index, value in enumerate(copy["title"]):
            draw.text((margin, h * .268 + index * size * .98), value,
                      font=font(size, 880), fill=ink, anchor="lt",
                      stroke_width=max(1, round(s * .003)), stroke_fill=bg)
        _paragraph(draw, copy["subtitle"], (margin, h * .728), w * .60,
                   s * .030, ink, weight=500, max_lines=2)
        text(draw, (margin, h * .82), copy["cta"].upper(), s * .023,
             accent, weight=650, max_width=w * .65)
    else:
        size = _fit_size(draw, copy["title"], s * .215, w * .87, 880)
        for value, yy in zip(copy["title"],
                             (h * (.185 if portrait else .18),
                              h * (.635 if portrait else .61))):
            draw.text((margin, yy), value, font=font(size, 880), fill=ink, anchor="lt",
                      stroke_width=max(1, round(s * .003)), stroke_fill=bg)
        _paragraph(draw, copy["subtitle"], (margin, h * .79), w * .85,
                   s * .026, ink, weight=500, max_lines=2, leading=1.15)
        text(draw, (margin, h * .85), copy["cta"].upper(), s * .020,
             accent, weight=650, max_width=w * .82)
    footer(draw, config)
    return image
