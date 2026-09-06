/* ===================================================================
   The world, and the loop that runs it.
   =================================================================== */

/* Set after a context loss or an out-of-memory, and read on the next load
   so that a machine which has already fallen over once comes back gently
   instead of straight back into the thing that broke it. */
const SAFE_KEY = 'grassfield.saferestart';
const SAFE_MODE = (() => {
  try { return localStorage.getItem(SAFE_KEY) === '1'; } catch (e) { return false; }
})();
function markSafeRestart() { try { localStorage.setItem(SAFE_KEY, '1'); } catch (e) {} }
function clearSafeRestart() { try { localStorage.removeItem(SAFE_KEY); } catch (e) {} }

const DEFAULTS = {
  quality: 'auto',
  renderScale: 1.0,
  density: 1.0,
  grassRange: 130,
  bladeHeight: 1.45,
  wind: 0.70,
  fov: 68,
  exposure: 1.00,
  bloom: 0.09,
  grain: 0.028,
  vignette: 0.42,
  saturation: 1.04,
  groundLift: 5.9,
  sheen: 1.45,
  chroma: 0.0035,
  stars: 1.0,
  fireflies: 0.0,
  sensitivity: 1.0,
  invertY: false,
  headBob: 1.0,
  trail: 26,
  sound: false,
  volume: 0.55,
  showHud: true,
  msaa: true,
  /* Megabytes of video memory the render targets may use. This is the
     setting that stops a high-DPI display asking the GPU for the better
     part of a gigabyte and getting a half-painted frame back. */
  vramBudget: 160
};

const QUALITY_PRESETS = {
  low:    { renderScale: 0.62, density: 0.35, grassRange: 70,  bloomLevels: 4, msaa: 1 },
  medium: { renderScale: 0.85, density: 0.65, grassRange: 100, bloomLevels: 5, msaa: 2 },
  high:   { renderScale: 1.00, density: 1.00, grassRange: 130, bloomLevels: 6, msaa: 4 },
  ultra:  { renderScale: 1.25, density: 1.55, grassRange: 130, bloomLevels: 6, msaa: 4 }
};

/* ------------------------------------------------------------------ */

