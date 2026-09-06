/* ===================================================================
   Fireflies. Off by default - the photograph has none, and the brief
   was to match the photograph. Turn them up in Settings if you want
   the field to feel inhabited; the bloom pass treats them as real
   light sources, so they smear properly through the grass.
   =================================================================== */

const FLY_VS = CHUNK.head + CHUNK.common + `
uniform mat4 uViewProj;
uniform vec3 uCam;
uniform float uBox;
uniform float uPointScale;
out float vGlow;
out vec3 vWorld;

void main(){
  float id = float(gl_VertexID);
  vec3 h  = hash31(id * 1.7 + 3.1);
  vec3 h2 = hash31(id * 2.3 + 91.7);

  vec2 xz = h.xy * uBox;
  xz += vec2(sin(uTime * 0.31 + h2.x * TAU), cos(uTime * 0.27 + h2.y * TAU)) * 1.8;
  xz += uWind * uTime * 0.35;

  /* keep the swarm around the camera by wrapping it into a moving box */
  vec2 corner = uCam.xz - uBox * 0.5;
  xz = mod(xz - corner, uBox) + corner;

  float y = surfaceHeight(xz) + 0.12 + h2.z * 1.15
          + sin(uTime * 0.9 + h.z * TAU) * 0.22;
  vWorld = vec3(xz.x, y, xz.y);

  float blink = pow(max(sin(uTime * (0.7 + h.z * 0.9) + h2.x * TAU), 0.0), 9.0);
  vGlow = blink;

  vec4 clip = uViewProj * vec4(vWorld, 1.0);
  float dist = length(uCam - vWorld);
  gl_PointSize = clamp(uPointScale / max(dist, 0.4), 1.5, 40.0);
  gl_Position = clip;
}`;

const FLY_FS = CHUNK.head + CHUNK.common + `
in float vGlow;
in vec3 vWorld;
out vec4 oColor;
uniform vec3 uCam;
uniform vec3 uTint;
uniform float uIntensity;
void main(){
  vec2 d = gl_PointCoord - 0.5;
  float r = length(d) * 2.0;
  if (r > 1.0) discard;
  float core = exp(-r * r * 5.0);
  float dist = length(uCam - vWorld);
  float fog = 1.0 - hazeAmount(dist);
  oColor = vec4(uTint * core * vGlow * uIntensity * fog, 1.0);
}`;

class Fireflies {
  constructor(glw, max) {
    this.glw = glw;
    this.max = max;
    this.prog = glw.program(FLY_VS, FLY_FS, 'fireflies');
    this.vao = glw.gl.createVertexArray();
  }

  draw(env, amount) {
    if (amount <= 0.001) return;
    const gl = this.glw.gl, p = this.prog;
    const n = Math.round(this.max * amount);
    if (n < 1) return;
    gl.useProgram(p);
    env.bindCommon(p);
    gl.uniformMatrix4fv(p.u.uViewProj, false, env.viewProj);
    gl.uniform3fv(p.u.uCam, env.camPos);
    gl.uniform2fv(p.u.uWind, env.windDir);
    gl.uniform1f(p.u.uBox, 70.0);
    gl.uniform1f(p.u.uPointScale, 26.0 * (this.glw.canvas.height / 1080));
    gl.uniform3f(p.u.uTint, 1.0, 0.86, 0.42);
    gl.uniform1f(p.u.uIntensity, 0.5);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.depthMask(false);
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.POINTS, 0, n);
    gl.bindVertexArray(null);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
  }
}
