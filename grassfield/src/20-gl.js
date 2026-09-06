/* ===================================================================
   Thin WebGL2 layer. No framework: the whole renderer is four passes
   and a handful of programs, and hand-rolling it keeps the page a
   single file with nothing to install.
   =================================================================== */

class GL {
  constructor(canvas) {
    const opts = {
      alpha: false, antialias: false, depth: true, stencil: false,
      powerPreference: 'high-performance'
      // NB: no preserveDrawingBuffer. It makes the browser keep and copy a
      // second full-size buffer every frame, which at Retina resolutions is
      // tens of megabytes of pure overhead. "Save a frame" instead calls
      // toBlob inside the same task as the draw, while the buffer is valid.
    };
    const gl = canvas.getContext('webgl2', opts);
    if (!gl) throw new Error('WEBGL2_UNAVAILABLE');
    this.gl = gl;
    this.canvas = canvas;

    // Half-float render targets give us the headroom for physically-sane
    // night radiance and a bloom that responds to the galactic core.
    this.extHalf = gl.getExtension('EXT_color_buffer_half_float');
    this.extFloat = gl.getExtension('EXT_color_buffer_float');
    this.extLinear = gl.getExtension('OES_texture_float_linear');
    this.extAniso = gl.getExtension('EXT_texture_filter_anisotropic');
    this.maxAniso = this.extAniso
      ? gl.getParameter(this.extAniso.MAX_TEXTURE_MAX_ANISOTROPY_EXT) : 1;
    this.hdrFormat = (this.extHalf || this.extFloat) ? gl.RGBA16F : gl.RGBA8;
    this.hdr = this.hdrFormat === gl.RGBA16F;
  }