class World {
  constructor(canvas, skyImage, light) {
    this.canvas = canvas;
    this.light = light;
    this.glw = new GL(canvas);
    const gl = this.glw.gl;
    this.settings = loadSettings(DEFAULTS);
    if (SAFE_MODE) {
      /* this machine has already fallen over once - come back gently */
      this.settings.msaa = false;
      this.settings.density = Math.min(this.settings.density, 0.5);
      this.settings.grassRange = Math.min(this.settings.grassRange, 70);
      this.settings.vramBudget = Math.min(this.settings.vramBudget, 64);
    }

    /* ---------------- textures -------------------------------------- */
    this.skyTex = this.glw.texture({
      image: skyImage, wrap: gl.REPEAT, wrapT: gl.CLAMP_TO_EDGE, filter: gl.LINEAR
    });

    this.heightPeriod = 1024;
    this.heightScale = 4.2;
    this.heightRes = 1024;
    this.heightData = this.bakeHeight(this.heightRes);
    this.heightTex = this.glw.texture({
      w: this.heightRes, h: this.heightRes, internal: gl.R16F, format: gl.RED,
      type: gl.FLOAT, data: this.heightData, wrap: gl.REPEAT, filter: gl.LINEAR
    });

    this.fieldPeriod = 64;
    this.tussock = 0.46;
    this.fieldRes = 256;
    this.fieldData = this.bakeField(this.fieldRes);
    this.fieldTex = this.glw.texture({
      w: this.fieldRes, h: this.fieldRes, data: this.fieldData,
      wrap: gl.REPEAT, filter: gl.LINEAR
    });

    /* One metre scale: tussock mounds, per-tuft comb, blade length.
       Kept apart from the field texture because the two live at
       completely different scales and sharing one made both worse. */
    this.detailPeriod = 12;
    this.detailRes = 256;
    this.detailData = this.bakeDetail(this.detailRes);
    this.detailTex = this.glw.texture({
      w: this.detailRes, h: this.detailRes, data: this.detailData,
      wrap: gl.REPEAT, filter: gl.LINEAR
    });

    this.matTex = this.glw.texture({
      w: 512, h: 512, data: this.bakeMat(512),
      wrap: gl.REPEAT, filter: gl.LINEAR, mips: true, aniso: 8
    });

    /* ---------------- passes ---------------------------------------- */
    this.sky = new SkyPass(this.glw);
    this.terrain = new Terrain(this.glw, 170, 256, 18000);
    this.grass = new Grass(this.glw);
    this.flies = new Fireflies(this.glw, 900);
    this.trample = new Trample(this.glw, 512, 56);
    this.post = new Post(this.glw);

    /* ---------------- lighting from the photograph ------------------ */
    this.sh = new Float32Array(27);
    for (let i = 0; i < 9; i++) {
      const c = light.sh[i];
      this.sh[i * 3] = c[0]; this.sh[i * 3 + 1] = c[1]; this.sh[i * 3 + 2] = c[2];
    }
    this.calibrate();

    /* ---------------- player ---------------------------------------- */
    this.pos = [0, 0, 0];
    this.vel = [0, 0, 0];
    this.yaw = 0.32;
    this.pitch = 0.02;
    this.eye = 1.68;
    this.eyeCur = 1.68;
    this.bobPhase = 0;
    this.bobAmt = 0;
    this.grounded = true;
    this.vy = 0;
    this._playerXZ = new Float32Array(2);
    this.roll = 0;

    this.time = 0;
    this.windTime = 0;
    this.windAngle = 0.7;
    this.windDir = new Float32Array([Math.cos(0.7), Math.sin(0.7)]);
    this.gust = 0.5;

    /* ---------------- matrices -------------------------------------- */
    this.proj = M4.ident();
    this.viewM = M4.ident();
    this.viewProj = M4.ident();
    this.invViewProj = M4.ident();
    this.camPos = new Float32Array(3);
    this.fwdXZ = new Float32Array(2);

    this.scene = null;
    this.rw = 0; this.rh = 0;
    this.samples = 1;
    /* Deliberately conservative to begin with. On a Retina display this
       lands at roughly one buffer pixel per CSS pixel, which looks right
       and costs a fifth of what going native would; auto-quality raises
       it if the machine turns out to have the headroom. */
    this.lastResizeAt = 0;
    this.frameMs = 16;
    this.fps = 60;
    this.autoScale = 1.0;

    this.env = this.makeEnv();
  }

  /* ================================================================
     Baking. Everything the shaders read about the shape of the field
     is generated here, once, so that the CPU and the GPU are looking
     at literally the same numbers.
     ================================================================ */

