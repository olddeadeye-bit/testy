/* ===================================================================
   Post.

   The photograph is a long exposure taken on a real lens: the core of
   the galaxy blooms, the shadows are full of sensor grain, the corners
   fall off. A clean render of the same scene looks wrong precisely
   because it is clean, so all of that goes back on here.
   =================================================================== */

const BLOOM_PREFILTER_FS = CHUNK.head + CHUNK.common + `
in vec2 vUv; out vec4 oColor;
uniform sampler2D uTex;
uniform float uThreshold, uKnee, uExposure;
void main(){
  vec3 c = texture(uTex, vUv).rgb * uExposure;
  float br = max(c.r, max(c.g, c.b));
  float soft = clamp(br - uThreshold + uKnee, 0.0, 2.0 * uKnee);
  soft = soft * soft / (4.0 * uKnee + 1e-4);
  float w = max(soft, br - uThreshold) / max(br, 1e-4);
  oColor = vec4(c * w, 1.0);
}`;

/* Jimenez's 13-tap downsample: no pulsing fireflies as the chain shrinks. */
const BLOOM_DOWN_FS = CHUNK.head + `
in vec2 vUv; out vec4 oColor;
uniform sampler2D uTex;
uniform vec2 uTexel;
void main(){
  vec2 t = uTexel;
  vec3 a = texture(uTex, vUv + vec2(-2, 2) * t).rgb;
  vec3 b = texture(uTex, vUv + vec2( 0, 2) * t).rgb;
  vec3 c = texture(uTex, vUv + vec2( 2, 2) * t).rgb;
  vec3 d = texture(uTex, vUv + vec2(-2, 0) * t).rgb;
  vec3 e = texture(uTex, vUv                ).rgb;
  vec3 f = texture(uTex, vUv + vec2( 2, 0) * t).rgb;
  vec3 g = texture(uTex, vUv + vec2(-2,-2) * t).rgb;
  vec3 h = texture(uTex, vUv + vec2( 0,-2) * t).rgb;
  vec3 i = texture(uTex, vUv + vec2( 2,-2) * t).rgb;
  vec3 j = texture(uTex, vUv + vec2(-1, 1) * t).rgb;
  vec3 k = texture(uTex, vUv + vec2( 1, 1) * t).rgb;
  vec3 l = texture(uTex, vUv + vec2(-1,-1) * t).rgb;
  vec3 m = texture(uTex, vUv + vec2( 1,-1) * t).rgb;
  vec3 o = e * 0.125
         + (a + c + g + i) * 0.03125
         + (b + d + f + h) * 0.0625
         + (j + k + l + m) * 0.125;
  oColor = vec4(o, 1.0);
}`;

const BLOOM_UP_FS = CHUNK.head + `
in vec2 vUv; out vec4 oColor;
uniform sampler2D uTex;
uniform vec2 uTexel;
uniform float uRadius;
void main(){
  vec2 t = uTexel * uRadius;
  vec3 s = texture(uTex, vUv + vec2(-1, 1) * t).rgb * 1.0
         + texture(uTex, vUv + vec2( 0, 1) * t).rgb * 2.0
         + texture(uTex, vUv + vec2( 1, 1) * t).rgb * 1.0
         + texture(uTex, vUv + vec2(-1, 0) * t).rgb * 2.0
         + texture(uTex, vUv                ).rgb * 4.0
         + texture(uTex, vUv + vec2( 1, 0) * t).rgb * 2.0
         + texture(uTex, vUv + vec2(-1,-1) * t).rgb * 1.0
         + texture(uTex, vUv + vec2( 0,-1) * t).rgb * 2.0
         + texture(uTex, vUv + vec2( 1,-1) * t).rgb * 1.0;
  oColor = vec4(s * (1.0 / 16.0), 1.0);
}`;

