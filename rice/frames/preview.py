#!/usr/bin/env python3
"""Previews frames against a wallpaper without touching Hyprland.

Any svg works: a name from this folder or a path. Its colour tokens are filled with the wallpaper's matugen colours
(a dry run, like the wallpaper picker does), its settings are read from its <svg> tag like borders.lua does, and it
is cut up and placed exactly like the plugin does it, around a mock-up of the rice: translucent blurred windows with
their border and shadow, and the neighbouring scrolling columns. By default the wallpaper is the current one, the
rounding is the live one and inactive_alpha is borders.lua's. For an svg without a data-slice it also suggests one.

    ./preview.py myframe
    ./preview.py ~/Downloads/frame.svg --slice 40 --border-size 18
    ./preview.py sakura --wall ~/Pictures/wallpapers/0qg185.jpg --out /tmp/sakura.png
    ./preview.py halo neon torii --corners --wall a.jpg --wall b.jpg --out /tmp/grid.png

Needs matugen, python-gobject with librsvg's typelib, pycairo and pillow.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Gio, GLib, Rsvg  # noqa: E402
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # no __pycache__ next to the frames
import generate  # noqa: E402

CACHE = os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "borders-plus-plus-svg")
TOKEN = re.compile(r"\{\{\s*colors\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\s*\}\}")
COLORS_LUA = os.path.expanduser("~/.config/hypr/colors.lua")
BORDERS_LUA = [os.path.expanduser("~/.config/hypr/borders.lua"), os.path.join(HERE, "..", "borders.lua")]

# what borders.lua uses for svgs that don't set them
DEFAULTS = {"border-size": 14, "slice": 0, "corner": 0, "edges": "stretch"}

# the rice
SW, SH = 1920, 1200
GAPS_IN, GAPS_OUT, BAR = 5, 20, 36
COLUMN = 0.90
ACTIVE_OPACITY, INACTIVE_OPACITY = 0.65, 0.55
INACTIVE_ALPHA = 1.0  # the plugin's inactive_alpha, set with --inactive-alpha
ROUNDING = 35  # decoration.rounding, set with --rounding


def lround(v):
    return int(math.floor(v + 0.5)) if v >= 0 else -int(math.floor(-v + 0.5))


def font(names, size):
    for name in names:
        path = subprocess.run(["fc-match", "-f", "%{file}", name], capture_output=True, text=True).stdout
        if path:
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def palette(img):
    os.makedirs(CACHE, exist_ok=True)
    st = os.stat(img)
    key = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{os.path.abspath(img)}-{st.st_size}-{int(st.st_mtime)}") + ".json"
    path = os.path.join(CACHE, key)
    if not os.path.exists(path):
        out = subprocess.run(["matugen", "image", img, "--source-color-index", "0", "--dry-run", "-j", "hex", "-q"],
                             capture_output=True, text=True, check=True).stdout
        with open(path, "w") as fh:
            json.dump({k: v["default"]["color"] for k, v in json.loads(out)["colors"].items()}, fh)
    with open(path) as fh:
        return json.load(fh)


def fill(template, pal):
    """the same tokens borders.lua fills: {{colors.<role>.default.hex}}, .dark, and .hex_stripped"""
    bad = sorted({".".join(m) for m in TOKEN.findall(template)
                  if m[0] not in pal or m[1] not in ("default", "dark") or m[2] not in ("hex", "hex_stripped")})
    if bad:
        print(f"note: borders.lua can't fill {', '.join(bad)}, they stay as they are", file=sys.stderr)

    def rep(m):
        role, mode, fmt = m.groups()
        if role not in pal or mode not in ("default", "dark") or fmt not in ("hex", "hex_stripped"):
            return m.group(0)
        return pal[role] if fmt == "hex" else pal[role].lstrip("#")

    return TOKEN.sub(rep, template)


def resolve(frame):
    """a name from this folder or a path to an svg"""
    for path in (frame, os.path.join(HERE, frame + ".svg")):
        if path.endswith(".svg") and os.path.isfile(path):
            return path
    names = sorted(f[:-4] for f in os.listdir(HERE) if f.endswith(".svg"))
    sys.exit(f"no frame called {frame}, the ones here are: {', '.join(names)}")


def settings(svg, overrides):
    """borders.lua's reading of the data- attributes on the <svg> tag, then anything given on the command line"""
    tag = (re.search(r"<svg[^>]*>", svg) or [""])[0]
    out = {}
    for key, default in DEFAULTS.items():
        m = re.search(r"\sdata-" + key + r"""\s*=\s*["']([^"']*)["']""", tag)
        value = m.group(1) if m else None
        if key != "edges":
            try:
                value = lround(float(value))
            except (TypeError, ValueError):
                value = None
        out[key] = overrides.get(key) if overrides.get(key) is not None else default if value is None else value
    out["has-slice"] = bool(re.search(r"\sdata-slice\s*=", tag)) or overrides.get("slice") is not None
    return out


