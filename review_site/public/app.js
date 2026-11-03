'use strict';
(function () {
  const TOKEN = new URLSearchParams(location.search).get('k') || '';
  const LEVEL = { open: '一级 · 开放编码', axial: '二级 · 主轴编码', selective: '三级 · 选择性编码' };
  const KIND = { participant: '受访者', block: '整段引文', inline: '正文内引语', fieldnote: '田野笔记' };
  const TAGS = ['较优不忠于作者', '较劣不像自然写法', '两边意思差不多', '两边都没读到', '其他'];
  const TIER = { open: '一级 · 开放码', category: '二级 · 范畴', relation: '二级 · 关系', core: '三级 · 核心范畴', storyline: '三级 · 故事线' };
  const PH = '⟨X⟩';
  const BLIND_TXT = { A: 'A', B: 'B', neither: '两边都不行' };
  const $ = id => document.getElementById(id);

  const S = { me: null, idx: 0, cur: null, blind: null, verdict: null, busy: false };

  // ---------- API ----------
  async function api(method, path, body) {
    const r = await fetch(path, {
      method,
      headers: Object.assign({ 'X-Review-Token': TOKEN }, body ? { 'Content-Type': 'application/json' } : {}),
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
    let data = null;
    try { data = await r.json(); } catch (e) { /* 非 JSON */ }
    if (!r.ok) { const err = new Error((data && data.error) || ('出错了（' + r.status + '）')); err.status = r.status; throw err; }
    return data;
  }

  function fatal(msg) {
    $('loading').hidden = true; $('pair').hidden = true; $('top').hidden = true; $('howto').hidden = true;
    const e = $('err'); e.textContent = msg; e.hidden = false;
  }
  let toastT;
  function toast(msg) {
    const t = $('toast'); t.textContent = msg; t.classList.add('show');
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), 2200);
  }

  // ---------- 文字差异（按汉字 / 英文词切分，LCS 之外的部分加底色） ----------
  function tokenize(s) { return String(s || '').match(/[A-Za-z0-9_\-]+|\s+|[\s\S]/g) || []; }
  function diffMarks(a, b) {
    const x = tokenize(a), y = tokenize(b), n = x.length, m = y.length;
    const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--)
      L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    const ka = new Array(n).fill(false), kb = new Array(m).fill(false);
    let i = 0, j = 0;
    while (i < n && j < m) {
      if (x[i] === y[j]) { ka[i] = kb[j] = true; i++; j++; }
      else if (L[i + 1][j] >= L[i][j + 1]) i++; else j++;
    }
    return [render(x, ka), render(y, kb)];
  }
  function render(toks, keep) {
    const frag = document.createDocumentFragment();
    let buf = '', mode = null;
    const flush = () => {
      if (!buf) return;
      if (mode) frag.appendChild(document.createTextNode(buf));
      else { const mk = document.createElement('mark'); mk.textContent = buf; frag.appendChild(mk); }
      buf = '';
    };
    toks.forEach((t, k) => {
      const kp = keep[k] || /^\s+$/.test(t);
      if (mode !== null && kp !== mode) flush();
      mode = kp; buf += t;
    });
    flush();
    return frag;
  }

  function sectionLabel(s) {
    const m = String(s).match(/^(open code|category|relation)\s*(.*)$/i);
    if (m) return ({ 'open code': '开放码', category: '范畴', relation: '关系' })[m[1].toLowerCase()] + ' ' + m[2];
    return ({ core: '核心范畴', storyline: '故事线' })[s] || s;
  }

  function el(tag, cls, text) { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  // ---------- 渲染一对 ----------
  function renderPair(d) {
    const p = d.pair;
    $('pos').textContent = '第 ' + (d.index + 1) + ' / ' + d.n + ' 对';
    $('background').textContent = p.background || '';
    $('background_zh').textContent = p.background_zh || '';

    const ql = $('quotes'); ql.textContent = '';
    (p.quotes || []).forEach(q => {
      const li = el('li', q.kind === 'fieldnote' ? 'fieldnote' : '');
      li.appendChild(el('span', 'num', q.n + '.'));
      const body = el('div', 'qt');
      if (q.note) {
        body.appendChild(el('div', 'qnote', '（' + q.note + '）'));
        if (q.note_zh) body.appendChild(el('div', 'qnote zh', '（' + q.note_zh + '）'));
      }
      const line = el('div');
      line.appendChild(el('span', 'kind', KIND[q.kind] || q.kind));
      line.appendChild(document.createTextNode(q.text));
      body.appendChild(line);
      if (q.zh) body.appendChild(el('div', 'zh', q.zh));
      li.appendChild(body); ql.appendChild(li);
    });

    const dv = $('diffs'); dv.textContent = '';
    if (p.chain) { dv.className = 'chain'; $('diffhead').textContent = '编码：按开放码 → 范畴 → 关系 → 核心范畴排，两边只在「比较处」不同'; renderChain(dv, p); }
    else { dv.className = 'diffs'; $('diffhead').textContent = '两边不同的地方'; renderDiffs(dv, p); }

    renderPi(d);
    // 状态
    renderState(d);
  }

  // ---------- PI 只读面板（只有 PI 口令的返回带 d.pi；其他人看不到）----------
  function renderPi(d) {
    let box = $('pibox');
    if (!d.pi) { if (box) box.hidden = true; return; }
    if (!box) { box = el('section', 'card pibox'); box.id = 'pibox'; const art = $('pair'); art.insertBefore(box, art.firstChild); }
    box.hidden = false; box.textContent = '';
    const m = d.pi.meta || {}, x = d.pi.x1, c = (d.pi.reveal || {}).claim || {};
    box.appendChild(el('h2', 'label', 'PI 视图 · 专家一的判断（只读）'));
    const rows = [
      ['轮次', m.round || '–'], ['对型', m.type || '–'], ['原编号', m.source_pair_id || '–'],
      ['真正较优', (m.truth || '–') + (m.calibration ? '（校准对：给专家看的揭晓语故意说反）' : '')],
      ['专家一盲选', x ? (x.blind === 'neither' ? '两边都不行' : (x.blind || '–')) + (x.blind && m.truth ? (x.blind === m.truth ? '（选中较优）' : x.blind === 'neither' ? '' : '（选了较劣）') : '') : '–'],
      ['专家一裁决', x ? (x.skipped ? '跳过' : (x.verdict || '未提交')) : '未作答'],
      ['专家一意见', x ? (x.reason || x.skip_note || '（没写）') : '–'],
    ];
    if (x && x.tags && x.tags.length) rows.push(['标签', x.tags.join('、')]);
    const dl = el('dl', 'pimeta');
    rows.forEach(([k, v]) => { dl.appendChild(el('dt', null, k)); dl.appendChild(el('dd', k === '专家一裁决' ? 'piverdict v-' + v : null, v)); });
    box.appendChild(dl);
    const cl = el('details', 'piclaim'); cl.appendChild(el('summary', null, '给专家看的揭晓语（我们的判断）'));
    cl.appendChild(el('p', 'claim-text', c.text || '')); if (c.text_zh) cl.appendChild(el('p', 'claim-text zh', c.text_zh));
    box.appendChild(cl);
  }

  function renderDiffs(dv, p) {
    dv.appendChild(el('div', 'colhead a', 'A')); dv.appendChild(el('div', 'colhead b', 'B'));
    (p.diffs || []).forEach(df => {
      dv.appendChild(el('div', 'sec', sectionLabel(df.section)));
      const [fa, fb] = diffMarks(df.A, df.B);
      const [za, zb] = (df.A_zh || df.B_zh) ? diffMarks(df.A_zh, df.B_zh) : [null, null];
      [['a', 'A', df.A, fa, df.A_zh, za], ['b', 'B', df.B, fb, df.B_zh, zb]].forEach(([c, side, txt, frag, zt, zfrag]) => {
        const cell = el('div', 'cell ' + c);
        cell.appendChild(el('span', 'side', side));
        if (txt && String(txt).trim()) {
          cell.appendChild(frag);
          if (zt && String(zt).trim()) { const z = el('div', 'zh'); z.lang = 'zh-CN'; z.appendChild(zfrag); cell.appendChild(z); }
        } else cell.appendChild(el('span', 'none', '（这一边没有此项）'));
        dv.appendChild(cell);
      });
    });
  }

  // 共用文字：把指到比较处的名字（⟨X⟩）显示成〔比较处〕
  function phText(s) {
    const frag = document.createDocumentFragment();
    String(s || '').split(PH).forEach((part, i) => {
      if (i) frag.appendChild(el('span', 'ph', '〔比较处〕'));
      frag.appendChild(document.createTextNode(part));
    });
    return frag;
  }

  function chainRows(box, rows) {
    let last = null;
    rows.forEach(r => {
      if (r.sec !== last) { box.appendChild(el('div', 'tier', TIER[r.sec] || r.sec)); last = r.sec; }
      if (r.cmp) {
        const w = el('div', 'cmprow');
        const h = el('div', 'rl'); h.appendChild(document.createTextNode(sectionLabel(r.label) + ' ')); h.appendChild(el('span', 'cmptag', '比较处')); w.appendChild(h);
        const g = el('div', 'diffs');
        g.appendChild(el('div', 'colhead a', 'A')); g.appendChild(el('div', 'colhead b', 'B'));
        const [fa, fb] = diffMarks(r.A, r.B);
        const [za, zb] = (r.A_zh || r.B_zh) ? diffMarks(r.A_zh, r.B_zh) : [null, null];
        [['a', 'A', fa, r.A_zh, za], ['b', 'B', fb, r.B_zh, zb]].forEach(([c, side, frag, zt, zfrag]) => {
          const cell = el('div', 'cell ' + c); cell.appendChild(el('span', 'side', side)); cell.appendChild(frag);
          if (zt) { const z = el('div', 'zh'); z.lang = 'zh-CN'; z.appendChild(zfrag); cell.appendChild(z); }
          g.appendChild(cell);
        });
        w.appendChild(g); box.appendChild(w);
      } else {
        const w = el('div', 'row');
        w.appendChild(el('div', 'rl', sectionLabel(r.label)));
        const t = el('div', 'rt'); t.appendChild(phText(r.text));
        if (r.zh) { const z = el('div', 'zh'); z.lang = 'zh-CN'; z.appendChild(phText(r.zh)); t.appendChild(z); }
        w.appendChild(t); box.appendChild(w);
      }
    });
  }

  function renderChain(dv, p) {
    chainRows(dv, p.chain);
    if (p.more && p.more.length) {
      const det = el('details', 'more');
      det.appendChild(el('summary', null, '其余编码（与比较处不在一条链上，两边相同，' + p.more.length + ' 条）'));
      chainRows(det, p.more); dv.appendChild(det);
    }
  }

  function renderState(d) {
    // 状态
    const a = d.answer || {};
    S.blind = a.blind || null; S.verdict = a.verdict || null;
    const st = d.status;
    const lockedBlind = st === 'claim' || st === 'done' || st === 'skipped';
    setChoice('blind', S.blind, lockedBlind);
    $('q1submit').hidden = lockedBlind;
    $('q1hint').textContent = lockedBlind
      ? (st === 'skipped' && !a.blind ? '这一对已跳过。' : '你的盲选：' + (BLIND_TXT[a.blind] || '—') + '（已锁定）')
      : '提交后会显示我们的判断，这一题就不能再改了。';
    $('q1submit').disabled = !S.blind;

    $('q2').hidden = true; $('donebox').hidden = true;
    $('reason').value = a.reason || '';
    buildTags(a.tags || []);
    $('skip').disabled = st === 'done' || st === 'skipped';
    if (st === 'skipped') {
      const box = $('donebox'); box.textContent = '';
      box.appendChild(el('p', null, '已跳过' + (a.skip_note ? '：' + a.skip_note : '。')));
      box.hidden = false;
    }
    $('pair').hidden = false;
    updateNav();
    window.scrollTo({ top: 0 });

    if (st === 'claim' || st === 'done') return loadClaim(st === 'done');
  }

  function setChoice(kind, val, locked) {
    document.querySelectorAll('[data-' + kind + ']').forEach(b => {
      b.setAttribute('aria-checked', String(b.dataset[kind] === val));
      b.disabled = !!locked;
    });
  }

  function buildTags(checked) {
    const fs = $('tags');
    fs.querySelectorAll('label').forEach(l => l.remove());
    TAGS.forEach(t => {
      const lb = el('label'); const cb = el('input'); cb.type = 'checkbox'; cb.value = t; cb.checked = checked.includes(t);
      lb.appendChild(cb); lb.appendChild(document.createTextNode(t)); fs.appendChild(lb);
    });
  }

  async function loadClaim(readOnly) {
    const id = S.cur.pair.pair_id;
    const r = await api('GET', '/api/claim?id=' + encodeURIComponent(id));
    if (!S.cur || S.cur.pair.pair_id !== id) return;
    S.cur.status = r.status; S.cur.answer = r.answer;
    $('claim').textContent = r.claim.text;
    $('claim_zh').textContent = r.claim.text_zh || '';
    $('revealLevel').textContent = r.level ? '这一对的层级（模型一侧的标注）：' + (LEVEL[r.level] || r.level) : '';
    const q2 = $('q2'); q2.hidden = false;
    q2.classList.remove('slide'); void q2.offsetWidth; q2.classList.add('slide');
    const done = readOnly || r.status === 'done';
    setChoice('verdict', S.verdict, done);
    $('reason').disabled = done;
    $('tags').querySelectorAll('input').forEach(i => { i.disabled = done; });
    $('q2submit').hidden = done;
    $('q2hint').textContent = done ? '已提交。' : '';
    $('q2hint').classList.remove('bad');
    $('q1submit').hidden = true; setChoice('blind', S.blind, true);
    $('q1hint').textContent = '你的盲选：' + (BLIND_TXT[S.blind] || '—') + '（已锁定）';
    refreshQ2();
    updateNav();
    if (!done) q2.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function refreshQ2() {
    const need = S.verdict && S.verdict !== '对';
    $('reasonlabel').textContent = need ? '一句话理由（必填）' : '一句话理由（选「不对」或「部分对」时必填）';
    $('q2submit').disabled = !S.verdict || (need && !$('reason').value.trim());
  }

  function updateNav() {
    const me = S.me; if (!me) return;
    const finished = me.queue.filter(q => q.status === 'done' || q.status === 'skipped').length;
    $('bar').style.width = (100 * finished / me.n) + '%';
    $('prev').disabled = S.idx <= 0;
    const st = me.queue[S.idx] && me.queue[S.idx].status;
    const pi = S.me && S.me.expert && S.me.expert.id === 'PI';   // PI 只读浏览：不必先作答就能翻页
    $('next').disabled = !(pi || st === 'done' || st === 'skipped') || S.idx >= me.n - 1;
  }

  async function go(idx) {
    if (S.busy) return;
    S.busy = true;
    try {
      S.idx = idx;
      $('finish').hidden = true;
      const d = await api('GET', '/api/pair?id=' + encodeURIComponent(S.me.queue[idx].pair_id));
      S.cur = d;
      S.me.queue[idx].status = d.status;
      await renderPair(d);
    } catch (e) { toast(e.message); }
    finally { S.busy = false; }
  }

  function markStatus(st) { S.me.queue[S.idx].status = st; S.cur.status = st; }

  async function nextUnanswered() {
    const me = await api('GET', '/api/me'); S.me = me;
    if (me.first_unanswered < 0) return showFinish();
    await go(me.first_unanswered);
  }
  function showFinish() {
    const me = S.me;
    {
      $('pair').hidden = true; $('finish').hidden = false;
      if (me.n === 0) {                          // 队列是空的：新一批还没上
        $('finish').querySelector('h2').textContent = '暂时没有要审的对';
        $('finish').querySelector('p').textContent = '新一批偏好对上线后会通知你，到时用同一个链接打开即可。';
        $('pos').textContent = '暂无'; $('bar').style.width = '0%';
        $('prev').disabled = true; $('next').disabled = true; $('skip').disabled = true;
        return;
      }
      S.idx = me.n; $('pos').textContent = '全部 ' + me.n + ' 对已完成';
      $('bar').style.width = '100%'; $('prev').disabled = false; $('next').disabled = true; $('skip').disabled = true;
    }
  }

  // ---------- 交互 ----------
  async function submitBlind() {
    if (!S.blind || S.busy || $('q1submit').hidden) return;
    S.busy = true;
    try {
      const id = S.cur.pair.pair_id;
      await api('POST', '/api/blind', { pair_id: id, blind: S.blind });
      markStatus('blind');
      S.busy = false;
      await loadClaim(false);
    } catch (e) { toast(e.message); }
    finally { S.busy = false; }
  }

  async function submitVerdict() {
    if (S.busy || $('q2').hidden || $('q2submit').hidden) return;
    const reason = $('reason').value.trim();
    if (!S.verdict) { $('q2hint').textContent = '先选对 / 不对 / 部分对'; $('q2hint').classList.add('bad'); return; }
    if (S.verdict !== '对' && !reason) { $('q2hint').textContent = '请写一句理由'; $('q2hint').classList.add('bad'); $('reason').focus(); return; }
    const tags = [...$('tags').querySelectorAll('input:checked')].map(i => i.value);
    S.busy = true;
    try {
      await api('POST', '/api/verdict', { pair_id: S.cur.pair.pair_id, verdict: S.verdict, reason, tags });
      markStatus('done');
      toast('已保存');
      S.busy = false;
      await nextUnanswered();
    } catch (e) { toast(e.message); }
    finally { S.busy = false; }
  }

  async function doSkip(note) {
    S.busy = true;
    try {
      await api('POST', '/api/skip', { pair_id: S.cur.pair.pair_id, note });
      markStatus('skipped');
      toast('已跳过');
      S.busy = false;
      await nextUnanswered();
    } catch (e) { toast(e.message); }
    finally { S.busy = false; }
  }

  document.addEventListener('click', ev => {
    const b = ev.target.closest('.choice');
    if (!b || b.disabled) return;
    if (b.dataset.blind) { S.blind = b.dataset.blind; setChoice('blind', S.blind, false); $('q1submit').disabled = false; }
    if (b.dataset.verdict) { S.verdict = b.dataset.verdict; setChoice('verdict', S.verdict, false); $('q2hint').classList.remove('bad'); $('q2hint').textContent = ''; refreshQ2(); }
  });
  $('q1submit').addEventListener('click', submitBlind);
  $('q2submit').addEventListener('click', submitVerdict);
  $('reason').addEventListener('input', refreshQ2);
  $('prev').addEventListener('click', () => S.idx > 0 && go(S.idx - 1));
  $('next').addEventListener('click', () => go(S.idx + 1));
  $('skip').addEventListener('click', () => { if (!$('skip').disabled) { $('skipnote').value = ''; $('skipdlg').showModal(); } });
  $('skipdlg').addEventListener('close', () => { if ($('skipdlg').returnValue === 'ok') doSkip($('skipnote').value.trim()); });

  document.addEventListener('keydown', ev => {
    if (ev.metaKey || ev.ctrlKey || ev.altKey || $('skipdlg').open) return;
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement && document.activeElement.tagName) && document.activeElement.type !== 'checkbox';
    if (ev.key === 'Enter') {
      const ae = document.activeElement;
      if (ae && ae.tagName === 'BUTTON' && !ae.classList.contains('choice')) return; // 导航、提交等按钮按原样处理
      if (!$('q2').hidden && !$('q2submit').hidden) { ev.preventDefault(); submitVerdict(); }
      else if (!$('q1submit').hidden && !$('pair').hidden) { ev.preventDefault(); submitBlind(); }
      return;
    }
    if (typing || $('pair').hidden) return;
    const k = ev.key.toLowerCase();
    const q1open = !$('q1submit').hidden;
    const q2open = !$('q2').hidden && !$('q2submit').hidden;
    if (q1open && (k === 'a' || k === 'b' || k === 'x')) {
      const v = { a: 'A', b: 'B', x: 'neither' }[k];
      document.querySelector('[data-blind="' + v + '"]').click();
    } else if (q2open && (k === '1' || k === '2' || k === '3')) {
      document.querySelector('[data-verdict="' + ['对', '不对', '部分对'][+k - 1] + '"]').click();
    }
  });

  // 说明面板：首次访问展开，之后默认收起（只是本机偏好，读写失败也不影响使用）
  (function () {
    let seen = false;
    try { seen = localStorage.getItem('gtpr-howto-seen') === '1'; } catch (e) { /* 忽略 */ }
    $('howto').open = !seen;
    try { localStorage.setItem('gtpr-howto-seen', '1'); } catch (e) { /* 忽略 */ }
  })();

  // 「显示中文」：只是本机偏好，记在 localStorage；读写失败也不影响使用。中文始终放在英文下面，以英文为准。
  (function () {
    const KEY = 'gtpr-show-zh';
    let on = false;
    try { on = localStorage.getItem(KEY) === '1'; } catch (e) { /* 忽略 */ }
    const apply = v => { document.body.classList.toggle('show-zh', v); $('zhtoggle').checked = v; };
    apply(on);
    $('zhtoggle').addEventListener('change', ev => {
      apply(ev.target.checked);
      try { localStorage.setItem(KEY, ev.target.checked ? '1' : '0'); } catch (e) { /* 忽略 */ }
    });
  })();

  // ---------- 启动 ----------
  (async function boot() {
    if (!TOKEN) return fatal('链接不完整：请使用发给你的个人链接打开。');
    try {
      const me = await api('GET', '/api/me');
      S.me = me;
      $('loading').hidden = true; $('top').hidden = false;
      document.title = '编码对评审 · ' + me.expert.name;
      if (me.first_unanswered < 0) showFinish();
      else await go(me.first_unanswered);
    } catch (e) {
      fatal(e.status === 403 ? '链接无效：请确认使用的是发给你的个人链接。' : ('载入失败：' + e.message));
    }
  })();
})();
