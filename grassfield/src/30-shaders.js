/* ===================================================================
   Shared GLSL. Every pass pastes CHUNK.common in, so the sky lookup,
   the lighting model and the fog are literally the same code in the
   sky, the terrain and the grass - which is why they meet at the
   skyline without a seam.
   =================================================================== */

const CHUNK = {};

CHUNK.head = `#version 300 es
precision highp float;
precision highp int;
`;

CHUNK.common = `
const float PI  = 3.14159265359;
const float TAU = 6.28318530718;

/* ---- colour space ---- */
vec3 srgbToLinear(vec3 c){
  return mix(c / 12.92, pow((c + 0.055) / 1.055, vec3(2.4)), step(vec3(0.04045), c));
}
vec3 linearToSrgb(vec3 c){
  c = max(c, vec3(0.0));
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0/2.4)) - 0.055, step(vec3(0.0031308), c));
}
float luma(vec3 c){ return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

/* ---- hashing (Dave Hoskins style: no sin, stable across drivers) ---- */
float hash11(float p){
  p = fract(p * 0.1031);
  p *= p + 33.33;
  p *= p + p;
  return fract(p);
}
vec2 hash21(float p){
  vec3 p3 = fract(vec3(p) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.xx + p3.yz) * p3.zy);
}
vec3 hash31(float p){
  vec3 p3 = fract(vec3(p) * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.xxy + p3.yzz) * p3.zyx);
}
vec4 hash41(float p){
  vec4 p4 = fract(vec4(p) * vec4(0.1031, 0.1030, 0.0973, 0.1099));
  p4 += dot(p4, p4.wzxy + 33.33);
  return fract((p4.xxyz + p4.yzzw) * p4.zywx);
}
/* Hash a 2D lattice cell. Feeding a raw instance id into a hash is a
   precision trap: at 900k instances the value needs 20 bits of mantissa
   before fract() ever runs, leaving about 4 bits of randomness. Cell
   coordinates stay small, so this is both better distributed and stable
   in world space - a blade keeps its identity no matter how the grid
   covering it happens to be indexed this frame. */
vec4 hash42(vec2 p){
  vec4 p4 = fract(p.xyxy * vec4(0.1031, 0.1030, 0.0973, 0.1099));
  p4 += dot(p4, p4.wzxy + 33.33);
  return fract((p4.xxyz + p4.yzzw) * p4.zywx);
}

vec3 hash33(vec3 p3){
  p3 = fract(p3 * vec3(0.1031, 0.1030, 0.0973));
  p3 += dot(p3, p3.yxz + 33.33);
  return fract((p3.xxy + p3.yxx) * p3.zyx);
}

/* =====================================================================
   The sky.
   uSky holds the original photograph as a 2:1 equirectangular dome.
   The build step lifted the black point to stop JPEG blocking in the
   deep sky; uSkyLift/uSkyScale undo that exactly.
   ===================================================================== */
uniform sampler2D uSky;
uniform float uSkyLift;
uniform float uSkyScale;
uniform float uHighlightBoost;
uniform float uTime;

vec2 dirToEquirect(vec3 d){
  return vec2(atan(d.x, -d.z) * 0.15915494 + 0.5,
              acos(clamp(d.y, -1.0, 1.0)) * 0.31830989);
}

/* Photograph as linear radiance, black point restored. */
vec3 skyPlate(vec3 d){
  vec3 c = textureLod(uSky, dirToEquirect(d), 0.0).rgb;
  c = max((c - uSkyLift) / uSkyScale, vec3(0.0));
  return srgbToLinear(c);
}

/* An 8-bit photograph has no headroom, so nothing in it would ever bloom.
   Re-expanding the top end puts the galactic core and the brighter stars
   back above 1.0 where the bloom pass can find them. The lift is driven
   by luminance so the airglow band stays where the photograph put it. */
vec3 skyHDR(vec3 d){
  vec3 c = skyPlate(d);
  float l = luma(c);
  /* Only the top of the range moves. The airglow band and the dust lanes
     stay exactly where the photograph put them; the core and the brighter
     stars get just enough headroom to bloom. */
  float hi = smoothstep(0.15, 0.40, l);
  return c * (1.0 + uHighlightBoost * hi * hi * 1.9);
}

/* =====================================================================
   Lighting.
   uSH is an order-2 spherical-harmonic projection of the sky above,
   baked by tools/build_sky.py. On a night this dark the sky IS the
   light, so this single term carries almost the whole image.
   ===================================================================== */
uniform vec3 uSH[9];

vec3 shIrradiance(vec3 n){
  const float c1 = 0.429043, c2 = 0.511664, c3 = 0.743125,
              c4 = 0.886227, c5 = 0.247708;
  return  c1 * uSH[8] * (n.x*n.x - n.y*n.y)
        + c3 * uSH[6] * (n.z*n.z)
        + c4 * uSH[0]
        - c5 * uSH[6]
        + 2.0 * c1 * (uSH[4]*n.x*n.y + uSH[7]*n.x*n.z + uSH[5]*n.y*n.z)
        + 2.0 * c2 * (uSH[3]*n.x + uSH[1]*n.y + uSH[2]*n.z);
}

/* =====================================================================
   Distance haze.
   Fog is not a grey constant - it is the sky, sampled in the direction
   you are looking, at the height of the horizon. That is what makes the
   far grass dissolve into the green airglow band on the left and the
   warm light dome on the right, exactly as it does in the photograph.
   ===================================================================== */
uniform float uFogDensity;
uniform float uFogTint;

vec3 hazeColour(vec3 viewDir){
  /* Aerial perspective is light scattered in from the WHOLE sky, not just
     the strip on the skyline. Taking only the horizon plate made the far
     field too warm, because the horizon is where the light-pollution
     domes are; folding in the sky's average radiance puts the airglow's
     green back into the distance, where the photograph has it. */
  vec3 h = normalize(vec3(viewDir.x, 0.055, viewDir.z));
  vec3 amb = shIrradiance(vec3(0.0, 1.0, 0.0)) * (1.0 / PI);
  return mix(skyPlate(h), amb * 1.45, 0.42) * uFogTint;
}

float hazeAmount(float dist){
  return 1.0 - exp(-dist * uFogDensity);
}

/* =====================================================================
   Field lookup texture (RGBA8, tiling every uFieldPeriod metres)
     r  gust field       - drives the travelling wind waves
     g  clump height     - tufts and thin patches
     b  comb direction   - the prevailing lie of the grass
     a  bare-ground mask - the trodden paths in the photograph
   ===================================================================== */
uniform sampler2D uField;
uniform float uFieldPeriod;
uniform vec2 uWind;          /* prevailing wind, unit length, world XZ */

vec4 field(vec2 world){ return textureLod(uField, world / uFieldPeriod, 0.0); }
vec4 fieldAt(vec2 world, float scale){ return textureLod(uField, world / (uFieldPeriod * scale), 0.0); }
float fieldR(vec2 world, float scale){ return fieldAt(world, scale).r; }
float fieldG(vec2 world, float scale){ return fieldAt(world, scale).g; }

/* Terrain height, baked to an R16F texture so the CPU (which decides
   where your feet are) and the vertex shader (which decides where the
   ground is drawn) cannot possibly disagree. */
uniform sampler2D uHeight;
uniform float uHeightPeriod;
uniform float uHeightScale;

/* =====================================================================
   Detail texture (RGBA8, tiling every uDetailPeriod metres)

   The field texture above works at tens of metres - swathes, gusts, worn
   tracks. This one works at ONE metre, which is the scale a tussock
   actually is. Trying to carry both in one texture meant sampling the
   coarse field at a tiny scale, and its fine octaves then turned the
   mound signal into noise: the hollows came out speckled instead of
   shaped, and the grass never grouped into tufts.

     r  mound height    - the dome each tussock sits on
     g  local comb      - which way THIS tuft is combed
     b  length          - how long its blades run
     a  spare variation
   ===================================================================== */
uniform sampler2D uDetail;
uniform float uDetailPeriod;
uniform float uTussock;

vec4 detail(vec2 world){ return textureLod(uDetail, world / uDetailPeriod, 0.0); }

float groundHeight(vec2 world){
  return textureLod(uHeight, world / uHeightPeriod, 0.0).r * uHeightScale;
}

/* Grass does not grow on a plane. It grows in tussocks, and the hollows
   between them are where the photograph's blacks come from - there is no
   sky down there at all. A metre-scale mound field on top of the terrain
   is what gives the canopy somewhere to cast those hollows. */
float surfaceHeight(vec2 world){
  return groundHeight(world) + (detail(world).r - 0.5) * uTussock;
}
vec3 groundNormal(vec2 world, float eps){
  float hx = groundHeight(world + vec2(eps, 0.0)) - groundHeight(world - vec2(eps, 0.0));
  float hz = groundHeight(world + vec2(0.0, eps)) - groundHeight(world - vec2(0.0, eps));
  return normalize(vec3(-hx, 2.0 * eps, -hz));
}

/* ---- trample: a decaying footprint map that follows the player ---- */
uniform sampler2D uTrample;
uniform vec3 uTrampleWin;   /* x,y = window origin (world), z = window size */

float trampleAt(vec2 world){
  vec2 uv = (world - uTrampleWin.xy) / uTrampleWin.z;
  if (any(lessThan(uv, vec2(0.0))) || any(greaterThan(uv, vec2(1.0)))) return 0.0;
  return textureLod(uTrample, uv, 0.0).r;
}

/* Sky sheen.

   The bright strands in the photograph are not a highlight from one
   light - there isn't one bright enough. They are the whole sky dome
   reflecting off waxy leaf surfaces, which is why they appear on every
   blade turned face-up and why they run silver rather than green. A
   Fresnel-weighted lookup of the sky's own irradiance in the reflected
   direction reproduces them almost for free.                          */
vec3 skySheen(vec3 n, vec3 v, float amount){
  vec3 r = reflect(-v, n);
  /* Leaf cuticle, but a rough one. A textbook Fresnel term runs to 1.0 at
     grazing incidence, and a blade seen edge-on then mirrors whatever is
     on the horizon - which here is a warm light-pollution dome, so the
     whole field turned khaki and grew wiry yellow streaks. Capping the
     grazing response is what a rough surface does anyway. */
  const float f0 = 0.045, fMax = 0.40;
  float f = f0 + (fMax - f0) * pow(1.0 - clamp(dot(n, v), 0.0, 1.0), 4.0);

  /* Part mirror, part diffuse dome. The sharp half is what makes a blade
     turned toward the galactic core glint while its neighbour does not;
     the smooth half stops that from becoming a field of hot wires. */
  vec3 refl = mix(shIrradiance(r) * (1.0 / PI), skyPlate(r), 0.62);
  return refl * f * amount;
}

/* ---- specular ---- */
float ggx(vec3 n, vec3 v, vec3 l, float rough){
  vec3 h = normalize(v + l);
  float a = max(rough * rough, 1e-3);
  float a2 = a * a;
  float ndh = max(dot(n, h), 0.0);
  float ndv = max(dot(n, v), 1e-4);
  float ndl = max(dot(n, l), 0.0);
  float dd = ndh * ndh * (a2 - 1.0) + 1.0;
  float D = a2 / (PI * dd * dd);
  float k = a * 0.5;
  float G = (ndl / (ndl * (1.0 - k) + k)) * (ndv / (ndv * (1.0 - k) + k));
  return D * G / (4.0 * ndv * ndl + 1e-4);
}
`;