def live_rounding():
    try:
        out = subprocess.run(["hyprctl", "-j", "getoption", "decoration:rounding"], capture_output=True, text=True,
                             timeout=2).stdout
        return int(json.loads(out)["int"])
    except Exception:
        return 35


def current_wallpaper():
    try:
        with open(COLORS_LUA) as fh:
            return re.search(r'image\s*=\s*"([^"]+)"', fh.read()).group(1)
    except Exception:
        return None


def configured_inactive_alpha():
    for path in BORDERS_LUA:
        try:
            with open(path) as fh:
                return float(re.search(r"inactive_alpha\s*=\s*([0-9.]+)", fh.read()).group(1))
        except Exception:
            continue
    return 1.0


def rgb(h, a=1.0):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def rgb8(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def cairo_to_pil(surf):
    surf.flush()
    return Image.frombuffer("RGBA", (surf.get_width(), surf.get_height()), bytes(surf.get_data()), "raw", "BGRa",
                            surf.get_stride(), 1).copy()


# ---- what the plugin does (svgSlices.cpp) ----

def load(svg, base):
    # with the svg's own file as the base, so images it links to next to it still load
    stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(svg.encode()))
    handle = Rsvg.Handle.new_from_stream_sync(stream, Gio.File.new_for_path(base), Rsvg.HandleFlags.FLAGS_NONE, None)
    ok, w, h = handle.get_intrinsic_size_in_pixels()
    if not ok:
        has_vb, vb = handle.get_intrinsic_dimensions()[4:6]
        if not has_vb:
            sys.exit("the svg has neither a width/height nor a viewBox")
        w, h = vb.width, vb.height
    return handle, w, h


def layer_for(handle, rounding):
    """the frame for the closest rounding the svg has, or all of it for a plain svg"""
    variants = [r for r in range(201) if handle.has_sub(f"#rounding-{r}")]
    return f"#rounding-{min(variants, key=lambda r: abs(r - rounding))}" if variants else None


def rasterize(svg, base, slice_, c, rounding):
    handle, w, h = load(svg, base)
    layer = layer_for(handle, rounding)
    if slice_ <= 0:
        slice_ = min(w, h) / 3
    if slice_ * 2 >= w or slice_ * 2 >= h:
        sys.exit(f"data-slice must be less than half of the svg's width and height ({w:g} x {h:g})")
    W, H = lround(w * c / slice_), lround(h * c / slice_)
    if W - 2 * c < 1 or H - 2 * c < 1:
        sys.exit("data-slice leaves no room for the edges")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    handle.render_layer(cairo.Context(surf), layer, vp)
    return cairo_to_pil(surf)


