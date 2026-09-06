/* =====================================================================
   Grassfield - a walkable night prairie.

   The sky you are standing under is the original 360 photograph, mapped
   onto a dome. That part is exact: stars are far enough away that a
   panorama IS a correct sky, no matter how far you walk.

   Everything below the skyline is rebuilt as real geometry, because a
   photograph has no depth and cannot be walked into. The grass is a few
   hundred thousand instanced blades whose colour, density and falloff
   were measured off the photograph's own pixels (tools/build_sky.py),
   so the reconstruction lands on the same palette rather than a guess.
   ===================================================================== */

const TAU = Math.PI * 2;
const DEG = Math.PI / 180;

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (e0, e1, x) => { const t = clamp((x - e0) / (e1 - e0), 0, 1); return t * t * (3 - 2 * t); };
const fract = (x) => x - Math.floor(x);

/* frame-rate independent exponential approach */
const approach = (cur, target, rate, dt) => cur + (target - cur) * (1 - Math.exp(-rate * dt));

/* ---------------------------------------------------------------- 4x4 */
const M4 = {
  ident: () => new Float32Array([1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1]),

  perspective(out, fovY, aspect, near, far) {
    const f = 1 / Math.tan(fovY * 0.5), nf = 1 / (near - far);
    out[0]=f/aspect; out[1]=0; out[2]=0;  out[3]=0;
    out[4]=0; out[5]=f;        out[6]=0;  out[7]=0;
    out[8]=0; out[9]=0;        out[10]=(far+near)*nf; out[11]=-1;
    out[12]=0;out[13]=0;       out[14]=2*far*near*nf; out[15]=0;
    return out;
  },

  /* right-handed look-at built straight from a yaw/pitch basis */
  view(out, eye, fwd, up) {
    const zx=-fwd[0], zy=-fwd[1], zz=-fwd[2];
    let xx = up[1]*zz - up[2]*zy, xy = up[2]*zx - up[0]*zz, xz = up[0]*zy - up[1]*zx;
    const xl = Math.hypot(xx,xy,xz) || 1; xx/=xl; xy/=xl; xz/=xl;
    const yx = zy*xz - zz*xy, yy = zz*xx - zx*xz, yz = zx*xy - zy*xx;
    out[0]=xx; out[1]=yx; out[2]=zx; out[3]=0;
    out[4]=xy; out[5]=yy; out[6]=zy; out[7]=0;
    out[8]=xz; out[9]=yz; out[10]=zz; out[11]=0;
    out[12]=-(xx*eye[0]+xy*eye[1]+xz*eye[2]);
    out[13]=-(yx*eye[0]+yy*eye[1]+yz*eye[2]);
    out[14]=-(zx*eye[0]+zy*eye[1]+zz*eye[2]);
    out[15]=1;
    return out;
  },

  mul(out, a, b) {
    for (let c = 0; c < 4; c++) {
      const b0=b[c*4], b1=b[c*4+1], b2=b[c*4+2], b3=b[c*4+3];
      out[c*4  ] = a[0]*b0 + a[4]*b1 + a[8 ]*b2 + a[12]*b3;
      out[c*4+1] = a[1]*b0 + a[5]*b1 + a[9 ]*b2 + a[13]*b3;
      out[c*4+2] = a[2]*b0 + a[6]*b1 + a[10]*b2 + a[14]*b3;
      out[c*4+3] = a[3]*b0 + a[7]*b1 + a[11]*b2 + a[15]*b3;
    }
    return out;
  },

  invert(out, m) {
    const a00=m[0],a01=m[1],a02=m[2],a03=m[3], a10=m[4],a11=m[5],a12=m[6],a13=m[7],
          a20=m[8],a21=m[9],a22=m[10],a23=m[11], a30=m[12],a31=m[13],a32=m[14],a33=m[15];
    const b00=a00*a11-a01*a10, b01=a00*a12-a02*a10, b02=a00*a13-a03*a10,
          b03=a01*a12-a02*a11, b04=a01*a13-a03*a11, b05=a02*a13-a03*a12,
          b06=a20*a31-a21*a30, b07=a20*a32-a22*a30, b08=a20*a33-a23*a30,
          b09=a21*a32-a22*a31, b10=a21*a33-a23*a31, b11=a22*a33-a23*a32;
    let det = b00*b11 - b01*b10 + b02*b09 + b03*b08 - b04*b07 + b05*b06;
    if (!det) return null;
    det = 1 / det;
    out[0]=(a11*b11-a12*b10+a13*b09)*det;  out[1]=(a02*b10-a01*b11-a03*b09)*det;
    out[2]=(a31*b05-a32*b04+a33*b03)*det;  out[3]=(a22*b04-a21*b05-a23*b03)*det;
    out[4]=(a12*b08-a10*b11-a13*b07)*det;  out[5]=(a00*b11-a02*b08+a03*b07)*det;
    out[6]=(a32*b02-a30*b05-a33*b01)*det;  out[7]=(a20*b05-a22*b02+a23*b01)*det;
    out[8]=(a10*b10-a11*b08+a13*b06)*det;  out[9]=(a01*b08-a00*b10-a03*b06)*det;
    out[10]=(a30*b04-a31*b02+a33*b00)*det; out[11]=(a21*b02-a20*b04-a23*b00)*det;
    out[12]=(a11*b07-a10*b09-a12*b06)*det; out[13]=(a00*b09-a01*b07+a02*b06)*det;
    out[14]=(a31*b01-a30*b03-a32*b00)*det; out[15]=(a20*b03-a21*b01+a22*b00)*det;
    return out;
  }
};

