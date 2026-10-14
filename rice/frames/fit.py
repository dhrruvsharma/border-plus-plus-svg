#!/usr/bin/env python3
"""Fits a downloaded frame svg for borders.lua: finds the frame in it, repairs what it can and works out its settings.

    ./fit.py ~/Downloads/gold-frame.svg              # writes gold-frame.svg here, says what it did, renders a preview
    ./fit.py ~/Downloads/x.svg --name gilded --border-size 20

It unhides parts that empty clip paths hide (a common PDF-to-SVG export bug), removes a background drawn behind the
frame, crops the empty page around it, then measures where the corner ornaments end and the plain or repeating edges
begin and how deep the frame is, and writes those as data- attributes on a copy in this folder. The original is left
alone. What a 9-slice frame can't do, like oval frames or ornaments in the middle of an edge, it warns about.
"""
import argparse
import math
import os
import re
import sys

import gi

gi.require_version("Rsvg", "2.0")
import cairo  # noqa: E402
from gi.repository import Gio, GLib, Rsvg  # noqa: E402
from lxml import etree  # noqa: E402
from PIL import Image  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = "{http://www.w3.org/2000/svg}"
INK = 40  # alpha that counts as part of the frame
WORK = 1200  # longest side of the working render, in pixels

# what the sizes aim for on screen: a border about this thick, corners about this big, whichever is smaller
BORDER_TARGET, CORNER_TARGET, BORDER_MIN, BORDER_MAX = 22, 140, 8, 40


def say(text):
    print("  " + text)


# ---- svg in and out ----

def parse(path):
    parser = etree.XMLParser(huge_tree=True, remove_comments=False, resolve_entities=True)
    return etree.parse(path, parser)


def to_bytes(tree):
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8")


def render(data, base, scale=None, longest=None):
    """RGBA render and the svg's size in its own pixels"""
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(data))
    handle = Rsvg.Handle.new_from_stream_sync(stream, Gio.File.new_for_path(base), Rsvg.HandleFlags.FLAGS_NONE, None)
    ok, w, h = handle.get_intrinsic_size_in_pixels()
    if not ok:
        has_vb, vb = handle.get_intrinsic_dimensions()[4:6]
        if not has_vb:
            sys.exit("the svg has neither a width/height nor a viewBox")
        w, h = vb.width, vb.height
    scale = scale or longest / max(w, h)
    W, H = max(1, round(w * scale)), max(1, round(h * scale))
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    handle.render_document(cairo.Context(surf), vp)
    surf.flush()
    img = Image.frombuffer("RGBA", (W, H), bytes(surf.get_data()), "raw", "BGRa", surf.get_stride(), 1).copy()
    return img, (w, h), scale


def viewbox(root, size):
    vb = root.get("viewBox")
    if vb:
        vals = [float(v) for v in re.split(r"[\s,]+", vb.strip())]
        if len(vals) == 4 and vals[2] > 0 and vals[3] > 0:
            return vals
    return [0.0, 0.0, size[0], size[1]]