def measure(svg, base, rounding):
    """roughly how deep the frame's border is on its widest side, in the svg's own units, or None"""
    handle, w, h = load(svg, base)
    scale = 600 / min(w, h)
    W, H = lround(w * scale), lround(h * scale)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    vp = Rsvg.Rectangle()
    vp.x, vp.y, vp.width, vp.height = 0, 0, W, H
    handle.render_layer(cairo.Context(surf), layer_for(handle, rounding), vp)
    alpha = cairo_to_pil(surf).getchannel("A")
    deepest = 0
    for side in range(4):
        img = alpha.rotate(90 * side, expand=True)  # each side in turn becomes the top edge
        strip = img.crop((img.width // 4, 0, img.width * 3 // 4, img.height // 2))
        rows = list(strip.resize((1, strip.height), Image.BOX).tobytes())  # each row's average alpha
        top = max(rows) if rows else 0
        if top <= 0:
            continue
        inked = [y for y, v in enumerate(rows) if v > top * 0.12]
        deepest = max(deepest, inked[-1] + 1)
    if not deepest or deepest > min(W, H) * 0.4:  # nothing there, or not shaped like a frame
        return None
    return math.ceil(deepest / scale * 1.05)


def pieces(img, t, c):
    W, H = img.size
    return {"tl": img.crop((0, 0, c, c)), "t": img.crop((c, 0, W - c, t)), "tr": img.crop((W - c, 0, W, c)),
            "r": img.crop((W - t, c, W, H - c)), "br": img.crop((W - c, H - c, W, H)),
            "b": img.crop((c, H - t, W - c, H)), "bl": img.crop((0, H - c, c, H)), "l": img.crop((0, c, t, H - c))}


def paste(layer, img, pos):
    x, y = pos
    sx, sy = max(0, -x), max(0, -y)
    w, h = min(img.width - sx, layer.width - x - sx), min(img.height - sy, layer.height - y - sy)
    if w > 0 and h > 0:
        layer.alpha_composite(img.crop((sx, sy, sx + w, sy + h)), (x + sx, y + sy))


def edge(layer, tex, box, horizontal, repeat):
    x, y, w, h = box
    length = w if horizontal else h
    if length < 1:
        return
    tile = tex.width if horizontal else tex.height
    n = max(1, lround(length / tile)) if repeat and tile >= 1 else 1
    start = x if horizontal else y
    for i in range(n):
        a, b = lround(start + length * i / n), lround(start + length * (i + 1) / n)
        if b > a:
            piece = tex.resize((b - a, h) if horizontal else (w, b - a), Image.BILINEAR)
            paste(layer, piece, (a, y) if horizontal else (x, a))


def draw_frame(layer, frame, o):
    p, t, c, repeat = frame["pieces"], frame["t"], frame["c"], frame["repeat"]
    ox, oy, ow, oh = o
    R, B = ox + ow, oy + oh
    for key, pos in (("tl", (ox, oy)), ("tr", (R - c, oy)), ("br", (R - c, B - c)), ("bl", (ox, B - c))):
        paste(layer, p[key], pos)
    edge(layer, p["t"], (ox + c, oy, ow - 2 * c, t), True, repeat)
    edge(layer, p["b"], (ox + c, B - t, ow - 2 * c, t), True, repeat)
    edge(layer, p["l"], (ox, oy + c, t, oh - 2 * c), False, repeat)
    edge(layer, p["r"], (R - t, oy + c, t, oh - 2 * c), False, repeat)


# ---- the rest of the desktop ----

def rrect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def mask(size, box, r):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, *size)
    cr = cairo.Context(surf)
    rrect(cr, *box, r)
    cr.set_source_rgba(1, 1, 1, 1)
    cr.fill()
    return cairo_to_pil(surf).getchannel("A")


def window(scene, blurred, pal, o, frame, active, text):
    rounding, border, t = ROUNDING, generate.BORDER, frame["t"]
    outer = generate.radius_for(rounding)  # the border's outer radius, square when rounding is 0
    ox, oy, ow, oh = o
    bx, by, bw, bh = ox + t, oy + t, ow - 2 * t, oh - 2 * t
    cx, cy, cw, ch = bx + border, by + border, bw - 2 * border, bh - 2 * border

    sh = mask(scene.size, (ox - 2, oy - 2, ow + 4, oh + 4), outer + t + 2).filter(ImageFilter.GaussianBlur(9))
    sh = Image.composite(Image.new("L", scene.size, 0), sh, mask(scene.size, o, outer + t))
    shadow = Image.new("RGBA", scene.size, rgb8(pal["shadow"]))
    shadow.putalpha(sh.point(lambda v: int(v * 0.8)))
    scene.alpha_composite(shadow)

    content = Image.blend(blurred, Image.new("RGBA", scene.size, rgb8(pal["background"])),
                          ACTIVE_OPACITY if active else INACTIVE_OPACITY)
    if text:
        d, mono = ImageDraw.Draw(content), font(["JetBrainsMono Nerd Font", "monospace"], 17)
        for i, line in enumerate(text):
            x = cx + 32
            for seg, col in line:
                d.text((x, cy + 30 + 25 * i), seg, font=mono, fill=rgb8(pal[col]))
                x += mono.getlength(seg)
    scene.paste(content, (0, 0), mask(scene.size, (cx, cy, cw, ch), rounding))

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, *scene.size)
    cr = cairo.Context(surf)
    rrect(cr, bx, by, bw, bh, outer)
    rrect(cr, cx, cy, cw, ch, rounding)
    cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    g = cairo.LinearGradient(bx, by, bx + bw, by + bh)
    a, b = ("primary", "tertiary") if active else ("surface_container", "outline")
    g.add_color_stop_rgba(0, *rgb(pal[a]))
    g.add_color_stop_rgba(1, *rgb(pal[b]))
    cr.set_source(g)
    cr.fill()
    scene.alpha_composite(cairo_to_pil(surf))

    layer = Image.new("RGBA", scene.size, (0, 0, 0, 0))
    draw_frame(layer, frame, o)
    if not active and INACTIVE_ALPHA < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: round(v * INACTIVE_ALPHA)))
    scene.alpha_composite(layer)


