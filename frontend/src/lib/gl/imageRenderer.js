// WebGL2 renderer for float images: stretch, gamma, colour map, RGB composites, clip / NaN
// highlighting and threshold highlighting all run in the fragment shader, so changing any of
// them never touches the CPU-side data.

const VS = `#version 300 es
in vec2 aPos;          // unit quad 0..1
uniform vec4 uRect;    // image rect in clip space: x0, y0, x1, y1
out vec2 vUv;
void main() {
  vUv = aPos;
  gl_Position = vec4(mix(uRect.x, uRect.z, aPos.x), mix(uRect.y, uRect.w, aPos.y), 0.0, 1.0);
}`;

const FS = `#version 300 es
precision highp float;
precision highp sampler2D;
uniform sampler2D uT0, uT1, uT2, uLut;
uniform int uMode;          // 0 single channel + LUT, 1 RGB
uniform vec3 uLo, uHi;
uniform float uGamma;
uniform vec2 uSize;         // image size in px
uniform float uFoot;        // image px per screen px
uniform int uNan, uClip;
uniform int uThr;           // 0 off, 1 highlight v <= thr, 2 highlight v >= thr
uniform float uThrV;
in vec2 vUv;
out vec4 outColor;

bool bad(float v) { return isnan(v) || isinf(v) || v != v; }

float fetchAt(sampler2D t, vec2 p) {
  ivec2 ip = clamp(ivec2(floor(p)), ivec2(0), ivec2(uSize) - 1);
  return texelFetch(t, ip, 0).r;
}

// Box-filter when minified so zoomed-out views don't alias; exact texels when magnified.
float samp(sampler2D t, vec2 p) {
  if (uFoot <= 1.0) return fetchAt(t, p);
  float s = 0.0, n = 0.0;
  for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) {
    float v = fetchAt(t, p + (vec2(float(i), float(j)) - 1.0) / 3.0 * uFoot);
    if (!bad(v)) { s += v; n += 1.0; }
  }
  return n > 0.0 ? s / n : uintBitsToFloat(0x7fc00000u);
}

float stretch(float v, int c) {
  float t = clamp((v - uLo[c]) / max(uHi[c] - uLo[c], 1e-30), 0.0, 1.0);
  return pow(t, 1.0 / uGamma);
}

vec3 lut(float t) { return texture(uLut, vec2(t * (255.0 / 256.0) + 0.5 / 256.0, 0.5)).rgb; }

void main() {
  vec2 p = vUv * uSize;
  p.y = uSize.y - p.y;
  const vec3 NAN_C = vec3(1.0, 0.24, 0.95);
  const vec3 UNDER = vec3(0.23, 0.42, 1.0);
  const vec3 OVER = vec3(1.0, 0.22, 0.22);
  if (uMode == 0) {
    float v = samp(uT0, p);
    if (bad(v)) { outColor = uNan == 1 ? vec4(NAN_C, 1.0) : vec4(0.0); return; }
    float t = stretch(v, 0);
    vec3 c = lut(t);
    if (uThr > 0) {
      // Matches glow in a fixed accent over a dimmed grey backdrop.
      bool hit = uThr == 1 ? v <= uThrV : v >= uThrV;
      float g = 0.12 + 0.4 * (uThr == 1 ? 1.0 - t : t);
      vec3 accent = uThr == 1 ? vec3(0.2, 0.9, 1.0) : vec3(1.0, 0.82, 0.25);
      float strength = uThr == 1 ? 1.0 - 0.5 * clamp(v / max(uThrV, 1e-30), 0.0, 1.0) : 1.0;
      c = hit ? mix(vec3(g), accent, 0.55 + 0.45 * strength) : vec3(g);
    }
    if (uClip == 1) { if (v < uLo[0]) c = UNDER; else if (v > uHi[0]) c = OVER; }
    outColor = vec4(c, 1.0);
  } else {
    float r = samp(uT0, p), g = samp(uT1, p), b = samp(uT2, p);
    if (bad(r) || bad(g) || bad(b)) { outColor = uNan == 1 ? vec4(NAN_C, 1.0) : vec4(0.0); return; }
    vec3 c = vec3(stretch(r, 0), stretch(g, 1), stretch(b, 2));
    if (uClip == 1) {
      if (r > uHi[0] || g > uHi[1] || b > uHi[2]) c = OVER;
      else if (r < uLo[0] && g < uLo[1] && b < uLo[2]) c = UNDER;
    }
    outColor = vec4(c, 1.0);
  }
}`;

