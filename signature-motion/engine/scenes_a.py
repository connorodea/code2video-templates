"""Typography, evidence and quantitative editorial motion."""
from __future__ import annotations

import math
from PIL import Image, ImageDraw
from .style import blend, clamp, draw_lines, ease, font, footer, label, mix, paper, phase, rgb, text, wrap


def _axis_number(value):
    for threshold, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "k")):
        if value >= threshold:
            return f"{value / threshold:.3g}{suffix}"
    return f"{value:,.0f}" if value >= 10 or value == 0 else f"{value:.1f}"


def type_impact(config, frame_index):
    w, h = config["width"], config["height"]
    s, portrait = min(w, h), h > w * 1.15
    landscape = w > h * 1.15
    p, c = config["palette"], config["content"]
    t = phase(config, frame_index)
    image = Image.new("RGB", (w, h), p["background"])
    d = ImageDraw.Draw(image)
    # The first reveal is a single slab, followed by measured typographic masks.
    margin = w * .075
    label(d, (margin, h * .115), "A STATEMENT IN MOTION", s * .023, p["foreground"])
    text(d, (w - margin, h * .105), "+", s * .085, p["foreground"], anchor="rt")
    lines = c["headline"]
    hero_size = s * (.155 if portrait else (.17 if landscape and len(lines) == 2 else .115 if len(lines) == 3 else .145))
    available = w * (.56 if landscape else .85)
    for line in lines:
        while d.textlength(line, font=font(hero_size, 900)) > available and hero_size > s * .055:
            hero_size -= 1
    line_height = hero_size * 1.14
    top = h * (.32 if portrait else .27)
    for i, line in enumerate(lines):
        progress = ease((t - .04 - i * .09) / .18)
        line_layer = Image.new("RGBA", (w, int(line_height + 6)), (0, 0, 0, 0))
        ld = ImageDraw.Draw(line_layer)
        y = (1 - progress) * line_height
        text(ld, (margin, y), line, hero_size, p["foreground"], weight=900, max_width=available)
        image.paste(line_layer, (0, round(top + i * line_height)), line_layer)
    d = ImageDraw.Draw(image)
    bar_y = top + len(lines) * line_height + s * .035
    rule = ease((t - .25) / .17)
    d.rectangle((margin, bar_y, margin + available * rule, bar_y + s * .013), fill=p["foreground"])
    if t > .35:
        opacity = ease((t - .35) / .1)
        sub_width = w * (.235 if landscape else .48 if not portrait else .8)
        sub_x = w * .69 if landscape else margin
        sub_y = h * .33 if landscape else bar_y + s * .055
        sub = wrap(c["subhead"], sub_width, s * .032, 500)
        draw_lines(d, sub, sub_x, sub_y, s * .032,
                   blend(p["background"], p["foreground"], opacity), sub_width, 1.3, 500)
    if t > .58:
        q = ease((t - .58) / .13)
        cy = h * (.65 if landscape else .76) + (1-q) * s * .055
        cx = w * (.69 if landscape else .65) if not portrait else margin
        cmax = w * (.235 if landscape else .275) if not portrait else available
        cw = min(cmax, d.textlength(c["cta"], font=font(s * .027, 700)) + s * .13)
        d.rectangle((cx, cy, cx+cw, cy+s * .087), fill=p["foreground"])
        text(d, (cx+s * .035, cy+s * .027), c["cta"], s * .027, p["background"], weight=700, max_width=cw-s * .07)
    # A quiet optical registration mark closes the composition.
    for x in (w * .82, w * .85, w * .88):
        d.ellipse((x, h * .82, x + s * .012, h * .82 + s * .012), fill=p["foreground"])
    footer(d, config)
    return image


