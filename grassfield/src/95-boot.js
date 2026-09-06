/* ===================================================================
   Boot, interface, and the frame loop.
   =================================================================== */

const $ = (id) => document.getElementById(id);

const CONTROLS = [
  { grp: 'Image' },
  { k: 'exposure',   label: 'Exposure',            min: 0.5,  max: 3.2,  step: 0.01 },
  { k: 'bloom',      label: 'Bloom',               min: 0,    max: 1.6,  step: 0.01 },
  { k: 'grain',      label: 'Film grain',          min: 0,    max: 0.09, step: 0.001 },
  { k: 'vignette',   label: 'Vignette',            min: 0,    max: 0.85, step: 0.01 },
  { k: 'saturation', label: 'Saturation',          min: 0.4,  max: 1.6,  step: 0.01 },
  { k: 'chroma',     label: 'Lens fringing',       min: 0,    max: 0.02, step: 0.0005 },
  { k: 'fov',        label: 'Field of view',       min: 50,   max: 100,  step: 1, unit: '°' },

  { grp: 'Field' },
  { k: 'wind',        label: 'Wind',               min: 0,    max: 1.6,  step: 0.01 },
  { k: 'groundLift',  label: 'Ground brightness',  min: 0.5,  max: 7.0,  step: 0.05 },
  { k: 'sheen',       label: 'Leaf sheen',         min: 0,    max: 5.0,  step: 0.05 },
  { k: 'density',     label: 'Grass density',      min: 0.2,  max: 2.0,  step: 0.05 },
  { k: 'bladeHeight', label: 'Grass height',       min: 0.4,  max: 1.6,  step: 0.02, unit: ' m' },
  { k: 'grassRange',  label: 'Grass distance',     min: 40,   max: 165,  step: 5, unit: ' m' },
  { k: 'maxBlades',   label: 'Grass budget',       min: 40,   max: 1200, step: 20, unit: 'k',
    note: 'Ceiling on blades submitted per frame. Tile-based GPUs (Apple Silicon especially) quietly drop geometry once their primitive buffer overflows - 60 fps, no error, no grass. If the field vanishes, lower this.' },
  { k: 'trail',       label: 'Trail memory',       min: 0,    max: 120,  step: 1, unit: ' s' },
  { k: 'stars',       label: 'Zenith stars',       min: 0,    max: 2,    step: 0.05 },
  { k: 'fireflies',   label: 'Fireflies',          min: 0,    max: 1,    step: 0.05,
    note: 'Not in the original photograph. Off by default.' },

  { grp: 'Performance' },
  { k: 'quality',     label: 'Quality', select: [
      ['auto', 'Auto'], ['low', 'Low'], ['medium', 'Medium'],
      ['high', 'High'], ['ultra', 'Ultra']] },
  { k: 'vramBudget',  label: 'Video memory',       min: 48,   max: 1024, step: 8, unit: ' MB', needsResize: true,
    note: 'What the render targets may cost. Resolution is taken first, down to one buffer pixel per screen pixel; whatever is left buys antialiasing. Raise it if you have a discrete GPU, lower it if the picture breaks up.' },
  { k: 'renderScale', label: 'Render scale',       min: 0.4,  max: 1.5,  step: 0.05, needsResize: true },
  { k: 'msaa',        label: 'Antialiasing',        toggle: true, needsResize: true,
    note: 'Multisampling. Grass is almost all thin edges, so this is the single biggest quality setting here.' },

  { grp: 'Controls' },
  { k: 'sensitivity', label: 'Look sensitivity',   min: 0.2,  max: 3.0,  step: 0.05 },
  { k: 'headBob',     label: 'Head bob',           min: 0,    max: 1.6,  step: 0.05 },
  { k: 'invertY',     label: 'Invert look',        toggle: true },

  { grp: 'Sound' },
  { k: 'sound',       label: 'Ambience',           toggle: true },
  { k: 'volume',      label: 'Volume',             min: 0,    max: 1,    step: 0.01 },

  { grp: 'Interface' },
  { k: 'showHud',     label: 'Show readout',       toggle: true }
];