  bakeHeight(res) {
    const f = makeFbm(1337, 4, 7, 0.55);
    const out = new Float32Array(res * res);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) out[y * res + x] = f(x / res, y / res);
    }
    return out;
  }

  /** Bilinear sample of a baked texture channel, matching the shader. */
  sampleBaked(data, res, stride, ch, x, z, period) {
    let u = (x / period) * res, v = (z / period) * res;
    const xi = Math.floor(u), yi = Math.floor(v);
    const fx = u - xi, fy = v - yi;
    const x0 = ((xi % res) + res) % res, y0 = ((yi % res) + res) % res;
    const x1 = (x0 + 1) % res, y1 = (y0 + 1) % res;
    const g = (X, Y) => data[(Y * res + X) * stride + ch];
    return lerp(lerp(g(x0, y0), g(x1, y0), fx), lerp(g(x0, y1), g(x1, y1), fx), fy);
  }

  /** The CPU's copy of surfaceHeight(): terrain plus tussock mounds. */
  surfaceAt(x, z) {
    const t = this.sampleBaked(this.detailData, this.detailRes, 4, 0, x, z,
                               this.detailPeriod) / 255;
    return this.groundAt(x, z) + (t - 0.5) * this.tussock;
  }

  /**
   * Where a person's feet actually go. Not the same as surfaceAt: you
   * walk BETWEEN tussocks and push through them, you do not step neatly
   * over each dome, and following them exactly turns a walk across the
   * field into a ride on a trampoline.
   */
  walkAt(x, z) {
    const t = this.sampleBaked(this.detailData, this.detailRes, 4, 0, x, z,
                               this.detailPeriod) / 255;
    return this.groundAt(x, z) + (t - 0.5) * this.tussock * 0.28;
  }

  /** Height in metres at a world position - the CPU's copy of groundHeight(). */
  groundAt(x, z) {
    const res = this.heightRes, d = this.heightData;
    let u = (x / this.heightPeriod) * res, v = (z / this.heightPeriod) * res;
    const xi = Math.floor(u), yi = Math.floor(v);
    const fx = u - xi, fy = v - yi;
    const x0 = ((xi % res) + res) % res, y0 = ((yi % res) + res) % res;
    const x1 = (x0 + 1) % res, y1 = (y0 + 1) % res;
    const a = d[y0 * res + x0], b = d[y0 * res + x1];
    const c = d[y1 * res + x0], e = d[y1 * res + x1];
    return lerp(lerp(a, b, fx), lerp(c, e, fx), fy) * this.heightScale;
  }

  bakeField(res) {
    /* gusts: long rolling waves, tens of metres across */
    const gust = makeFbm(20214, 2, 4, 0.58);
    /* tufts */
    const clump = makeFbm(9091, 8, 4, 0.5);
    /* the lie of the grass, as an offset from the prevailing wind */
    const comb = makeFbm(4242, 3, 3, 0.5);
    /* where the grass thins out. Stretched 5:1 so the bare ground comes
       in swathes and tracks, the way it does in the photograph, rather
       than in round bald spots. */
    const bare = makeFbm2(777, 3, 15, 4, 0.55);

    const out = new Uint8Array(res * res * 4);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const u = x / res, v = y / res, i = (y * res + x) * 4;
        out[i] = (gust(u, v) * 255) | 0;
        /* stretch the clump contrast so tufts read as tufts */
        const c = clamp((clump(u, v) - 0.5) * 1.95 + 0.5, 0, 1);
        out[i + 1] = (c * 255) | 0;
        out[i + 2] = (comb(u, v) * 255) | 0;
        const b = clamp((bare(u, v) - 0.46) * 2.3 + 0.5, 0, 1);
        out[i + 3] = (b * 255) | 0;
      }
    }
    return out;
  }

  /**
   * Tussocks. Deliberately only two octaves: the point of this field is
   * that it is SMOOTH at a metre. Fine detail here does not read as
   * texture, it reads as speckle, and it destroys the very grouping the
   * field is here to create.
   */
  bakeDetail(res) {
    const mound = makeFbm(5150, 6, 2, 0.45);
    const comb = makeFbm(8801, 5, 2, 0.5);
    const len = makeFbm(2233, 7, 2, 0.5);
    const spare = makeFbm(4477, 9, 2, 0.5);
    const out = new Uint8Array(res * res * 4);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const u = x / res, v = y / res, i = (y * res + x) * 4;
        out[i] = clamp((mound(u, v) - 0.5) * 1.7 + 0.5, 0, 1) * 255;
        out[i + 1] = comb(u, v) * 255;
        out[i + 2] = len(u, v) * 255;
        out[i + 3] = spare(u, v) * 255;
      }
    }
    return out;
  }

  /**
   * The mat of thatch under the blades. RG is a tangent-space normal,
   * A is how much dead stalk is showing. Strongly stretched along one
   * axis so it reads as combed grass; the shader spins it to follow the
   * local comb direction.
   */
  bakeMat(res) {
    const streak = makeFbm2(31337, 3, 24, 5, 0.55);
    const speck = makeFbm2(6161, 40, 40, 3, 0.5);
    const h = new Float32Array(res * res);
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const u = x / res, v = y / res;
        h[y * res + x] = streak(u, v) * 0.78 + speck(u, v) * 0.22;
      }
    }
    const out = new Uint8Array(res * res * 4);
    const at = (x, y) => h[(((y % res) + res) % res) * res + (((x % res) + res) % res)];
    for (let y = 0; y < res; y++) {
      for (let x = 0; x < res; x++) {
        const dx = (at(x + 1, y) - at(x - 1, y)) * 3.2;
        const dy = (at(x, y + 1) - at(x, y - 1)) * 3.2;
        const i = (y * res + x) * 4;
        out[i] = clamp(-dx * 0.5 + 0.5, 0, 1) * 255;
        out[i + 1] = clamp(-dy * 0.5 + 0.5, 0, 1) * 255;
        out[i + 2] = 255;
        const v = h[y * res + x];
        out[i + 3] = clamp((v - 0.42) * 2.0 + 0.5, 0, 1) * 255;
      }
    }
    return out;
  }

  /* ================================================================
     Colour calibration.

     We know two things: the spherical-harmonic irradiance of the sky
     that is actually lighting this field, and the exact colour the
     grass came out in the photograph. Dividing one by the other gives
     the albedo that lands the render back on the photograph, instead
     of on a number somebody liked the look of.
     ================================================================ */
  shIrradianceJS(n) {
    const c1 = 0.429043, c2 = 0.511664, c3 = 0.743125, c4 = 0.886227, c5 = 0.247708;
    const L = (i, k) => this.sh[i * 3 + k];
    const out = [0, 0, 0];
    for (let k = 0; k < 3; k++) {
      out[k] = c1 * L(8, k) * (n[0] * n[0] - n[1] * n[1])
             + c3 * L(6, k) * (n[2] * n[2])
             + c4 * L(0, k)
             - c5 * L(6, k)
             + 2 * c1 * (L(4, k) * n[0] * n[1] + L(7, k) * n[0] * n[2] + L(5, k) * n[1] * n[2])
             + 2 * c2 * (L(3, k) * n[0] + L(1, k) * n[1] + L(2, k) * n[2]);
    }
    return out;
  }

  calibrate() {
    const p = this.light.groundPercentiles;

    /* Take the HUE from the photograph and the LEVEL from physics.
       Dividing the photograph's grass colour straight through by the
       sky's irradiance asks for an albedo above 1 at the bright end -
       those pale streaks are backlit and specular, not diffuse - and
       clamping there turns every highlight grey. So the measured colour
       sets the ratio between the channels, plausible grass reflectances
       set the magnitude, and one scalar (groundLift) carries what is
       really a long exposure's lifted shadows. */
    const hue = (t) => {
      const m = Math.max(t[0], t[1], t[2], 1e-6);
      return [t[0] / m, t[1] / m, t[2] / m];
    };
    /* Divide the photograph's colour by the sky's, THEN normalise. The
       sky lighting this field is blue-green, so an albedo copied
       straight off the photograph comes out grey once that sky is
       multiplied through it. Dividing first asks the right question:
       what colour must this grass be for THIS sky to render it the
       colour the photograph recorded? Magnitude stays free - only the
       ratio between channels is being fixed here. */
    const amb = this.shIrradianceJS([0, 1, 0]).map(v => Math.max(v / Math.PI, 1e-6));
    const reflectance = (t) => hue([t[0] / amb[0], t[1] / amb[1], t[2] / amb[2]]);
    const hd = reflectance(p['25']);
    /* the top 2% is where the silver strands live: nearly neutral */
    const hl = reflectance(p['98']).map((v) => v * 0.82 + 0.18);
    this.grassDark = new Float32Array(hd.map((v) => v * 0.046));
    this.grassLight = new Float32Array(hl.map((v) => v * 0.700));
    this.ambientUp = this.shIrradianceJS([0, 1, 0]).map(v => v / Math.PI);

    const az = this.light.coreAzimuthDeg * DEG, el = this.light.coreElevationDeg * DEG;
    const ct = Math.cos(el);
    this.coreDir = new Float32Array([ct * Math.sin(az), Math.sin(el), -ct * Math.cos(az)]);
    const h = this.light.horizonRadiance;
    this.coreColour = new Float32Array([h[0] * 3.2, h[1] * 3.0, h[2] * 2.9]);
  }

  /* ================================================================ */

  makeEnv() {
    const gl = this.glw.gl, w = this;
    return {
      get viewProj() { return w.viewProj; },
      get invViewProj() { return w.invViewProj; },
      get camPos() { return w.camPos; },
      get fwdXZ() { return w.fwdXZ; },
      get cullDot() { return w.cullDot; },
      get windDir() { return w.windDir; },
      get windTime() { return w.windTime; },
      get windStrength() { return w.settings.wind; },
      /* Prairie grass is not a lawn: it lies over. Roughly 30 degrees
         at rest, more as the wind gets up. */
      get baseBend() { return 0.50 + w.settings.wind * 0.16; },
      get playerXZ() { return w._playerXZ; },
      get partRadius() { return 0.85; },
      get partStrength() { return 0.9; },
      get density() { return w._density; },
      get grassRange() { return w._range; },
      get bladeHeight() { return w.settings.bladeHeight; },
      get bladeWidth() { return 0.0086; },
      get grassDark() { return w.grassDark; },
      get grassLight() { return w.grassLight; },
      get coreDir() { return w.coreDir; },
      get coreColour() { return w.coreColour; },
      /* A blade of grass is glossy, but at night the only thing bright
         enough to make a highlight is the galactic core, and that is a
         soft area source - hence high roughness and a low weight. Any
         more than this and the field fills with white speckle. */
      get specular() { return 0.22; },
      /* how hard the sky glints off the leaf surface */
      get sheen() { return w.settings.sheen; },
      get translucency() { return 0.88; },
      get backLight() { return 0.36; },
      get groundGain() { return w.settings.groundLift; },
      get matTex() { return w.matTex; },
      get starAmount() { return w.settings.stars; },

      bindCommon(p) {
        w.glw.bindTex(0, w.skyTex); gl.uniform1i(p.u.uSky, 0);
        w.glw.bindTex(1, w.fieldTex); gl.uniform1i(p.u.uField, 1);
        w.glw.bindTex(2, w.heightTex); gl.uniform1i(p.u.uHeight, 2);
        w.glw.bindTex(3, w.trample.texture); gl.uniform1i(p.u.uTrample, 3);
        w.glw.bindTex(5, w.detailTex); gl.uniform1i(p.u.uDetail, 5);
        gl.uniform1f(p.u.uDetailPeriod, w.detailPeriod);
        gl.uniform1f(p.u.uSkyLift, w.light.blackLift);
        gl.uniform1f(p.u.uSkyScale, w.light.blackScale);
        gl.uniform1f(p.u.uHighlightBoost, 0.17);
        gl.uniform1f(p.u.uTime, w.time);
        gl.uniform3fv(p.u.uSH, w.sh);
        gl.uniform1f(p.u.uFogDensity, 0.0170);
        gl.uniform1f(p.u.uFogTint, 1.0);
        gl.uniform1f(p.u.uFieldPeriod, w.fieldPeriod);
        gl.uniform1f(p.u.uHeightPeriod, w.heightPeriod);
        gl.uniform1f(p.u.uHeightScale, w.heightScale);
        gl.uniform3fv(p.u.uTrampleWin, w.trample.window);
        gl.uniform1f(p.u.uTussock, w.tussock);
        gl.uniform2fv(p.u.uWind, w.windDir);
      }
    };
  }

  /* ---------------------------------------------------------------- */

  /**
   * Choose a drawing-buffer size and a sample count together, against a
   * video-memory budget.
   *
   * This is the bug that made the ground stop being painted. Capping
   * devicePixelRatio at 2 is not enough on its own: a 4x multisampled
   * RGBA16F colour buffer and its depth buffer cost 48 bytes for every
   * drawing-buffer pixel, so an uncapped Retina laptop asked for 8.3 MP
   * (~460 MB of render targets) and a 27-inch Retina display for 14.7 MP
   * (~825 MB). A laptop GPU answers that by thrashing, dropping draws or
   * losing the context, and what you see is a half-painted frame.
   *
   * Budgeting PIXELS alone is not enough either - that spends the whole
   * allowance on samples and then renders below one buffer pixel per CSS
   * pixel, which is softer than it needs to be. So: take the resolution
   * first, down to 1x CSS, and spend whatever is left on antialiasing.
   */
  planTarget() {
    const s = this.settings;
    const gl = this.glw.gl;
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const scale = s.renderScale * this.autoScale;

    const cssPx = Math.max(innerWidth * innerHeight, 1);
    const wantPx = Math.min(cssPx * dpr * dpr * scale * scale, 6.0e6);
    /* below this the upscale starts to show, so we trade samples first */
    const floorPx = cssPx * scale * scale;

    const budget = clamp(s.vramBudget, 48, 1024) * 1048576;
    /* colour + depth are multisampled; the resolve, bloom chain and the
       canvas itself are not */
    const bytesPerPx = (n) => 12 * n + 18.7;
    const maxPxFor = (n) => budget / bytesPerPx(n);

    const wanted = s.msaa
      ? ((QUALITY_PRESETS[s.quality] || QUALITY_PRESETS.high).msaa || 4) : 1;
    const maxSamples = Math.min(wanted, gl.getParameter(gl.MAX_SAMPLES) || 1);

    let samples = 1, px = Math.min(wantPx, maxPxFor(1));
    for (let n = maxSamples; n >= 1; n--) {
      const cap = maxPxFor(n);
      if (cap >= floorPx || n === 1) { samples = n; px = Math.min(wantPx, cap); break; }
    }

    const aspect = innerWidth / Math.max(innerHeight, 1);
    let h = Math.sqrt(px / Math.max(aspect, 1e-3));
    let w = h * aspect;

    const lim = Math.min(gl.getParameter(gl.MAX_TEXTURE_SIZE),
                         gl.getParameter(gl.MAX_RENDERBUFFER_SIZE));
    const shrink = Math.max(w / lim, h / lim, 1);
    return {
      w: Math.max(320, Math.round(w / shrink)),
      h: Math.max(240, Math.round(h / shrink)),
      samples: samples > 1 ? samples : 1
    };
  }

  resize() {
    const gl = this.glw.gl;
    const plan = this.planTarget();
    const { w, h } = plan;

    this.canvas.width = w;
    this.canvas.height = h;
    this.canvas.style.width = '100%';
    this.canvas.style.height = '100%';
    if (this.rw === w && this.rh === h && this.samples === plan.samples) return;
    this.rw = w; this.rh = h;

    if (this.scene) this.scene.free();
    this.scene = plan.samples > 1
      ? this.glw.targetMS(w, h, plan.samples, { depth: true })
      : this.glw.target(w, h, { depth: true });
    const preset = QUALITY_PRESETS[this.settings.quality] || QUALITY_PRESETS.high;
    this.post.resize(w, h, preset.bloomLevels || 6);
    this.samples = this.scene.samples || 1;

    /* Running out of video memory is reported through getError, not by an
       exception, and the symptom downstream is a half-painted frame rather
       than a crash. If it happens, halve the budget and try again. */
    const err = gl.getError();
    if (err === gl.OUT_OF_MEMORY && this.settings.vramBudget > 56) {
      console.warn('grassfield: out of video memory at ' + w + 'x' + h +
                   ' (' + plan.samples + 'x AA), halving the budget');
      this.settings.vramBudget = Math.max(48, this.settings.vramBudget * 0.5);
      this.rw = this.rh = 0;
      this.resize();
    }
  }

  /** Gust strength at the player, for the sound and the readout. */
  gustAt(x, z) {
    const res = this.fieldRes, d = this.fieldData;
    const sx = x - this.windDir[0] * this.windTime * 2.6;
    const sz = z - this.windDir[1] * this.windTime * 2.6;
    let u = (sx / this.fieldPeriod) * res, v = (sz / this.fieldPeriod) * res;
    const xi = Math.floor(u), yi = Math.floor(v);
    const fx = u - xi, fy = v - yi;
    const x0 = ((xi % res) + res) % res, y0 = ((yi % res) + res) % res;
    const x1 = (x0 + 1) % res, y1 = (y0 + 1) % res;
    const g = (X, Y) => d[(Y * res + X) * 4] / 255;
    return lerp(lerp(g(x0, y0), g(x1, y0), fx), lerp(g(x0, y1), g(x1, y1), fx), fy);
  }

  step(dt, input, audio) {
    const s = this.settings;
    this.time += dt;
    /* The wind veers slowly, the way real wind does - but everything here
       scales with the wind setting, so that turning it to zero leaves the
       field genuinely still. A veering direction with no wind behind it
       still rotates every blade, which is not what "0" should mean. */
    const w = Math.min(1, s.wind * 1.4);
    this.windAngle += dt * 0.035 * w * Math.sin(this.time * 0.043 + 1.7);
    this.windDir[0] = Math.cos(this.windAngle);
    this.windDir[1] = Math.sin(this.windAngle);
    this.windTime += dt * 1.15 * w;

    /* ---- look ---- */
    const [ldx, ldy] = input.takeLook();
    this.yaw += ldx;
    /* short of straight up: the view basis degenerates when the
       forward vector lines up with world up */
    this.pitch = clamp(this.pitch - ldy, -1.45, 1.45);
    if (this.yaw > Math.PI) this.yaw -= TAU;
    if (this.yaw < -Math.PI) this.yaw += TAU;

    /* ---- move ---- */
    const mv = input.moveVector();
    const run = input.running(), crouch = input.crouching();
    const sy = Math.sin(this.yaw), cy = Math.cos(this.yaw);
    /* wading through waist-high grass is not a sprint */
    const base = crouch ? 1.05 : (run ? 3.5 : 1.55);
    const target = [
      (mv[0] * cy + mv[1] * sy) * base,
      (mv[0] * sy - mv[1] * cy) * base
    ];
    this.vel[0] = approach(this.vel[0], target[0], 9.0, dt);
    this.vel[2] = approach(this.vel[2], target[1], 9.0, dt);

    this.pos[0] += this.vel[0] * dt;
    this.pos[2] += this.vel[2] * dt;

    const gh = this.walkAt(this.pos[0], this.pos[2]);
    if (this.grounded && input.jumping()) { this.vy = 4.1; this.grounded = false; }
    if (!this.grounded) {
      this.vy -= 18.0 * dt;
      this.pos[1] += this.vy * dt;
      if (this.pos[1] <= gh) { this.pos[1] = gh; this.vy = 0; this.grounded = true; }
    } else {
      this.pos[1] = gh;
    }

    /* ---- head ---- */
    const speed = Math.hypot(this.vel[0], this.vel[2]);
    this.eye = approach(this.eye, crouch ? 1.06 : 1.68, 8.0, dt);
    const bobTarget = this.grounded ? Math.min(speed / 3.5, 1) : 0;
    this.bobAmt = approach(this.bobAmt, bobTarget, 6.0, dt);
    const prevPhase = this.bobPhase;
    this.bobPhase += speed * dt * (crouch ? 2.6 : 1.85);
    if (this.grounded && Math.floor(this.bobPhase / Math.PI) > Math.floor(prevPhase / Math.PI)) {
      audio.footstep(0.4 + this.bobAmt * 0.7);
    }
    const bob = s.headBob;
    this.eyeCur = this.eye
      + Math.sin(this.bobPhase * 2) * 0.030 * this.bobAmt * bob
      - this.bobAmt * 0.018 * bob;
    const sway = Math.sin(this.bobPhase) * 0.026 * this.bobAmt * bob;
    /* a touch of roll when you strafe, the way a shoulder-carried camera does */
    const strafe = (this.vel[0] * cy + this.vel[2] * sy) / Math.max(base, 0.001);
    this.roll = approach(this.roll, -strafe * 0.022 - sway * 0.35, 7.0, dt);

    /* The tussock field has centimetre-scale detail in it, which is
       right for the grass and far too busy for a head. The body follows
       the ground exactly; the camera follows the body through a filter. */
    this.groundSmooth = this.groundSmooth === undefined
      ? this.pos[1] : approach(this.groundSmooth, this.pos[1], 13.0, dt);

    this._playerXZ[0] = this.pos[0];
    this._playerXZ[1] = this.pos[2];
    this.gust = this.gustAt(this.pos[0], this.pos[2]);
    audio.update(this.gust, speed, s.wind);

    /* ---- camera basis ---- */
    const cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
    const fwd = [sy * cp, sp, -cy * cp];
    this.camPos[0] = this.pos[0] + sway * cy;
    this.camPos[1] = this.groundSmooth + this.eyeCur;
    this.camPos[2] = this.pos[2] + sway * sy;
    this.fwdXZ[0] = sy; this.fwdXZ[1] = -cy;

    const aspect = this.canvas.width / Math.max(this.canvas.height, 1);
    const fovY = s.fov * DEG;
    M4.perspective(this.proj, fovY, aspect, 0.055, 26000);
    /* roll about the view axis: rotate the world up vector around forward */
    const upv = rotateAboutAxis([0, 1, 0], fwd, this.roll);
    M4.view(this.viewM, this.camPos, fwd, upv);
    M4.mul(this.viewProj, this.proj, this.viewM);
    M4.invert(this.invViewProj, this.viewProj);

    /* how far off-axis a blade can be before we stop submitting it */
    const halfH = Math.atan(Math.tan(fovY * 0.5) * aspect);
    this.cullDot = Math.cos(Math.min(halfH + 0.6, Math.PI));

    /* ---- quality ---- */
    const preset = QUALITY_PRESETS[s.quality];
    this._density = clamp(s.density * (preset ? preset.density : 1.0) * this.autoScale, 0.05, 2.0);
    this._range = Math.min(s.grassRange, preset ? preset.grassRange : s.grassRange);
  }

  render(dt) {
    const gl = this.glw.gl, s = this.settings;

    this.trample.update(this.pos[0], this.pos[2], dt, 0.55, Math.max(s.trail, 0.5));

    this.glw.bindTarget(this.scene, true);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);
    gl.depthFunc(gl.LEQUAL);

    this.sky.draw(this.env);
    this.terrain.draw(this.env);
    this.grass.draw(this.env);
    this.flies.draw(this.env, s.fireflies);

    if (this.scene.resolve) this.scene.resolve();

    const bloomTex = this.post.bloom(this.scene.tex, s.exposure, 0.32, 0.18, 1.3);
    this.post.composite(this.scene.tex, bloomTex, s);

    /* Grab the frame here, still inside the task that drew it. Without
       preserveDrawingBuffer the contents are gone once we yield. */
    if (this._shot) {
      const done = this._shot;
      this._shot = null;
      try { this.canvas.toBlob(done, 'image/png'); } catch (e) { done(null); }
    }
  }

  /** Ask for a PNG of the next rendered frame. */
  requestShot(done) { this._shot = done; }
}

/** Rotate `v` about unit axis `a` by angle `t` (Rodrigues). */
function rotateAboutAxis(v, a, t) {
  const c = Math.cos(t), s = Math.sin(t);
  const d = a[0] * v[0] + a[1] * v[1] + a[2] * v[2];
  const cx = a[1] * v[2] - a[2] * v[1];
  const cy = a[2] * v[0] - a[0] * v[2];
  const cz = a[0] * v[1] - a[1] * v[0];
  return [
    v[0] * c + cx * s + a[0] * d * (1 - c),
    v[1] * c + cy * s + a[1] * d * (1 - c),
    v[2] * c + cz * s + a[2] * d * (1 - c)
  ];
}