def num(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ---- repairs ----

def unhide_empty_clips(tree):
    """clip paths with nothing in them hide whatever uses them: stop using them"""
    empty = {c.get("id") for c in tree.iter(SVG + "clipPath")
             if c.get("id") and not any(isinstance(ch.tag, str) for ch in c)}
    fixed = 0
    for el in tree.iter():
        if not isinstance(el.tag, str):
            continue
        clip = el.get("clip-path", "")
        m = re.fullmatch(r"\s*url\(\s*#([^)\s]+)\s*\)\s*", clip)
        if m and m.group(1) in empty:
            del el.attrib["clip-path"]
            fixed += 1
        style = el.get("style", "")
        if "clip-path" in style:
            new = re.sub(r"clip-path\s*:\s*url\(\s*#([^)\s]+)\s*\)\s*;?",
                         lambda m: "" if m.group(1) in empty else m.group(0), style)
            if new != style:
                el.set("style", new)
                fixed += 1
    return fixed


def drawables(tree):
    """shapes in drawing order, outside defs and other things that aren't drawn directly"""
    skip = {SVG + t for t in ("defs", "clipPath", "mask", "pattern", "symbol", "marker", "linearGradient",
                              "radialGradient", "filter", "style", "metadata", "title", "desc")}
    out = []

    def walk(el):
        for ch in el:
            if not isinstance(ch.tag, str) or ch.tag in skip:
                continue
            if ch.tag in (SVG + "rect", SVG + "path", SVG + "polygon", SVG + "image"):
                out.append(ch)
            walk(ch)

    walk(tree.getroot())
    return out


def middle_alpha(img):
    W, H = img.size
    box = img.getchannel("A").crop((int(W * .35), int(H * .35), int(W * .65), int(H * .65)))
    data = box.tobytes()
    return sum(data) / max(1, len(data))


def remove_background(tree, base):
    """if something opaque fills the middle, try taking away each of the first few shapes until it's see-through
    while the frame itself stays"""
    img, _, _ = render(to_bytes(tree), base, longest=400)
    if middle_alpha(img) < 128:
        return None
    for el in drawables(tree)[:8]:
        parent = el.getparent()
        index = parent.index(el)
        parent.remove(el)
        test, _, _ = render(to_bytes(tree), base, longest=400)
        bbox = test.getchannel("A").point(lambda v: 255 if v > INK else 0).getbbox()
        if middle_alpha(test) < 20 and bbox:
            return el.tag.replace(SVG, "")
        parent.insert(index, el)
    return "stuck"


# ---- measuring ----

def sides(img):
    """the image turned so each side in turn is at the top: top, right, bottom, left (and each corner in turn at the
    top left: top-left, top-right, bottom-right, bottom-left)"""
    return [img, img.rotate(90, expand=True), img.rotate(180), img.rotate(270, expand=True)]


def signature(alpha, light, L, D):
    """each column from the edge inwards, its transparency and then its brightness, so shapes and colours both count"""
    a = alpha.crop((0, 0, L, D)).tobytes()
    b = light.crop((0, 0, L, D)).tobytes()
    return [a[x::L] + b[x::L] for x in range(L)]


def differs(p, q):
    """rows where two columns clearly differ: a thin stroke can't hide in an average this way"""
    return sum(1 for x, y in zip(p, q) if abs(x - y) > 64)


def deepest(column, D):
    """how far in the column's ink goes (only its transparency half counts)"""
    for d in range(D - 1, -1, -1):
        if column[d] > INK:
            return d + 1
    return 0


def attached(column, D, gap):
    """how deep the ink hanging off the edge goes: from its first ink near the edge until an empty stretch longer
    than `gap`, so text or a picture further in doesn't count as part of the frame"""
    last = None
    for d in range(D):
        if column[d] > INK:
            if last is None and d > D // 2:
                return 0  # nothing near the edge in this column
            if last is not None and d - last > gap:
                break
            last = d
    return 0 if last is None else last + 1


def period_of(signal):
    """the repeat length of a signal if it clearly has one: the first peak of its autocorrelation after that has
    dropped away (a smooth shape looks like itself a pixel along, which isn't a repeat)"""
    n = len(signal)
    if n < 24:
        return None
    m = sum(signal) / n
    s = [v - m for v in signal]
    energy = sum(v * v for v in s)
    if energy <= 0:
        return None
    r = [sum(s[i] * s[i + p] for i in range(n - p)) / energy * n / (n - p) for p in range(n // 3 + 1)]
    dropped = False
    for p in range(1, len(r) - 1):
        if not dropped:
            dropped = r[p] < 0.3
        elif r[p] > 0.7 and r[p] >= r[p - 1] and r[p] >= r[p + 1]:
            return p
    return None


def measure_side(alpha, light):
    """where the plain (or repeating) middle of this side starts and ends, and how deep the edge is there"""
    L, D = alpha.width, alpha.height // 2
    gap = max(4, int(D * 0.15))
    col = signature(alpha, light, L, D)
    centre = range(int(L * .45), int(L * .55) + 1)
    ref = bytes(sorted(col[x][d] for x in centre)[len(centre) // 2] for d in range(2 * D))
    result = {"length": L, "period": None, "plain": max(differs(col[x], ref) for x in centre) <= 2}

    if result["plain"]:
        same = lambda x, step: differs(col[x], ref) <= 2  # noqa: E731
    else:
        middle = range(int(L * .25), int(L * .75))
        p = period_of([sum(col[x]) for x in middle])
        if p and max(differs(col[x], col[x + p]) for x in range(int(L * .4), int(L * .6))) <= 3:
            result["period"] = p
            same = lambda x, step: 0 <= x + step * p < L and differs(col[x], col[x + step * p]) <= 3  # noqa: E731
        else:  # neither plain nor repeating: no telling where the corners end, so judge its depth away from them
            middle = range(L // 4, L * 3 // 4)
            depths = [attached(col[x], D, gap) for x in middle]
            result.update(start=L // 2, end=L // 2, edge_depth=max(depths),
                          inner=any(deepest(col[x], D) > d + gap for x, d in zip(middle, depths)))
            return result

    def walk(x, step):
        misses = 0
        while 0 <= x < L:
            if same(x, -step if result["period"] else step):
                misses = 0
            else:
                misses += 1
                if misses >= 3:
                    return x - step * 3  # the last column that matched
            x += step
        return x - step

    start, end = walk(L // 2, -1), walk(L // 2, 1)
    run = range(start, end + 1) if result["period"] is None else range(L // 2, L // 2 + result["period"])
    depths = [attached(col[x], D, gap) for x in run]
    result.update(start=start, end=end, edge_depth=max(depths),
                  inner=any(deepest(col[x], D) > d + gap for x, d in zip(run, depths)))
    return result


def corner_depths(alpha, s, gap):
    """how deep the frame has to be to hold the corner ornaments (give or take a few stray pixels), and how far
    their furthest bit reaches: a pixel x along and y down from a corner needs a frame min(x, y) deep. Only ink
    reachable from the corner without crossing an empty stretch longer than `gap` counts."""
    need = reach = 0
    for img in sides(alpha):
        data = img.crop((0, 0, s, s)).tobytes()
        hist = [0] * s
        for y in range(s):
            row = data[y * s:(y + 1) * s]
            for x in range(s):
                if row[x] > INK:
                    hist[min(x, y)] += 1
        last = -1
        for d in range(s):
            if hist[d]:
                if last >= 0 and d - last > gap:
                    break
                last = d
        if last < 0:
            continue
        total, seen = sum(hist[:last + 1]), 0
        for d in range(last + 1):
            seen += hist[d]
            if seen >= total * 0.997:
                need = max(need, d + 1)
                break
        reach = max(reach, last + 1)
    return need, reach


# ---- the fit ----

def fit(src, name, border_size=None, corner=None, force=False):
    base = os.path.abspath(src)
    tree = parse(src)
    root = tree.getroot()
    if root.tag != SVG + "svg":
        sys.exit(f"{src} isn't an svg")
    if any(re.fullmatch(r"rounding-\d+", el.get("id") or "") for el in tree.iter() if isinstance(el.tag, str)):
        sys.exit(f"{src} has frames for several roundings already (it's one generate.py made), there's nothing to fit")
    out = os.path.join(HERE, name + ".svg")
    if os.path.exists(out) and os.path.abspath(out) != base and not force:
        mine = parse(out).getroot().get("data-fitted-by") == "fit.py"
        if not mine:
            sys.exit(f"there's already a {name}.svg here that fit.py didn't make; pick another --name, or --force")
    warnings = []

    hidden = unhide_empty_clips(tree)
    if hidden:
        say(f"unhid {hidden} part{'s' * (hidden > 1)} hidden by empty clip paths (a PDF-to-SVG export bug)")

    removed = remove_background(tree, base)
    if removed == "stuck":
        warnings.append("its middle is filled in and that couldn't be separated from the frame, so the fill will show "
                        "along the edges; it may need editing in Inkscape")
    elif removed:
        say(f"removed the background {removed} drawn behind the frame")

    img, size, scale = render(to_bytes(tree), base, longest=WORK)
    bbox = img.getchannel("A").point(lambda v: 255 if v > INK else 0).getbbox()
    if not bbox:
        sys.exit("there's nothing visible in it")
    x0, y0, x1, y1 = max(0, bbox[0] - 1), max(0, bbox[1] - 1), min(img.width, bbox[2] + 1), min(img.height, bbox[3] + 1)
    vx, vy, vw, vh = viewbox(root, size)
    u = vw / img.width  # svg units per working pixel
    margins = [y0, img.width - x1, img.height - y1, x0]
    if max(margins) * u > max(vw, vh) * 0.005:
        say("cropped the empty page around it (top, right, bottom, left: {})".format(
            " / ".join(num(m * u) for m in margins)))
    img = img.crop((x0, y0, x1, y1))
    W, H = img.size
    alpha = img.getchannel("A")
    light = Image.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, 255)), img).convert("L")

    found = [measure_side(a, l) for a, l in zip(sides(alpha), sides(light))]
    irregular = any(not f["plain"] and not f["period"] for f in found)
    periods = [f["period"] for f in found if f["period"]]
    limit = min(W, H) // 2 - 2
    slice_px = max(max(f["start"], f["length"] - 1 - f["end"]) for f in found) + 2
    if irregular:
        warnings.append("the middle of some edges isn't plain or repeating (an ornament in the middle of an edge, or "
                        "not a rectangular frame), so those parts get stretched")
    elif slice_px > limit:
        warnings.append("its decoration runs along whole edges with no plain stretch between the corners, so the "
                        "edges will look stretched")
    slice_px = min(slice_px, limit)
    if periods:
        say(f"the edges repeat every {num(min(periods) * u)}, so they'll be tiled")
    elif not irregular:
        say("the edges are plain between the corners, so they'll be stretched")

    S = slice_px * u
    if periods:  # line the plain middle up with whole repeats so tiles meet seamlessly
        P = min(periods) * u
        best = min((S + i * P / 40 for i in range(41)),
                   key=lambda s: sum(min((L - 2 * s) % P, P - (L - 2 * s) % P) ** 2 for L in (W * u, H * u)))
        if best <= limit * u:
            S = best

    need_px, reach_px = corner_depths(alpha, round(S / u), max(4, int(min(W, H) // 2 * 0.15)))
    edge_px = max(f["edge_depth"] for f in found)
    depth = (max(edge_px, need_px) + 1) * u
    if any(f.get("inner") for f in found):
        say("left out something in the middle (text or a picture) that isn't part of the frame; the plugin never "
            "draws the middle anyway")
    say(f"corners: the ornaments reach {num(S)} along the edges; the frame is {num(depth)} deep"
        + (f" (its edges alone {num(edge_px * u)})" if need_px > edge_px * 1.2 else ""))
    if (reach_px + 1) * u > depth * 1.25:
        warnings.append(f"bits of the corner ornaments reach {num((reach_px + 1) * u - depth)} past that, so they're "
                        "drawn over the window's corners; a bigger --border-size keeps them off it")

    if border_size:
        k = border_size / depth
    elif corner:
        k = corner / S
    else:
        k = min(BORDER_TARGET / depth, CORNER_TARGET / S)
        k = min(max(k, BORDER_MIN / depth), BORDER_MAX / depth)
    t = border_size or max(1, math.ceil(depth * k))
    c = corner or max(t, round(S * k))
    # the plugin needs at least a pixel of edge between the corners once it's scaled: shrink the corners if not
    while min(round(W * u * c / S), round(H * u * c / S)) - 2 * c < 1 and S > 2:
        S *= 0.97
        c = corner or max(t, round(S * k))

    # the copy: cropped to the frame, sized in its own units so data-slice means what it says, settings attached
    crop = [vx + x0 * u, vy + y0 * u, (x1 - x0) * u, (y1 - y0) * u]
    root.set("viewBox", " ".join(num(v) for v in crop))
    root.set("width", num(crop[2]))
    root.set("height", num(crop[3]))
    root.set("data-border-size", str(t))
    root.set("data-slice", str(round(S)))
    root.set("data-corner", str(c))
    root.set("data-edges", "repeat" if periods else "stretch")
    root.set("data-fitted-by", "fit.py")

    if os.path.abspath(out) == base and not os.path.exists(out + ".orig"):
        os.replace(out, out + ".orig")
        say(f"kept the original as {name}.svg.orig")
    with open(out + ".tmp", "wb") as fh:
        fh.write(to_bytes(tree))
    os.replace(out + ".tmp", out)
    say(f'wrote {name}.svg: data-border-size="{t}" data-slice="{round(S)}" data-corner="{c}" '
        f'data-edges="{root.get("data-edges")}"')
    for w in warnings:
        say("warning: " + w)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("svg", help="the downloaded svg")
    ap.add_argument("--name", help="what to call it here (default: its file name)")
    ap.add_argument("--border-size", type=int, help="border thickness on screen, instead of the suggested one")
    ap.add_argument("--corner", type=int, help="corner size on screen, instead of the suggested one")
    ap.add_argument("--wall", help="wallpaper for the preview (default: the current one)")
    ap.add_argument("--no-preview", action="store_true", help="don't render a preview")
    ap.add_argument("--force", action="store_true", help="overwrite a frame of the same name that fit.py didn't make")
    args = ap.parse_args()

    name = args.name or re.sub(r"\.svg(\.orig)?$", "", os.path.basename(args.svg))
    print(os.path.basename(args.svg))
    out = fit(args.svg, name, args.border_size, args.corner, args.force)

    if not args.no_preview:
        sys.path.insert(0, HERE)
        sys.dont_write_bytecode = True
        import preview  # noqa: E402

        preview.ROUNDING = preview.live_rounding()
        preview.INACTIVE_ALPHA = preview.configured_inactive_alpha()
        wall = args.wall or preview.current_wallpaper()
        if wall:
            scene, o = preview.scene_for(out, wall, {})
            path = f"/tmp/{name}-preview.png"
            preview.sheet(scene, o).save(path)
            say(f"preview: {path}")
    say(f'to use it: local style = "{name}" in ~/.config/hypr/borders.lua')


if __name__ == "__main__":
    main()