/* ------------------------------------------------------------- noise --
   A tiny seeded value-noise generator. It runs on the CPU only, at load
   time, to bake the two lookup textures the renderer reads. Baking rather
   than evaluating noise live is what keeps the ground the player walks on
   bit-identical to the ground the vertex shader draws - hash functions
   famously disagree between CPU and GPU, and a mismatch there shows up as
   the camera sinking into or floating over the field.                    */

function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Tileable value noise on an N x N integer lattice. */
function latticeNoise(nx, ny, rnd) {
  const g = new Float32Array(nx * ny);
  for (let i = 0; i < g.length; i++) g[i] = rnd();
  return g;
}

function sampleLattice(g, nx, ny, x, y) {
  const xi = Math.floor(x), yi = Math.floor(y);
  let fx = x - xi, fy = y - yi;
  fx = fx * fx * (3 - 2 * fx);
  fy = fy * fy * (3 - 2 * fy);
  const x0 = ((xi % nx) + nx) % nx, y0 = ((yi % ny) + ny) % ny;
  const x1 = (x0 + 1) % nx, y1 = (y0 + 1) % ny;
  const a = g[y0 * nx + x0], b = g[y0 * nx + x1], c = g[y1 * nx + x0], d = g[y1 * nx + x1];
  return lerp(lerp(a, b, fx), lerp(c, d, fx), fy);
}

/**
 * Tileable fractal noise over [0,1)^2. `bx` and `by` are the lattice
 * resolutions of the first octave and every octave doubles both, so the
 * result always tiles at period 1. Independent x and y resolutions let a
 * field be stretched into streaks without breaking the tiling - which is
 * how the worn tracks and the mat of thatch get their direction.
 */
function makeFbm2(seed, bx, by, octaves, gain) {
  const layers = [];
  const rnd = mulberry32(seed);
  for (let o = 0; o < octaves; o++) {
    const nx = bx << o, ny = by << o;
    layers.push({ nx, ny, g: latticeNoise(nx, ny, rnd), amp: Math.pow(gain, o) });
  }
  const norm = 1 / layers.reduce((s, l) => s + l.amp, 0);
  return (u, v) => {
    let s = 0;
    for (const l of layers) s += l.amp * sampleLattice(l.g, l.nx, l.ny, u * l.nx, v * l.ny);
    return s * norm;
  };
}

/** Isotropic case of makeFbm2. */
function makeFbm(seed, base, octaves, gain) {
  return makeFbm2(seed, base, base, octaves, gain);
}

/* ------------------------------------------------------------- wind --
   Real wind is not a sine wave. It sits mostly below its own peaks: long
   lulls, then a gust that builds and dies over a few seconds, with the
   direction veering as it does. That shape is what layered 1/f noise in
   TIME gives you, so the field gets one of those rather than a clock. */

function makeWindNoise(seed) {
  const N = 1024;
  const rnd = mulberry32(seed);
  const g = new Float32Array(N);
  for (let i = 0; i < N; i++) g[i] = rnd();
  const at = (x) => {
    const i = Math.floor(x);
    let f = x - i;
    f = f * f * (3 - 2 * f);
    const a = g[((i % N) + N) % N], b = g[((((i + 1) % N)) + N) % N];
    return a + (b - a) * f;
  };
  return (t, octaves) => {
    let sum = 0, amp = 1, tot = 0, fr = 1;
    for (let o = 0; o < (octaves || 4); o++) {
      sum += amp * at(t * fr);
      tot += amp;
      amp *= 0.55;
      fr *= 2.13;
    }
    return sum / tot;
  };
}

/* --------------------------------------------------------- settings -- */
const SETTINGS_KEY = 'grassfield.settings.v1';

function loadSettings(defaults) {
  const s = Object.assign({ _touched: false }, defaults);
  try {
    const raw = localStorage.getItem(SETTINGS_KEY);
    if (raw) {
      const j = JSON.parse(raw);
      for (const k in defaults) if (k in j && typeof j[k] === typeof defaults[k]) s[k] = j[k];
      s._touched = !!j._touched;
    }
  } catch (e) { /* private mode, blocked storage - defaults are fine */ }
  return s;
}

function saveSettings(s) {
  /* Marks the settings as the user's own, so first-run device defaults
     are applied once and never override a deliberate choice later. */
  s._touched = true;
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch (e) {}
}
