/* ===================================================================
   Input: pointer-lock mouse, keyboard, a thumb stick on touch, and a
   gamepad if one is plugged in.
   =================================================================== */

class Input {
  constructor(canvas) {
    this.canvas = canvas;
    this.keys = Object.create(null);
    this.dx = 0; this.dy = 0;
    this.locked = false;
    /* Pointer lock is not granted inside a sandboxed frame, which is how
       the hosted page is served - so mouse look silently did nothing
       there. Drag-look is the fallback that works everywhere. */
    this.lockAvailable = true;
    this.dragging = false;
    this.lastX = 0;
    this.lastY = 0;
    this.sensitivity = 1.0;
    this.invertY = false;
    this.touch = { active: false, id: -1, ox: 0, oy: 0, x: 0, y: 0 };
    this.lookTouch = { id: -1, x: 0, y: 0 };
    this.onLockChange = null;
    this.stickEl = null;
    this._bind();
  }

  _bind() {
    const c = this.canvas;

    addEventListener('keydown', (e) => {
      if (e.code === 'Tab') e.preventDefault();
      this.keys[e.code] = true;
      if (this.onKey) this.onKey(e);
    });
    addEventListener('keyup', (e) => { this.keys[e.code] = false; });
    addEventListener('blur', () => { this.keys = Object.create(null); });

    document.addEventListener('pointerlockchange', () => {
      this.locked = document.pointerLockElement === c;
      if (this.onLockChange) this.onLockChange(this.locked);
    });

    addEventListener('mousemove', (e) => {
      if (this.locked) {
        /* Chrome can deliver one enormous movement value on lock; clamping
           stops the view snapping halfway round the field. */
        const mx = Math.max(-260, Math.min(260, e.movementX || 0));
        const my = Math.max(-260, Math.min(260, e.movementY || 0));
        this.dx += mx * 0.0022 * this.sensitivity;
        this.dy += my * 0.0022 * this.sensitivity * (this.invertY ? -1 : 1);
        return;
      }
      if (!this.dragging) return;
      const dx = e.clientX - this.lastX, dy = e.clientY - this.lastY;
      this.lastX = e.clientX; this.lastY = e.clientY;
      this.dx += dx * 0.0034 * this.sensitivity;
      this.dy += dy * 0.0034 * this.sensitivity * (this.invertY ? -1 : 1);
    });

    c.addEventListener('mousedown', (e) => {
      if (this.locked || e.button !== 0) return;
      this.dragging = true;
      this.lastX = e.clientX; this.lastY = e.clientY;
      e.preventDefault();
    });
    addEventListener('mouseup', () => { this.dragging = false; });
    addEventListener('blur', () => { this.dragging = false; });
    c.addEventListener('contextmenu', (e) => e.preventDefault());

    document.addEventListener('pointerlockerror', () => {
      this.lockAvailable = false;
      if (this.onLockUnavailable) this.onLockUnavailable();
    });

    /* ---- touch: left half drives, right half looks ---- */
    const half = () => innerWidth * 0.5;
    c.addEventListener('touchstart', (e) => {
      for (const t of e.changedTouches) {
        if (t.clientX < half() && !this.touch.active) {
          this.touch = { active: true, id: t.identifier, ox: t.clientX, oy: t.clientY,
                         x: t.clientX, y: t.clientY };
          if (this.stickEl) {
            this.stickEl.style.left = (t.clientX - 59) + 'px';
            this.stickEl.style.top = (t.clientY - 59) + 'px';
            this.stickEl.style.opacity = '1';
          }
        } else if (this.lookTouch.id < 0) {
          this.lookTouch = { id: t.identifier, x: t.clientX, y: t.clientY };
        }
      }
      e.preventDefault();
    }, { passive: false });

    c.addEventListener('touchmove', (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier === this.touch.id) {
          this.touch.x = t.clientX; this.touch.y = t.clientY;
          if (this.stickEl) {
            const k = this.stickVector();
            this.stickEl.firstElementChild.style.transform =
              'translate(' + (k[0] * 34) + 'px,' + (k[1] * 34) + 'px)';
          }
        } else if (t.identifier === this.lookTouch.id) {
          this.dx += (t.clientX - this.lookTouch.x) * 0.006 * this.sensitivity;
          this.dy += (t.clientY - this.lookTouch.y) * 0.006 * this.sensitivity
                   * (this.invertY ? -1 : 1);
          this.lookTouch.x = t.clientX; this.lookTouch.y = t.clientY;
        }
      }
      e.preventDefault();
    }, { passive: false });

    const end = (e) => {
      for (const t of e.changedTouches) {
        if (t.identifier === this.touch.id) {
          this.touch.active = false; this.touch.id = -1;
          if (this.stickEl) {
            this.stickEl.style.opacity = '0';
            this.stickEl.firstElementChild.style.transform = '';
          }
        }
        if (t.identifier === this.lookTouch.id) this.lookTouch.id = -1;
      }
    };
    c.addEventListener('touchend', end);
    c.addEventListener('touchcancel', end);
  }

  stickVector() {
    if (!this.touch.active) return [0, 0];
    const dx = (this.touch.x - this.touch.ox) / 52;
    const dy = (this.touch.y - this.touch.oy) / 52;
    const m = Math.hypot(dx, dy);
    return m > 1 ? [dx / m, dy / m] : [dx, dy];
  }

  requestLock() {
    if (!this.canvas.requestPointerLock) { this.noteLockUnavailable(); return; }
    /* unadjustedMovement gives raw mouse deltas where it is supported;
       older browsers reject the options object outright, so both the
       throw and the rejected promise have to fall back */
    try {
      const p = this.canvas.requestPointerLock({ unadjustedMovement: true });
      if (p && p.catch) p.catch(() => { try { this.canvas.requestPointerLock(); } catch (e) {} });
    } catch (e) {
      try { this.canvas.requestPointerLock(); } catch (e2) {}
    }
    /* A sandboxed frame does not always fire pointerlockerror - it just
       never locks. If we are not locked shortly after asking, assume we
       never will be and switch to dragging. */
    clearTimeout(this._lockTimer);
    this._lockTimer = setTimeout(() => {
      if (!this.locked) this.noteLockUnavailable();
    }, 600);
  }

  noteLockUnavailable() {
    if (!this.lockAvailable) return;
    this.lockAvailable = false;
    if (this.onLockUnavailable) this.onLockUnavailable();
  }

  /** Movement in camera space: x right, y forward, both -1..1. */
  moveVector() {
    const k = this.keys;
    let x = 0, y = 0;
    if (k.KeyW || k.ArrowUp) y += 1;
    if (k.KeyS || k.ArrowDown) y -= 1;
    if (k.KeyD || k.ArrowRight) x += 1;
    if (k.KeyA || k.ArrowLeft) x -= 1;

    const s = this.stickVector();
    x += s[0]; y -= s[1];

    const gp = this.gamepad();
    if (gp) {
      const dz = (v) => Math.abs(v) < 0.16 ? 0 : v;
      x += dz(gp.axes[0]); y -= dz(gp.axes[1]);
      this.dx += dz(gp.axes[2] || 0) * 0.045 * this.sensitivity;
      this.dy += dz(gp.axes[3] || 0) * 0.045 * this.sensitivity * (this.invertY ? -1 : 1);
    }

    const m = Math.hypot(x, y);
    return m > 1 ? [x / m, y / m] : [x, y];
  }

  gamepad() {
    if (!navigator.getGamepads) return null;
    const list = navigator.getGamepads();
    for (const g of list) if (g && g.connected && g.axes.length >= 2) return g;
    return null;
  }

  running() {
    const gp = this.gamepad();
    return !!(this.keys.ShiftLeft || this.keys.ShiftRight ||
              (gp && gp.buttons[10] && gp.buttons[10].pressed));
  }
  crouching() { return !!this.keys.KeyC; }
  jumping() {
    const gp = this.gamepad();
    return !!(this.keys.Space || (gp && gp.buttons[0] && gp.buttons[0].pressed));
  }

  /** Consume the accumulated look delta. */
  takeLook() {
    const d = [this.dx, this.dy];
    this.dx = 0; this.dy = 0;
    return d;
  }
}
