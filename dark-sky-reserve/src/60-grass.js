/* ===================================================================
   Grass.

   Every blade is an instance with no per-instance buffer at all: the
   vertex shader hashes gl_InstanceID into a cell of a grid that is
   re-centred on the camera each frame, so the field is endless and
   costs nothing on the CPU. Four rings of decreasing density and
   segment count carry it from your bootlaces to the skyline.

   The bend is a true circular arc, not a bezier. An arc of fixed length
   cannot stretch, so a blade in a gale is exactly as long as a blade at
   rest - which is the difference between grass and rubber.
   =================================================================== */

const GRASS_VS = CHUNK.head + CHUNK.common + `
in vec2 aV;                  /* x: -1..1 across the blade, y: 0..1 along it */

uniform mat4 uViewProj;
uniform vec3 uCam;
uniform vec2 uFwdXZ;
uniform float uCullDot;

uniform vec2 uOriginCell;    /* integer world cell of grid slot (0,0) */
uniform float uCell;
uniform int  uGridW;
uniform int  uGridH;
uniform int  uInstanceBase;  /* draws are chunked; this is the offset */
uniform vec2 uRange;         /* radial band this ring covers */
uniform vec2 uFadeIn;
uniform vec2 uFadeOut;
uniform float uSeed;

uniform float uBladeHeight;
uniform float uBladeWidth;
uniform float uWidthMul;
uniform float uViewFace;
uniform float uCurve;

uniform float uWindStrength;
uniform float uWindTime;
uniform float uBaseBend;

uniform vec2  uPlayerXZ;
uniform vec2  uPlayerVel;    /* unit heading, zero when standing still */
uniform float uPlayerSpeed;  /* 0..1, normalised against a run */
uniform float uPartRadius;
uniform float uPartStrength;

out vec3 vWorld;
out vec3 vNormal;
out float vT;
out float vColVar;
out float vDist;
out float vAO;

void cull(){ gl_Position = vec4(2.0, 2.0, 2.0, 1.0); }

void main(){
  int id = gl_InstanceID + uInstanceBase;
  int gz = id / uGridW;
  if (gz >= uGridH) { cull(); return; }
  vec2 cellF = uOriginCell + vec2(float(id - gz * uGridW), float(gz));

  vec4 h0 = hash42(cellF + uSeed);
  vec2 base = (cellF + 0.5 + (h0.xy - 0.5) * 0.94) * uCell;

  vec2 toCam = base - uCam.xz;
  float dist = length(toCam);
  if (dist < uRange.x || dist > uRange.y) { cull(); return; }
  if (dist > 4.0 && dot(toCam / dist, uFwdXZ) < uCullDot) { cull(); return; }

  vec4 f = field(base);
  /* Tufts at two scales. The photograph's field is organised into broad
     swathes tens of metres across with smaller tussocks inside them; one
     octave of clumping only ever gives you an even stipple. */
  float clump = clamp(f.g * 0.52 + fieldG(base, 3.1) * 0.48, 0.0, 1.0);
  float bare  = f.a;
  /* thinner patches and the worn tracks that run through the photograph */
  if (h0.w > mix(0.30, 1.0, smoothstep(0.26, 0.66, bare))) { cull(); return; }

  float fade = smoothstep(uFadeIn.x, uFadeIn.y, dist)
             * (1.0 - smoothstep(uFadeOut.x, uFadeOut.y, dist));
  if (fade < 0.02) { cull(); return; }

  vec4 h1 = hash42(cellF * 1.6180339 + (uSeed + 7.31));

  /* The same mound field the ground is displaced by. Grass grows longer
     on a tussock and thins out in the hollow between them, and coupling
     the two is what turns a flat sward into the lumpy, shadowed surface
     the photograph has. */
  vec4 det = detail(base);
  float mound = det.r;

  /* how tall this blade is relative to the others in its own tuft */
  float rel   = 0.40 + 0.98 * pow(clamp(h1.x, 0.0, 1.0), 1.30);
  float hgt   = uBladeHeight * rel
                             * (0.60 + 0.86 * clump)
                             * (0.74 + 0.40 * mound)
                             * (0.80 + 0.36 * det.b) * fade;
  float halfW = uBladeWidth * uWidthMul * (0.68 + 0.64 * h1.y);

  /* A few blades in every hundred stand taller and finer than the rest,
     so the top of the canopy breaks into individual strokes rather than
     a mown edge. Kept modest - overdone, they read as bamboo. */
  float stalk = smoothstep(0.955, 0.995, h0.z);
  hgt   *= 1.0 + 0.30 * stalk;
  halfW *= 1.0 + 0.22 * stalk;
  float roll  = h1.z * TAU;
  float phase = h1.w * TAU;
  float stiff = 0.60 + 0.65 * h0.z;

  /* ---- which way it lies ------------------------------------------
     Coarse comb from the swathe field, plus a per-tuft turn: in the
     photograph each tussock is combed its own way inside the broader
     sweep, and without the second term the whole field brushes as one.
     Then a little per-blade disagreement on top, because grass that all
     leans identically reads as carpet pile. */
  float combAng = atan(uWind.y, uWind.x)
                + (f.b - 0.5) * 1.55 + (det.g - 0.5) * 1.15;
  vec2 comb = vec2(cos(combAng), sin(combAng));
  vec2 jit  = vec2(cos(h1.z * TAU), sin(h1.z * TAU));
  /* Pulled toward the wind, but not all the way: grass that all points
     downwind reads as carpet pile, and the photograph plainly does not. */
  vec2 lean2 = normalize(mix(normalize(mix(comb, uWind, 0.22 + 0.26 * uWindStrength)),
                             jit, 0.26) + vec2(1e-5, 0.0));

  /* ---- how far it bends -------------------------------------------
     Two travelling noise fields scrolled along the wind vector give the
     long waves that roll across a field, plus a finer ripple on top;
     a per-blade sine adds the individual nodding. */
  vec2 sc = uWind * uWindTime;
  float g1 = fieldR(base - sc * 2.6, 1.0);
  float g2 = fieldR(base - sc * 6.2, 0.26);
  float sway = sin(uWindTime * 2.4 / stiff + phase + dot(base, uWind) * 0.85);

  /* How far a patch is permanently laid over. This is the single thing
     that gives the photograph its banding: grass pressed flat turns its
     blades face-up to the sky and goes pale, grass still standing is
     edge-on and reads almost black. Making it a broad spatial field
     rather than per-blade noise is what produces swathes. */
  float lay = fieldR(base, 2.6);

  float gustAmp = uWindStrength * (0.42 + 0.80 * g1);
  float bend = uBaseBend * (0.42 + 0.46 * clump + 0.62 * lay)
             + gustAmp * (0.62 + 0.34 * (g2 - 0.5) * 2.0 + 0.24 * sway);
  bend *= 0.72 + 0.48 * h1.x;

  /* ---- the player pushes through ----------------------------------
     Blades are shoved away radially AND carried along the direction of
     travel, so moving through the field opens a wake in front of you
     rather than a symmetrical bubble around you. The reach and the force
     both grow with speed: walking parts the grass, running flattens it. */
  vec2 toP = base - uPlayerXZ;
  float dp = length(toP) + 1e-4;
  vec2 outward = toP / dp;
  float reach = uPartRadius * (1.0 + 0.85 * uPlayerSpeed);
  /* elongate the affected patch along the direction of travel */
  float along = dot(outward, uPlayerVel);
  float shaped = dp * (1.0 - 0.30 * uPlayerSpeed * along);
  float push = smoothstep(reach, reach * 0.12, shaped)
             * uPartStrength * (0.55 + 0.75 * uPlayerSpeed);
  vec2 shove = normalize(outward + uPlayerVel * (0.85 * uPlayerSpeed) + vec2(1e-5, 0.0));
  /* the shove can cancel the lean exactly; keep it off zero */
  lean2 = normalize(lean2 + shove * push * 3.4 + vec2(1.0e-6, 0.0));
  bend += push * 1.15;

  /* ---- and leaves a trail ----------------------------------------- */
  float tr = trampleAt(base);
  bend += tr * 1.05;
  hgt  *= 1.0 - tr * 0.22;

  bend = clamp(bend * (1.0 - 0.35 * stalk), 0.015, 1.85);

  float gh = surfaceHeight(base);

  /* ---- circular-arc bend, length preserved exactly ---------------- */
  float t = aV.y;
  vec3 up = vec3(0.0, 1.0, 0.0);
  vec3 ld = vec3(lean2.x, 0.0, lean2.y);
  float s = t * bend;
  vec3 pos = (hgt / bend) * ((1.0 - cos(s)) * ld + sin(s) * up);
  vec3 tangent = normalize(sin(s) * ld + cos(s) * up);

  /* stable frame: sideBase is horizontal and never collapses, however
     far the blade lies over */
  vec3 sideBase = vec3(-ld.z, 0.0, ld.x);
  vec3 n0 = normalize(cross(sideBase, tangent));
  vec3 sideAxis = sideBase * cos(roll) + n0 * sin(roll);

  /* far rings turn edge-on blades toward the camera so they do not
     flicker out of existence at a kilometre */
  if (uViewFace > 0.001){
    vec3 toEye = normalize(uCam - (vec3(base.x, gh, base.y) + pos));
    vec3 billboard = cross(tangent, toEye);
    float bl = length(billboard);
    if (bl > 1e-3) {
      vec3 mixed = mix(sideAxis, billboard / bl, uViewFace);
      float ml = length(mixed);
      if (ml > 1.0e-4) sideAxis = mixed / ml;
    }
  }
  vec3 faceN = normalize(cross(sideAxis, tangent));

  float w = halfW * pow(max(1.0 - t, 0.0), 0.45) * (1.0 - 0.32 * t);

  /* high-frequency flutter, strongest at the tip */
  float flut = sin(uWindTime * 6.1 / stiff + phase * 3.1 + base.x * 2.3)
             * 0.016 * t * t * gustAmp;

  vec3 local = pos + sideAxis * (aV.x * w + flut);
  vWorld = vec3(base.x, gh, base.y) + local;

  /* the cross-section of a blade is a shallow trough, not a plane */
  vNormal = normalize(faceN + sideAxis * (aV.x * uCurve));
  vT = t;
  /* tufts catch the light together - weighting the clump field over
     the per-blade hash is what produces the pale streaks that run
     across the photograph, instead of even salt-and-pepper */
  /* Laid-over patches are the pale ones, so the colour variation has to
     follow the same field as the bend, not an independent hash. */
  vColVar = clamp(h1.y * 0.18 + clump * 0.26 + lay * 0.30 + mound * 0.26, 0.0, 1.0);
  vDist = length(uCam - vWorld);
  /* Almost NO sky reaches the bottom of a real canopy. The photograph's
     hollows are essentially black, and a gentle root-to-tip ramp cannot
     produce that - the falloff has to be steep and it has to bottom out
     near zero, or the whole field turns into flat grey felt. */
  float ao = mix(0.025, 1.0, pow(t, 1.95)) * mix(0.66, 1.0, 1.0 - clump * 0.55);
  /* A blade shorter than its neighbours is buried inside the canopy and
     sees almost no sky, however near its own tip you are. Without this
     every blade at a given height is lit identically and the field has
     no hollows in it at all - just even fur. */
  ao *= mix(0.32, 1.0, smoothstep(0.42, 1.05, rel));
  /* down in the hollow between tussocks little sky reaches the roots */
  ao *= mix(0.46, 1.0, smoothstep(0.05, 0.85, mound));
  /* Close up you see down into the canopy, where it is nearly black. At
     fifty metres you only resolve the tops, and the dark interior is
     hidden behind them - so the same occlusion term has to relax with
     distance or the far field comes out far too dark. */
  vAO = mix(ao, mix(ao, 1.0, 0.72), smoothstep(7.0, 55.0, dist));

  gl_Position = uViewProj * vec4(vWorld, 1.0);
}`;

