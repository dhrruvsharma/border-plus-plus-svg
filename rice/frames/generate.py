#!/usr/bin/env python3
"""Generates the matugen SVG frame templates for borders-plus-plus-svg.

Every frame hugs the window: its inner edge is cut with the radius of the window border's outer edge, so
nothing is drawn over the window. Each svg holds one frame per window rounding (top-level "rounding-N"
groups) and the plugin draws the one closest to each window's actual rounding, so the frames keep fitting
when a desktop theme changes `decoration.rounding`. 1 svg unit is 1 logical pixel, so a frame's svg_slice
and svg_corner are the same number.

    ./generate.py                                  # the roundings below, border 2
    ./generate.py --rounding 0,8,20 --border 3

Writes <style>.svg next to this file, each carrying its own plugin settings as data- attributes on its <svg> tag
and matugen colour tokens that borders.lua fills in from the wallpaper.
"""
import argparse
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# hyprland.lua's rounding and the ones the Quickshell desktop themes set, and general.border_size
ROUNDINGS, BORDER = [0, 1, 3, 4, 6, 8, 10, 14, 18, 35], 2
STYLES = {}


def C(role):
    """a matugen colour"""
    return "{{colors.%s.default.hex}}" % role


def n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def pts(points):
    return " ".join(f"{n(x)},{n(y)}" for x, y in points)


def tangent(deg):
    """direction of travel at `deg` degrees when going clockwise around a ring"""
    r = math.radians(deg)
    return -math.sin(r), math.cos(r)


def style(name, band, tile, edges, about, corner=64):
    def wrap(fn):
        STYLES[name] = {"band": band, "tile": tile, "edges": edges, "about": about, "min_corner": corner,
                        "build": fn}
        return fn

    return wrap


def radius_for(rounding):
    """radius of the window border's outer edge (Hyprland squares the border off too when rounding is 0)"""
    return 0 if rounding == 0 else rounding + BORDER


