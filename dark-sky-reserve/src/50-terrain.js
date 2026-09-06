/* ===================================================================
   Ground.

   A radial disc that rides along under the camera - dense at your feet,
   coarse at the horizon, out to 900 m. It is the mat of dead thatch and
   soil the blades stand in, and past the last row of blades it becomes
   the whole ground, which is exactly where the haze has taken over.
   =================================================================== */

const TERRAIN_VS = CHUNK.head + CHUNK.common + `
in vec2 aRA;                 /* x: 0..1 along the radius, y: 0..1 around */
uniform mat4 uViewProj;
uniform vec2 uOrigin;
uniform float uMaxR;

out vec3 vWorld;

void main(){
  float r = uMaxR * pow(aRA.x, 2.7);
  float a = aRA.y * TAU;
  vec2 xz = uOrigin + vec2(cos(a), sin(a)) * r;
  vWorld = vec3(xz.x, surfaceHeight(xz), xz.y);
  gl_Position = uViewProj * vec4(vWorld, 1.0);
}`;

const TERRAIN_FS = CHUNK.head + CHUNK.common + `
in vec3 vWorld;
out vec4 oColor;

uniform vec3 uCam;
uniform sampler2D uMat;
uniform vec3 uGrassDark;
uniform vec3 uGrassLight;
uniform vec3 uCoreDir;
uniform vec3 uCoreColour;
uniform float uSpecular;
uniform float uSheen;
uniform float uGroundGain;

/* the mat texture is a directional streak pattern; we spin it to follow
   the local lie of the grass so the ground reads as combed, not tiled */
vec4 matAt(vec2 world, float scale, float ang){
  float c = cos(ang), s = sin(ang);
  mat2 R = mat2(c, -s, s, c);
  return texture(uMat, (R * world) / scale);
}

void main(){
  vec3 V = normalize(uCam - vWorld);
  float dist = length(uCam - vWorld);

  vec4 f = field(vWorld.xz);
  /* The comb is stored as an offset from the prevailing wind rather than
     an absolute bearing: an absolute angle in a byte wraps at 0/1, and
     bilinear filtering across that wrap draws seams across the field. */
  vec4 det = detail(vWorld.xz);
  float ang = atan(uWind.y, uWind.x) + (f.b - 0.5) * 1.55 + (det.g - 0.5) * 1.15;

  /* two octaves at incommensurable scales: kills the visible repeat */
  vec4 m0 = matAt(vWorld.xz, 1.35, ang);
  vec4 m1 = matAt(vWorld.xz, 5.90, ang + 1.1);
  float thatch = m0.a * 0.62 + m1.a * 0.38;

  vec3 nT = normalize(vec3((m0.rg - 0.5) * 1.6 + (m1.rg - 0.5) * 0.7, 1.0));
  float c = cos(-ang), s = sin(-ang);
  vec3 nRot = vec3(nT.x * c - nT.y * s, nT.x * s + nT.y * c, nT.z);
  vec3 gN = groundNormal(vWorld.xz, 1.5);
  /* graft the mat detail onto the terrain slope */
  vec3 N = normalize(vec3(gN.x + nRot.x * 0.55, gN.y, gN.z + nRot.y * 0.55));

  float lay = fieldR(vWorld.xz, 2.6);
  vec3 albedo = mix(uGrassDark, uGrassLight, thatch * 0.55 + f.g * 0.17 + lay * 0.28);
  albedo *= mix(0.42, 1.0, thatch);                  /* self-shadowing of the mat */
  albedo *= mix(0.55, 1.0, smoothstep(0.25, 0.75, f.a));

  /* the mat sits at the bottom of the canopy, so very little sky reaches it */
  float canopy = mix(0.038, 0.30, smoothstep(6.0, 60.0, dist))
               * mix(0.58, 1.0, smoothstep(0.05, 0.85, det.r));
  float tr = trampleAt(vWorld.xz);
  canopy = mix(canopy, canopy * 1.7, tr);            /* flattened grass opens up */

  vec3 amb = shIrradiance(N) * (1.0 / PI) * canopy;
  vec3 spec = uCoreColour * ggx(N, V, uCoreDir, 0.78)
            * max(dot(N, uCoreDir), 0.0) * uSpecular * 0.30;

  vec3 col = albedo * amb * uGroundGain + spec
           + skySheen(N, V, uSheen) * canopy * 1.6;

  col = mix(col, hazeColour(-V), hazeAmount(dist));
  oColor = vec4(col, 1.0);
}`;

class Terrain {
  constructor(glw, rings, segs, maxR) {
    this.glw = glw;
    const gl = glw.gl;
    this.maxR = maxR;
    this.prog = glw.program(TERRAIN_VS, TERRAIN_FS, 'terrain');

    /* radial grid: ring 0 is a degenerate centre point */
    const verts = [];
    for (let i = 0; i <= rings; i++) {
      const t = i / rings;
      for (let j = 0; j <= segs; j++) verts.push(t, j / segs);
    }
    const idx = [];
    const row = segs + 1;
    for (let i = 0; i < rings; i++) {
      for (let j = 0; j < segs; j++) {
        const a = i * row + j, b = a + 1, c = a + row, d = c + 1;
        idx.push(a, c, b, b, c, d);
      }
    }
    this.count = idx.length;

    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    glw.buffer(gl.ARRAY_BUFFER, new Float32Array(verts));
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    glw.buffer(gl.ELEMENT_ARRAY_BUFFER, new Uint32Array(idx));
    gl.bindVertexArray(null);
  }

  draw(env) {
    const gl = this.glw.gl, p = this.prog;
    gl.useProgram(p);
    env.bindCommon(p);
    gl.uniformMatrix4fv(p.u.uViewProj, false, env.viewProj);
    gl.uniform3fv(p.u.uCam, env.camPos);
    /* snapping the disc to a coarse grid stops far vertices from
       shimmering as they resample the height field while you walk */
    gl.uniform2f(p.u.uOrigin,
      Math.round(env.camPos[0] / 2.0) * 2.0,
      Math.round(env.camPos[2] / 2.0) * 2.0);
    gl.uniform1f(p.u.uMaxR, this.maxR);
    gl.uniform3fv(p.u.uGrassDark, env.grassDark);
    gl.uniform3fv(p.u.uGrassLight, env.grassLight);
    gl.uniform3fv(p.u.uCoreDir, env.coreDir);
    gl.uniform3fv(p.u.uCoreColour, env.coreColour);
    gl.uniform1f(p.u.uSpecular, env.specular);
    gl.uniform1f(p.u.uSheen, env.sheen);
    gl.uniform1f(p.u.uGroundGain, env.groundGain);
    this.glw.bindTex(4, env.matTex);
    gl.uniform1i(p.u.uMat, 4);

    gl.enable(gl.DEPTH_TEST);
    gl.disable(gl.CULL_FACE);
    gl.bindVertexArray(this.vao);
    gl.drawElements(gl.TRIANGLES, this.count, gl.UNSIGNED_INT, 0);
    gl.bindVertexArray(null);
  }
}