const GRASS_FS = CHUNK.head + CHUNK.common + `
in vec3 vWorld;
in vec3 vNormal;
in float vT;
in float vColVar;
in float vDist;
in float vAO;
out vec4 oColor;

uniform vec3 uCam;
uniform vec3 uGrassDark;
uniform vec3 uGrassLight;
uniform vec3 uCoreDir;
uniform vec3 uCoreColour;
uniform float uSpecular;
uniform float uSheen;
uniform float uTranslucency;
uniform float uBackLight;
uniform float uGroundGain;

void main(){
  vec3 N = normalize(vNormal);
  if (!gl_FrontFacing) N = -N;
  vec3 V = normalize(uCam - vWorld);
  vec3 D = -V;

  vec3 albedo = mix(uGrassDark, uGrassLight, vColVar);
  albedo *= mix(0.38, 1.22, vT);          /* dark at the root, pale at the tip */

  vec3 amb = shIrradiance(N) * (1.0 / PI) * vAO;

  /* light passing through the leaf from behind - the thing that makes a
     field read as grass rather than as green plastic */
  float t01 = clamp(vT, 0.0, 1.0);      /* an interpolated varying can overshoot */
  vec3 trans = shIrradiance(-N) * (1.0 / PI) * uTranslucency * pow(t01, 1.3) * vAO;

  /* and the airglow band directly behind the blade, catching its edge */
  /* A squared edge term lights an edge-on blade evenly down its whole
     length and the field fills with bright scratches. Cubed, only the
     blades genuinely presenting an edge catch it. */
  vec3 behind = normalize(vec3(D.x, 0.06, D.z));
  /* N and V are both unit, but the dot product still rounds to a hair
     over 1, and pow() of a negative base is NaN - which the bloom chain
     then smears into a black rectangle. This was the black squares. */
  float edge = pow(max(1.0 - abs(dot(N, V)), 0.0), 3.0);
  vec3 rim = skyPlate(behind) * edge * uBackLight * pow(t01, 1.15) * vAO;

  vec3 sheen = skySheen(N, V, uSheen) * mix(0.12, 1.0, vAO);
  vec3 spec = uCoreColour * ggx(N, V, uCoreDir, 0.42)
            * max(dot(N, uCoreDir), 0.0) * uSpecular;

  vec3 col = albedo * (amb + trans) * uGroundGain + albedo * rim + sheen + spec;

  col = mix(col, hazeColour(D), hazeAmount(vDist));
  oColor = vec4(col, 1.0);
}`;