def corner_size(band, minimum=64):
    # room for the roundest variant's corner plus a little for ornaments, as a multiple of 4
    R = max(radius_for(r) for r in ROUNDINGS)
    return max(minimum, -(-(band + R + 8) // 4) * 4)


def finalize():
    for st in STYLES.values():
        st["corner"] = st["slice"] = corner_size(st["band"], st["min_corner"])


class Frame:
    def __init__(self, band, tile, corner, R):
        self.t, self.tile = band, tile
        self.R = R  # radius of the window border's outer edge
        self.c = corner
        self.W = self.H = 2 * self.c + tile
        self.a = band + self.R  # the corner arcs are centred a units in from both edges
        # radius of the biggest circle fitting in a corner between the frame's outer edges and the window
        self.nook = (self.a * math.sqrt(2) - self.R) / (1 + math.sqrt(2))
        self.defs, self.body = [], []

    # ---- geometry ----

    def centre(self, k):
        """centre of corner k's arcs: 0 top-left, 1 top-right, 2 bottom-right, 3 bottom-left"""
        a, W, H = self.a, self.W, self.H
        return ((a, a), (W - a, a), (W - a, H - a), (a, H - a))[k]

    @staticmethod
    def diag(k):
        """direction from corner k's centre out to the corner itself, in degrees (y points down)"""
        return 225 + 90 * k

    def radius(self, d):
        """radius of the ring d units in from the outer edge"""
        return self.R + self.t - d

    def polar(self, k, rho, deg):
        cx, cy = self.centre(k)
        r = math.radians(deg)
        return cx + rho * math.cos(r), cy + rho * math.sin(r)

    def along(self, side, u, d):
        """u units along edge tile `side` (0 top, 1 right, 2 bottom, 3 left, running clockwise), d units in"""
        c, W, H = self.c, self.W, self.H
        return ((c + u, d), (W - d, c + u), (W - c - u, H - d), (d, H - c - u))[side]

    def ring(self, d):
        """rounded rect d units in from the outer edge, concentric with the window's border"""
        r, x0, y0, x1, y1 = self.radius(d), d, d, self.W - d, self.H - d
        A = f"A{n(r)},{n(r)} 0 0 1"
        return (f"M{n(x0 + r)},{n(y0)} H{n(x1 - r)} {A} {n(x1)},{n(y0 + r)} V{n(y1 - r)} {A} {n(x1 - r)},{n(y1)} "
                f"H{n(x0 + r)} {A} {n(x0)},{n(y1 - r)} V{n(y0 + r)} {A} {n(x0 + r)},{n(y0)} Z")

    def run(self, d, k, start, stop):
        """open path along ring d from corner k at `start` degrees, clockwise to the next corner at `stop`"""
        r, k1 = self.radius(d), (k + 1) % 4
        p = [self.polar(k, r, start), self.polar(k, r, self.diag(k) + 45), self.polar(k1, r, self.diag(k1) - 45),
             self.polar(k1, r, stop)]
        A = f"A{n(r)},{n(r)} 0 0 1"
        return f"M{pts(p[:1])} {A} {pts(p[1:2])} L{pts(p[2:3])} {A} {pts(p[3:])}"

    def corner_run(self, d, k, ext):
        """open path along ring d around corner k, running `ext` units along both edges"""
        r = self.radius(d)
        a0, a1 = self.diag(k) - 45, self.diag(k) + 45
        p0, p1 = self.polar(k, r, a0), self.polar(k, r, a1)
        t0, t1 = tangent(a0), tangent(a1)
        s = (p0[0] - ext * t0[0], p0[1] - ext * t0[1])
        e = (p1[0] + ext * t1[0], p1[1] + ext * t1[1])
        return f"M{pts([s])} L{pts([p0])} A{n(r)},{n(r)} 0 0 1 {pts([p1])} L{pts([e])}"

    def dots(self, d, spacing):
        """evenly spaced points along ring d that line up with the edge tiles, so repeat mode stays seamless"""
        out = []
        for side in range(4):
            out += [self.along(side, spacing / 2 + spacing * i, d) for i in range(int(self.tile // spacing))]
        # the straight bit of each corner piece continues the edge lattice up to where the arc starts
        straight = []
        x = self.c - spacing / 2
        while x > self.a:
            straight.append(x)
            x -= spacing
        gap = (straight[-1] - self.a) if straight else 0
        r = self.radius(d)
        arc = math.pi / 2 * r
        m = max(1, round((arc + 2 * gap) / spacing))
        step = (arc + 2 * gap) / m
        for k in range(4):
            a0, a1 = self.diag(k) - 45, self.diag(k) + 45
            for x in straight:  # mirrored onto both edges of this corner
                off = x - self.a
                for a, sign in ((a0, -1), (a1, 1)):
                    (bx, by), t = self.polar(k, r, a), tangent(a)
                    out.append((bx + sign * off * t[0], by + sign * off * t[1]))
            s = step - gap
            while s < arc - 1e-6:
                out.append(self.polar(k, r, self.diag(k) - 45 + math.degrees(s / r)))
                s += step
        return out

    def outside_window(self):
        return f"M0,0 H{self.W} V{self.H} H0 Z {self.ring(self.t)}"

    # ---- defs ----

    def clip_outside(self, id="frame"):
        """keeps glows and ornaments off the window, which the corner pieces would otherwise draw over"""
        self.defs.append(f'<clipPath id="{id}"><path clip-rule="evenodd" d="{self.outside_window()}"/></clipPath>')

    def fade_out(self, id="fade", inset=2.2, sd=1.1):
        """mask that fades to nothing along a rounded outline just inside the frame's outer edge, so glows don't
        end in a hard line where the frame stops (or in a square at the corners)"""
        self.blur(id + "-blur", sd)
        self.defs.append(f'<mask id="{id}" maskUnits="userSpaceOnUse" x="0" y="0" width="{self.W}" height="{self.H}">'
                         f'<path d="{self.ring(inset)}" fill="#fff" filter="url(#{id}-blur)"/></mask>')

    def blur(self, id, sd):
        self.defs.append(f'<filter id="{id}" filterUnits="userSpaceOnUse" x="-40" y="-40" width="{self.W + 80}" '
                         f'height="{self.H + 80}"><feGaussianBlur stdDeviation="{n(sd)}"/></filter>')

    def variant(self, rounding):
        """this frame as the group the plugin picks for windows with `rounding`, its ids made unique to it"""
        sfx = f"-r{rounding}"
        text = "".join(f"    {d}\n" for d in (["<defs>"] + ["  " + d for d in self.defs] + ["</defs>"]
                                               if self.defs else []))
        text += "".join(f"    {b}\n" for b in self.body)
        text = re.sub(r'id="([^"]+)"', lambda m: f'id="{m.group(1)}{sfx}"', text)
        text = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{m.group(1)}{sfx})", text)
        return f'  <g id="rounding-{rounding}">\n{text}  </g>\n'


# ---- shapes ----

def sparkle(x, y, r, rot=0.0, pinch=0.16):
    """path and transform of a four-pointed star"""
    k = r * pinch
    d = (f"M0,{n(-r)} Q{n(k)},{n(-k)} {n(r)},0 Q{n(k)},{n(k)} 0,{n(r)} Q{n(-k)},{n(k)} {n(-r)},0 "
         f"Q{n(-k)},{n(-k)} 0,{n(-r)} Z")
    return d, f"translate({n(x)} {n(y)}) rotate({n(rot)})"


def petal(length, width):
    """sakura petal with its base at the origin, pointing up, notched at the tip"""
    L, w = length, width / 2
    return (f"M0,0 C{n(-.55 * w)},{n(-.15 * L)} {n(-1.05 * w)},{n(-.55 * L)} {n(-.75 * w)},{n(-.85 * L)} "
            f"Q{n(-.5 * w)},{n(-1.02 * L)} {n(-.12 * w)},{n(-.97 * L)} L0,{n(-.86 * L)} L{n(.12 * w)},{n(-.97 * L)} "
            f"Q{n(.5 * w)},{n(-1.02 * L)} {n(.75 * w)},{n(-.85 * L)} C{n(1.05 * w)},{n(-.55 * L)} "
            f"{n(.55 * w)},{n(-.15 * L)} 0,0 Z")


def blossom(x, y, r, rot):
    out = [f'<g transform="translate({n(x)} {n(y)}) rotate({n(rot)})">']
    for i in range(5):
        out.append(f'  <path d="{petal(r, 1.25 * r)}" transform="rotate({72 * i})" fill="url(#petal)" '
                   f'stroke="{C("primary_container")}" stroke-width=".5" stroke-opacity=".6"/>')
    out.append(f'  <circle r="{n(.27 * r)}" fill="{C("primary_container")}"/>')
    for i in range(5):
        a = math.radians(72 * i + 36)
        out.append(f'  <circle cx="{n(.4 * r * math.cos(a))}" cy="{n(.4 * r * math.sin(a))}" '
                   f'r="{n(max(.5, .075 * r))}" fill="{C("tertiary")}"/>')
    out.append("</g>")
    return out


def loose_petal(x, y, length, rot):
    """a single petal centred on x, y"""
    return (f'<path d="{petal(length, 1.1 * length)}" '
            f'transform="translate({n(x)} {n(y)}) rotate({n(rot)}) translate(0 {n(length / 2)})" '
            f'fill="url(#petal)" stroke="{C("primary_container")}" stroke-width=".4" stroke-opacity=".5"/>')


def tomoe(f, k, rho, deg, r):
    """tomoe on corner k's ring of radius rho at `deg` degrees, its head leading clockwise and its tail curling
    outwards. Drawn like half a yin-yang: a half disc of radius 2r, plus the head, minus its twin."""
    px, py = f.polar(k, rho, deg)
    a = math.radians(deg)
    o, t = (math.cos(a), math.sin(a)), tangent(deg)
    # local x points inwards and local y backwards along the ring; the shape's middle (-r/2, 0) sits on the ring
    m = (-o[0], -o[1], -t[0], -t[1], px - r / 2 * o[0], py - r / 2 * o[1])
    R2 = n(2 * r)
    d = (f"M0,-{R2} A{R2},{R2} 0 0 0 -{R2},0 A{R2},{R2} 0 0 0 0,{R2} A{n(r)},{n(r)} 0 0 1 0,0 "
         f"A{n(r)},{n(r)} 0 0 0 0,-{R2} Z")
    return f'<path d="{d}" transform="matrix({" ".join(f"{v:.4f}".rstrip("0").rstrip(".") for v in m)})"/>'


# ---- the frames ----

# the corner room the ornaments were drawn for: rounding 35, border 2 and a 14 unit band
NOOK = (51 * math.sqrt(2) - 37) / (1 + math.sqrt(2))


@style("halo", band=14, tile=48, edges="stretch",
       about="A soft glow lifting off the window, with a fine line that shifts colour corner to corner.")
def halo(f):
    f.clip_outside()
    f.blur("wide", 6)
    f.blur("soft", 2.2)
    f.blur("glint", 1.5)
    f.defs.append(f'<linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{f.W}" y2="{f.H}">'
                  f'<stop offset="0" stop-color="{C("tertiary")}"/><stop offset=".5" stop-color="{C("primary")}"/>'
                  f'<stop offset="1" stop-color="{C("secondary")}"/></linearGradient>')
    f.fade_out(inset=1.8, sd=1.4)
    inner = f.ring(f.t)
    f.body += [
        '<g clip-path="url(#frame)" mask="url(#fade)" fill="none">',
        f'  <path d="{inner}" stroke="{C("primary")}" stroke-width="18" stroke-opacity=".5" filter="url(#wide)"/>',
        f'  <path d="{inner}" stroke="{C("primary")}" stroke-width="6" filter="url(#soft)"/>',
        "</g>",
        f'<path d="{f.ring(1)}" fill="none" stroke="{C("outline_variant")}" stroke-width=".8"/>',
        f'<path d="{f.ring(8)}" fill="none" stroke="url(#sheen)" stroke-width="1.4"/>',
    ]
    # glints where the light catches the line: bright top-left, fainter bottom-right
    g = ['<g clip-path="url(#frame)">']
    for k, r in ((0, 7), (2, 4.5)):
        x, y = f.polar(k, f.radius(8), f.diag(k))
        d, tr = sparkle(x, y, r)
        g += [f'  <path d="{d}" transform="{tr}" fill="{C("primary")}" filter="url(#glint)"/>',
              f'  <path d="{d}" transform="{tr}" fill="{C("primary_fixed")}"/>']
    f.body += g + ["</g>"]


@style("tomoe", band=18, tile=48, edges="stretch",
       about="Sharingan rings around the window with a tomoe at every corner, all turning the same way.")
def tomoe_frame(f):
    f.body += [
        f'<path fill-rule="evenodd" d="{f.ring(0)} {f.ring(f.t)}" fill="{C("primary_container")}" '
        f'fill-opacity=".55"/>',
        f'<path d="{f.ring(1.9)}" fill="none" stroke="{C("primary")}" stroke-width="1.2"/>',
        f'<path d="{f.ring(16.1)}" fill="none" stroke="{C("primary")}" stroke-width="1.2"/>',
        f'<g fill="{C("primary")}">',
    ]
    f.body += ["  " + tomoe(f, k, f.radius(9), f.diag(k), 3.9) for k in range(4)]
    f.body.append("</g>")


@style("sakura", band=14, tile=48, edges="stretch",
       about="Cherry blossoms and loose petals tucked into the window's corners, on a thin branch.")
def sakura(f):
    f.defs.append(f'<linearGradient id="petal" x1=".5" y1="1" x2=".5" y2="0"><stop offset="0" '
                  f'stop-color="{C("primary")}"/><stop offset="1" stop-color="{C("primary_fixed")}"/></linearGradient>')
    f.body.append(f'<path d="{f.ring(7)}" fill="none" stroke="{C("outline")}" stroke-width="1.2" '
                  f'stroke-opacity=".8"/>')
    W, H, s = f.W, f.H, f.nook / NOOK
    # blossoms: a cluster top-left, a smaller one bottom-right, single flowers and petals in the other two
    f.body += blossom(*f.polar(0, f.R + 17.5 * s, f.diag(0)), 13 * s, 8)
    f.body += blossom(39, 7, 5.8, 30)
    f.body += blossom(7.5, 41, 4.6, -12)
    f.body += blossom(*f.polar(2, f.R + 18.5 * s, f.diag(2)), 10 * s, 40)
    f.body += blossom(W - 38, H - 7, 5, 14)
    f.body += blossom(*f.polar(1, f.R + 19.5 * s, f.diag(1)), 7 * s, -20)
    f.body.append(loose_petal(W - 33, 7.5, 6, 70))
    x, y = f.polar(3, f.R + 19.5 * s, f.diag(3))
    f.body += [loose_petal(x, y, 6.5 * s, 35), loose_petal(23, H - 6.5, 5.5, -100)]


@style("neon", band=14, tile=48, edges="stretch",
       about="Two neon tubes, the outer one broken at the corners like a real sign, glowing into the gap.")
def neon(f):
    f.clip_outside()
    f.fade_out(inset=1.6, sd=1)
    f.blur("haze", 3.6)
    f.blur("glow", 1.6)
    gap = 21
    outer = " ".join(f.run(4.6, k, f.diag(k) + gap, f.diag((k + 1) % 4) - gap) for k in range(4))
    inner = f.ring(10)

    def tube(d, colour, core, width):
        return [f'  <path d="{d}" stroke="{C(colour)}" stroke-width="{n(width * 4.6)}" stroke-opacity=".55" '
                f'filter="url(#haze)"/>',
                f'  <path d="{d}" stroke="{C(colour)}" stroke-width="{n(width * 2)}" filter="url(#glow)"/>',
                f'  <path d="{d}" stroke="{C(colour)}" stroke-width="{n(width)}"/>',
                f'  <path d="{d}" stroke="{C(core)}" stroke-width="{n(width * .45)}"/>']

    f.body += ['<g clip-path="url(#frame)" mask="url(#fade)" fill="none" stroke-linecap="round">']
    f.body += tube(inner, "tertiary", "tertiary_fixed", 1.5)
    f.body += tube(outer, "primary", "primary_fixed", 2.1)
    f.body.append("</g>")
    # the electrodes capping each end of the outer tube
    r = f.radius(4.6)
    f.body.append(f'<g fill="{C("surface_container_highest")}" stroke="{C("outline")}" stroke-width=".5">')
    for k in range(4):
        for a in (f.diag(k) - gap, f.diag(k) + gap):
            x, y = f.polar(k, r, a)
            f.body.append(f'  <circle cx="{n(x)}" cy="{n(y)}" r="1.4"/>')
    f.body.append("</g>")


@style("hud", band=14, tile=48, edges="repeat", corner=72,
       about="A tactical readout: ruler ticks, heavy corner brackets and a different status mark after each one.")
def hud(f):
    straight = f.c - f.a  # straight run of each corner piece before its arc
    f.body.append(f'<path d="{f.ring(1.5)}" fill="none" stroke="{C("outline")}" stroke-width=".9"/>')
    # ruler ticks every 6 units, longer every 24, lined up across tiles and the corners' straight runs
    minor, major = [], []
    for side in range(4):
        for i in range(int(f.tile // 6)):
            u = 3 + 6 * i
            (major if u % 24 == 15 else minor).append((side, u))
        for off in range(3, straight, 6):
            minor += [(side, -off), (side, f.tile + off)]

    def tick(side, u, d0, d1):
        (x0, y0), (x1, y1) = f.along(side, u, d0), f.along(side, u, d1)
        return f"M{n(x0)},{n(y0)} L{n(x1)},{n(y1)}"

    f.body.append(f'<path d="{" ".join(tick(s, u, 1.5, 4.4) for s, u in minor)}" stroke="{C("outline")}" '
                  f'stroke-width=".8"/>')
    f.body.append(f'<path d="{" ".join(tick(s, u, 1.5, 7.5) for s, u in major)}" stroke="{C("primary")}" '
                  f'stroke-width="1.1"/>')
    # corner brackets with end stops
    ext = 9
    f.body.append(f'<path d="{" ".join(f.corner_run(7.5, k, ext) for k in range(4))}" fill="none" '
                  f'stroke="{C("primary")}" stroke-width="2.6"/>')
    stops = []
    for k in range(4):
        stops += [tick(k, -(straight - ext), 4.6, 10.4), tick((k + 3) % 4, f.tile + straight - ext, 4.6, 10.4)]
    f.body.append(f'<path d="{" ".join(stops)}" stroke="{C("primary")}" stroke-width="1.2"/>')

    # a status mark after each bracket, along the edge leaving the corner (drawn in that edge's frame)
    def mark(k, u, d, inner):
        x, y = f.along(k, u, d)
        return f'<g transform="translate({n(x)} {n(y)}) rotate({90 * k})">{inner}</g>'

    f.body += [
        mark(0, -6.2, 7.5, f'<rect x="-3.9" y="-1.3" width="2.6" height="2.6" fill="{C("tertiary")}"/>'
                           f'<rect x="1.3" y="-1.3" width="2.6" height="2.6" fill="{C("primary")}"/>'),
        mark(1, -5.6, 7.5, f'<rect x="-4.6" y="-2.1" width="9.2" height="4.2" fill="{C("tertiary")}"/>'
                           f'<path d="M-3.4,2.1 L-1.4,-2.1 M0.2,2.1 L2.2,-2.1 M3.8,2.1 L5,-0.4" '
                           f'stroke="{C("surface_container_lowest")}" stroke-width="1.3"/>'),
        mark(2, -6, 7.5, "".join(f'<circle cx="{n(-3.4 + 3.4 * i)}" cy="0" r="1.15" fill="{C(c)}"/>'
                                 for i, c in enumerate(("outline", "primary", "tertiary")))),
        mark(3, -6, 7.5, f'<path d="M-4.2,-2.2 L-2,0 L-4.2,2.2 M-0.2,-2.2 L2,0 L-0.2,2.2" fill="none" '
                         f'stroke="{C("tertiary")}" stroke-width="1.1"/>'),
    ]


@style("torii", band=20, tile=48, edges="stretch", corner=68,
       about="The window stands under a torii: an upswept kasagi and the nuki across the top, a pillar each side.")
def torii(f):
    W, H = f.W, f.H
    p0, p1 = 8, 14.5  # left pillar, mirrored on the right
    f.defs.append(f'<linearGradient id="wood" x1="0" y1="0" x2="1" y2="0"><stop offset="0" '
                  f'stop-color="{C("primary_fixed")}"/><stop offset=".3" stop-color="{C("primary")}"/>'
                  f'<stop offset="1" stop-color="{C("primary")}"/></linearGradient>')
    for x0, x1 in ((p0, p1), (W - p1, W - p0)):
        # hashira, with a dark kamebara sleeve at its foot
        f.body.append(f'<rect x="{n(x0)}" y="6" width="{n(x1 - x0)}" height="{n(H - 7.5)}" fill="url(#wood)"/>')
        f.body.append(f'<rect x="{n(x0 - 1.6)}" y="{n(H - 10)}" width="{n(x1 - x0 + 3.2)}" height="8.5" rx="1.2" '
                      f'fill="{C("surface_container_highest")}" stroke="{C("outline")}" stroke-width=".8"/>')
    f.body.append(f'<path d="M{n(p1 + 2)},{n(H - 1.3)} H{n(W - p1 - 2)}" stroke="{C("outline_variant")}" '
                  f'stroke-width="1"/>')
    # nuki, poking out past the pillars, held by dark kusabi wedges
    f.body.append(f'<rect x="3" y="12.5" width="{W - 6}" height="3.6" fill="{C("primary")}"/>')
    f.body += [f'<rect x="{n(x)}" y="12.5" width="2.3" height="3.6" fill="{C("surface_container_lowest")}"/>'
               for x in (p0 - 3.3, W - p0 + 1)]
    # kasagi sweeping up at both ends, under the dark shimaki
    top = f"M0,0 Q20,2.6 44,2.6 H{W - 44} Q{W - 20},2.6 {W},0"
    f.body += [f'<path d="{top} V4.2 Q{W - 22},9.6 {W - 48},9.6 H48 Q22,9.6 0,4.2 Z" fill="{C("primary")}"/>',
               f'<path d="{top} V1.8 Q{W - 20},5 {W - 44},5 H44 Q20,5 0,1.8 Z" '
               f'fill="{C("surface_container_lowest")}"/>']


@style("starlight", band=14, tile=144, edges="repeat",
       about="A dotted constellation line with four-pointed stars glinting in the corners and along the edges.")
def starlight(f):
    f.clip_outside()
    f.blur("glow", 1.6)
    W, H, s = f.W, f.H, f.nook / NOOK
    f.body.append(f'<path d="{f.ring(7)}" fill="none" stroke="{C("primary")}" stroke-width=".6" '
                  f'stroke-opacity=".22"/>')
    f.body.append(f'<g fill="{C("on_surface_variant")}" fill-opacity=".8">')
    f.body += [f'  <circle cx="{n(x)}" cy="{n(y)}" r=".85"/>' for x, y in f.dots(7, 6)]
    f.body.append("</g>")
    stars = [  # x, y, size, fill, glow
        (*f.polar(0, f.R + 18.5 * s, f.diag(0)), 11.5 * s, "primary_fixed", "primary"),
        (37, 7, 4.6, "primary_fixed", "primary"),
        (7, 34, 3, "on_surface", "primary"),
        (*f.polar(2, f.R + 19.5 * s, f.diag(2)), 8 * s, "tertiary_fixed", "tertiary"),
        (W - 34, H - 7, 3.2, "on_surface", "tertiary"),
        (*f.polar(1, f.R + 20.5 * s, f.diag(1)), 5 * s, "primary_fixed", "primary"),
        (*f.polar(3, f.R + 20.5 * s, f.diag(3)), 4.2 * s, "tertiary_fixed", "tertiary"),
    ]
    for side, u, size in ((0, 40, 3.6), (0, 101, 2.6), (1, 77, 3.2), (2, 22, 2.8), (2, 118, 3.8), (3, 61, 3)):
        stars.append((*f.along(side, u, 7), size, "primary_fixed", "primary"))
    f.body.append('<g clip-path="url(#frame)">')
    for x, y, r, fill, glow in stars:
        d, tr = sparkle(x, y, r)
        f.body += [f'  <path d="{d}" transform="{tr}" fill="{C(glow)}" filter="url(#glow)"/>',
                   f'  <path d="{d}" transform="{tr}" fill="{C(fill)}"/>']
    f.body.append("</g>")


@style("jewel", band=14, tile=48, edges="repeat",
       about="An art-deco band: gradient line, beads every 24px and a jewel at each corner.")
def jewel(f):
    f.defs.append(f'<linearGradient id="accent" x1="0" y1="0" x2="1" y2="1"><stop offset="0" '
                  f'stop-color="{C("primary")}"/><stop offset="1" stop-color="{C("tertiary")}"/></linearGradient>')
    f.body += [
        f'<path fill-rule="evenodd" d="{f.ring(0)} {f.ring(f.t)}" fill="{C("surface_container_low")}" '
        f'fill-opacity=".9"/>',
        f'<path d="{f.ring(3.5)}" fill="none" stroke="{C("primary")}" stroke-width="1.5"/>',
        f'<path d="{f.ring(10.5)}" fill="none" stroke="{C("outline_variant")}" stroke-width="1"/>',
        f'<g fill="{C("tertiary")}">',
    ]
    beads = [f.along(side, u, 7) for side in range(4) for u in range(12, int(f.tile), 24)]
    f.body += [f'  <circle cx="{n(x)}" cy="{n(y)}" r="1.5"/>' for x, y in beads] + ["</g>"]
    for k in range(4):
        x, y = f.polar(k, f.radius(7), f.diag(k))
        f.body += [f'<path d="M{n(x)},{n(y - 8)} L{n(x + 8)},{n(y)} L{n(x)},{n(y + 8)} L{n(x - 8)},{n(y)} Z" '
                   f'fill="url(#accent)"/>',
                   f'<circle cx="{n(x)}" cy="{n(y)}" r="2.5" fill="{C("surface_container_low")}"/>']


finalize()


def build(name):
    st = STYLES[name]
    size = 2 * st["corner"] + st["tile"]
    out = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}"\n'
           f'     data-border-size="{st["band"]}" data-slice="{st["corner"]}" data-corner="{st["corner"]}" '
           f'data-edges="{st["edges"]}">\n'
           f'  <!-- borders-plus-plus-svg frame "{name}", made by generate.py. {st["about"]}\n'
           f'       One frame per window rounding below (general.border_size = {BORDER}): the plugin draws the one\n'
           f'       closest to each window\'s rounding, so they overlap if you open this file directly. -->\n')
    for rounding in ROUNDINGS:
        f = Frame(st["band"], st["tile"], st["corner"], radius_for(rounding))
        st["build"](f)
        out += f.variant(rounding)
    return out + "</svg>\n"


def main():
    global ROUNDINGS, BORDER
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rounding", default=",".join(map(str, ROUNDINGS)),
                    help="window roundings to draw a frame for, comma separated (default %(default)s)")
    ap.add_argument("--border", type=int, default=BORDER, help="general.border_size (default %(default)s)")
    args = ap.parse_args()
    ROUNDINGS, BORDER = sorted({int(r) for r in args.rounding.split(",")}), args.border
    finalize()

    for name in STYLES:
        with open(os.path.join(HERE, name + ".svg"), "w") as fh:
            fh.write(build(name))

    print(f"wrote {len(STYLES)} frames for roundings {', '.join(map(str, ROUNDINGS))} and border {BORDER}: "
          f"{', '.join(STYLES)}")


if __name__ == "__main__":
    main()
