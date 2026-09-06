/* ===================================================================
   Sky pass. One full-screen triangle: for every pixel we rebuild the
   world-space view ray and look the photograph up along it.

   This is the part of the scene that is not a reconstruction. Stars are
   at infinity, so a 360 panorama really is a correct sky - walk a
   kilometre and it should not change, and here it doesn't.
   =================================================================== */

const SKY_FS = CHUNK.head + CHUNK.common + CHUNK.stars + `
in vec2 vUv;
out vec4 oColor;

uniform mat4 uInvViewProj;
uniform vec3 uCamPos;
uniform float uStarAmount;

void main(){
  vec4 far = uInvViewProj * vec4(vUv * 2.0 - 1.0, 1.0, 1.0);
  vec3 dir = normalize(far.xyz / far.w - uCamPos);

  vec3 col = skyHDR(dir);
  col += starfield(dir, (zenithBlend(dir) * 0.85 + 0.06) * uStarAmount);

  /* The photograph's own horizon is a hard cut where its ground began.
     We are drawing our own ground over it, but a few degrees of haze
     below the skyline stop any hairline showing through between blades. */
  float below = smoothstep(0.0, -0.05, dir.y);
  col = mix(col, hazeColour(dir), below * 0.35);

  oColor = vec4(col, 1.0);
}`;

class SkyPass {
  constructor(glw) {
    this.glw = glw;
    this.prog = glw.program(FULLSCREEN_VS, SKY_FS, 'sky');
  }

  draw(env) {
    const gl = this.glw.gl, p = this.prog;
    gl.useProgram(p);
    gl.disable(gl.DEPTH_TEST);
    gl.depthMask(false);
    env.bindCommon(p);
    gl.uniformMatrix4fv(p.u.uInvViewProj, false, env.invViewProj);
    gl.uniform3fv(p.u.uCamPos, env.camPos);
    gl.uniform1f(p.u.uStarAmount, env.starAmount);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.depthMask(true);
    gl.enable(gl.DEPTH_TEST);
  }
}