/* ------------------------------------------------------------------ */

/* Never hand a driver more than this many instances in one draw. */
const INSTANCE_CHUNK = 65536;

class GrassRing {
  constructor(cfg) { Object.assign(this, cfg); }
}

class Grass {
  constructor(glw) {
    this.glw = glw;
    const gl = glw.gl;
    this.prog = glw.program(GRASS_VS, GRASS_FS, 'grass');

    /* one blade mesh per segment count, shared by the rings that use it */
    this.meshes = new Map();

    /* r0..r1 metres, cell size, segments, blade width multiplier,
       how much the blade turns to face you, and cross-section curl. */
    this.rings = [
      new GrassRing({ name: 'near', r0: 0.0,  r1: 6.5,   cell: 0.048, seg: 5, width: 1.00, viewFace: 0.00, curve: 0.75, seed: 11.0 }),
      new GrassRing({ name: 'mid',  r0: 5.6,  r1: 22.0,  cell: 0.100, seg: 3, width: 1.75, viewFace: 0.30, curve: 0.60, seed: 137.0 }),
      new GrassRing({ name: 'far',  r0: 21.0, r1: 65.0,  cell: 0.245, seg: 2, width: 3.60, viewFace: 0.72, curve: 0.40, seed: 613.0 }),
      /* Past this the haze has taken over and single blades are smaller
         than a pixel, so the ground mat carries it to the skyline - which
         is what the photograph does too: its horizon is a clean line. */
      new GrassRing({ name: 'edge', r0: 63.0, r1: 130.0, cell: 0.640, seg: 1, width: 8.00, viewFace: 1.00, curve: 0.20, seed: 2711.0 })
    ];
    for (const r of this.rings) {
      r.mesh = this.mesh(r.seg);
      r.fadeIn = r.r0 <= 0.001 ? [-1, -0.5] : [r.r0, r.r0 + (r.r1 - r.r0) * 0.16];
      r.fadeOut = [r.r1 - (r.r1 - r.r0) * 0.20, r.r1];
    }
  }

