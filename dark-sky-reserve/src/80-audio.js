/* ===================================================================
   Sound, synthesised from noise - no audio files, nothing to download.

   Three voices: a low body of moving air, a bright hiss of grass that
   rises with the gusts and with how fast you are pushing through it,
   and a footstep swish fired off the walk cycle.
   =================================================================== */

class Ambience {
  constructor() {
    this.ctx = null;
    this.ready = false;
    this.enabled = false;
    this.volume = 0.55;
  }

  init() {
    if (this.ctx) return;
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return;
    const ctx = new AC();
    this.ctx = ctx;

    /* one second of pink-ish noise, looped */
    const len = ctx.sampleRate * 2;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1;
      b0 = 0.99765 * b0 + w * 0.0990460;
      b1 = 0.96300 * b1 + w * 0.2965164;
      b2 = 0.57000 * b2 + w * 1.0526913;
      d[i] = (b0 + b1 + b2 + w * 0.1848) * 0.16;
    }
    /* crossfade the tail into the head so the loop has no click */
    const xf = Math.floor(ctx.sampleRate * 0.25);
    for (let i = 0; i < xf; i++) {
      const t = i / xf;
      d[i] = d[i] * t + d[len - xf + i] * (1 - t);
    }
    this.noise = buf;

    this.master = ctx.createGain();
    this.master.gain.value = 0;
    this.master.connect(ctx.destination);

    const src = () => {
      const s = ctx.createBufferSource();
      s.buffer = buf; s.loop = true; s.start();
      return s;
    };

    /* body of the wind */
    this.lowSrc = src();
    this.lowFilt = ctx.createBiquadFilter();
    this.lowFilt.type = 'lowpass';
    this.lowFilt.frequency.value = 320;
    this.lowFilt.Q.value = 0.7;
    this.lowGain = ctx.createGain(); this.lowGain.gain.value = 0.5;
    this.lowSrc.connect(this.lowFilt).connect(this.lowGain).connect(this.master);

    /* grass hiss */
    this.hiSrc = src();
    this.hiFilt = ctx.createBiquadFilter();
    this.hiFilt.type = 'bandpass';
    this.hiFilt.frequency.value = 2600;
    this.hiFilt.Q.value = 0.55;
    this.hiGain = ctx.createGain(); this.hiGain.gain.value = 0.0;
    this.hiSrc.connect(this.hiFilt).connect(this.hiGain).connect(this.master);

    this.ready = true;
  }

  resume() { if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume(); }

  setEnabled(on) {
    this.enabled = on;
    if (on) { this.init(); this.resume(); }
    if (this.ready) {
      this.master.gain.setTargetAtTime(on ? this.volume : 0, this.ctx.currentTime, 0.4);
    }
  }

  setVolume(v) {
    this.volume = v;
    if (this.ready && this.enabled)
      this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.1);
  }

  /** gust 0..1, speed in m/s, strength = the wind setting */
  update(gust, speed, strength) {
    if (!this.ready || !this.enabled) return;
    const t = this.ctx.currentTime;
    const g = Math.min(1, gust * strength);
    this.lowFilt.frequency.setTargetAtTime(220 + g * 420, t, 0.25);
    this.lowGain.gain.setTargetAtTime(0.22 + g * 0.62, t, 0.3);
    this.hiFilt.frequency.setTargetAtTime(1900 + g * 2400, t, 0.25);
    this.hiGain.gain.setTargetAtTime(0.03 + g * 0.16 + Math.min(speed, 6) * 0.030, t, 0.18);
  }

  footstep(power) {
    if (!this.ready || !this.enabled) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const s = ctx.createBufferSource();
    s.buffer = this.noise;
    s.playbackRate.value = 0.85 + Math.random() * 0.4;
    const f = ctx.createBiquadFilter();
    f.type = 'bandpass';
    f.frequency.value = 1500 + Math.random() * 1600;
    f.Q.value = 0.8;
    const g = ctx.createGain();
    const peak = 0.16 * power;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(Math.max(peak, 0.0002), t + 0.012);
    g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16 + Math.random() * 0.08);
    s.connect(f).connect(g).connect(this.master);
    s.start(t, Math.random() * 1.5);
    s.stop(t + 0.3);
  }
}