function boot() {
  const canvas = $('view');
  /* A renderer that dies without saying why is just badly built. */
  addEventListener('error', (e) => {
    if (!window.__world && e && e.message) {
      const n = document.getElementById('gateNote');
      const lw = document.getElementById('loadWrap');
      if (n && lw && !lw.hidden) {
        lw.hidden = true;
        n.innerHTML = 'Something threw while starting up.<br><br>' +
          '<span style="opacity:.6">' + String(e.message) + '</span>';
      }
    }
  });
  const gate = $('gate');
  const note = $('gateNote');

  const fail = (msg, detail) => {
    $('loadWrap').hidden = true;
    $('playBtn').hidden = true;
    note.innerHTML = msg + (detail ? '<br><br><span style="opacity:.6">' + detail + '</span>' : '');
  };

  let world, input, audio;
  let running = true;

  const setProgress = (pct, msg) => {
    $('loadBar').firstElementChild.style.width = pct + '%';
    if (msg) $('loadMsg').textContent = msg;
  };

  /* ---- load the sky plate, then build the world ---- */
  setProgress(12, 'unrolling the sky…');
  const img = new Image();
  img.onload = () => {
    setProgress(46, 'sowing the field…');
    /* let the bar paint before the (synchronous) bake blocks the thread */
    requestAnimationFrame(() => setTimeout(() => {
      try {
        world = new World(canvas, img, SKY_LIGHT);
      } catch (e) {
        console.error(e);
        if (String(e.message).indexOf('WEBGL2') >= 0) {
          fail('This needs WebGL 2, and this browser has not got it.',
               'Try a current Chrome, Edge, Firefox or Safari, and check that ' +
               'hardware acceleration is switched on.');
        } else {
          fail('The renderer failed to start.', String(e.message));
        }
        return;
      }
      setProgress(100, 'ready');
      /* start() allocates every render target we own, and GL.target throws
         if the driver will not give us one. Outside a try that exception
         is uncaught, the Play button never appears, and all you get is a
         progress bar that stops - which is exactly what it did. */
      try {
        start(world);
      } catch (e) {
        console.error(e);
        fail('The renderer started but could not set itself up.',
             String(e && e.message || e) +
             '<br><br>This is usually the GPU refusing a render target. ' +
             'Opening the file in a normal browser window (rather than a ' +
             'preview pane) fixes it most of the time.');
      }
    }, 30));
  };
  img.onerror = () => fail('The sky image did not load.');
  img.src = SKY_IMAGE;

  /* ================================================================ */
  function start(world) {
    input = new Input(canvas);
    audio = new Ambience();
    input.stickEl = document.createElement('div');
    input.stickEl.id = 'stick';
    input.stickEl.innerHTML = '<i></i>';
    input.stickEl.style.opacity = '0';
    document.body.appendChild(input.stickEl);

    const isTouch = matchMedia('(hover: none)').matches || 'ontouchstart' in window;
    if (isTouch) document.body.classList.add('touch');

    const s = world.settings;
    input.sensitivity = s.sensitivity;
    input.invertY = s.invertY;
    audio.setVolume(s.volume);

    world.resize();
    let resizeT = 0;
    addEventListener('resize', () => {
      compassDirty = true;
      /* Mobile browsers fire this every time the URL bar slides, and each
         one would otherwise reallocate every render target we own. */
      clearTimeout(resizeT);
      resizeT = setTimeout(() => world.resize(), 180);
    });

    /* A lost context is otherwise completely silent: the loop keeps
       running, every draw is a no-op, and all you see is a black screen. */
    canvas.addEventListener('webglcontextlost', (e) => {
      e.preventDefault();
      running = false;
      markSafeRestart();
      gate.classList.remove('gone');
      $('loadWrap').hidden = true;
      $('playBtn').hidden = true;
      $('gateKeys').hidden = true;
      note.innerHTML = 'The graphics context was lost - usually the GPU running out of ' +
        'memory.<br><br><button id="reloadBtn" style="margin-top:10px">Reload, more gently</button>';
      const rb = $('reloadBtn');
      if (rb) rb.addEventListener('click', () => location.reload());
    });

    if (SAFE_MODE) {
      setTimeout(() => toast('restarted at reduced quality after a graphics fault'), 900);
      /* one clean minute and we stop treating this machine as fragile */
      setTimeout(clearSafeRestart, 60000);
    }

    buildPanel(world, input, audio);
    applyHud(s);

    $('loadWrap').hidden = true;
    $('playBtn').hidden = false;
    $('gateKeys').hidden = isTouch;
    note.innerHTML = isTouch
      ? 'Drag on the left to walk, on the right to look.'
      : 'The sky is the original photograph on a dome, so it stays exact however far ' +
        'you walk. The ground is rebuilt as real grass, because a photograph has no depth.';

    const enter = () => {
      gate.classList.add('gone');
      document.body.classList.add('playing');
      if (!isTouch) input.requestLock();
      if (s.sound) audio.setEnabled(true);
    };
    $('playBtn').addEventListener('click', enter);
    canvas.addEventListener('click', () => {
      if (!gate.classList.contains('gone')) return;
      if (!isTouch && !input.locked && $('panel').classList.contains('hidden')) input.requestLock();
    });

    input.onLockChange = (locked) => {
      if (!locked) document.body.classList.remove('playing');
      else document.body.classList.add('playing');
    };

    input.onKey = (e) => {
      if (gate.classList.contains('gone') === false) return;
      switch (e.code) {
        case 'KeyO': togglePanel(); break;
        case 'KeyH': s.showHud = !s.showHud; applyHud(s); saveSettings(s); break;
        case 'KeyM':
          s.sound = !s.sound; audio.setEnabled(s.sound); saveSettings(s);
          syncPanel(); toast(s.sound ? 'sound on' : 'sound off'); break;
        case 'KeyR':
          world.pos[0] = 0; world.pos[2] = 0; world.vel[0] = world.vel[2] = 0;
          world.trample.clear(); toast('back to the middle'); break;
        case 'KeyP': screenshot(); break;
      }
    };

    /* ---------------- loop ---------------- */
    let last = performance.now();
    let frames = 0, fpsT = 0;
    let msAvg = 16.7;

    function frame(now) {
      if (!running) return;
      requestAnimationFrame(frame);
      let dt = (now - last) / 1000;
      last = now;
      if (dt > 0.1) dt = 0.1;              /* a tab that was in the background */
      if (dt <= 0) return;

      const t0 = performance.now();
      world.step(dt, input, audio);
      world.render(dt);
      msAvg = msAvg * 0.92 + (performance.now() - t0) * 0.08;

      frames++; fpsT += dt;
      if (fpsT >= 0.5) {
        world.fps = frames / fpsT;
        frames = 0; fpsT = 0;
        updateReadout(world, msAvg);
        if (world.settings.quality === 'auto') autoQuality(world, msAvg);
      }
      updateCompass(world);
    }
    requestAnimationFrame(frame);
  }

  /* ---------------------------------------------------------------- */
  function autoQuality(world, ms) {
    /* Aim for a comfortable 60. Two separate knobs, because they cost
       very different things: grass density is free to change every time
       we look at it, while changing the resolution reallocates every
       render target we own. The old version reallocated ~460 MB of
       buffers for a 0.3% area change, twice a second. */
    const prev = world.autoScale;
    /* Comes down fast and goes back up slowly. autoScale now also scales
       the blade budget, so this is the loop that actually finds a load
       the machine can carry - it could not do that before, when the
       instance count was fixed by a camera-centred square. */
    if (ms > 28) world.autoScale = Math.max(0.22, world.autoScale - 0.18);
    else if (ms > 20) world.autoScale = Math.max(0.22, world.autoScale - 0.08);
    else if (ms < 11 && world.autoScale < 1.0) world.autoScale = Math.min(1.0, world.autoScale + 0.04);

    const now = performance.now();
    const moved = Math.abs(world.autoScale / (prev || 1) - 1);
    if (moved > 0.06 && now - world.lastResizeAt > 1500) {
      world.lastResizeAt = now;
      world.resize();
    }
  }

  function updateReadout(world, ms) {
    if (!world.settings.showHud) return;
    $('rFps').textContent =
      Math.round(world.fps) + ' fps · ' + ms.toFixed(1) + ' ms';
    const dirDeg = ((world.windAngle * 180 / Math.PI) % 360 + 360) % 360;
    $('rWind').textContent =
      'wind ' + Math.round(world.gust * world.settings.wind * 100) + '% · ' +
      Math.round(dirDeg) + '° · ' +
      (world.grass.instanceCount / 1000).toFixed(0) + 'k blades';
    $('rPos').textContent =
      world.pos[0].toFixed(0) + ', ' + world.pos[2].toFixed(0) + ' m  ·  ' +
      world.canvas.width + '\u00d7' + world.canvas.height +
      (world.samples > 1 ? '  ' + world.samples + '\u00d7 AA' : '');
  }

  const CARDINALS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  let tapeBuilt = false;
  let compassW = -1, compassDirty = true;
  function updateCompass(world) {
    const tape = $('compassTape');
    if (!tapeBuilt) {
      let html = '';
      for (let rep = 0; rep < 3; rep++)
        for (let i = 0; i < 24; i++) {
          const deg = i * 15;
          const label = deg % 45 === 0 ? CARDINALS[(deg / 45) | 0] : '·';
          html += '<span style="width:26px">' + label + '</span>';
        }
      tape.innerHTML = html;
      tapeBuilt = true;
    }
    const deg = ((world.yaw * 180 / Math.PI) % 360 + 360) % 360;
    /* cached: reading clientWidth every frame forces a layout */
    if (compassW < 0 || compassDirty) { compassW = tape.parentElement.clientWidth; compassDirty = false; }
    /* 26 px per 15 degrees; the middle repeat keeps it continuous */
    const x = -(deg / 15) * 26 - 24 * 26 + compassW * 0.5;
    tape.style.transform = 'translateX(' + x + 'px)';
  }

  function applyHud(s) {
    $('hud').classList.toggle('hidden', !s.showHud);
  }

  /* ---------------------------------------------------------------- */
  let panelRows = [];

  function togglePanel() {
    const p = $('panel');
    const opening = p.classList.contains('hidden');
    p.classList.toggle('hidden');
    if (opening && document.pointerLockElement) document.exitPointerLock();
  }

  function buildPanel(world, input, audio) {
    const s = world.settings;
    const body = $('panelBody');
    body.innerHTML = '';
    panelRows = [];

    for (const c of CONTROLS) {
      if (c.grp) {
        const h = document.createElement('div');
        h.className = 'grp'; h.textContent = c.grp;
        body.appendChild(h);
        continue;
      }
      const row = document.createElement('div');
      row.className = 'row';
      const lab = document.createElement('label');
      lab.textContent = c.label;
      row.appendChild(lab);

      let read = null, ctl;
      if (c.toggle) {
        ctl = document.createElement('div');
        ctl.className = 'sw' + (s[c.k] ? ' on' : '');
        ctl.addEventListener('click', () => {
          s[c.k] = !s[c.k];
          ctl.classList.toggle('on', s[c.k]);
          apply(c, world, input, audio);
        });
      } else if (c.select) {
        ctl = document.createElement('select');
        for (const [v, t] of c.select) {
          const o = document.createElement('option');
          o.value = v; o.textContent = t;
          ctl.appendChild(o);
        }
        ctl.value = s[c.k];
        ctl.addEventListener('change', () => {
          s[c.k] = ctl.value;
          applyQuality(world);
          apply(c, world, input, audio);
        });
      } else {
        ctl = document.createElement('input');
        ctl.type = 'range';
        ctl.min = c.min; ctl.max = c.max; ctl.step = c.step;
        ctl.value = s[c.k];
        read = document.createElement('span');
        read.className = 'val';
        const fmt = () => {
          const v = s[c.k];
          read.textContent = (c.step < 0.01 ? v.toFixed(4)
                            : c.step < 0.1 ? v.toFixed(2)
                            : v.toFixed(0)) + (c.unit || '');
        };
        ctl.addEventListener('input', () => {
          s[c.k] = parseFloat(ctl.value);
          fmt();
          apply(c, world, input, audio);
        });
        fmt();
      }
      row.appendChild(ctl);
      if (read) row.appendChild(read);
      body.appendChild(row);

      if (c.note) {
        const n = document.createElement('div');
        n.className = 'hintline'; n.textContent = c.note;
        body.appendChild(n);
      }
      panelRows.push({ c, ctl, read });
    }

    $('panelClose').addEventListener('click', togglePanel);
    $('btnReset').addEventListener('click', () => {
      Object.assign(world.settings, DEFAULTS);
      world.rw = world.rh = 0;
      clearSafeRestart();
      applyQuality(world);
      input.sensitivity = world.settings.sensitivity;
      input.invertY = world.settings.invertY;
      audio.setEnabled(world.settings.sound);
      audio.setVolume(world.settings.volume);
      world.resize();
      applyHud(world.settings);
      saveSettings(world.settings);
      syncPanel();
      toast('defaults restored');
    });
    if (!CAN_DOWNLOAD) $('btnShot').textContent = 'Photo mode (H)';
    $('btnShot').addEventListener('click', () => {
      if (!CAN_DOWNLOAD) {
        world.settings.showHud = !world.settings.showHud;
        applyHud(world.settings); saveSettings(world.settings);
        togglePanel();
        return;
      }
      screenshot();
    });
    const diagBtn = $('btnDiag');
    if (diagBtn) diagBtn.addEventListener('click', () => {
      const text = diagnostics();
      console.log(text);
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text)
          .then(() => toast('diagnostics copied'))
          .catch(() => toast('diagnostics printed to the console'));
      } else {
        toast('diagnostics printed to the console');
      }
    });
  }

  function syncPanel() {
    const s = window.__world.settings;
    for (const { c, ctl, read } of panelRows) {
      if (c.toggle) ctl.classList.toggle('on', !!s[c.k]);
      else if (c.select) ctl.value = s[c.k];
      else {
        ctl.value = s[c.k];
        if (read) read.textContent = (c.step < 0.01 ? s[c.k].toFixed(4)
                                    : c.step < 0.1 ? s[c.k].toFixed(2)
                                    : s[c.k].toFixed(0)) + (c.unit || '');
      }
    }
  }

  function applyQuality(world) {
    const s = world.settings;
    const p = QUALITY_PRESETS[s.quality];
    if (p) { s.renderScale = p.renderScale; world.autoScale = 1.0; }
    else { world.autoScale = clamp(world.autoScale, 0.45, 1.0); }
    world.resize();
    syncPanel();
  }

  function apply(c, world, input, audio) {
    const s = world.settings;
    if (c.k === 'sensitivity') input.sensitivity = s.sensitivity;
    if (c.k === 'invertY') input.invertY = s.invertY;
    if (c.k === 'sound') audio.setEnabled(s.sound);
    if (c.k === 'volume') audio.setVolume(s.volume);
    if (c.k === 'showHud') applyHud(s);
    if (c.k === 'msaa' || c.k === 'quality') world.rw = world.rh = 0;
    if (c.needsResize) world.resize();
    saveSettings(s);
  }

  /* ---------------------------------------------------------------- */
  let toastT = 0;
  function toast(msg) {
    const t = $('toast');
    t.textContent = msg;
    t.classList.add('show');
    clearTimeout(toastT);
    toastT = setTimeout(() => t.classList.remove('show'), 1600);
  }

  /* Hosted in a frame, a download link is inert - the viewer never grants
     the page permission to hand you a file. Better to say so than to
     claim the frame was saved and quietly do nothing. */
  const CAN_DOWNLOAD = (() => { try { return window.self === window.top; } catch (e) { return false; } })();

  function screenshot() {
    if (!world) return;
    if (!CAN_DOWNLOAD) {
      toast('use your device\u2019s own screenshot here');
      return;
    }
    world.requestShot((blob) => {
      if (!blob) { toast('could not save the frame'); return; }
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'grassfield-' + Date.now() + '.png';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      toast('frame saved');
    });
  }

  /** Everything worth knowing if it still will not run somewhere. */
  function diagnostics() {
    const lines = [];
    lines.push('Grassfield diagnostics');
    lines.push('userAgent: ' + navigator.userAgent);
    lines.push('devicePixelRatio: ' + devicePixelRatio +
               '   window: ' + innerWidth + 'x' + innerHeight);
    if (world) {
      const gl = world.glw.gl;
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      lines.push('renderer: ' + (dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER)));
      lines.push('vendor: ' + (dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR)));
      lines.push('version: ' + gl.getParameter(gl.VERSION));
      lines.push('drawing buffer: ' + world.canvas.width + 'x' + world.canvas.height +
                 '  (' + (world.canvas.width * world.canvas.height / 1e6).toFixed(2) + ' MP)' +
                 '  msaa: ' + world.samples + 'x');
      lines.push('vram budget: ' + world.settings.vramBudget + ' MB' +
                 '   autoScale: ' + world.autoScale.toFixed(2));
      lines.push('half-float targets: ' + world.glw.hdr +
                 '   colour_buffer_half_float: ' + !!world.glw.extHalf +
                 '   colour_buffer_float: ' + !!world.glw.extFloat);
      lines.push('MAX_TEXTURE_SIZE: ' + gl.getParameter(gl.MAX_TEXTURE_SIZE) +
                 '   MAX_RENDERBUFFER_SIZE: ' + gl.getParameter(gl.MAX_RENDERBUFFER_SIZE) +
                 '   MAX_SAMPLES: ' + gl.getParameter(gl.MAX_SAMPLES));
      lines.push('fps: ' + world.fps.toFixed(1) + '   blades submitted: ' + world.grass.instanceCount +
                 '   budget: ' + world.settings.maxBlades + 'k');
      const st = world.selfTest || {};
      lines.push('self-test  vertexTextureFetch: ' + st.vertexTextureFetch +
                 '   halfFloatTargets: ' + st.halfFloatTargets +
                 '   msaaResolve: ' + st.msaaResolve);
      if (st.notes && st.notes.length) lines.push('self-test notes: ' + st.notes.join(' | '));
      lines.push('glGetError: ' + gl.getError() + '   contextLost: ' + gl.isContextLost());
      lines.push('settings: ' + JSON.stringify(world.settings));
    } else {
      lines.push('renderer never started');
    }
    return lines.join('\n');
  }

  /* expose for the panel's sync helper and for poking at from a console */
  Object.defineProperty(window, '__world', { get: () => world });
}

if (document.readyState === 'loading') addEventListener('DOMContentLoaded', boot);
else boot();