  mesh(seg) {
    if (this.meshes.has(seg)) return this.meshes.get(seg);
    const gl = this.glw.gl;
    const v = [];
    for (let i = 0; i < seg; i++) { const t = i / seg; v.push(-1, t, 1, t); }
    v.push(0, 1);                                     /* the tip */
    const idx = [];
    for (let i = 0; i < seg - 1; i++) {
      const a = i * 2, b = a + 1, c = a + 2, d = a + 3;
      idx.push(a, b, c, b, d, c);
    }
    idx.push((seg - 1) * 2, (seg - 1) * 2 + 1, seg * 2);

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    this.glw.buffer(gl.ARRAY_BUFFER, new Float32Array(v));
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    this.glw.buffer(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(idx));
    gl.bindVertexArray(null);
    const m = { vao, count: idx.length };
    this.meshes.set(seg, m);
    return m;
  }

  /** Blades actually submitted this frame - the readout shows it. */
  get instanceCount() { return this._count | 0; }

  /**
   * The lattice covering what can actually be seen, in whole world cells.
   *
   * The grid used to be a square centred on the camera, of which the view
   * frustum only ever covers about a third - the rest was submitted purely
   * to be thrown away by the cull in the vertex shader, still paying a
   * vertex invocation per blade per vertex. Fitting the box to the visible
   * sector is free and cuts what is submitted by roughly two thirds.
   *
   * Returned in cell coordinates, so a blade's identity comes from where
   * it sits in the world rather than from where it happened to land in
   * this frame's grid, and it does not shuffle as you turn.
   */
  visibleBox(env, r1, cell) {
    const cx = env.camPos[0], cz = env.camPos[2];
    /* the same half-angle the vertex shader culls to, plus a margin */
    const half = Math.min(Math.acos(clamp(env.cullDot, -1, 1)) + 0.12, Math.PI);
    const yaw = Math.atan2(env.fwdXZ[0], -env.fwdXZ[1]);

    /* blades inside the near guard are never frustum-culled, because when
       you look straight down they are all around you */
    const near = Math.min(r1, 4.5);
    let minX = cx - near, maxX = cx + near;
    let minZ = cz - near, maxZ = cz + near;

    if (half < Math.PI - 1e-3) {
      const N = 14;
      for (let i = 0; i <= N; i++) {
        const a = yaw - half + (2 * half) * (i / N);
        const x = cx + Math.sin(a) * r1, z = cz - Math.cos(a) * r1;
        if (x < minX) minX = x;
        if (x > maxX) maxX = x;
        if (z < minZ) minZ = z;
        if (z > maxZ) maxZ = z;
      }
    } else {
      minX = cx - r1; maxX = cx + r1; minZ = cz - r1; maxZ = cz + r1;
    }

    const x0 = Math.floor(minX / cell), z0 = Math.floor(minZ / cell);
    return {
      x0, z0,
      w: Math.max(1, Math.ceil(maxX / cell) - x0 + 1),
      h: Math.max(1, Math.ceil(maxZ / cell) - z0 + 1)
    };
  }