  /* ------------------------------------------------------------ shaders */
  compile(type, src, label) {
    const gl = this.gl;
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(sh) || '';
      const numbered = src.split('\n')
        .map((l, i) => String(i + 1).padStart(4) + ' | ' + l).join('\n');
      console.error('shader failed: ' + label + '\n' + log + '\n' + numbered);
      throw new Error('shader ' + label + ': ' + log.split('\n')[0]);
    }
    return sh;
  }

  program(vsSrc, fsSrc, label) {
    const gl = this.gl;
    const p = gl.createProgram();
    const vs = this.compile(gl.VERTEX_SHADER, vsSrc, label + '.vert');
    const fs = this.compile(gl.FRAGMENT_SHADER, fsSrc, label + '.frag');
    gl.attachShader(p, vs); gl.attachShader(p, fs);
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS))
      throw new Error('link ' + label + ': ' + gl.getProgramInfoLog(p));
    gl.deleteShader(vs); gl.deleteShader(fs);

    // Cache every active uniform location up front; `u.name` beats a
    // getUniformLocation call in the middle of a hot frame.
    const u = Object.create(null);
    const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
    for (let i = 0; i < n; i++) {
      const info = gl.getActiveUniform(p, i);
      const name = info.name.replace(/\[0\]$/, '');
      u[name] = gl.getUniformLocation(p, name);
    }
    p.u = u;
    p.label = label;
    return p;
  }

  /* ----------------------------------------------------------- buffers */
  buffer(target, data, usage) {
    const gl = this.gl;
    const b = gl.createBuffer();
    gl.bindBuffer(target, b);
    gl.bufferData(target, data, usage || gl.STATIC_DRAW);
    return b;
  }

  /* ---------------------------------------------------------- textures */
  texture(opts) {
    const gl = this.gl;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    const wrap = opts.wrap || gl.CLAMP_TO_EDGE;
    const filt = opts.filter === undefined ? gl.LINEAR : opts.filter;
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrap);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, opts.wrapT || wrap);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER,
      opts.mips ? gl.LINEAR_MIPMAP_LINEAR : filt);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filt);
    if (opts.image) {
      gl.texImage2D(gl.TEXTURE_2D, 0, opts.internal || gl.RGBA8, opts.format || gl.RGBA,
        opts.type || gl.UNSIGNED_BYTE, opts.image);
    } else {
      gl.texImage2D(gl.TEXTURE_2D, 0, opts.internal || gl.RGBA8, opts.w, opts.h, 0,
        opts.format || gl.RGBA, opts.type || gl.UNSIGNED_BYTE, opts.data || null);
    }
    if (opts.mips) gl.generateMipmap(gl.TEXTURE_2D);
    if (opts.aniso && this.extAniso) {
      gl.texParameterf(gl.TEXTURE_2D, this.extAniso.TEXTURE_MAX_ANISOTROPY_EXT,
        Math.min(opts.aniso, this.maxAniso));
    }
    t.width = opts.w || (opts.image ? opts.image.width : 0);
    t.height = opts.h || (opts.image ? opts.image.height : 0);
    return t;
  }

  /* -------------------------------------------------------------- FBOs */
  target(w, h, opts) {
    const gl = this.gl;
    opts = opts || {};
    const internal = opts.internal || (this.hdr ? gl.RGBA16F : gl.RGBA8);
    const type = opts.type || (internal === gl.RGBA16F ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE);
    const tex = this.texture({
      w, h, internal, type, format: gl.RGBA,
      filter: opts.filter === undefined ? gl.LINEAR : opts.filter
    });
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    let depth = null;
    if (opts.depth) {
      depth = gl.createRenderbuffer();
      gl.bindRenderbuffer(gl.RENDERBUFFER, depth);
      gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT24, w, h);
      gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depth);
    }
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) throw new Error('incomplete framebuffer ' + w + 'x' + h);
    return { fbo, tex, depth, w, h,
      free: () => { gl.deleteFramebuffer(fbo); gl.deleteTexture(tex);
                    if (depth) gl.deleteRenderbuffer(depth); } };
  }

  /**
   * Same as target(), but the scene is rasterised into multisampled
   * renderbuffers and resolved into the texture afterwards.
   *
   * Grass is the worst case there is for aliasing: hundreds of thousands
   * of near-vertical shapes a pixel or less across. Without this they
   * break into crawling dashes whenever the wind moves them, and no
   * amount of shading work hides it.
   */
  targetMS(w, h, samples, opts) {
    const gl = this.gl;
    opts = opts || {};
    /* the resolve target needs no depth of its own - depth lives on the
       multisampled side and is never read back */
    const resolved = this.target(w, h, Object.assign({}, opts, { depth: false }));
    const fmt = opts.internal || (this.hdr ? gl.RGBA16F : gl.RGBA8);
    let max = 0;
    try {
      const counts = gl.getInternalformatParameter(gl.RENDERBUFFER, fmt, gl.SAMPLES);
      max = counts && counts.length ? counts[0] : 0;
    } catch (e) { max = 0; }
    const n = Math.min(samples, max, gl.getParameter(gl.MAX_SAMPLES) || 0);
    if (n < 2) { resolved.free(); return this.target(w, h, opts); }

    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    const col = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, col);
    gl.renderbufferStorageMultisample(gl.RENDERBUFFER, n, fmt, w, h);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.RENDERBUFFER, col);
    const dep = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, dep);
    gl.renderbufferStorageMultisample(gl.RENDERBUFFER, n, gl.DEPTH_COMPONENT24, w, h);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, dep);
    const ok = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!ok) {
      gl.deleteFramebuffer(fbo); gl.deleteRenderbuffer(col); gl.deleteRenderbuffer(dep);
      resolved.free();
      return this.target(w, h, opts);
    }

    const inner = resolved.free;
    resolved.msFbo = fbo;
    resolved.samples = n;
    resolved.resolve = () => {
      gl.bindFramebuffer(gl.READ_FRAMEBUFFER, fbo);
      gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER, resolved.fbo);
      gl.blitFramebuffer(0, 0, w, h, 0, 0, w, h, gl.COLOR_BUFFER_BIT, gl.NEAREST);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    };
    resolved.free = () => {
      inner();
      gl.deleteFramebuffer(fbo); gl.deleteRenderbuffer(col); gl.deleteRenderbuffer(dep);
    };
    return resolved;
  }

  bindTarget(t, forDraw) {
    const gl = this.gl;
    if (t) {
      /* draw into the multisampled side when there is one */
      const f = (forDraw && t.msFbo) ? t.msFbo : t.fbo;
      gl.bindFramebuffer(gl.FRAMEBUFFER, f);
      gl.viewport(0, 0, t.w, t.h);
    }
    else { gl.bindFramebuffer(gl.FRAMEBUFFER, null);
           gl.viewport(0, 0, this.canvas.width, this.canvas.height); }
  }

  bindTex(unit, tex) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, tex);
  }
}

/* A single oversized triangle covers the screen with no seam down the
   middle and one fewer vertex than a quad. Used by every full-screen pass. */
const FULLSCREEN_VS = `#version 300 es
out vec2 vUv;
void main(){
  vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}`;
