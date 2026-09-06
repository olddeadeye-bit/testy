/* ===================================================================
   Startup self-test.

   Written because three rounds of diagnosis were spent guessing at a
   machine I cannot run on. Every one of these features is one the
   renderer silently depends on: if the driver quietly does the wrong
   thing, the symptom is a black or flickering field with no error, no
   exception and no clue. So rather than assume, render something with a
   known answer and read it back.

   Anything that fails is switched off rather than left to misbehave, and
   the result is printed by the Diagnostics button.
   =================================================================== */

const ST_FS_VALUE = CHUNK.head + `
in float vV; out vec4 o;
void main(){ o = vec4(clamp(vV, 0.0, 1.0), 0.0, 0.0, 1.0); }`;

const ST_VS_VTF = CHUNK.head + `
uniform sampler2D uTex;
uniform vec2 uUV;
out float vV;
void main(){
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  /* the whole point: sample in the VERTEX stage, as the grass does */
  vV = textureLod(uTex, uUV, 0.0).r;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const ST_VS_CONST = CHUNK.head + `
uniform float uValue;
out float vV;
void main(){
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  vV = uValue;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;

const ST_FS_SAMPLE = CHUNK.head + `
in vec2 vUv; out vec4 o;
uniform sampler2D uTex;
void main(){ o = vec4(clamp(texture(uTex, vUv).r, 0.0, 1.0), 0.0, 0.0, 1.0); }`;

function runSelfTest(glw, heightTex, heightData, heightRes) {
  const gl = glw.gl;
  const R = { vertexTextureFetch: null, halfFloatTargets: null, msaaResolve: null, notes: [] };
  const made = [];
  const px = new Uint8Array(4 * 4 * 4);

  const readRed = () => {
    gl.readPixels(0, 0, 4, 4, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return px[0];
  };

  try {
    const probe = glw.target(4, 4, { internal: gl.RGBA8, type: gl.UNSIGNED_BYTE, filter: gl.NEAREST });
    made.push(probe);
    gl.disable(gl.DEPTH_TEST);
    gl.disable(gl.BLEND);

    /* ---- 1. vertex texture fetch ---------------------------------- */
    try {
      const prog = glw.program(ST_VS_VTF, ST_FS_VALUE, 'selftest.vtf');
      const tx = 137, ty = 241;
      const expect = Math.round(heightData[ty * heightRes + tx] * 255);
      glw.bindTarget(probe);
      gl.useProgram(prog);
      glw.bindTex(0, heightTex);
      gl.uniform1i(prog.u.uTex, 0);
      gl.uniform2f(prog.u.uUV, (tx + 0.5) / heightRes, (ty + 0.5) / heightRes);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      const got = readRed();
      R.vertexTextureFetch = Math.abs(got - expect) <= 4;
      if (!R.vertexTextureFetch) R.notes.push('vertex texture fetch read ' + got + ', expected ' + expect);
      gl.deleteProgram(prog);
    } catch (e) { R.vertexTextureFetch = false; R.notes.push('vtf: ' + e.message); }

    /* ---- 2. half-float render targets ------------------------------ */
    if (glw.hdr) {
      try {
        const hdrT = glw.target(4, 4, { filter: gl.NEAREST });
        made.push(hdrT);
        const pc = glw.program(ST_VS_CONST, ST_FS_VALUE, 'selftest.const');
        const ps = glw.program(FULLSCREEN_VS, ST_FS_SAMPLE, 'selftest.sample');
        glw.bindTarget(hdrT);
        gl.useProgram(pc);
        gl.uniform1f(pc.u.uValue, 0.5);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        glw.bindTarget(probe);
        gl.useProgram(ps);
        glw.bindTex(0, hdrT.tex);
        gl.uniform1i(ps.u.uTex, 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        const got = readRed();
        R.halfFloatTargets = Math.abs(got - 128) <= 6;
        if (!R.halfFloatTargets) R.notes.push('half-float target read ' + got + ', expected 128');
        gl.deleteProgram(pc); gl.deleteProgram(ps);
      } catch (e) { R.halfFloatTargets = false; R.notes.push('hdr: ' + e.message); }
    } else {
      R.halfFloatTargets = false;
      R.notes.push('no float colour buffer extension; using 8-bit targets');
    }

    /* ---- 3. multisample resolve ------------------------------------ */
    try {
      const ms = glw.targetMS(4, 4, 4, { depth: true, filter: gl.NEAREST });
      made.push(ms);
      if (!ms.resolve) {
        R.msaaResolve = false;
        R.notes.push('no multisampled target available');
      } else {
        const pc = glw.program(ST_VS_CONST, ST_FS_VALUE, 'selftest.msconst');
        const ps = glw.program(FULLSCREEN_VS, ST_FS_SAMPLE, 'selftest.mssample');
        glw.bindTarget(ms, true);
        gl.useProgram(pc);
        gl.uniform1f(pc.u.uValue, 0.5);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        ms.resolve();
        glw.bindTarget(probe);
        gl.useProgram(ps);
        glw.bindTex(0, ms.tex);
        gl.uniform1i(ps.u.uTex, 0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
        const got = readRed();
        R.msaaResolve = Math.abs(got - 128) <= 6;
        if (!R.msaaResolve) R.notes.push('msaa resolve read ' + got + ', expected 128');
        gl.deleteProgram(pc); gl.deleteProgram(ps);
      }
    } catch (e) { R.msaaResolve = false; R.notes.push('msaa: ' + e.message); }

    const err = gl.getError();
    if (err) R.notes.push('glGetError after self-test: ' + err);
  } catch (e) {
    R.notes.push('self-test could not run: ' + e.message);
  } finally {
    for (const t of made) { try { t.free(); } catch (e) {} }
    glw.bindTarget(null);
  }
  return R;
}
