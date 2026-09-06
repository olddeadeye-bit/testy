/* ===================================================================
   Trample map.

   A small decaying height field that follows the player. Where you walk,
   the grass goes down and stays down for a while, so you can look back
   and see the line you took through the field. It is a 512 square window
   56 m across, snapped to whole texels, ping-ponged each frame.
   =================================================================== */

const TRAMPLE_FS = CHUNK.head + `
in vec2 vUv;
out vec4 oColor;
uniform sampler2D uPrev;
uniform vec3 uPrevWin;
uniform vec3 uCurWin;
uniform vec2 uPlayer;
uniform vec2 uPrevPlayer;
uniform float uRadius;
uniform float uDecay;

/* distance from a point to the segment the player covered this frame,
   so fast movement still lays a continuous track */
float segDist(vec2 p, vec2 a, vec2 b){
  vec2 ab = b - a;
  float l2 = dot(ab, ab);
  float t = l2 > 1e-6 ? clamp(dot(p - a, ab) / l2, 0.0, 1.0) : 0.0;
  return length(p - (a + ab * t));
}

void main(){
  vec2 world = uCurWin.xy + vUv * uCurWin.z;

  float prev = 0.0;
  vec2 puv = (world - uPrevWin.xy) / uPrevWin.z;
  if (all(greaterThanEqual(puv, vec2(0.0))) && all(lessThanEqual(puv, vec2(1.0))))
    prev = texture(uPrev, puv).r;
  prev *= uDecay;

  float d = segDist(world, uPrevPlayer, uPlayer);
  float stamp = smoothstep(uRadius, uRadius * 0.3, d);

  oColor = vec4(max(prev, stamp), 0.0, 0.0, 1.0);
}`;

class Trample {
  constructor(glw, res, span) {
    this.glw = glw;
    const gl = glw.gl;
    this.res = res;
    this.span = span;
    this.texel = span / res;
    this.prog = glw.program(FULLSCREEN_VS, TRAMPLE_FS, 'trample');
    const mk = () => glw.target(res, res, { internal: gl.RGBA8, type: gl.UNSIGNED_BYTE });
    this.a = mk();
    this.b = mk();
    for (const t of [this.a, this.b]) {
      glw.bindTarget(t);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }
    glw.bindTarget(null);
    this.win = [0, 0, span];
    this.prevWin = [0, 0, span];
    this.prevPlayer = [0, 0];
    this.first = true;
  }

  get texture() { return this.a.tex; }
  get window() { return this.win; }

  update(px, pz, dt, radius, recoverSeconds) {
    const gl = this.glw.gl, p = this.prog;
    this.prevWin = this.win.slice();
    /* snap to whole texels: an unsnapped scroll would resample the map
       every frame and smear the track into mush within seconds */
    const ox = Math.round((px - this.span * 0.5) / this.texel) * this.texel;
    const oz = Math.round((pz - this.span * 0.5) / this.texel) * this.texel;
    this.win = [ox, oz, this.span];

    const dst = this.b;
    this.glw.bindTarget(dst);
    gl.useProgram(p);
    gl.disable(gl.DEPTH_TEST);
    this.glw.bindTex(0, this.a.tex);
    gl.uniform1i(p.u.uPrev, 0);
    gl.uniform3fv(p.u.uPrevWin, this.prevWin);
    gl.uniform3fv(p.u.uCurWin, this.win);
    gl.uniform2f(p.u.uPlayer, px, pz);
    const pp = this.first ? [px, pz] : this.prevPlayer;
    gl.uniform2f(p.u.uPrevPlayer, pp[0], pp[1]);
    gl.uniform1f(p.u.uRadius, radius);
    gl.uniform1f(p.u.uDecay, Math.exp(-dt / Math.max(recoverSeconds, 0.1)));
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    this.b = this.a; this.a = dst;
    this.prevPlayer = [px, pz];
    this.first = false;
    this.glw.bindTarget(null);
    gl.enable(gl.DEPTH_TEST);
  }

  clear() {
    const gl = this.glw.gl;
    for (const t of [this.a, this.b]) {
      this.glw.bindTarget(t);
      gl.clearColor(0, 0, 0, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }
    this.glw.bindTarget(null);
    this.first = true;
  }
}