TEXT = [
    [("igris@igris ", "on_surface"), ("~/borders-plus-plus-svg", "primary"), (" > make", "on_surface")],
    [("g++ -O2 -shared -fPIC -std=c++2b main.cpp borderDeco.cpp svgSlices.cpp -o borders-plus-plus-svg.so",
      "on_surface_variant")],
    [("igris@igris ", "on_surface"), ("~/borders-plus-plus-svg", "primary"),
     (" > hyprctl plugin load $PWD/borders-plus-plus-svg.so", "on_surface")],
    [("ok", "on_surface_variant")],
    [("igris@igris ", "on_surface"), ("~/borders-plus-plus-svg", "primary"), (" > █", "on_surface")],
]


def scene_for(frame_name, wall, overrides):
    path = resolve(frame_name)
    pal = palette(wall)
    with open(path) as fh:
        svg = fill(fh.read(), pal)
    st = settings(svg, overrides)
    t, c = st["border-size"], max(st["border-size"], st["corner"])
    base = os.path.abspath(path)
    frame = {"pieces": pieces(rasterize(svg, base, st["slice"], c, ROUNDING), t, c), "t": t, "c": c,
             "repeat": st["edges"] == "repeat"}
    if not st["has-slice"]:
        depth = measure(svg, base, ROUNDING)
        if depth:
            print(f"{os.path.basename(path)} has no data-slice: its border looks about {depth} units deep, so try "
                  f'data-slice="{depth}" (and data-corner the same as data-border-size), or let ./fit.py measure it '
                  "properly", file=sys.stderr)

    img = ImageOps.fit(Image.open(wall).convert("RGB"), (SW, SH), Image.LANCZOS).convert("RGBA")
    blurred = ImageEnhance.Color(img.filter(ImageFilter.GaussianBlur(36))).enhance(1.4)
    scene = img.copy()

    ww = round(COLUMN * (SW - 2 * GAPS_OUT))
    x, y, h = (SW - ww) // 2, BAR + GAPS_OUT, SH - BAR - 2 * GAPS_OUT
    for nx in (x - ww - 2 * GAPS_IN, x + ww + 2 * GAPS_IN):
        window(scene, blurred, pal, (nx, y, ww, h), frame, False, None)
    window(scene, blurred, pal, (x, y, ww, h), frame, True, TEXT)
    return scene.convert("RGB"), (x, y, ww, h)