const COMPOSITE_FS = CHUNK.head + CHUNK.common + CHUNK.tonemap + `
in vec2 vUv; out vec4 oColor;
uniform sampler2D uScene;
uniform sampler2D uBloom;
uniform vec2 uRes;
uniform float uExposure, uBloomAmt, uGrain, uVignette, uSat, uCA, uFrame;

void main(){
  vec2 uv = vUv;
  vec2 c = uv - 0.5;
  float r2 = dot(c, c);

  vec3 col;
  if (uCA > 0.0001){
    /* transverse chromatic aberration: a real wide lens splits colour
       toward the corners and almost nowhere in the middle */
    vec2 off = c * r2 * uCA;
    col = vec3(texture(uScene, uv + off).r,
               texture(uScene, uv).g,
               texture(uScene, uv - off).b);
  } else {
    col = texture(uScene, uv).rgb;
  }

  col += texture(uBloom, uv).rgb * uBloomAmt;
  col *= uExposure;

  col = shoulder(col);
  col = saturate3(col, uSat);
  col *= 1.0 - uVignette * smoothstep(0.10, 0.60, r2);

  /* Grain lives in the shadows on a real high-ISO frame, and it is
     mostly luminance with a little colour speckle underneath. */
  if (uGrain > 0.0001){
    vec2 g = gl_FragCoord.xy;
    float n1 = hash11(dot(g, vec2(12.9898, 78.233)) + uFrame * 1.618) - 0.5;
    float n2 = hash11(dot(g, vec2(39.346, 11.135)) + uFrame * 2.718 + 91.0) - 0.5;
    float n3 = hash11(dot(g, vec2(63.712, 27.409)) + uFrame * 3.142 + 17.0) - 0.5;
    float amt = uGrain * mix(1.25, 0.40, smoothstep(0.010, 0.32, luma(col)));
    col += (vec3(n1) * 0.72 + vec3(n2, n3, -n2 - n3) * 0.28) * amt;
  }

  col = linearToSrgb(max(col, vec3(0.0)));

  /* a hair of ordered dither: without it a night sky in 8 bits bands */
  float d = fract(dot(gl_FragCoord.xy, vec2(0.7548776662, 0.5698402909)));
  col += (d - 0.5) / 255.0;

  oColor = vec4(col, 1.0);
}`;

class Post {
  constructor(glw) {
    this.glw = glw;
    this.pre = glw.program(FULLSCREEN_VS, BLOOM_PREFILTER_FS, 'bloom.pre');
    this.down = glw.program(FULLSCREEN_VS, BLOOM_DOWN_FS, 'bloom.down');
    this.up = glw.program(FULLSCREEN_VS, BLOOM_UP_FS, 'bloom.up');
    this.comp = glw.program(FULLSCREEN_VS, COMPOSITE_FS, 'composite');
    this.chain = [];
    this.frame = 0;
  }

  resize(w, h, levels) {
    for (const t of this.chain) t.free();
    this.chain = [];
    let cw = Math.max(1, w >> 1), ch = Math.max(1, h >> 1);
    for (let i = 0; i < levels && cw > 4 && ch > 4; i++) {
      this.chain.push(this.glw.target(cw, ch, {}));
      cw = Math.max(1, cw >> 1); ch = Math.max(1, ch >> 1);
    }
  }

  /** Bright pass, shrink, then blur back up accumulating every level. */
  bloom(sceneTex, exposure, threshold, knee, radius) {
    const gl = this.glw.gl;
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);

    let p = this.pre;
    gl.useProgram(p);
    this.glw.bindTarget(this.chain[0]);
    this.glw.bindTex(0, sceneTex);
    gl.uniform1i(p.u.uTex, 0);
    gl.uniform1f(p.u.uThreshold, threshold);
    gl.uniform1f(p.u.uKnee, knee);
    gl.uniform1f(p.u.uExposure, exposure);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    p = this.down;
    gl.useProgram(p);
    for (let i = 1; i < this.chain.length; i++) {
      const src = this.chain[i - 1], dst = this.chain[i];
      this.glw.bindTarget(dst);
      this.glw.bindTex(0, src.tex);
      gl.uniform1i(p.u.uTex, 0);
      gl.uniform2f(p.u.uTexel, 1 / src.w, 1 / src.h);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    p = this.up;
    gl.useProgram(p);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    for (let i = this.chain.length - 1; i > 0; i--) {
      const src = this.chain[i], dst = this.chain[i - 1];
      this.glw.bindTarget(dst);
      this.glw.bindTex(0, src.tex);
      gl.uniform1i(p.u.uTex, 0);
      gl.uniform2f(p.u.uTexel, 1 / src.w, 1 / src.h);
      gl.uniform1f(p.u.uRadius, radius);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    gl.disable(gl.BLEND);
    return this.chain[0].tex;
  }

  composite(sceneTex, bloomTex, o) {
    const gl = this.glw.gl, p = this.comp;
    this.glw.bindTarget(null);
    gl.useProgram(p);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);
    this.glw.bindTex(0, sceneTex); gl.uniform1i(p.u.uScene, 0);
    this.glw.bindTex(1, bloomTex); gl.uniform1i(p.u.uBloom, 1);
    gl.uniform2f(p.u.uRes, this.glw.canvas.width, this.glw.canvas.height);
    gl.uniform1f(p.u.uExposure, o.exposure);
    gl.uniform1f(p.u.uBloomAmt, o.bloom);
    gl.uniform1f(p.u.uGrain, o.grain);
    gl.uniform1f(p.u.uVignette, o.vignette);
    gl.uniform1f(p.u.uSat, o.saturation);
    gl.uniform1f(p.u.uCA, o.chroma);
    gl.uniform1f(p.u.uFrame, (this.frame++ % 4096));
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }
}