CHUNK.tonemap = `
/* A shoulder, and nothing else.
   ACES and its cousins are built for footage that has to survive a grade.
   Here the source IS a finished photograph, so any curve that lifts or
   crushes the midtones is throwing away the very thing we are trying to
   match. Below the knee this is the identity - the sky comes out of the
   renderer at exactly the value the photograph had - and above it rolls
   off asymptotically so a boosted galactic core glows instead of
   clipping to a white hole. */
vec3 shoulder(vec3 x){
  const float k = 0.55;
  vec3 hi = 1.0 - (1.0 - k) * exp(-(x - k) / (1.0 - k));
  return max(mix(x, hi, step(vec3(k), x)), vec3(0.0));
}
vec3 saturate3(vec3 c, float s){
  return max(mix(vec3(luma(c)), c, s), vec3(0.0));
}
`;

/* Fragment-only. `fwidth` does not exist in a vertex shader, so anything
   that measures its own pixel footprint has to live in its own chunk. */
CHUNK.stars = `
/* Round, twinkling stars for the zenith cap.
   The photograph is cropped at +76 degrees, and anything synthesised into
   an equirect near the pole smears sideways. So the cap in the texture is
   deliberately smooth and the actual points are drawn here, in 3D, where
   they stay round however you tilt your head. Star size follows the
   pixel footprint and brightness is flux-conserved, so they neither
   sparkle-crawl at low resolution nor bloat at high. */
vec3 starfield(vec3 d, float amount){
  if (amount <= 0.001) return vec3(0.0);
  vec3 acc = vec3(0.0);
  for (int layer = 0; layer < 2; ++layer){
    float scale = layer == 0 ? 165.0 : 395.0;
    float bias  = layer == 0 ? 0.9835 : 0.9955;
    vec3 p  = d * scale;
    vec3 id = floor(p);
    vec3 f  = fract(p) - 0.5;
    vec3 h  = hash33(id + float(layer) * 71.3);
    float pick = h.z;
    if (pick < bias) continue;
    vec3 off = (hash33(id + 13.7) - 0.5) * 0.62;
    float dist = length(f - off);

    float px  = max(length(fwidth(p)), 1e-4);
    float rad = max(0.028, px * 0.85);
    float g   = exp(-pow(dist / rad, 2.0) * 2.2);
    g *= min(1.0, (0.028 / rad) * (0.028 / rad));   // conserve flux

    float mag = pow(fract(pick * 91.7), 4.5);
    /* stars low in the sky scintillate hard; overhead they barely move */
    float tw  = 1.0 + mix(0.06, 0.62, pow(1.0 - clamp(d.y, 0.0, 1.0), 3.0))
                    * (hash11(h.x * 733.0 + floor(uTime * 7.0 + h.y * 40.0)) - 0.5) * 2.0;
    vec3 tint = mix(vec3(1.0, 0.86, 0.70), vec3(0.74, 0.83, 1.0), h.y);
    acc += tint * g * (0.06 + mag * 3.4) * max(tw, 0.0);
  }
  return acc * amount;
}

/* Fade the synthetic stars in only where the photograph runs out. */
float zenithBlend(vec3 d){
  return smoothstep(0.80, 0.985, d.y);
}

vec3 skyFull(vec3 d){
  return skyHDR(d) + starfield(d, zenithBlend(d) * 0.85 + 0.05);
}
`;