def sheet(scene, o, zoom=3):
    """the whole screen, with the top-left corner and the gap between two windows blown up beside it"""
    x, y, w, h = o
    zw, zh = 640 // zoom, 400 // zoom
    out = Image.new("RGB", (1920, 800), (17, 17, 17))
    out.paste(scene.resize((1280, 800), Image.LANCZOS), (0, 0))
    out.paste(scene.crop((x - 14, y - 14, x - 14 + zw, y - 14 + zh)).resize((640, 400), Image.NEAREST), (1280, 0))
    out.paste(scene.crop((x + w - zw // 2, y + h - zh + 14, x + w + zw // 2, y + h + 14)).resize((640, 400),
                                                                                               Image.NEAREST), (1280, 400))
    return out


def corners(styles, walls, overrides):
    """the top-left corner of every frame (rows) on every wallpaper (columns)"""
    tw, th = 480, 300
    out = Image.new("RGB", (len(walls) * tw, len(styles) * th), (17, 17, 17))
    label = font(["Noto Sans:bold", "sans"], 18)
    d = ImageDraw.Draw(out)
    for r, style in enumerate(styles):
        for c, wall in enumerate(walls):
            scene, (x, y, w, h) = scene_for(style, wall, overrides)
            out.paste(scene.crop((x - 10, y - 10, x + 150, y + 90)).resize((tw, th), Image.LANCZOS), (c * tw, r * th))
        name = os.path.basename(style)[:-4] if style.endswith(".svg") else style
        w = int(label.getlength(name)) + 20
        d.rounded_rectangle((tw - w - 10, r * th + th - 40, tw - 10, r * th + th - 10), radius=15, fill=(0, 0, 0, 170))
        d.text((tw - w, r * th + th - 37), name, font=label, fill=(255, 255, 255))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("frames", nargs="+", metavar="frame", help="a name from this folder, or a path to an svg")
    ap.add_argument("--wall", action="append", help="wallpaper to take colours from, repeatable (default: the current one)")
    ap.add_argument("--out", help="png to write (default: /tmp/<frame>-preview.png)")
    ap.add_argument("--full", action="store_true", help="just the 1920x1200 screen")
    ap.add_argument("--corners", action="store_true", help="a grid of top-left corners, frames x wallpapers")
    ap.add_argument("--rounding", type=int, help="the windows' decoration.rounding (default: the live one)")
    ap.add_argument("--inactive-alpha", type=float, help="the plugin's inactive_alpha (default: borders.lua's)")
    for key in ("border-size", "slice", "corner"):
        ap.add_argument("--" + key, type=int, help=f"instead of the svg's data-{key}")
    ap.add_argument("--edges", choices=["stretch", "repeat"], help="instead of the svg's data-edges")
    args = ap.parse_args()

    global INACTIVE_ALPHA, ROUNDING
    ROUNDING = args.rounding if args.rounding is not None else live_rounding()
    INACTIVE_ALPHA = args.inactive_alpha if args.inactive_alpha is not None else configured_inactive_alpha()
    walls = args.wall or [current_wallpaper()]
    if not walls[0]:
        sys.exit("no --wall given and couldn't read the current wallpaper from colors.lua")
    overrides = {"border-size": args.border_size, "slice": args.slice, "corner": args.corner, "edges": args.edges}
    name = os.path.basename(args.frames[0])
    out = args.out or f"/tmp/{name[:-4] if name.endswith('.svg') else name}-preview.png"

    if args.corners:
        corners(args.frames, walls, overrides).save(out)
    else:
        scene, o = scene_for(args.frames[0], walls[0], overrides)
        (scene if args.full else sheet(scene, o)).save(out)
    print(out)


if __name__ == "__main__":
    main()