  draw(env) {
    const gl = this.glw.gl, p = this.prog;
    gl.useProgram(p);
    env.bindCommon(p);

    gl.uniformMatrix4fv(p.u.uViewProj, false, env.viewProj);
    gl.uniform3fv(p.u.uCam, env.camPos);
    gl.uniform2fv(p.u.uFwdXZ, env.fwdXZ);
    gl.uniform1f(p.u.uCullDot, env.cullDot);
    gl.uniform1f(p.u.uBladeHeight, env.bladeHeight);
    gl.uniform1f(p.u.uBladeWidth, env.bladeWidth);
    gl.uniform2fv(p.u.uWind, env.windDir);
    gl.uniform1f(p.u.uWindStrength, env.windStrength);
    gl.uniform1f(p.u.uWindTime, env.windTime);
    gl.uniform1f(p.u.uBaseBend, env.baseBend);
    gl.uniform2fv(p.u.uPlayerXZ, env.playerXZ);
    gl.uniform2fv(p.u.uPlayerVel, env.playerHeading);
    gl.uniform1f(p.u.uPlayerSpeed, env.playerSpeed);
    gl.uniform1f(p.u.uPartRadius, env.partRadius);
    gl.uniform1f(p.u.uPartStrength, env.partStrength);
    gl.uniform3fv(p.u.uGrassDark, env.grassDark);
    gl.uniform3fv(p.u.uGrassLight, env.grassLight);
    gl.uniform3fv(p.u.uCoreDir, env.coreDir);
    gl.uniform3fv(p.u.uCoreColour, env.coreColour);
    gl.uniform1f(p.u.uSpecular, env.specular);
    gl.uniform1f(p.u.uSheen, env.sheen);
    gl.uniform1f(p.u.uTranslucency, env.translucency);
    gl.uniform1f(p.u.uBackLight, env.backLight);
    gl.uniform1f(p.u.uGroundGain, env.groundGain);

    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);        /* blades are visible from both sides */