def redline(config, frame_index):
    w, h = config["width"], config["height"]
    s, portrait = min(w, h), h > w * 1.15
    p, c = config["palette"], config["content"]
    t = phase(config, frame_index)
    image = paper(w, h, p["background"], config["seed"]).copy()
    d = ImageDraw.Draw(image)
    m = w * .075
    label(d, (m, h * .115), "REDLINE / THE SOURCE MATTERS", s * .022, p["accent"])
    headline_size = s * .078
    headline = wrap(c["headline"], w * .84, headline_size, 850)
    while len(headline) * headline_size * 1.08 > h * .165 and headline_size > s * .025:
        headline_size -= 1
        headline = wrap(c["headline"], w * .84, headline_size, 850)
    draw_lines(d, headline, m, h * .18, headline_size, p["foreground"], w * .84, 1.08, 850)
    card_w, card_h = round(w * .85), round(h * (.34 if portrait else .36))
    card = Image.new("RGBA", (card_w, card_h), (255, 253, 244, 255))
    cd = ImageDraw.Draw(card)
    padding = s * .037
    cd.rectangle((0, 0, s * .012, card_h), fill=p["accent"])
    label(cd, (padding, padding), "EXCERPT / 001", s * .019, p["accent"])
    quote_size = s * (.051 if portrait else .043)
    quote_lines = wrap(c["quote"], card_w - padding * 2, quote_size, 600)
    # Fit long excerpts vertically before rendering. No clipping or ellipses.
    while len(quote_lines) * quote_size * 1.23 > card_h * .50:
        quote_size -= 1
        quote_lines = wrap(c["quote"], card_w - padding * 2, quote_size, 600)
    quote_y = card_h * .24
    for i, line in enumerate(quote_lines):
        y = quote_y + i * quote_size * 1.23
        reveal = ease((t - .22 - i * .045) / .2)
        length = cd.textlength(line, font=font(quote_size, 600))
        cd.rectangle((padding-3, y-3, padding + length * reveal + 3, y + quote_size * 1.04), fill=(255, 224, 193, 255))
        text(cd, (padding, y), line, quote_size, "#27231f", weight=600, max_width=card_w-padding*2)
    cd.line((padding, card_h * .8, card_w-padding, card_h * .8), fill="#d7cfc1", width=max(1, round(s * .001)))
    text(cd, (padding, card_h * .855), c["source"], s * .018, "#655d53", weight=500, max_width=card_w-padding*2)
    arrival = ease((t - .04) / .19)
    # Short geometric motion followed by a stable reading hold.
    angle = (1-arrival) * -5
    if abs(angle) > .01:
        card = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
    cy = h * .37 + (1-arrival) * h * .08
    shadow = Image.new("RGBA", card.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((0, 0, card.width, card.height), fill=(42, 34, 28, 20))
    image.paste(shadow, (round((w-card.width)/2+s*.008), round(cy+s*.01)), shadow)
    image.paste(card, (round((w-card.width)/2), round(cy)), card)
    d = ImageDraw.Draw(image)
    if t >= .57:
        reveal = ease((t - .57) / .16)
        vy = h * .77
        d.line((m, vy, m + w * .1 * reveal, vy), fill=p["accent"], width=max(2, round(s*.008)))
        color = blend(p["background"], p["accent"], reveal)
        text(d, (m, vy+s*.027), c["verdict"], s * .036, color, weight=800, max_width=w*.85)
    footer(d, config, p["foreground"])
    return image


def signal(config, frame_index):
    w, h = config["width"], config["height"]
    s, portrait = min(w, h), h > w * 1.15
    p, c = config["palette"], config["content"]
    t = phase(config, frame_index)
    image = Image.new("RGB", (w, h), p["background"])
    d = ImageDraw.Draw(image)
    m = w * .075
    label(d, (m, h * .115), "SIGNAL / FOLLOW THE EVIDENCE", s * .022, p["accent"])
    title_size = s * .069
    title = wrap(c["headline"], w * .83, title_size, 800)
    while len(title) * title_size * 1.13 > h * .14 and title_size > s * .025:
        title_size -= 1
        title = wrap(c["headline"], w * .83, title_size, 800)
    draw_lines(d, title, m, h * .18, title_size, p["foreground"], w*.84, 1.13, 800)
    left, right = w*.16, w*.88
    top, bottom = h*(.39 if portrait else .36), h*.68
    values = [item["value"] for item in c["series"]]
    ceiling = max(max(values)*1.15, 1)
    dim = blend(p["background"], p["foreground"], .15)
    secondary = blend(p["background"], p["foreground"], .52)
    for fraction in (0, .5, 1):
        y = bottom - (bottom-top)*fraction
        d.line((left, y, right, y), fill=dim, width=max(1, round(s*.001)))
        tick = _axis_number(ceiling*fraction)
        text(d, (left-s*.022, y), tick, s*.022, secondary, 500, anchor="rm", max_width=left-m*.65)
    pts = [(mix(left,right,i/(len(values)-1)), bottom-v/ceiling*(bottom-top)) for i,v in enumerate(values)]
    progress = clamp((t-.16)/.42)
    count = progress*(len(pts)-1)
    full = int(count)
    active = pts[:full+1]
    if full < len(pts)-1:
        alpha = count-full
        active.append((mix(pts[full][0],pts[full+1][0],alpha),mix(pts[full][1],pts[full+1][1],alpha)))
    if len(active)>1:
        area = Image.new("RGBA", (w,h), (0,0,0,0))
        ad = ImageDraw.Draw(area)
        ad.polygon([(left,bottom), *active, (active[-1][0],bottom)], fill=(*rgb(p["accent"]),24))
        image.paste(area,(0,0),area)
        d = ImageDraw.Draw(image)
        d.line(active, fill=p["accent"], width=max(2,round(s*.007)), joint="curve")
    for i, item in enumerate(c["series"]):
        # Direct labels use identical positions in every frame.
        label_width = (right-left)/len(values) * .94
        text(d, (pts[i][0], bottom+s*.028), item["label"], s*.021, secondary, 500,
             anchor="mt", max_width=label_width)
        if i <= full and progress > 0:
            x,y=pts[i]
            r=s*.006
            d.ellipse((x-r,y-r,x+r,y+r),fill=p["accent"])
    if progress >= 1:
        x,y=pts[-1]
        r=s*.013
        d.ellipse((x-r,y-r,x+r,y+r), fill=p["background"], outline=p["accent"], width=max(2,round(s*.004)))
        last = f"{values[-1]:,.0f}" if float(values[-1]).is_integer() else f"{values[-1]:,.1f}"
        text(d,(right,y-s*.03),f"{last} {c['unit']}".strip(),s*.04,p["accent"],800,anchor="rb",max_width=w*.4)
    if t > .62:
        q=ease((t-.62)/.1)
        text(d,(m,h*.765),c["takeaway"],s*.033,blend(p["background"],p["foreground"],q),700,max_width=w*.85)
    text(d,(m,h*.835),c["source"],s*.018,secondary,500,max_width=w*.85)
    footer(d,config)
    return image
