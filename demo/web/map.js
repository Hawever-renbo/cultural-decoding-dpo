/* The coding drawn as a map. The core category sits in the middle, the categories stand around it, each category
   carries its concepts, and every concept wears the open codes it was built from. Arrows are the typed relations
   between categories. Canvas only: every string a model wrote is drawn with fillText, never parsed as markup. */
(function () {
  "use strict";

  const C = { ink: "#1b1915", ink2: "#5a5448", ink3: "#8a8272", paper: "#fbf8f1", wash: "rgba(250,246,237,.94)",
              pen: "#1f3f73", red: "#b3261e", hl: "rgba(255,223,107,.75)" };
  // one coloured pencil per paradigm slot; style.css repeats these as .sw-<slot>
  const SLOT = { P: "#b3261e", CC: "#b5651d", Ctx: "#2f6b3f", IC: "#1f3f73", S: "#6a3d7c", Csq: "#1d6f7a" };
  const ORDER = ["P", "CC", "Ctx", "IC", "S", "Csq"];
  const SERIF = '"Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif';
  const DISPLAY = '"Hoefler Text", Baskerville, "Baskerville Old Face", Garamond, Georgia, serif';
  const SANS = '"Avenir Next", Avenir, "Gill Sans", "Gill Sans MT", "Trebuchet MS", "Segoe UI", sans-serif';
  const F = { cat: "13px " + SERIF, core: "italic 16px " + DISPLAY, name: "11.5px " + SANS, tab: "600 9px " + SANS,
              rel: "600 9.5px " + SANS, tip: "italic 13px " + SERIF };
  const slotColor = (s) => SLOT[s] || C.ink2;
  const rank = (s) => { const i = ORDER.indexOf(s); return i < 0 ? 99 : i; };
  // a line may break at a space, after a hyphen inside a long compound, or between two CJK characters
  const TOKEN = /[\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]|[^\s\-\u2E80-\u9FFF\uF900-\uFAFF\uFF00-\uFFEF]+-*|-+|\s+/g;

  function wrap(ctx, text, maxWidth, maxLines) {     // words for Latin text, single characters for CJK
    const lines = [];
    let cur = "";
    for (const t of String(text || "").trim().match(TOKEN) || []) {
      if (/^\s+$/.test(t)) { if (cur) cur += " "; continue; }
      if (cur && ctx.measureText(cur + t).width > maxWidth) { lines.push(cur.trimEnd()); cur = t; } else cur += t;
    }
    if (cur.trim()) lines.push(cur.trimEnd());
    if (lines.length > maxLines) {
      lines.length = maxLines;
      let last = lines[maxLines - 1];
      while (last.length > 1 && ctx.measureText(last + "…").width > maxWidth) last = last.slice(0, -1);
      lines[maxLines - 1] = last.trimEnd() + "…";
    }
    return lines;
  }

  function mount(canvas, opts) {
    const ctx = canvas.getContext("2d");
    const onSelect = (opts && opts.onSelect) || function () {};
    const M = { nodes: [], links: [], rels: [], core: null, view: { x: 0, y: 0, k: 1 }, W: 0, H: 0, dpr: 1,
                hover: null, selected: null, own: false, drag: null };

    // ------------------------------------------------------------ model
    function add(n) { n.id = M.nodes.length; n.x = n.x || 0; n.y = n.y || 0; M.nodes.push(n); return n; }

    function setGraph(g) {
      M.nodes = []; M.links = []; M.rels = []; M.hover = M.selected = M.drag = null; M.own = false;
      const coreData = g.core_category || {};
      const taken = new Set(coreData.mapping || []);
      if (!taken.size) for (const r of g.relations || []) if (r.type === "abstracts_to" && r.to === coreData.name) taken.add(r.from);
      M.core = coreData.name ? add({ kind: "core", key: "core", name: coreData.name }) : null;
      const cats = (g.categories || []).map((c, i) => [c, i]).sort((a, b) => rank(a[0].c6_slot) - rank(b[0].c6_slot) || a[1] - b[1]).map((x) => x[0]);
      const byCat = new Map(), byCon = new Map(), conData = new Map((g.concepts || []).map((c) => [c.concept, c]));
      for (const c of cats) {
        if (!byCat.has(c.name)) byCat.set(c.name, add({ kind: "category", key: c.name, name: c.name, slot: c.c6_slot, inCore: taken.has(c.name), kids: [] }));
      }
      for (const c of cats) {
        const cat = byCat.get(c.name);
        for (const cn of c.concepts || []) {
          let n = byCon.get(cn);
          if (!n) {
            n = add({ kind: "concept", key: cn, name: cn, slot: c.c6_slot, parent: cat, kids: [] });
            byCon.set(cn, n); cat.kids.push(n);
          }
          M.links.push({ a: n, b: cat, kind: "member" });
        }
      }
      for (const c of g.concepts || []) {              // concepts no category took in
        if (!byCon.has(c.concept)) byCon.set(c.concept, add({ kind: "concept", key: c.concept, name: c.concept, slot: "", parent: null, kids: [] }));
      }
      (g.labels || []).forEach((l, i) => {
        const con = byCon.get(l.concept);
        if (con) con.kids.push(add({ kind: "code", key: i, name: l.label, parent: con }));
      });
      byCon.forEach((n) => { n.r = 4.5 + Math.min(n.kids.length || (conData.get(n.key) || {}).freq || 1, 9) * 0.85; });
      byCat.forEach((cat) => { if (cat.inCore && M.core) M.links.push({ a: cat, b: M.core, kind: "core" }); });
      const seen = {};
      for (const r of g.relations || []) {
        const a = byCat.get(r.from), b = byCat.get(r.to);
        if (!a || !b || a === b || r.type === "abstracts_to") continue;
        const pair = Math.min(a.id, b.id) + "|" + Math.max(a.id, b.id);
        seen[pair] = (seen[pair] || 0) + 1;
        M.rels.push({ a: a, b: b, type: String(r.type || ""), nth: seen[pair] });
      }
      measure(); layout(); resize(true);
      canvas.classList.add("in");
    }

    function measure() {
      for (const n of M.nodes) {
        if (n.kind === "category") {
          ctx.font = F.cat;
          n.lines = wrap(ctx, n.name, 140, 4);
          n.w = Math.max.apply(null, n.lines.map((l) => ctx.measureText(l).width).concat([60])) + 24; n.h = n.lines.length * 16 + 20;
        } else if (n.kind === "core") {
          ctx.font = F.core;
          n.lines = wrap(ctx, n.name, 178, 6);
          n.w = Math.max.apply(null, n.lines.map((l) => ctx.measureText(l).width).concat([80])) + 34; n.h = n.lines.length * 19 + 28;
        } else if (n.kind === "concept") {
          ctx.font = F.name;
          n.lines = wrap(ctx, n.name, 104, 3);
          crown(n);
        } else n.r = 2.6;
      }
    }

    function crown(con) {                              // the codes of a concept sit in arcs above its dot
      let row = 0, placed = 0;
      con.top = con.r;
      while (placed < con.kids.length) {
        const rho = con.r + 8.5 + row * 7.5, cap = Math.max(3, Math.floor((Math.PI * 0.92 * rho) / 7.2)), n = Math.min(cap, con.kids.length - placed);
        for (let j = 0; j < n; j++) {
          const t = n === 1 ? 0.5 : j / (n - 1), a = -Math.PI * (0.96 - 0.92 * t), k = con.kids[placed + j];
          k.ox = Math.cos(a) * rho; k.oy = Math.sin(a) * rho;
        }
        con.top = rho + 4; placed += n; row++;
      }
      con.fw = 58; con.fu = con.top + 4; con.fd = con.r + 6 + con.lines.length * 13;    // footprint: half width, up, down
    }

    // ------------------------------------------------------------ layout
    function layout() {
      const cats = M.nodes.filter((n) => n.kind === "category"), n = cats.length;
      const girth = cats.reduce((s, c) => s + Math.max(c.w + 54, c.kids.length * 96), 0);
      const R = Math.max(150 + (M.core ? M.core.h * 0.45 : 0), (girth / (2 * Math.PI)) * 0.76);
      const rx = R * 1.34 + (M.core ? M.core.w * 0.12 : 0), ry = R;
      cats.forEach((c, i) => {
        const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(n, 1) + (n === 2 ? Math.PI / 2 : 0);
        c.x = Math.cos(a) * rx; c.y = Math.sin(a) * ry;
        const out = Math.atan2(c.y / ry, c.x / rx), k = c.kids.length;
        const spread = Math.min(Math.PI * 1.05, 0.6 + 0.5 * k), dist = Math.max(Math.hypot(c.w, c.h) * 0.3 + 44, ((k - 1) * 104) / spread);
        c.kids.forEach((con, j) => {
          const t = k === 1 ? 0 : j / (k - 1) - 0.5;
          con.x = c.x + Math.cos(out + t * spread) * dist; con.y = c.y + Math.sin(out + t * spread) * dist; con.rest = dist;
        });
      });
      const loose = M.nodes.filter((x) => x.kind === "concept" && !x.parent);
      loose.forEach((con, j) => { con.x = (j - (loose.length - 1) / 2) * 124; con.y = ry + 230; con.rest = 0; });
      relax();
      place();
    }

    function relax() {                                 // push concepts off the boxes and off each other, near their category
      const cons = M.nodes.filter((n) => n.kind === "concept"), boxes = M.nodes.filter((n) => n.kind === "category" || n.kind === "core");
      for (let it = 0; it < 220; it++) {
        for (let i = 0; i < cons.length; i++) {
          const a = cons[i];
          for (let j = i + 1; j < cons.length; j++) {
            const b = cons[j], dx = a.x - b.x, dy = a.y - b.y;
            const px = a.fw + b.fw + 6 - Math.abs(dx), py = (dy < 0 ? a.fd + b.fu : a.fu + b.fd) + 8 - Math.abs(dy);
            if (px <= 0 || py <= 0) continue;
            if (px < py) { const s = (dx < 0 ? -px : px) / 2; a.x += s; b.x -= s; } else { const s = (dy < 0 ? -py : py) / 2; a.y += s; b.y -= s; }
          }
          for (const s of boxes) {
            const dx = a.x - s.x, dy = a.y - s.y;
            const px = s.w / 2 + a.fw + 10 - Math.abs(dx), py = s.h / 2 + (dy < 0 ? a.fd : a.fu) + 12 - Math.abs(dy);
            if (px <= 0 || py <= 0) continue;
            if (px < py) a.x += dx < 0 ? -px : px; else a.y += dy < 0 ? -py : py;
          }
          if (a.parent) {
            const dx = a.parent.x - a.x, dy = a.parent.y - a.y, d = Math.hypot(dx, dy) || 1;
            if (d > a.rest) { a.x += (dx / d) * (d - a.rest) * 0.18; a.y += (dy / d) * (d - a.rest) * 0.18; }
          }
        }
      }
    }

    function place() { for (const n of M.nodes) if (n.kind === "code") { n.x = n.parent.x + n.ox; n.y = n.parent.y + n.oy; } }

    // ------------------------------------------------------------ view
    function bounds() {
      let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
      const grow = (ax, bx, ay, by) => { x0 = Math.min(x0, ax); x1 = Math.max(x1, bx); y0 = Math.min(y0, ay); y1 = Math.max(y1, by); };
      for (const n of M.nodes) {
        if (n.kind === "category" || n.kind === "core") grow(n.x - n.w / 2, n.x + n.w / 2, n.y - n.h / 2 - 8, n.y + n.h / 2);
        else if (n.kind === "concept") grow(n.x - n.fw, n.x + n.fw, n.y - n.fu, n.y + n.fd);
      }
      return { x0: x0, x1: x1, y0: y0, y1: y1 };
    }

    function fit() {
      if (!M.nodes.length || !M.W) return;
      const b = bounds(), pad = 26;
      M.view.k = Math.min((M.W - pad * 2) / (b.x1 - b.x0), (M.H - pad * 2) / (b.y1 - b.y0), 1.3);
      M.view.x = M.W / 2 - ((b.x0 + b.x1) / 2) * M.view.k; M.view.y = M.H / 2 - ((b.y0 + b.y1) / 2) * M.view.k;
      M.own = false; canvas.classList.remove("free");
      draw();
    }

    function resize(refit) {
      M.dpr = window.devicePixelRatio || 1; M.W = canvas.clientWidth; M.H = canvas.clientHeight;
      canvas.width = Math.round(M.W * M.dpr); canvas.height = Math.round(M.H * M.dpr);
      if (refit || !M.own) fit(); else draw();
    }

    function zoom(f, px, py) {
      const k = Math.max(0.25, Math.min(3.2, M.view.k * f)), cx = px === undefined ? M.W / 2 : px, cy = py === undefined ? M.H / 2 : py;
      M.view.x = cx - ((cx - M.view.x) / M.view.k) * k; M.view.y = cy - ((cy - M.view.y) / M.view.k) * k; M.view.k = k;
      M.own = true; canvas.classList.add("free");
      draw();
    }

    // ------------------------------------------------------------ drawing
    function around(n) {                               // what stays lit when n is hovered or selected
      const lit = new Set([n]);
      if (n.kind === "core") for (const l of M.links) { if (l.kind === "core") lit.add(l.a); }
      else if (n.kind === "category") {
        for (const con of n.kids) { lit.add(con); con.kids.forEach((k) => lit.add(k)); }
        for (const l of M.links) if (l.kind === "member" && l.b === n) lit.add(l.a);
        for (const r of M.rels) { if (r.a === n) lit.add(r.b); if (r.b === n) lit.add(r.a); }
        if (n.inCore && M.core) lit.add(M.core);
      } else if (n.kind === "concept") {
        n.kids.forEach((k) => lit.add(k));
        for (const l of M.links) if (l.kind === "member" && l.a === n) lit.add(l.b);
      } else { lit.add(n.parent); for (const l of M.links) if (l.kind === "member" && l.a === n.parent) lit.add(l.b); }
      return lit;
    }

    function rim(box, tx, ty, gap) {                   // where the line from a box's centre towards (tx, ty) leaves the box
      const dx = tx - box.x, dy = ty - box.y, hw = box.w / 2 + gap, hh = box.h / 2 + gap;
      if (!dx && !dy) return [box.x, box.y];
      const s = Math.min(dx ? hw / Math.abs(dx) : Infinity, dy ? hh / Math.abs(dy) : Infinity);
      return [box.x + dx * s, box.y + dy * s];
    }

    function bend(r) {                                 // control point: neighbours bow towards the middle, far pairs go round the core
      const mx = (r.a.x + r.b.x) / 2, my = (r.a.y + r.b.y) / 2, dx = r.b.x - r.a.x, dy = r.b.y - r.a.y, len = Math.hypot(dx, dy) || 1;
      let nx = -dy / len, ny = dx / len;
      const t = Math.max(0, Math.min(1, -(r.a.x * dx + r.a.y * dy) / (len * len)));
      const near = Math.hypot(r.a.x + dx * t, r.a.y + dy * t), clear = M.core ? Math.max(M.core.w, M.core.h) / 2 + 26 : 0;
      const outward = (mx + nx) * (mx + nx) + (my + ny) * (my + ny) > (mx - nx) * (mx - nx) + (my - ny) * (my - ny);
      let amount;
      if (near < clear) { amount = (clear - near) * 1.7 + 30; if (!outward) { nx = -nx; ny = -ny; } }
      else { amount = 16; if (outward) { nx = -nx; ny = -ny; } }
      amount += (r.nth - 1) * 24;
      return [mx + nx * amount, my + ny * amount];
    }

    function draw() {
      ctx.setTransform(M.dpr, 0, 0, M.dpr, 0, 0);
      ctx.clearRect(0, 0, M.W, M.H);
      if (!M.nodes.length || !M.W) return;
      const k = M.view.k, focus = M.hover || M.selected, lit = focus ? around(focus) : null;
      const on = (a, b) => !lit || (lit.has(a) && (!b || lit.has(b)));
      ctx.save();
      ctx.translate(M.view.x, M.view.y); ctx.scale(k, k);
      ctx.lineCap = "round"; ctx.lineJoin = "round"; ctx.setLineDash([]);

      for (const l of M.links) {                       // membership and "taken up by the core"
        const [x2, y2] = rim(l.b, l.a.x, l.a.y, 0);
        let x1 = l.a.x, y1 = l.a.y;
        if (l.kind === "core") [x1, y1] = rim(l.a, l.b.x, l.b.y, 0);
        ctx.globalAlpha = on(l.a, l.b) ? (l.kind === "core" ? 0.8 : 0.55) : 0.08;
        ctx.strokeStyle = l.kind === "core" ? C.red : C.ink3; ctx.lineWidth = l.kind === "core" ? 1.15 : 0.8;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      }

      const names = [];
      for (const r of M.rels) {                        // typed relations between categories
        const [cx, cy] = bend(r), [x1, y1] = rim(r.a, cx, cy, 2), [x2, y2] = rim(r.b, cx, cy, 3);
        const lift = on(r.a, r.b) && (!lit || focus === r.a || focus === r.b);
        ctx.globalAlpha = lit ? (lift ? 1 : 0.07) : 0.78;
        ctx.strokeStyle = ctx.fillStyle = lift && lit ? C.pen : C.ink; ctx.lineWidth = lift && lit ? 1.5 : 1.1;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo(cx, cy, x2, y2); ctx.stroke();
        const ux = x2 - cx, uy = y2 - cy, ul = Math.hypot(ux, uy) || 1, ex = ux / ul, ey = uy / ul;
        ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 - ex * 8 - ey * 3.4, y2 - ey * 8 + ex * 3.4); ctx.lineTo(x2 - ex * 8 + ey * 3.4, y2 - ey * 8 - ex * 3.4);
        ctx.closePath(); ctx.fill();
        const text = r.type.toUpperCase();
        ctx.font = F.rel; ctx.textAlign = "center"; ctx.textBaseline = "middle";
        const tw = ctx.measureText(text).width;
        let lx = 0, ly = 0;
        for (const t of [0.5, 0.42, 0.58, 0.34, 0.66, 0.5]) {     // the name of the relation sits on the line, clear of the boxes
          lx = (1 - t) * (1 - t) * x1 + 2 * (1 - t) * t * cx + t * t * x2; ly = (1 - t) * (1 - t) * y1 + 2 * (1 - t) * t * cy + t * t * y2;
          if (!M.nodes.some((b) => (b.kind === "category" || b.kind === "core") && Math.abs(lx - b.x) < b.w / 2 + tw / 2 + 5 && Math.abs(ly - b.y) < b.h / 2 + 14)) break;
        }
        names.push({ text: text, x: lx, y: ly, w: tw, alpha: ctx.globalAlpha, color: lift && lit ? C.pen : C.ink2 });
      }

      for (const n of M.nodes) {                       // concepts with their crown of codes
        if (n.kind !== "concept") continue;
        const lifted = on(n);
        for (const c of n.kids) {
          const hot = c === M.hover || c === M.selected;
          ctx.globalAlpha = on(c) ? 1 : 0.12;
          if (hot) { ctx.fillStyle = C.hl; ctx.beginPath(); ctx.arc(c.x, c.y, 7, 0, Math.PI * 2); ctx.fill(); }
          ctx.fillStyle = C.pen; ctx.beginPath(); ctx.arc(c.x, c.y, hot ? 3.6 : c.r, 0, Math.PI * 2); ctx.fill();
        }
        ctx.globalAlpha = lifted ? 1 : 0.14;
        if (n === M.selected || n === M.hover) { ctx.fillStyle = C.hl; ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 5, 0, Math.PI * 2); ctx.fill(); }
        ctx.fillStyle = slotColor(n.slot); ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = C.paper; ctx.lineWidth = 1.4; ctx.stroke();
        ctx.font = F.name; ctx.textAlign = "center"; ctx.textBaseline = "top";
        n.lines.forEach((line, i) => {                 // a wash under the name keeps lines from running through the letters
          const lw = ctx.measureText(line).width;
          ctx.fillStyle = C.wash; ctx.fillRect(n.x - lw / 2 - 2, n.y + n.r + 4 + i * 13, lw + 4, 13);
          ctx.fillStyle = lifted && lit ? C.ink : C.ink2; ctx.fillText(line, n.x, n.y + n.r + 5 + i * 13);
        });
      }

      for (const n of M.nodes) {                       // category boxes, then the core
        if (n.kind !== "category") continue;
        const x = n.x - n.w / 2, y = n.y - n.h / 2, col = slotColor(n.slot), hot = n === M.selected || n === M.hover;
        ctx.globalAlpha = on(n) ? 1 : 0.16;
        if (hot) { ctx.fillStyle = C.hl; ctx.fillRect(x - 5, y - 5, n.w + 10, n.h + 10); }
        ctx.fillStyle = C.paper; ctx.fillRect(x, y, n.w, n.h);
        ctx.strokeStyle = col; ctx.lineWidth = 1.5; ctx.setLineDash(n.inCore || !M.core ? [] : [5, 3.5]); ctx.strokeRect(x, y, n.w, n.h); ctx.setLineDash([]);
        ctx.font = F.tab; ctx.textAlign = "left"; ctx.textBaseline = "middle";
        const tab = n.slot || "?", tw = ctx.measureText(tab).width + 10;
        ctx.fillStyle = col; ctx.fillRect(x + 8, y - 7, tw, 14);
        ctx.fillStyle = C.paper; ctx.fillText(tab, x + 13, y + 0.5);
        ctx.font = F.cat; ctx.textAlign = "center"; ctx.fillStyle = C.ink;
        n.lines.forEach((line, i) => ctx.fillText(line, n.x, y + 19 + i * 16));
      }
      if (M.core) {
        const n = M.core, x = n.x - n.w / 2, y = n.y - n.h / 2, hot = n === M.selected || n === M.hover;
        ctx.globalAlpha = on(n) ? 1 : 0.2;
        if (hot) { ctx.fillStyle = C.hl; ctx.fillRect(x - 6, y - 6, n.w + 12, n.h + 12); }
        ctx.fillStyle = C.paper; ctx.fillRect(x, y, n.w, n.h);
        ctx.strokeStyle = C.red; ctx.lineWidth = 2; ctx.strokeRect(x, y, n.w, n.h);
        ctx.lineWidth = 0.7; ctx.strokeRect(x + 4, y + 4, n.w - 8, n.h - 8);
        ctx.font = F.core; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = C.ink;
        n.lines.forEach((line, i) => ctx.fillText(line, n.x, y + 23.5 + i * 19));
      }
      ctx.font = F.rel; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      for (const t of names) {
        ctx.globalAlpha = t.alpha;
        ctx.fillStyle = C.wash; ctx.fillRect(t.x - t.w / 2 - 4, t.y - 7, t.w + 8, 14);
        ctx.fillStyle = t.color; ctx.fillText(t.text, t.x, t.y + 0.5);
      }
      ctx.restore();
      ctx.globalAlpha = 1;
      const h = M.hover;
      if (h && !M.drag && (h.kind === "code" || ((h.kind === "category" || h.kind === "core") && /…$/.test(h.lines[h.lines.length - 1])) || (h.kind === "concept" && /…$/.test(h.lines[h.lines.length - 1])))) tip(h);
    }

    function tip(n) {                                  // the full wording of what the pointer is on
      ctx.font = n.kind === "code" ? F.tip : "13px " + SERIF;
      const lines = wrap(ctx, n.name, Math.min(280, M.W - 40), 5), w = Math.max.apply(null, lines.map((l) => ctx.measureText(l).width)) + 20, h = lines.length * 17 + 14;
      const sx = n.x * M.view.k + M.view.x, top = (n.y - (n.kind === "code" ? 6 : n.kind === "concept" ? n.top : n.h / 2 + 8)) * M.view.k + M.view.y;
      const x = Math.max(6, Math.min(M.W - w - 6, sx - w / 2)), y = top - h - 8 < 6 ? (n.y + (n.kind === "code" ? 8 : n.kind === "concept" ? n.fd : n.h / 2 + 4)) * M.view.k + M.view.y + 8 : top - h - 8;
      ctx.fillStyle = "#fffdf7"; ctx.fillRect(x, y, w, h);
      ctx.strokeStyle = C.ink; ctx.lineWidth = 1; ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      ctx.fillStyle = n.kind === "code" ? C.pen : C.ink; ctx.textAlign = "left"; ctx.textBaseline = "top";
      lines.forEach((line, i) => ctx.fillText(line, x + 10, y + 8 + i * 17));
    }

    // ------------------------------------------------------------ pointer
    function pick(px, py) {
      const k = M.view.k, wx = (px - M.view.x) / k, wy = (py - M.view.y) / k;
      let best = null, bestD = 1e9;
      for (const n of M.nodes) {
        if (n.kind === "core" || n.kind === "category") {
          if (Math.abs(wx - n.x) <= n.w / 2 && Math.abs(wy - n.y) <= n.h / 2 + (n.kind === "category" ? 7 : 0)) return n;
        } else {
          const d = Math.hypot(wx - n.x, wy - n.y), reach = n.kind === "code" ? Math.max(4.2, 5.5 / k) : n.r + 5;
          if (d <= reach && d < bestD) { best = n; bestD = d; }
        }
      }
      return best;
    }

    function carry(n, dx, dy) {                        // a dragged node takes what hangs on it along
      const root = n.kind === "code" ? n.parent : n;
      root.x += dx; root.y += dy;
      if (root.kind === "category") for (const c of root.kids) { c.x += dx; c.y += dy; }
      place();
    }

    function at(ev) { const r = canvas.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; }

    canvas.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      const [px, py] = at(ev);
      M.drag = { node: pick(px, py), x: px, y: py, moved: false, touch: ev.pointerType === "touch" };
      if (!M.drag.touch || M.own) { try { canvas.setPointerCapture(ev.pointerId); } catch (e) { /* older browsers */ } }
    });
    canvas.addEventListener("pointermove", (ev) => {
      const [px, py] = at(ev), d = M.drag;
      if (d && (!d.touch || M.own)) {
        const dx = px - d.x, dy = py - d.y;
        if (!d.moved && Math.hypot(dx, dy) < 4) return;
        d.moved = true; d.x = px; d.y = py; M.own = true;
        if (d.node) carry(d.node, dx / M.view.k, dy / M.view.k); else { M.view.x += dx; M.view.y += dy; }
        canvas.classList.toggle("grabbing", true);
        draw();
        return;
      }
      const h = pick(px, py);
      if (h !== M.hover) { M.hover = h; canvas.classList.toggle("point", Boolean(h)); draw(); }
    });
    const release = (ev) => {
      const d = M.drag;
      M.drag = null; canvas.classList.remove("grabbing");
      if (!d) return;
      if (ev.type === "pointerup" && !d.moved) choose(d.node, true); else draw();
    };
    canvas.addEventListener("pointerup", release);
    canvas.addEventListener("pointercancel", release);
    canvas.addEventListener("pointerleave", () => { if (M.hover && !M.drag) { M.hover = null; canvas.classList.remove("point"); draw(); } });
    canvas.addEventListener("wheel", (ev) => {         // plain scrolling stays with the page; pinch or ctrl/cmd + wheel zooms
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      const [px, py] = at(ev);
      zoom(Math.exp(-ev.deltaY * 0.012), px, py);
    }, { passive: false });
    if (window.ResizeObserver) new ResizeObserver(() => resize(false)).observe(canvas); else window.addEventListener("resize", () => resize(false));

    function choose(n, tell) {
      M.selected = n || null;
      draw();
      if (tell) onSelect(n ? { kind: n.kind, key: n.key } : null);
    }

    function select(kind, key) {                       // from outside: the panel's buttons
      const n = kind ? M.nodes.find((x) => x.kind === kind && x.key === key) : null;
      if (n && M.W) {
        const sx = n.x * M.view.k + M.view.x, sy = n.y * M.view.k + M.view.y;
        if (sx < 20 || sy < 20 || sx > M.W - 20 || sy > M.H - 20) fit();
      }
      choose(n, true);
    }

    function reveal(covered) {                         // slide the map so the selected node is not under a panel of that width
      const n = M.selected;
      if (!n || !M.W) return;
      const sx = n.x * M.view.k + M.view.x, half = ((n.w || 110) / 2) * M.view.k, limit = M.W - covered - 24;
      if (sx + half > limit) { M.view.x -= sx + half - limit; M.own = true; draw(); }
    }

    function clear() { M.nodes = []; M.links = []; M.rels = []; M.hover = M.selected = null; canvas.classList.remove("in"); draw(); }

    return { setGraph: setGraph, select: select, zoom: (f) => zoom(f), fit: fit, reveal: reveal, clear: clear };
  }

  window.CodingMap = { mount: mount, SLOT: SLOT };
})();