    let total = 0;
    /* Density widens the lattice instead of discarding instances in the
       vertex shader. Thinning by hash still pays the full vertex cost for
       every blade it throws away, which is exactly backwards on the
       hardware that needs the setting. Quantised so that a small change
       in the auto-quality scaler does not reshuffle the whole field. */
    const dens = Math.max(0.06, Math.round(env.density * 10) / 10);

    /* Plan every ring first, then hold the whole frame to a budget.
       A tile-based GPU bins primitives into a fixed buffer before it
       shades anything, and when that buffer overflows the driver drops
       geometry rather than reporting an error - the frame rate stays at
       60 and the grass simply is not there. Nothing in WebGL exposes
       where that limit is, so the only safe move is not to approach it,
       and to make the ceiling adjustable so it can be found. */
    const plan = [];
    let want = 0;
    for (const r of this.rings) {
      if (r.r0 > env.grassRange) continue;
      const r1 = Math.min(r.r1, env.grassRange);
      const cell = r.cell / Math.sqrt(dens);
      const box = this.visibleBox(env, r1, cell);
      plan.push({ r, r1, cell, box, coarsen: 1 });
      want += box.w * box.h;
    }
    if (want > env.bladeBudget) {
      /* coarsen every ring together so the field thins evenly */
      const k = Math.sqrt(want / env.bladeBudget);
      for (const q of plan) {
        q.cell *= k;
        q.coarsen = k;
        q.box = this.visibleBox(env, q.r1, q.cell);
      }
    }

    for (const q of plan) {
      const r = q.r, r1 = q.r1, cell = q.cell, box = q.box;
      /* fewer blades, each a little broader, so thinning the field costs
         coverage far more slowly than it costs vertices */
      const widen = clamp(1 + 0.4 * (1 / Math.sqrt(dens) - 1), 1, 2.1)
                  * clamp(1 + 0.55 * (q.coarsen - 1), 1, 2.6);

      gl.uniform1f(p.u.uCell, cell);
      gl.uniform2f(p.u.uOriginCell, box.x0, box.z0);
      gl.uniform1i(p.u.uGridW, box.w);
      gl.uniform1i(p.u.uGridH, box.h);
      gl.uniform2f(p.u.uRange, r.r0, r1);
      gl.uniform2f(p.u.uFadeIn, r.fadeIn[0], r.fadeIn[1]);
      gl.uniform2f(p.u.uFadeOut,
        Math.min(r.fadeOut[0], r1 - Math.max(1, r1 * 0.06)),
        r1);
      gl.uniform1f(p.u.uSeed, r.seed);
      gl.uniform1f(p.u.uWidthMul, r.width * widen);
      gl.uniform1f(p.u.uViewFace, r.viewFace);
      gl.uniform1f(p.u.uCurve, r.curve);

      /* Chunked. A single draw of a million instances is more than some
         drivers will take in one piece: a tile-based GPU can overflow the
         buffer it bins primitives into and silently drop geometry, and
         ANGLE splits oversized instanced draws itself, which has not
         always got gl_InstanceID right across the split. Splitting it
         here, with an explicit base, keeps it predictable. */
      const n = box.w * box.h;
      gl.bindVertexArray(r.mesh.vao);
      for (let base = 0; base < n; base += INSTANCE_CHUNK) {
        gl.uniform1i(p.u.uInstanceBase, base);
        gl.drawElementsInstanced(gl.TRIANGLES, r.mesh.count, gl.UNSIGNED_SHORT, 0,
                                 Math.min(INSTANCE_CHUNK, n - base));
      }
      total += n;
    }
    gl.bindVertexArray(null);
    this._count = total;
  }
}
