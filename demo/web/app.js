/* Demo client. No framework, no third-party code. Everything a model wrote reaches the page as text nodes. */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  function el(tag, props) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
    }
    for (let i = 2; i < arguments.length; i++) {
      const kid = arguments[i];
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid);
    }
    return node;
  }
  const clear = (node) => { while (node.firstChild) node.removeChild(node.firstChild); return node; };
  const pct = (x) => (x === null || x === undefined ? "–" : Math.round(x * 100) + "%");
  function show(node, on) { node.hidden = !on; }
  function say(node, text, ok) {
    clear(node); node.className = "msg" + (ok ? " ok" : "");
    if (text) node.append(text);
    show(node, Boolean(text));
  }

  async function api(path, body) {
    const opts = body === undefined ? {} : {
      method: "POST", body: JSON.stringify(body),
      headers: { "Content-Type": "application/json", "X-Requested-With": "demo" },
    };
    let res;
    try { res = await fetch(path, Object.assign({ credentials: "same-origin" }, opts)); }
    catch (e) { return { status: 0, data: { error: "The server could not be reached." } }; }
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    return { status: res.status, data: data };
  }

  const S = { config: null, me: null, examples: [], turns: new Map(), spans: new Map(), graph: null, runId: null,
              stream: null, seen: 0, busy: false, chat: [], selectedCat: null };
  let MAP = null;                                   // the drawn map of a finished coding (map.js)

  const SLOTS = [["P", "Phenomenon"], ["CC", "Causal conditions"], ["Ctx", "Context"], ["IC", "Intervening conditions"],
                 ["S", "Action strategies"], ["Csq", "Consequences"]];
  const LAYERS = [["surface", "Surface"], ["functional", "Functional"], ["emotional", "Emotional"], ["social", "Social"],
                  ["cultural", "Cultural"], ["cultural_logic", "Cultural logic"], ["symbolic_meaning", "Symbolic meaning"]];
  const STAGES = ["open", "concepts", "axial", "selective", "decode", "checks"];
  const ASKS = ["What is the core category, and which quotes carry it?", "Where do the speakers disagree?",
                "Which category rests on the thinnest evidence?", "How was this coding checked?"];

  // ------------------------------------------------------------ sign-in
  async function boot() {
    S.config = (await api("/api/config")).data;
    const me = await api("/api/me");
    if (me.status === 200) { S.me = me.data; return openBench(); }
    openGate();
  }

  function openGate() {
    show($("bench"), false); show($("gate"), true);
    const auth = (S.config && S.config.auth) || {};
    show($("email-form"), Boolean(auth.email));
    show($("gh-wrap"), Boolean(auth.github));
    if (auth.github && !auth.email) $("gh-wrap").querySelector(".or").hidden = true;
    const link = $("request-link");
    if (S.config && S.config.request_access_url) link.href = S.config.request_access_url;
    else show(link.parentNode, false);
    const why = new URLSearchParams(location.search).get("signin");
    if (why === "denied") say($("gate-msg"), "That GitHub account is not on the access list. You can request access below.");
    if (why === "failed") say($("gate-msg"), "GitHub sign-in did not complete. Please try again.");
    if (!auth.email && !auth.github) say($("gate-msg"), "Sign-in is not set up on this server yet.");
    if (why) history.replaceState(null, "", "/");
  }

  $("email-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const email = $("email").value.trim();
    const btn = ev.target.querySelector("button");
    btn.disabled = true;
    const r = await api("/api/auth/request", { email: email });
    btn.disabled = false;
    if (r.status !== 200) return say($("gate-msg"), r.data.error || "That did not work. Try again.");
    say($("gate-msg"), "");
    $("sent-to").textContent = email;
    show($("email-form"), false); show($("gh-wrap"), false); show($("code-form"), true);
    $("code").value = ""; $("code").focus();
  });
  $("code-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const r = await api("/api/auth/verify", { email: $("email").value.trim(), code: $("code").value });
    if (r.status !== 200) return say($("gate-msg"), r.data.error || "That code is wrong or has expired.");
    location.replace("/");
  });
  $("code-back").addEventListener("click", () => {
    show($("code-form"), false); show($("email-form"), true);
    show($("gh-wrap"), Boolean(S.config.auth.github)); say($("gate-msg"), "");
  });

  // ------------------------------------------------------------ workbench frame
  async function openBench() {
    show($("gate"), false); show($("bench"), true);
    paintMe();
    $("asks").replaceChildren.apply($("asks"), ASKS.map((q) => el("button", { class: "ask", type: "button", text: q, onclick: () => ask(q) })));
    const ex = await api("/api/examples");
    S.examples = (ex.data && ex.data.examples) || [];
    countWords();
    const mine = await api("/api/runs");
    const last = mine.status === 200 && mine.data.runs[0];
    if (last) {
      $("reopen-btn").textContent = last.core_category || last.focus || last.run_id;
      $("reopen-btn").onclick = () => loadGraph(last.run_id, true);
      show($("reopen"), true);
    }
  }

  function paintMe() {
    const me = S.me, m = me.models, box = clear($("models"));
    const status = me.opencoder;
    if (m.open_coding_is_post_trained) {
      box.append(el("span", { class: "dot " + status }), "Level I: ", el("b", { text: m.open_coding }),
                 " post-trained, " + (status === "online" ? "online" : "offline right now"));
    } else {
      box.append(el("span", { class: "dot" }), "Level I: ", el("b", { text: m.open_coding }), " general model (no post-trained model connected)");
    }
    box.append("  ·  Levels II–V: ", el("b", { text: m.reasoner }));
    $("who").textContent = me.user.name;
    $("keep").textContent = me.limits.keep_hours;
    $("quota").textContent = me.quota.runs_left + " run" + (me.quota.runs_left === 1 ? "" : "s") + " left today, up to " + me.limits.max_words + " words each. A run takes a few minutes.";
    const canCompare = m.open_coding_is_post_trained && Boolean(m.open_coding_base) && status === "online";
    $("compare").disabled = !canCompare;
    if (!canCompare) $("compare").checked = false;
  }
  async function refreshMe() {
    const me = await api("/api/me");
    if (me.status === 200) { S.me = me.data; paintMe(); } else if (me.status === 401) location.replace("/");
  }

  $("signout").addEventListener("click", async () => { await api("/api/auth/logout", {}); location.replace("/"); });

  function loadExample() {
    const ex = S.examples[0];
    if (!ex) return;
    $("focus").value = ex.focus; $("text").value = ex.text;
    $("site").value = (ex.context && ex.context.site) || ""; $("method").value = (ex.context && ex.context.method) || "";
    $("question").value = "";
    countWords(); $("run-btn").focus();
  }
  $("load-example").addEventListener("click", loadExample);
  $("load-example-2").addEventListener("click", loadExample);

  function countWords() {
    const n = ($("text").value.trim().match(/\S+/g) || []).length;
    const max = S.me ? S.me.limits.max_words : 0;
    const hint = $("word-count");
    hint.textContent = n ? n + " / " + max + " words" : "";
    hint.style.color = n > max ? "var(--red)" : "";
  }
  $("text").addEventListener("input", countWords);

  // ------------------------------------------------------------ a run
  $("run-form").addEventListener("submit", (ev) => { ev.preventDefault(); startRun(false); });

  async function startRun(allowGeneral) {
    if (S.busy) return;
    say($("run-msg"), "");
    const body = {
      text: $("text").value, focus: $("focus").value,
      context: { site: $("site").value, method: $("method").value, research_question: $("question").value },
      compare: $("compare").checked, lens: $("market").checked ? "market" : "general", allow_general_model: allowGeneral,
    };
    setBusy(true);
    const r = await api("/api/runs", body);
    if (r.status === 409 && r.data.error === "opencoder_offline") {
      setBusy(false);
      const node = $("run-msg");
      say(node, "The post-trained open-coding model is offline right now. You can come back later, or let the general model write the open codes for this run.");
      node.append(el("button", { class: "btn link", type: "button", text: "Run with the general model", onclick: () => startRun(true) }));
      return refreshMe();
    }
    if (r.status !== 202) { setBusy(false); if (r.status === 401) return location.replace("/"); return say($("run-msg"), r.data.error || "The run could not start."); }
    resetSheet();
    S.runId = r.data.run_id; S.seen = 0;
    listen();
  }

  function setBusy(on) {
    S.busy = on;
    $("run-btn").disabled = on;
    $("run-btn").textContent = on ? "Coding…" : "Code this text";
  }

  function listen() {
    const es = new EventSource("/api/runs/" + S.runId + "/events?from=" + S.seen);
    S.stream = es;
    const on = (name, fn) => es.addEventListener(name, (ev) => { S.seen += 1; fn(JSON.parse(ev.data)); });
    on("start", onStart); on("round.start", () => {}); on("open.start", onOpenStart); on("open.label", onLabel);
    on("open.done", onOpenDone); on("concepts.done", onConcepts); on("axial.done", onAxial);
    on("selective.done", onSelective); on("decode.done", onDecode); on("round.done", onRound);
    on("stage.error", onStageError); on("saved", onSaved); on("done", onDone);
    on("error", (p) => { say($("run-msg"), p.message || "The run stopped."); });
    es.addEventListener("end", () => { es.close(); S.stream = null; setBusy(false); markRail(null); refreshMe(); });
    es.onerror = () => {                       // dropped connection: resume from the last event seen
      if (S.stream !== es) return;
      es.close();
      setTimeout(() => { if (S.busy && S.stream === es) listen(); }, 1500);
    };
  }

  function resetSheet() {
    show($("intro"), false); show($("results"), true);
    S.turns = new Map(); S.spans = new Map(); S.graph = null; S.selectedCat = null; S.chat = [];
    for (const id of ["page", "concepts", "board", "rels", "storyline", "propositions", "strata", "gates", "ledger", "notes", "chat", "scorecard", "trace"]) clear($(id));
    $("core").textContent = "";
    show($("map"), false); show(clear($("map-panel")), false); S.mapList = false; S.mapSel = null; if (MAP) MAP.clear();
    for (const id of ["sec-concepts", "sec-axial", "sec-selective", "sec-decode", "sec-checks", "sec-chat", "scorecard", "trace", "rel-wrap"]) show($(id), false);
    document.querySelectorAll(".stage-error").forEach((n) => n.remove());
    document.querySelectorAll("#rail li").forEach((li) => { li.className = ""; });
  }

  function markRail(active, failed) {
    let before = true;
    document.querySelectorAll("#rail li").forEach((li) => {
      const st = li.dataset.stage;
      if (failed && st === failed) { li.className = "failed"; return; }
      if (li.classList.contains("failed")) return;
      if (st === active) { li.className = "active"; before = false; }
      else if (active === null) li.className = li.classList.contains("active") || li.classList.contains("done") ? "done" : li.className;
      else li.className = before ? "done" : "";
    });
  }

  // ---- level I: the coded page
  function onStart(p) {
    for (const t of p.turns) S.turns.set(t.i, t);
    const page = clear($("page"));
    for (const t of p.turns) page.append(turnRow(t, true));
    const m = p.models, by = clear($("open-by"));
    by.append("Written by ", el("b", { text: m.open_coding }),
              m.open_coding_is_post_trained ? ", the post-trained open-coding model. One code per statement of one to three sentences, checked by program."
                                           : ", a general model (the post-trained model is not in this run).");
    clear($("concepts-by")).append("Abstractions made on the researcher's side by ", el("b", { text: m.reasoner }), ".");
    markRail("open");
  }

  function turnRow(t, pending) {
    const row = el("div", { class: "turn" + (t.coded ? "" : " asked"), id: "turn-" + t.i });
    row.append(el("span", { class: "who" }, t.role || "—", el("i", { text: "turn " + t.i })),
               el("div", { class: "said", text: t.text }),
               el("div", { class: "margin" }, t.coded && pending ? el("span", { class: "pending", text: "reading" }) : null));
    return row;
  }

  function onOpenStart(p) {
    if (p.dropped) $("open-by").append(" " + p.dropped + " further statements were left uncoded (demo limit).");
  }

  function onLabel(p) { addSpan(p.turn_id, { key: "k" + p.i, target: p.target, label: p.label, checks: p.checks || {}, base: p.base }, true); }

  function addSpan(turnId, item, animate) {
    if (!S.turns.has(turnId)) return;
    if (!S.spans.has(turnId)) S.spans.set(turnId, []);
    const list = S.spans.get(turnId), text = S.turns.get(turnId).text;
    item.at = item.target ? text.indexOf(item.target) : -1;
    list.push(item);
    list.sort((a, b) => (a.at < 0 ? 1e9 : a.at) - (b.at < 0 ? 1e9 : b.at));
    paintTurn(turnId, animate ? item.key : null);
  }

  function paintTurn(turnId, freshKey) {
    const row = $("turn-" + turnId), t = S.turns.get(turnId), list = S.spans.get(turnId) || [];
    const said = clear(row.querySelector(".said")), margin = clear(row.querySelector(".margin"));
    let pos = 0;
    for (const it of list) {                       // highlight each coded span where it sits in the turn
      if (it.at < 0 || it.at < pos) continue;
      if (it.at > pos) said.append(t.text.slice(pos, it.at));
      const mark = el("mark", { "data-k": it.key, text: it.target });
      if (it.key !== freshKey) { mark.style.animation = "none"; mark.style.backgroundSize = "100% 100%"; }
      said.append(mark);
      pos = it.at + it.target.length;
    }
    if (pos < t.text.length) said.append(t.text.slice(pos));
    for (const it of list) {
      const ok = it.checks.format_ok !== false && it.label;
      const code = el("div", { class: "code" + (ok ? "" : " failed"), "data-k": it.key });
      if (it.key !== freshKey) code.style.animation = "none";
      const label = el("span", { class: "label" });
      if (ok) flagged(label, it.label, it.checks.outside_words); else label.textContent = "no well-formed code returned";
      code.append(label);
      if (ok && it.checks.verbatim_ok === false) code.append(el("span", { class: "flag", text: "quote not verbatim" }));
      if (it.base) {
        const b = el("div", { class: "base" + (it.base.label ? "" : " none") });
        if (it.base.label) flagged(b, it.base.label, (it.base.checks || {}).outside_words); else b.append("no well-formed code");
        code.append(b);
      }
      const lit = (on) => { row.querySelectorAll('[data-k="' + it.key + '"]').forEach((n) => n.classList.toggle("lit", on)); };
      code.addEventListener("mouseenter", () => lit(true)); code.addEventListener("mouseleave", () => lit(false));
      margin.append(code);
    }
    said.querySelectorAll("mark").forEach((mk) => {
      const k = mk.dataset.k;
      mk.addEventListener("mouseenter", () => row.querySelectorAll('[data-k="' + k + '"]').forEach((n) => n.classList.add("lit")));
      mk.addEventListener("mouseleave", () => row.querySelectorAll('[data-k="' + k + '"]').forEach((n) => n.classList.remove("lit")));
    });
  }

  function flagged(node, text, outside) {          // underline, in red, every word the speaker never used
    const bad = new Set((outside || []).map((w) => w.toLowerCase()));
    if (!bad.size) { node.append(text); return; }
    for (const part of text.split(/([A-Za-z']+)/)) {
      if (bad.has(part.toLowerCase())) node.append(el("span", { class: "outside", title: "not in what was said", text: part }));
      else if (part) node.append(part);
    }
  }

  function onOpenDone(p) {
    document.querySelectorAll(".margin .pending").forEach((n) => n.remove());
    if (p.items) p.items.forEach((it, i) => { if (it.turn_id !== null) addSpan(it.turn_id, { key: "d" + i, target: it.evidence, label: it.label, checks: it.checks || {} }, false); });
    paintScorecard(p);
    markRail("concepts");
    show($("sec-concepts"), true);
    clear($("concepts")).append(el("span", { class: "fine", text: "Abstracting " + (p.labels || 0) + " labels into concepts…" }));
  }

  function paintScorecard(info) {
    const box = clear($("scorecard"));
    const col = (title, card, cls) => {
      if (!card) return null;
      const stats = el("div", { class: "stats" },
        el("div", { class: "stat" }, el("b", { text: String(card.n) }), el("span", { text: "statements coded" })),
        el("div", { class: "stat" + (card.verbatim_ok < 1 ? " bad" : "") }, el("b", { text: pct(card.verbatim_ok) }), el("span", { text: "quote copied verbatim" })),
        el("div", { class: "stat" + (card.outside_word_labels > 0 ? " bad" : "") }, el("b", { text: pct(card.outside_word_labels) }), el("span", { text: "labels with a word nobody said" })));
      if (card.markup) stats.append(el("div", { class: "stat bad" }, el("b", { text: pct(card.markup) }), el("span", { text: "labels wrapped in markup" })));
      return el("div", { class: "score-col " + cls }, el("h3", { text: title }), stats);
    };
    box.append(col(info.coder + (info.post_trained ? " · post-trained" : " · general model"), info.scorecard, "main") || "");
    if (info.base) box.append(col(info.base.model + " · untrained base, same prompt", info.base.scorecard, "base"));
    show(box, Boolean(info.scorecard));
  }

  // ---- levels II-IV
  function onConcepts(p) {
    const box = clear($("concepts"));
    show($("sec-concepts"), true);
    for (const c of p.concepts) box.append(el("span", { class: "chip" }, c.concept, el("small", { text: String((c.label_ids || []).length) })));
    if (!p.concepts.length) box.append(el("span", { class: "fine", text: "No concepts came back." }));
    markRail("axial");
  }

  function onAxial(p) {
    show($("sec-axial"), true);
    const board = clear($("board")), known = new Set(SLOTS.map((s) => s[0]));
    const slots = SLOTS.concat(p.categories.some((c) => !known.has(c.c6_slot)) ? [["?", "Unplaced"]] : []);
    for (const [code, name] of slots) {
      const cats = p.categories.filter((c) => (known.has(c.c6_slot) ? c.c6_slot : "?") === code);
      const card = el("div", { class: "slot" + (cats.length ? "" : " empty") }, el("h3", {}, el("b", { text: code }), name));
      for (const c of cats) {
        card.append(el("button", { class: "cat", type: "button", onclick: (ev) => selectCat(c, ev.currentTarget) }, c.name,
                       el("small", { text: c.concepts.length + " concept" + (c.concepts.length === 1 ? "" : "s") })));
      }
      board.append(card);
    }
    const rels = clear($("rels"));
    for (const r of p.relations) rels.append(el("li", {}, r.from, el("span", { class: "t", text: "— " + r.type + " →" }), r.to));
    $("rel-count").textContent = p.relations.length;
    show($("rel-wrap"), p.relations.length > 0);
    markRail("selective");
  }

  function selectCat(cat, btn) {
    document.querySelectorAll(".cat.on").forEach((n) => n.classList.remove("on"));
    btn.classList.add("on");
    const box = clear($("trace"));
    show(box, true);
    box.append(el("h3", { text: cat.name }));
    const g = S.graph;
    if (!g) { box.append(el("p", { class: "fine", text: cat.concepts.join(" · ") + ". Quotes appear here when the run has finished." })); return; }
    const byName = new Map(g.concepts.map((c) => [c.concept, c]));
    for (const cn of cat.concepts) {
      const c = byName.get(cn);
      box.append(el("p", { class: "concept", text: cn }));
      const ids = (c && c.label_ids) || [];
      if (!ids.length) box.append(el("p", { class: "fine", text: "No labels under this concept." }));
      for (const i of ids.slice(0, 6)) {
        const l = g.labels[i];
        if (!l) continue;
        box.append(el("blockquote", {}, el("i", { text: l.label }), "“" + l.evidence + "”",
                      el("span", { text: (l.role ? l.role + ", " : "") + "turn " + l.turn_id })));
      }
    }
  }

  function onSelective(p) {
    show($("sec-selective"), true);
    $("core").textContent = p.core_category.name || "No core category came back.";
    paintTheory(p.theory);
    markRail("decode");
  }
  function paintTheory(theory) {
    const st = clear($("storyline"));
    for (const s of theory.storyline || []) st.append(el("p", { class: /^\(from decoding\)|^（解码回馈）/.test(s) ? "fed" : "", text: s }));
    const pr = clear($("propositions"));
    for (const s of theory.propositions || []) pr.append(el("li", { text: s }));
  }

  // ---- decoding and checks
  function onDecode(p) {
    const d = p.decode || {}, box = clear($("strata"));
    show($("sec-decode"), Object.keys(d).length > 0);
    for (const [key, name] of LAYERS) if (d[key]) box.append(el("div", { class: "layer" }, el("h3", { text: name }), el("p", { text: d[key] })));
    if (d.counter_example) box.append(el("div", { class: "layer counter" }, el("h3", { text: "Counter-example" }), el("p", { text: d.counter_example })));
    markRail("checks");
  }

  function onRound(p) {
    show($("sec-checks"), true);
    const box = clear($("gates"));
    for (let i = 1; i <= 9; i++) {
      const fail = (p.failed || []).some((f) => f.indexOf("G" + i + " ") === 0);
      box.append(el("span", { class: "gate-stamp" + (fail ? " fail" : ""), text: "G" + i + (fail ? " ✗" : " ✓") }));
    }
    if (p.failed && p.failed.length) {
      const ul = el("ul", { class: "gate-fails" });
      for (const f of p.failed) ul.append(el("li", { text: f }));
      box.after(ul);
    }
  }

  function onStageError(p) {
    const sec = { open: "sec-open", concepts: "sec-concepts", axial: "sec-axial", selective: "sec-selective", decode: "sec-decode" }[p.stage];
    if (!sec) return;
    show($(sec), true);
    $(sec).querySelector(".sec-head").after(el("p", { class: "stage-error", text: "This step returned nothing usable (" + p.error + ")." }));
    markRail(null, p.stage);
  }

  function onSaved(p) {
    paintLedger(p.rubric, p.reflexive);
    loadGraph(p.run_id, false);
    show($("sec-chat"), true);
  }
  function onDone(p) { if (p.status === "failed") say($("run-msg"), "No open codes came back, so the run stopped. " + (p.reason || "")); }

  function paintLedger(r, reflexive) {
    document.querySelectorAll(".gate-fails").forEach((n) => { if (!(r.gates_failed || []).length) n.remove(); });
    const box = clear($("ledger"));
    const row = (name, value, cls) => box.append(el("div", { class: "entry" + (cls || "") }, el("span", { text: name }), el("b", { text: String(value) })));
    const parts = r.score_parts || {};
    row("Compression — labels : concepts : categories : core", r.compression);
    row("Paradigm slots covered", Math.round(r.paradigm_completeness * 6) + " / 6");
    row("Categories connected to the core", pct(r.reachability));
    row("Concepts absorbed by a category", pct(r.fidelity_T1T2));
    row("Labels absorbed by a concept", pct(parts.absorption));
    row("Labels left without a concept", r.orphan_labels);
    row("Concept specificity (0–1)", parts.specificity);
    row("Relations below 0.6 confidence", r.low_confidence_relations);
    row("Decoding lenses covered", r.decode_lenses_covered);
    row("Quotes in the decoding not found in the text", (r.decode_unsupported_quotes || []).length);
    row("Score — .25 fidelity + .20 reach + .20 paradigm + .20 specificity + .15 absorption", (r.score || 0).toFixed(3), " score");
    const notes = clear($("notes"));
    if (reflexive) {
      const n = el("div", {}, el("h3", { text: "Limits of this reading" }));
      for (const k of ["boundary", "position", "uncertainty"]) for (const s of reflexive[k] || []) n.append(el("p", { text: s }));
      notes.append(n);
    }
    const tel = r.telemetry || {};
    const t = el("div", { class: "muted" }, el("h3", { text: "Recorded, not used" }));
    t.append(el("p", { text: "A model's ratings of its own output are logged as telemetry and never rank or pass a run." + (tel.decode_self_score ? " Self-rating of the decoding: " + Object.entries(tel.decode_self_score).map((kv) => kv[0].replace(/_/g, " ") + " " + kv[1]).join(", ") + "." : "") }));
    notes.append(t);
    if ((r.failure_modes || []).length) notes.append(el("div", {}, el("h3", { text: "Flags" }), el("p", { text: r.failure_modes.join(", ") })));
  }

  async function loadGraph(runId, repaint) {
    const r = await api("/api/runs/" + runId);
    if (r.status === 401) return location.replace("/");
    if (r.status !== 200) {
      if (!repaint) return;
      if (r.status === 404) {                        // asked for by a click: say why nothing opened
        const hours = S.me ? S.me.limits.keep_hours : 24;
        clear($("reopen")).append("That coding is no longer stored: codings are deleted after " + hours + " hours. Run it again to get it back.");
      } else say($("run-msg"), r.data.error || "The coding could not be opened. Try again in a moment.");
      return;
    }
    S.graph = r.data.graph; S.runId = runId;
    if (repaint) {
      paintAll(r.data.graph, r.data.rubric);
      if (!$("focus").value) $("focus").value = r.data.graph.focus || "";
    } else paintTheory(S.graph.theory);
    paintMap(S.graph);
  }

  // ------------------------------------------------------------ the coding as a map (map.js draws, this explains)
  function paintMap(g) {
    const ok = Boolean(window.CodingMap) && (g.categories || []).length > 0;
    show($("map"), ok);
    if (!ok) return;
    if (!MAP) {
      MAP = window.CodingMap.mount($("map-canvas"), { onSelect: (sel) => { S.mapSel = sel; if (sel) S.mapList = false; paintMapPanel(S.graph, sel); } });
      $("map-in").addEventListener("click", () => MAP.zoom(1.25));
      $("map-out").addEventListener("click", () => MAP.zoom(0.8));
      $("map-fit").addEventListener("click", () => MAP.fit());
      $("map-list").addEventListener("click", () => {          // the same content as text, for keyboards and screen readers
        const open = S.mapList && !S.mapSel;
        S.mapList = !open;
        MAP.select(null, null);
      });
    }
    S.mapList = false; S.mapSel = null;
    MAP.setGraph(g);
    clear($("map-legend")).append(...mapLegend(g));
    paintMapPanel(g, null);
  }

  const mapWide = () => window.matchMedia("(min-width: 821px)").matches;   // wide: the panel is a drawer over the plate
  function mapLegend(g) {
    const cats = g.categories || [], rows = [];
    for (const [code, name] of SLOTS) {
      rows.push(el("li", {}, el("span", { class: "sw sw-" + code }), code + " · " + name, el("small", { text: String(cats.filter((c) => c.c6_slot === code).length) })));
    }
    rows.push(el("li", { class: "brk", "aria-hidden": "true" }),
              el("li", {}, el("span", { class: "sw dot" }), "a dot is a concept"),
              el("li", {}, el("span", { class: "sw pen" }), "small dots above it: its open codes"),
              el("li", {}, el("span", { class: "sw line" }), "arrow: a relation, named on the line"),
              el("li", {}, el("span", { class: "sw line red" }), "red line: taken up by the core"));
    if ((g.core_category || {}).name) rows.push(el("li", {}, el("span", { class: "sw box" }), "dashed box: left outside the core"));
    return rows;
  }

  const slotName = (code) => { const f = SLOTS.find((x) => x[0] === code); return f ? f[1] : "Unplaced"; };
  const mapGo = (kind, key, text, cls) => el("button", { class: "mp-go" + (cls ? " " + cls : ""), type: "button", text: text, onclick: () => MAP.select(kind, key) });
  const mapList = (items) => { const ul = el("ul", { class: "mp-list" }); items.forEach((it) => ul.append(el.apply(null, ["li", {}].concat(it)))); return ul; };
  const quoted = (l) => [el("span", { class: "mp-q" }, "“" + l.evidence + "”",
                            l.turn_id === null || l.turn_id === undefined ? null : el("a", { class: "mp-src", href: "#turn-" + l.turn_id, text: (l.role ? l.role + ", " : "") + "turn " + l.turn_id }))];

  function paintMapPanel(g, sel) {
    const box = clear($("map-panel")), wide = mapWide();
    $("map-list").setAttribute("aria-expanded", String(Boolean(g && !sel && S.mapList)));
    if (!g || (!sel && wide && !S.mapList)) { show(box, false); return; }
    show(box, true);
    const cats = g.categories || [], concepts = g.concepts || [], labels = g.labels || [], core = g.core_category || {};
    const taken = new Set(core.mapping || []), rels = (g.relations || []).filter((r) => r.type !== "abstracts_to");
    const overview = () => { S.mapList = true; MAP.select(null, null); };
    const back = () => el("p", { class: "mp-h" }, el("button", { class: "mp-go", type: "button", text: "← The whole map as a list", onclick: overview }));
    if (wide) box.append(el("button", { class: "mp-close", type: "button", "aria-label": "Close", text: "×", onclick: () => { S.mapList = false; MAP.select(null, null); } }));
    if (!sel) {
      box.append(el("p", { class: "mp-kick", text: "The map as a list" }),
                 el("p", { text: labels.length + " open codes → " + concepts.length + " concepts → " + cats.length + " categories" + (core.name ? " → one core category. " : ". ") +
                                 rels.length + " relation" + (rels.length === 1 ? "" : "s") + " between categories." }));
      if (core.name) box.append(el("p", { class: "mp-h", text: "Core category" }), mapList([[mapGo("core", "core", core.name)]]));
      box.append(el("p", { class: "mp-h", text: "Categories" }),
                 mapList(cats.map((c) => [el("span", { class: "mp-t slot", text: c.c6_slot || "?" }), mapGo("category", c.name, c.name)])),
                 el("p", { class: "fine", text: wide ? "Select anything on the map or in this list. Drag to rearrange the map. Zoom with the buttons, a pinch, or Ctrl + scroll."
                                               : "Select anything on the map or in this list. Zoom in with +, then drag the map with a finger; Fit gives the page its scrolling back." }));
      return;
    }
    if (sel.kind === "core") {
      const inn = cats.filter((c) => taken.has(c.name)), out = cats.filter((c) => !taken.has(c.name));
      box.append(el("p", { class: "mp-kick", text: "Core category" }), el("p", { class: "mp-name core", text: core.name || "" }),
                 el("p", { class: "fine", text: "It takes up " + inn.length + " of " + cats.length + " categories." }));
      if (inn.length) box.append(el("p", { class: "mp-h", text: "Taken up" }), mapList(inn.map((c) => [el("span", { class: "mp-t slot", text: c.c6_slot || "?" }), mapGo("category", c.name, c.name)])));
      if (out.length) box.append(el("p", { class: "mp-h", text: "Left outside" }), mapList(out.map((c) => [el("span", { class: "mp-t slot", text: c.c6_slot || "?" }), mapGo("category", c.name, c.name)])));
    } else if (sel.kind === "category") {
      const c = cats.find((x) => x.name === sel.key) || { name: sel.key, concepts: [] };
      const mine = rels.filter((r) => r.from === c.name || r.to === c.name);
      box.append(el("p", { class: "mp-kick" }, el("span", { class: "sw sw-" + (c.c6_slot || "x") }), "Category · " + (c.c6_slot || "?") + " " + slotName(c.c6_slot)),
                 el("p", { class: "mp-name", text: c.name }));
      if (core.name) box.append(el("p", { class: "fine", text: taken.has(c.name) ? "Taken up by the core category." : "Left outside the core category." }));
      box.append(el("p", { class: "mp-h", text: "Concepts (" + (c.concepts || []).length + ")" }), mapList((c.concepts || []).map((cn) => [mapGo("concept", cn, cn)])));
      if (mine.length) {
        box.append(el("p", { class: "mp-h", text: "Relations (" + mine.length + ")" }),
                   mapList(mine.map((r) => {
                     const outgoing = r.from === c.name, other = outgoing ? r.to : r.from;
                     return [el("span", { class: "mp-t", text: outgoing ? r.type + " →" : "← " + r.type }), mapGo("category", other, other),
                             r.evidence ? el("span", { class: "mp-q", text: "“" + r.evidence + "”" }) : null];
                   })));
      }
    } else if (sel.kind === "concept") {
      const c = concepts.find((x) => x.concept === sel.key) || { concept: sel.key }, parents = cats.filter((x) => (x.concepts || []).includes(sel.key));
      const ids = labels.map((l, i) => (l.concept === sel.key ? i : -1)).filter((i) => i >= 0), attrs = Object.entries(c.attributes || {}).filter((kv) => kv[1]);
      box.append(el("p", { class: "mp-kick" }, el("span", { class: "sw dot sw-" + ((parents[0] || {}).c6_slot || "x") }), "Concept · " + ids.length + " open code" + (ids.length === 1 ? "" : "s")),
                 el("p", { class: "mp-name", text: c.concept }));
      if (parents.length) box.append(el.apply(null, ["p", { class: "fine" }, "Under "].concat(parents.map((x, i) => [i ? ", " : null, mapGo("category", x.name, x.name)]).flat())));
      else box.append(el("p", { class: "fine", text: "No category took this concept in." }));
      if (attrs.length) {
        const table = el("table", { class: "mp-attr" });
        attrs.forEach((kv) => table.append(el("tr", {}, el("td", { text: kv[0].replace(/_/g, " ") }), el("td", { text: String(kv[1]) }))));
        box.append(table);
      }
      box.append(el("p", { class: "mp-h", text: "Open codes behind it" }), mapList(ids.map((i) => [mapGo("code", i, labels[i].label, "code")].concat(quoted(labels[i])))));
    } else if (sel.kind === "code") {
      const l = labels[sel.key];
      if (!l) return;
      box.append(el("p", { class: "mp-kick" }, el("span", { class: "sw pen" }), "Open code"), el("p", { class: "mp-name code", text: l.label }),
                 el.apply(null, ["p", {}].concat(quoted(l))));
      if (l.concept) box.append(el("p", { class: "fine" }, "Under the concept ", mapGo("concept", l.concept, l.concept)));
    }
    box.append(back());
    box.scrollTop = 0;
    if (wide) MAP.reveal(box.offsetWidth);
  }

  function paintAll(g, rubric) {                   // a finished coding, drawn in one go (used after a run started in chat)
    const keep = S.chat;
    resetSheet(); S.chat = keep; S.graph = g;
    onStart({ turns: g.excerpts.map((e) => ({ i: e.i, role: e.role, text: e.text, coded: true })), models: g.models });
    g.labels.forEach((l, i) => { if (l.turn_id !== null) addSpan(l.turn_id, { key: "g" + i, target: l.target || l.evidence, label: l.label, checks: l.checks || {}, base: l.base }, false); });
    document.querySelectorAll(".margin .pending").forEach((n) => n.remove());
    paintScorecard(g.open_coding || {});
    onConcepts({ concepts: g.concepts }); onAxial({ categories: g.categories, relations: g.relations });
    onSelective({ core_category: g.core_category, theory: g.theory }); onDecode({ decode: g.decode });
    onRound({ failed: rubric.gates_failed }); paintLedger(rubric, g.reflexive);
    show($("sec-chat"), true); markRail(null);
    document.querySelectorAll("#rail li").forEach((li) => { li.className = "done"; });
  }

  // ------------------------------------------------------------ ask the agent
  function ask(q) { $("chat-input").value = q; $("chat-form").requestSubmit(); }
  $("chat-input").addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); $("chat-form").requestSubmit(); } });
  $("chat-input").addEventListener("input", (ev) => { ev.target.style.height = "auto"; ev.target.style.height = Math.min(160, ev.target.scrollHeight) + "px"; });

  $("chat-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const q = $("chat-input").value.trim();
    if (!q || $("chat-btn").disabled) return;
    $("chat-input").value = ""; $("chat-input").style.height = "auto";
    $("chat-btn").disabled = true;
    S.chat.push({ role: "user", content: q });
    const tools = el("div", { class: "tools" }), body = el("div", {});
    const answer = el("div", { class: "turn-a working" }, tools, body);
    $("chat").append(el("div", { class: "turn-q", text: q }), answer);
    answer.scrollIntoView({ block: "nearest", behavior: "smooth" });
    let text = "";
    await stream("/api/chat", { run_id: S.runId, messages: S.chat }, (kind, p) => {
      if (kind === "tool.call") tools.append(el("div", { text: p.name + "(" + Object.entries(p.arguments || {}).map((kv) => kv[0] + ": " + JSON.stringify(kv[1])).join(", ") + ")" }));
      else if (kind === "run.ready") loadGraph(p.run_id, true);
      else if (kind === "answer") { text = p.text; markdown(clear(body), text); }
      else if (kind === "error" || kind === "http") { body.append(el("p", { class: "stage-error", text: p.message || p.error || "The answer stopped." })); }
    });
    answer.classList.remove("working");
    if (text) S.chat.push({ role: "assistant", content: text }); else S.chat.pop();
    $("chat-btn").disabled = false;
    refreshMe();
  });

  async function stream(path, body, onEvent) {     // POST, then read the response as server-sent events
    let res;
    try {
      res = await fetch(path, { method: "POST", credentials: "same-origin", body: JSON.stringify(body),
                                headers: { "Content-Type": "application/json", "X-Requested-With": "demo" } });
    } catch (e) { return onEvent("http", { error: "The server could not be reached." }); }
    if (!res.ok || !res.body) {
      let data = {};
      try { data = await res.json(); } catch (e) { /* no body */ }
      return onEvent("http", { error: data.error || "The request failed." });
    }
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      buf += dec.decode(chunk.value, { stream: true });
      let cut;
      while ((cut = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, cut); buf = buf.slice(cut + 2);
        let kind = "", data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event: ")) kind = line.slice(7);
          else if (line.startsWith("data: ")) data += line.slice(6);
        }
        if (kind && kind !== "end") { try { onEvent(kind, JSON.parse(data)); } catch (e) { /* skip a malformed event */ } }
      }
    }
  }

  function markdown(node, text) {                  // paragraphs, lists, **bold**, *italic*, `code`: built as nodes, never as HTML
    const inline = (parent, s) => {
      for (const part of s.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*)/)) {
        if (!part) continue;
        if (part.startsWith("**")) parent.append(el("b", { text: part.slice(2, -2) }));
        else if (part.startsWith("`")) parent.append(el("code", { text: part.slice(1, -1) }));
        else if (part.startsWith("*") && part.length > 2) parent.append(el("i", { text: part.slice(1, -1) }));
        else parent.append(part);
      }
    };
    let list = null;
    for (const raw of text.split("\n")) {
      const line = raw.trim();
      if (!line) { list = null; continue; }
      const item = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
      const head = line.match(/^#{1,6}\s+(.*)$/);
      if (item) { if (!list) { list = el("ul", {}); node.append(list); } const li = el("li", {}); inline(li, item[1]); list.append(li); continue; }
      list = null;
      const p = el("p", {});
      if (head) p.append(el("b", { text: head[1].replace(/\*\*/g, "") })); else inline(p, line);
      node.append(p);
    }
  }

  boot();
})();
