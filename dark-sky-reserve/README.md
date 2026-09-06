# Dark Sky Reserve

A night walk under the darkest skies in Britain, built from a single 360°
photograph.

Open **`dark-sky-reserve.html`**. That is the whole thing — one file, no server,
no install, no network. Double-click it.

---

## The dark it is about

In December 2020 the Yorkshire Dales and the North York Moors were designated
**International Dark Sky Reserves** together — a combined **3,615 km²**, the
largest area in the UK, and one of the largest in Europe, to be designated at
once. A Reserve is a dark core protected by a surrounding buffer where lighting
is controlled, which is why they read as one continuous piece of sky rather than
two islands of it.

That is the thing this is trying to put you inside: not a picture of a night sky,
but the experience of standing in one — a horizon with no glow on it, a Milky Way
bright enough to cast the faintest light on the grass, and nothing to hear but the
wind moving through the field.

The sky here is a real 360° night photograph rather than a survey of the Dales
themselves, so treat it as the same *kind* of dark rather than a specific
hillside. Everything below the skyline is reconstructed.

Sources: [Yorkshire Dales National Park Authority](https://www.yorkshiredales.org.uk/park-authority/looking-after/dark-sky/) ·
[DarkSky International](https://darksky.org/news/uk-dark-sky-reserve/) ·
[BBC Sky at Night](https://www.skyatnightmagazine.com/advice/yorkshire-dales-north-york-moors-dark-sky-reserves)

---

## What is real and what is rebuilt

This matters, because a 360° photograph cannot simply be "made walkable". It is
captured from **one point in space**. It has colour but no depth. Put a camera
inside it and move, and the ground smears, because there is nothing behind those
pixels to walk into.

So the scene is split along the only line where that problem has a clean answer:

**The sky is the photograph.** Stars are effectively at infinity, so a panorama
*is* a physically correct sky — the direction you look is the only thing that
decides what you see, and walking a kilometre changes nothing. The upper half of
the plate is mapped onto a dome and is reproduced pixel-for-pixel: the Milky Way
arch, the dust lanes, the green airglow band, the warm light-pollution domes on
the horizon. None of it is repainted. Only the missing zenith cap above +76°
(the photograph is vertically cropped) is synthesised, and the stars up there are
drawn procedurally in 3D so they stay round instead of smearing at the pole.

**The ground is rebuilt as real geometry,** because it has to be. It is a few
hundred thousand GPU-instanced grass blades over a terrain heightfield. You can
walk into it, through it, and look back at where you have been.

The reconstruction is not eyeballed against the photograph — it is *measured*
against it. `tools/build_sky.py` reads the plate and writes out the sky dome plus
a small lighting file: an order-2 spherical-harmonic projection of the sky's
radiance, and percentile statistics of the photograph's own grass pixels. At
load, the renderer divides the photographed grass colour by the measured sky
colour to derive the leaf albedo. So the field comes out the colour the
photograph recorded, under the light the photograph was taken by, rather than a
colour somebody liked the look of.

`tools/compare.py` is how that was checked rather than guessed. It maps every
pixel of a screenshot to a real direction and samples the photograph along the
same rays, so the two can be compared over matching solid angles. At the
default settings the render lands within about 10% of the plate across every
elevation band, sky and ground, with the channels balanced to within 3%.

---

## Controls

| | |
|---|---|
| `W A S D` / arrows | walk |
| `Shift` | run |
| `Space` | hop |
| `C` | crouch |
| mouse | look (click to capture the cursor) |
| `O` | settings |
| `H` | hide the interface |
| `M` | sound on/off |
| `P` | save the current frame as a PNG |
| `R` | return to the middle of the field |
| `Esc` | release the cursor |

Touch: drag on the left half to walk, the right half to look.
A gamepad works if one is plugged in.

---

## The wind

The grass moves because each blade is bent along a **circular arc** in the vertex
shader, not displaced by a wave. An arc of fixed length cannot stretch, so a
blade in a gale is exactly as long as a blade at rest — the difference between
grass and rubber.

Four things drive the bend, and they are layered deliberately:

- a **prevailing lie**, so the field is combed rather than random, and it veers
  slowly over minutes the way real wind does;
- **travelling gusts** — a noise field scrolled along the wind vector, which is
  what produces the long waves rolling across the field;
- a **finer ripple** at a shorter wavelength on top of them;
- and a **per-blade nod**, so neighbours are never quite in step.

Push the *Wind* slider to 0 and the field goes still; push it to 1.6 and it lies
flat in the gusts.

You also press through it. Blades part around you within about a metre, and a
decaying trample map remembers where you walked, so you can turn round and see
your own track. *Trail memory* in the settings controls how long it lasts.

---

## Performance

Defaults target 60 fps on a discrete GPU at 1080p. **Quality: Auto** watches the
frame time and scales the render resolution and grass density to hold that; if
you would rather pin it, choose Low / Medium / High / Ultra explicitly.

The settings worth knowing:

- **Video memory** is the one that matters if the picture breaks up. Render
  targets are budgeted, and resolution and antialiasing are chosen together to
  fit: resolution comes first, down to one buffer pixel per screen pixel, and
  whatever is left buys samples. Raise it if you have a discrete GPU. It exists
  because capping device pixel ratio alone is *not* enough — a 4× multisampled
  HDR colour buffer plus its depth costs ~48 MB per megapixel, so an uncapped
  Retina display asks for 460–825 MB of render targets and a laptop GPU answers
  by dropping draws, which looks like the ground never being painted.
- **Antialiasing** is the biggest quality lever. Grass is hundreds of thousands
  of shapes a pixel or less across — the worst case there is for aliasing — and
  without multisampling the blades break into crawling dashes as soon as the
  wind moves them.
- **Grass density** widens the lattice rather than discarding blades, so turning
  it down actually costs less vertex work instead of paying for blades it then
  throws away. Blades widen slightly as it drops, so coverage falls much more
  slowly than the vertex count.
- **Grass distance** is where most of the cost is beyond about 60 m.

Needs WebGL 2. Half-float render targets are used where available and it falls
back to 8-bit if they are not.

---

## Building

The single HTML file is generated. Do not edit it — edit `src/` and rebuild.

```
python3 tools/build_sky.py     # panorama  -> assets/sky.jpg + sky_light.json
python3 tools/build.py         # src/*     -> dark-sky-reserve.html
python3 tools/compare.py shot.png 18.3 1.1 68     # check it against the plate
```

`build_sky.py` needs `pillow` and `numpy`. `build.py` needs neither — it inlines
the sky plate as a data URI, which is what lets the page run straight off the
filesystem with nothing to fetch.

```
src/
  page.html      the shell
  style.css
  05-assets.js   generated: sky plate + lighting constants
  10-util.js     maths, tileable noise, settings
  20-gl.js       WebGL2 helpers, render targets, MSAA resolve
  30-shaders.js  shared GLSL: sky lookup, lighting, haze, field sampling
  40-sky.js      50-terrain.js   60-grass.js
  70-trample.js  75-post.js      78-fireflies.js
  80-audio.js    85-input.js     90-main.js   95-boot.js
```

There is no framework and no dependency. The renderer is four passes — trample
update, scene, bloom chain, composite — and hand-rolling it is what keeps the
deliverable a single file.

---

## Notes on the picture

- **Tone curve.** The source is a *finished* photograph, so any curve that lifts
  or crushes midtones throws away the thing being matched. The shoulder here is
  the identity below 0.55 and rolls off asymptotically above it: the sky comes
  out at exactly the value the photograph had, and a boosted galactic core glows
  instead of clipping to a white hole.
- **Haze is the sky, not grey.** Distance fog samples the sky plate in the
  direction you are looking, mixed with the sky's average radiance. That is why
  the far field dissolves into green airglow on one side and a warm light dome
  on the other, exactly as the photograph does.
- **The silver strands** on the blades are the sky dome reflecting off waxy leaf
  surfaces — a Fresnel-weighted lookup of the plate in the reflected direction —
  not a highlight from a light source. There is no light source at night bright
  enough to make them.
- **Fireflies** are off by default. They are not in the photograph.

---

## Checked, not assumed

Three things the design rests on, each verified against the running page
rather than taken on trust:

- **The sky does not move when you do.** Screenshot the same heading from the
  origin and from a kilometre away: mean absolute difference 0.0012, and the
  1% of pixels that differ at all are the stars scintillating, which is
  deliberate. That is the claim about panoramas being correct skies, measured.
- **The ground you walk on is the ground that is drawn.** The camera's height
  and the vertex shader's height agree to 0.00000 m, standing still, after
  teleporting across the field and throughout a walk over the undulations.
  They read the same baked texture, which is why.
- **The wind is doing the work.** Between two frames half a second apart, 44%
  of the grass pixels change with the wind up and 7% with it off - and that
  7% is the camera settling and trampled grass standing back up, not the
  blades.

Colour is checked with `tools/compare.py` as described above.

---

## If it misbehaves

Open Settings (**O**) and press **Diagnostics** — it copies the renderer,
driver, drawing-buffer size, sample count, memory budget and limits to the
clipboard, which is everything needed to tell what went wrong.

If the graphics context is ever lost, the page says so instead of going quietly
black, and the next load comes back at reduced quality on its own.

---

## What this is not

It is an explorable place, not a game with objectives. Everything a game layer
would need is already here — a walkable world, collision with the ground, player
position, an interaction radius that the grass already responds to — but no goal
has been imposed on it, because the brief was to match the photograph and a
scattering of collectibles across a prairie at night would have fought that.
