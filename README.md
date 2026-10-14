# borders-plus-plus-svg

A [Hyprland](https://hyprland.org) plugin that draws extra borders around your windows: plain colours, or any
**SVG frame**, stretched to fit every window.

It's a fork of [borders-plus-plus](https://github.com/hyprwm/hyprland-plugins/tree/main/borders-plus-plus) from
hyprwm's official plugins (see [Credits](#credits)). On top of the original's coloured borders it adds:

- **SVG frames**, drawn as a 9-slice: the frame's corners are drawn as they are, its edges are stretched or tiled
  along the window, its middle is left out. Corners can be bigger than the border and reach over a window's
  rounded corner, so a frame can hug rounded windows.
- **Rounding-aware frames**: one SVG can carry a version for each window rounding, and each window gets the one
  that matches its rounding at that moment, even when something changes `decoration:rounding` at runtime.
- **Focus dimming**: `inactive_alpha` fades the borders of unfocused windows, on the same animation as Hyprland's
  border colours. Borders also fade in and out with their windows.
- **Optional extras** for wallpaper-themed setups (`rice/`): frames that recolour themselves from your wallpaper
  with [matugen](https://github.com/InioX/matugen), eight ready-made frames, a tool that sets up frames
  downloaded from the web, and an offline previewer.

It uses its own config namespace and decoration, so it can run next to the original borders-plus-plus.

## Contents

- [How SVG frames are drawn](#how-svg-frames-are-drawn)
- [Requirements](#requirements)
- [Installing](#installing)
- [Configuration](#configuration)
- [Getting a frame to fit](#getting-a-frame-to-fit)
- [Wallpaper-coloured drop-in frames](#wallpaper-coloured-drop-in-frames)
- [The bundled frames](#the-bundled-frames)
- [Using frames from the web](#using-frames-from-the-web)
- [Previewing without Hyprland](#previewing-without-hyprland)
- [After a Hyprland update](#after-a-hyprland-update)
- [Troubleshooting](#troubleshooting)
- [Uninstalling](#uninstalling)
- [What's in here](#whats-in-here)
- [Credits](#credits)
- [License](#license)

## How SVG frames are drawn

The plugin cuts the SVG into a 3×3 grid:

```
   svg_slice
   <------>
+----------+--------------------------+----------+
|  corner  |           edge           |  corner  |   corners: drawn as they are
+----------+--------------------------+----------+
|          |                          |          |
|   edge   |   middle (never drawn)   |   edge   |   edges: stretched or tiled
|          |                          |          |   along the window
+----------+--------------------------+----------+
|  corner  |           edge           |  corner  |
+----------+--------------------------+----------+
```

- `svg_slice` is how big the corners are **inside the SVG**. The plugin scales the whole SVG so that this
  becomes `svg_corner` pixels **on screen**.
- Each corner is drawn as a `svg_corner` × `svg_corner` square at the window's corner.
- Of each edge, only the outer `border_size` pixels are drawn, along the window between the corners.
- The window's own space is pushed in by `border_size`, so the frame sits around the window. Corners larger
  than `border_size` reach in over the window's corner, which is what lets a frame wrap a rounded window.

The SVG is rendered once per monitor scale and cached, so resizing windows costs nothing; it's re-read on
`hyprctl reload`.

## Requirements

- **Hyprland 0.56**, with the development headers of the **exact version you're running**. Plugins only load
  into the Hyprland their headers came from. On Arch the `hyprland` package installs them in
  `/usr/include/hyprland`; check that `pkg-config --modversion hyprland` prints the same version as
  `hyprctl version`.
- A C++23 compiler (GCC 13+ or Clang 17+), `make` (or meson/CMake) and `pkg-config`.
- These libraries and their headers, most of which Hyprland already needs: librsvg, pango (pangocairo),
  pixman, libdrm, libinput, libudev, wayland, xkbcommon.

  ```sh
  # Arch
  sudo pacman -S --needed base-devel hyprland librsvg pango pixman libdrm libinput systemd-libs wayland libxkbcommon
  ```
- **Only for the extras in `rice/`:** a Lua Hyprland config (`hyprland.lua`), matugen, and Python 3 with
  PyGObject (and librsvg's GObject introspection data), pycairo, Pillow and lxml.

  ```sh
  # Arch
  sudo pacman -S --needed matugen python-gobject python-cairo python-pillow python-lxml
  ```

## Installing

### 1. Get the code

Put this folder at `~/borders-plus-plus-svg` (clone it there, or copy it). Any other place works too; the extras'
`borders.lua` has a `root` setting at its top for that.

### 2. Build

```sh
cd ~/borders-plus-plus-svg
make
```

This produces `borders-plus-plus-svg.so`. `make` writes a new file and swaps it in rather than overwriting the old
one, so rebuilding while Hyprland has the plugin loaded is safe.

meson and CMake work too, and name the result `libborders-plus-plus-svg.so`:

```sh
meson setup build && ninja -C build          # build/libborders-plus-plus-svg.so
cmake -B build-cmake && cmake --build build-cmake
```

### 3. Try it

```sh
hyprctl plugin load ~/borders-plus-plus-svg/borders-plus-plus-svg.so
```

A green "Initialized successfully!" notification means it's running, drawing one dark border around every
window until you configure it. If it says "Version mismatch" instead, the headers you built against aren't from
the Hyprland you're running; see [Requirements](#requirements).

`hyprctl plugin unload ~/borders-plus-plus-svg/borders-plus-plus-svg.so` takes it away again.

### 4. Load it with your config

In `hyprland.lua`:

```lua
hl.plugin.load(os.getenv("HOME") .. "/borders-plus-plus-svg/borders-plus-plus-svg.so")
```

or in `hyprland.conf`:

```ini
plugin = /home/you/borders-plus-plus-svg/borders-plus-plus-svg.so
```

Then configure it as below. If you'd like wallpaper-coloured frames you pick by name, skip ahead to
[Wallpaper-coloured drop-in frames](#wallpaper-coloured-drop-in-frames): its `borders.lua` loads and configures
the plugin for you.

## Configuration

Options live under `plugin:borders-plus-plus-svg`: `plugin = { borders_plus_plus_svg = { ... } }` in Lua, or a
`plugin { borders-plus-plus-svg { ... } }` block in hyprlang.

**Global:**

| option             | default | meaning |
|--------------------|---------|---------|
| `add_borders`      | `1`     | how many border layers to draw, 0-9 |
| `natural_rounding` | `true`  | colour layers use the window's own rounding (SVG layers bring their own shape) |
| `inactive_alpha`   | `1`     | opacity of the borders of windows without focus, 0-1; it fades on Hyprland's `border` animation |

**Per layer**, `N` from 1 to `add_borders`; layer 1 is closest to the window:

| option          | default      | meaning |
|-----------------|--------------|---------|
| `border_size_N` | `-1`         | thickness on screen, in logical pixels; `-1` means `general:border_size` |
| `col.border_N`  | `0xee000000` | colour, used when `svg_N` is empty or can't be loaded |
| `svg_N`         | empty        | an SVG to draw instead of the colour (`~/` is expanded) |
| `svg_slice_N`   | `0`          | corner size inside the SVG, in its own pixels (its `width`/`height`, or `viewBox` units if it has neither); `0` means a third of its smaller side. Must be under half its width and height |
| `svg_corner_N`  | `0`          | corner size on screen; `0` means `border_size_N`. Larger corners reach in over the window's corner |
| `svg_edges_N`   | `stretch`    | `stretch` draws each edge stretched once; `repeat` tiles it, scaling the tiles slightly so a whole number fits |

If an SVG can't be loaded, a notification says why and that layer falls back to its colour.

### Example: two colour borders

```lua
hl.config({
    plugin = {
        borders_plus_plus_svg = {
            add_borders   = 2,
            border_size_1 = 4,
            border_size_2 = 2,
            col = { border_1 = "rgb(1e1e2e)", border_2 = "rgb(f5c2e7)" },
        },
    },
})
```

### Example: an SVG frame

`examples/frame.svg` is a 96×96 frame whose corners are 24 units:

```lua
hl.config({
    plugin = {
        borders_plus_plus_svg = {
            add_borders    = 1,
            inactive_alpha = 0.45,
            border_size_1  = 24,
            svg_1          = "~/borders-plus-plus-svg/examples/frame.svg",
            svg_slice_1    = 24,
            svg_edges_1    = "repeat",
        },
    },
})
```

The same in hyprlang:

```ini
plugin {
    borders-plus-plus-svg {
        add_borders = 1
        inactive_alpha = 0.45
        border_size_1 = 24
        svg_1 = ~/borders-plus-plus-svg/examples/frame.svg
        svg_slice_1 = 24
        svg_edges_1 = repeat
    }
}
```

## Getting a frame to fit

Three numbers decide how a frame looks: `svg_slice` (corner size in the SVG), `svg_corner` (corner size on
screen) and `border_size` (border thickness on screen). The plugin scales the SVG by `svg_corner / svg_slice`, so:

- **`svg_slice`** should take in everything decorative at the corners, so that what's left along the edges is
  plain (for `stretch`) or a clean repeating pattern (for `repeat`). Too small, and the ends of corner ornaments
  get smeared along the edges; too large, and the frame shrinks.
- **`border_size`** should cover how deep the frame is in the SVG, at the same scale:
  `border_size / svg_corner = depth in the SVG / svg_slice`. Any less, and the inner parts of the frame get
  cut off along the edges and drawn over the window at the corners.
- **`svg_corner`** then just sets the overall size.

For frames from the web, [`fit.py`](#using-frames-from-the-web) measures all of this for you.

### Making your own SVG

- Draw a rectangular frame with a see-through middle, and give the SVG a `width`/`height` or a `viewBox`.
- Leave no empty margin around the frame: the outer edge of the drawing is the outer edge of the border.
- With `repeat`, make the part of each edge between the corners (`width - 2 × svg_slice` long) a whole number of
  repeats. A gradient running along a whole edge will restart on every tile.
- The SVG decides the corner's shape; the window's `rounding` doesn't apply to it. For rounded windows, cut the
  frame's inner corner with a radius of `rounding + general:border_size` (or square it off when `rounding` is 0)
  and make `svg_corner` at least `border_size` + that radius, so the cut fits inside the corner.
- If windows' rounding changes (window rules, or a shell theme setting `decoration:rounding` at runtime), put one
  version of the frame per rounding in the same SVG, as top-level elements with `id="rounding-N"` on the same
  canvas. The plugin draws the one closest to each window's rounding; an SVG without them is drawn whole.

## Wallpaper-coloured drop-in frames

`rice/borders.lua` turns the plugin into frames you pick by name: put any `<name>.svg` in `rice/frames/`, set
`local style = "<name>"`, save, and it's on. Frames can recolour themselves from your wallpaper.

### What it expects

- A **Lua** Hyprland config.
- **matugen writing a `~/.config/hypr/colors.lua`** that lists every colour of the current wallpaper's palette,
  and reloading Hyprland after. If you don't have one, this template does it. Save it as
  `~/.config/matugen/templates/hyprland.lua`:

  ```
  return {
      image = "{{image}}",
  <* for name, value in colors *>
      {{name}} = "rgba({{value.default.hex_stripped}}ff)",
  <* endfor *>
  }
  ```

  and add it to `~/.config/matugen/config.toml`:

  ```toml
  [templates.hyprland_lua]
  input_path = "~/.config/matugen/templates/hyprland.lua"
  output_path = "~/.config/hypr/colors.lua"
  post_hook = "hyprctl reload"
  ```

  Run matugen once (`matugen image /path/to/wallpaper`) so the file exists. Frames without colour tokens don't
  need any of this.

### Setup

1. Build the plugin (above).
2. `cp ~/borders-plus-plus-svg/rice/borders.lua ~/.config/hypr/`
3. Add `require("borders")` to `hyprland.lua`.
4. Pick a frame: set `local style = "..."` at the top of `~/.config/hypr/borders.lua` to one of the
   [bundled frames](#the-bundled-frames) or any SVG you've added, and save. Hyprland reloads by itself.

`borders.lua` loads the plugin itself, so drop any `hl.plugin.load` line for it from `hyprland.lua`. If the
project isn't at `~/borders-plus-plus-svg`, change `root` at the top of `borders.lua`. Its `defaults` and
`inactive_alpha` lines are the other things you might want to change.

### Colours

Write [matugen](https://github.com/InioX/matugen)'s colour tokens into the SVG where a colour goes:

```xml
<path stroke="{{colors.primary.default.hex}}" fill="#{{colors.surface_container.default.hex_stripped}}"/>
```

`.hex` gives `#rrggbb`, `.hex_stripped` the same without `#`, and `.dark` works like `.default`. The colour names
are matugen's (`primary`, `on_primary`, `primary_container`, `secondary`, `tertiary`, `surface_container_low`,
`outline`, ... the ones `colors.lua` lists). Every time Hyprland loads its config, `borders.lua` fills them in
from `colors.lua` and writes the result to `~/.config/hypr/borders/`. Matugen reloads Hyprland on every wallpaper
change, so frames follow the wallpaper without any matugen setup of their own. An SVG without tokens is used
straight from the folder.

An SVG that uses colour tokens and links to images by a relative path should embed them instead, since its
filled-in copy lives in another folder.

### Settings

Each SVG carries its own settings as attributes on its `<svg>` tag. Anything left out uses the default:

| attribute          | default                     | meaning |
|--------------------|-----------------------------|---------|
| `data-border-size` | `14`                        | border thickness on screen |
| `data-slice`       | a third of its smaller side | corner size inside the SVG |
| `data-corner`      | the border thickness        | corner size on screen |
| `data-edges`       | `stretch`                   | `stretch` or `repeat` |

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 300"
     data-border-size="18" data-slice="30" data-corner="18" data-edges="repeat">
```

### When something's wrong

A missing file, a colour `colors.lua` doesn't have or a bad `data-edges` shows up as a notification, and the frame
is turned off. It never stops the rest of `hyprland.lua` from loading. If the plugin itself can't load (say after
a Hyprland update, until it's rebuilt), `borders.lua` leaves its options out, so there are no config errors
either.

### With a hyprland.conf

`borders.lua` needs a Lua config. With hyprlang, set the options directly as in the
[example](#example-an-svg-frame), copying each SVG's `data-` values into them. For wallpaper colours, have
matugen fill the SVG as one of its templates, writing to e.g. `~/.config/hypr/borders/<name>.svg`, and point
`svg_1` there.

## The bundled frames

`rice/frames/` comes with eight frames, made by `rice/frames/generate.py`. Each holds a version for window
roundings 0, 1, 3, 4, 6, 8, 10, 14, 18 and 35 with `general:border_size = 2`, so it hugs the window whatever the
rounding:

| style       | look |
|-------------|------|
| `halo`      | a soft glow lifting off the window, with a fine line that catches the light at the corners |
| `tomoe`     | Sharingan rings with a tomoe at every corner, all turning the same way |
| `sakura`    | cherry blossoms and loose petals tucked into the corners, on a thin branch |
| `neon`      | two glowing tubes, the outer one broken at the corners like a real sign |
| `hud`       | ruler ticks, heavy corner brackets and a different status mark after each |
| `torii`     | the window stands under a torii: upswept kasagi and nuki across the top, a pillar each side |
| `starlight` | a dotted constellation line with four-pointed stars in the corners and along the edges |
| `jewel`     | an art-deco band with beads every 24 px and a jewel at each corner |

`rice/frames/gallery.png` shows each one's corner in three palettes, `rice/frames/overview.jpg` the whole screen.

For other roundings or another `general:border_size`, regenerate them:

```sh
cd ~/borders-plus-plus-svg/rice/frames
./generate.py --rounding 0,8,20 --border 3
```

## Using frames from the web

Frame SVGs from the web rarely work as they come. They're often a whole printable page, sometimes drawn on a white
background, sometimes with part of them hidden by an export bug, and never with `data-` settings.
`rice/frames/fit.py` sets one up:

```sh
cd ~/borders-plus-plus-svg/rice/frames
./fit.py ~/Downloads/gold-frame.svg        # then: local style = "gold-frame"
```

It:

- brings back parts that empty clip paths hide (a common PDF-to-SVG export bug),
- removes a background drawn behind the frame,
- crops the empty page around the frame,
- measures where the corner ornaments end and the plain or repeating edges begin, and how deep the frame is,
- writes a copy into the folder with those `data-` settings, prints what it did and renders a preview.

The download itself is left alone. `--border-size` or `--corner` make the result bigger or smaller (the other
follows), `--name` names it, and it won't overwrite a frame it didn't make itself unless you add `--force`.

It handles rectangular frames whose edges are plain or repeat: mouldings, corner ornaments joined by lines,
beading and other patterns, which get tiled with corners sized so the tiles meet seamlessly. Oval frames, or ones
with an ornament in the middle of each edge, can't be reproduced by stretching edges; it warns about those.

Mind the licence of what you download: such files belong to their authors, and this project's licence doesn't
cover them.

## Previewing without Hyprland

`rice/frames/preview.py` draws a frame around a mock-up of a desktop: translucent, blurred windows with a rounded
gradient border, in a scrolling layout. It cuts and places the frame exactly like the plugin does. By default it
uses the current wallpaper and its colours (from `colors.lua`), the live rounding and `borders.lua`'s
`inactive_alpha`:

```sh
./preview.py halo                                    # writes /tmp/halo-preview.png
./preview.py ~/Downloads/frame.svg --slice 30 --border-size 18
./preview.py sakura --wall ~/Pictures/wallpapers/forest.jpg
./preview.py halo neon torii --corners --wall a.jpg --wall b.jpg --out /tmp/grid.png
```

For an SVG without a `data-slice` it also suggests one. The mock-up's look (gaps, opacity, layout) is set by the
constants at the top of the file.

## After a Hyprland update

A plugin built for one Hyprland version won't load into another. After updating Hyprland:

```sh
cd ~/borders-plus-plus-svg
make
hyprctl plugin unload ~/borders-plus-plus-svg/borders-plus-plus-svg.so
hyprctl plugin load ~/borders-plus-plus-svg/borders-plus-plus-svg.so
```

(or rebuild and log in again). This fork was built against Hyprland **0.56.2**. If a new Hyprland version
changes the plugin API, the build fails, and the changes needed are usually the same ones made to
borders-plus-plus in [hyprland-plugins](https://github.com/hyprwm/hyprland-plugins) for that version.

## Troubleshooting

| what you see | what to do |
|--------------|------------|
| "Version mismatch" notification | rebuild against the headers of the Hyprland you're running, see [above](#after-a-hyprland-update) |
| "unknown config key plugin.borders_plus_plus_svg..." | the plugin isn't loaded: check the path, and `hyprctl plugin list` |
| a thin, tiny or squashed frame | its settings don't fit it: run `fit.py` on it, or try values with `preview.py` |
| part of the frame missing | likely an empty clip path from a PDF export: `fit.py` fixes that |
| corners drawn over the window's content | `border_size` is too small for the frame's depth, see [Getting a frame to fit](#getting-a-frame-to-fit) |
| a frame that doesn't follow the window's rounded corners | give it [rounding variants](#making-your-own-svg), or regenerate the bundled frames for your rounding |
| changes to an SVG don't show | SVGs are read on config reloads, and Hyprland only watches config files: `hyprctl reload` |
| a notification from `borders.lua` | it names the problem; the frame is off until it's fixed |

To check what the plugin is actually using: `hyprctl getoption plugin:borders-plus-plus-svg:svg_1` (or any other
option), and `hyprctl configerrors`.

## Uninstalling

1. Remove `require("borders")` (or your `hl.plugin.load` / `plugin =` line) from your Hyprland config. On the next
   reload Hyprland unloads the plugin; `hyprctl plugin unload ...` does it right away.
2. If you used the extras: delete `~/.config/hypr/borders.lua` and `~/.config/hypr/borders/`.
3. Delete `~/borders-plus-plus-svg`.

## What's in here

```
borders-plus-plus-svg/
├── main.cpp, borderDeco.*, BorderppPassElement.*, globals.hpp   the plugin, from borders-plus-plus
├── svgSlices.*                                                  loading, slicing and drawing SVG frames
├── Makefile, meson.build, CMakeLists.txt                        three ways to build it
├── examples/frame.svg                                           a simple frame for the examples above
└── rice/                                                        the optional extras
    ├── borders.lua                                              copy to ~/.config/hypr/ and require("borders")
    └── frames/
        ├── halo.svg ... jewel.svg                               the bundled frames
        ├── generate.py                                          makes the bundled frames
        ├── fit.py                                               sets up frames from the web
        ├── preview.py                                           previews frames without Hyprland
        └── gallery.png, overview.jpg                            what the bundled frames look like
```

## Credits

- **[borders-plus-plus](https://github.com/hyprwm/hyprland-plugins/tree/main/borders-plus-plus)**, the plugin this
  is built on, by [Vaxry](https://github.com/vaxerski) and the contributors to
  [hyprwm/hyprland-plugins](https://github.com/hyprwm/hyprland-plugins), Copyright (c) 2023 Hypr Development,
  under the BSD 3-Clause License. Its decoration, its positioning and its colour borders are the base everything
  here is added to. The focus animation follows the approach of hyprbars from the same repository.
- **[Hyprland](https://github.com/hyprwm/Hyprland)**, by Vaxry and contributors.
- **[librsvg](https://gitlab.gnome.org/GNOME/librsvg)** (GNOME) renders the SVGs, with
  **[cairo](https://www.cairographics.org)**.
- **[matugen](https://github.com/InioX/matugen)**, by InioX, makes the wallpaper palettes the optional frames use.
- The tools use [PyGObject](https://pygobject.gnome.org), [pycairo](https://github.com/pygobject/pycairo),
  [Pillow](https://python-pillow.org) and [lxml](https://lxml.de).
- SVG frames, the bundled frames and the tools in `rice/` by dhrruvsharma.

## License

[BSD 3-Clause](LICENSE), like hyprland-plugins, which this is derived from. The original code is Copyright (c)
2023 Hypr Development; the changes and additions are Copyright (c) 2026 dhrruvsharma.

Frames you download and add yourself stay under their authors' licences.