function compile(gl, type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
  return s;
}

export class ImageRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext('webgl2', { antialias: false, preserveDrawingBuffer: true, premultipliedAlpha: false });
    if (!gl) throw new Error('WebGL2 is not available in this browser');
    this.gl = gl;
    const prog = gl.createProgram();
    gl.attachShader(prog, compile(gl, gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, compile(gl, gl.FRAGMENT_SHADER, FS));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    this.prog = prog;
    this.u = {};
    for (const n of ['uRect', 'uT0', 'uT1', 'uT2', 'uLut', 'uMode', 'uLo', 'uHi', 'uGamma', 'uSize', 'uFoot', 'uNan', 'uClip', 'uThr', 'uThrV']) this.u[n] = gl.getUniformLocation(prog, n);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    const loc = gl.getAttribLocation(prog, 'aPos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    this.tex = [0, 1, 2].map(() => this._makeTex());
    this.texSrc = [null, null, null];
    this.nChannels = 1;
    this.lutTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.lutTex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    this.lutSrc = null;
    this.size = [1, 1];
  }

  _makeTex() {
    const gl = this.gl;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.NEAREST], [gl.TEXTURE_MAG_FILTER, gl.NEAREST], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
    return t;
  }

  /**
   * Upload channels (Float32Array, w×h each; one for a single band, three for RGB). Re-uploads
   * only arrays that changed, and each array once: a single band is not copied into all three
   * textures, which would triple the GPU upload on every step while scrubbing.
   */
  setChannels(channels, w, h) {
    const gl = this.gl;
    this.size = [w, h];
    this.nChannels = Math.min(channels.length, 3);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    for (let i = 0; i < this.nChannels; i++) {
      const src = channels[i];
      if (this.texSrc[i] === src) continue;
      gl.bindTexture(gl.TEXTURE_2D, this.tex[i]);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, w, h, 0, gl.RED, gl.FLOAT, src);
      this.texSrc[i] = src;
    }
  }

  setLut(rgba) {
    if (this.lutSrc === rgba) return;
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, this.lutTex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, rgba);
    this.lutSrc = rgba;
  }

  /**
   * view: {scale, tx, ty} (CSS px), opts: {mode: 0|1, lo[3], hi[3], gamma, nan, clip, thr, thrV}
   */
  draw(view, opts) {
    const gl = this.gl, c = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const W = Math.round(c.clientWidth * dpr), H = Math.round(c.clientHeight * dpr);
    if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
    gl.viewport(0, 0, W, H);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!opts) return;
    const [w, h] = this.size;
    const cw = c.clientWidth, ch = c.clientHeight;
    const x0 = view.tx, y0 = view.ty, x1 = view.tx + w * view.scale, y1 = view.ty + h * view.scale;
    gl.useProgram(this.prog);
    gl.bindVertexArray(this.vao);
    gl.uniform4f(this.u.uRect, (x0 / cw) * 2 - 1, 1 - (y1 / ch) * 2, (x1 / cw) * 2 - 1, 1 - (y0 / ch) * 2);
    for (let i = 0; i < 3; i++) {
      // Fewer than three channels: the missing units repeat the last one.
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, this.tex[Math.min(i, this.nChannels - 1)]);
      gl.uniform1i(this.u[`uT${i}`], i);
    }
    gl.activeTexture(gl.TEXTURE3);
    gl.bindTexture(gl.TEXTURE_2D, this.lutTex);
    gl.uniform1i(this.u.uLut, 3);
    const pad = (a) => [a[0], a[1] ?? a[0], a[2] ?? a[0]];
    gl.uniform1i(this.u.uMode, opts.mode);
    gl.uniform3fv(this.u.uLo, pad(opts.lo));
    gl.uniform3fv(this.u.uHi, pad(opts.hi));
    gl.uniform1f(this.u.uGamma, opts.gamma || 1);
    gl.uniform2f(this.u.uSize, w, h);
    gl.uniform1f(this.u.uFoot, 1 / (view.scale * dpr));
    gl.uniform1i(this.u.uNan, opts.nan ? 1 : 0);
    gl.uniform1i(this.u.uClip, opts.clip ? 1 : 0);
    gl.uniform1i(this.u.uThr, opts.thr || 0);
    gl.uniform1f(this.u.uThrV, opts.thrV ?? 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
}
