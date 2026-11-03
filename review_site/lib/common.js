// 共享逻辑：口令校验、私有 Blob 读写、答卷状态。
// 存储：Vercel Blob 私有库（access: 'private'），读写都要带 BLOB_READ_WRITE_TOKEN，外部无法凭 URL 读取。
//   config/pairs.json                   —— 偏好对（含我们的判断 claim，只经 API 下发）
//   answers/<expert_id>/<pair_id>.json  —— 每位专家每一对一份答卷
// 专家名单（含口令）在环境变量 EXPERTS_JSON，管理口令在 ADMIN_TOKEN。
import { get, put, list } from '@vercel/blob';
import { timingSafeEqual } from 'node:crypto';

const ACCESS = 'private';
export const PAIRS_PATH = 'config/pairs.json';
export const BLIND_CHOICES = ['A', 'B', 'neither'];
export const VERDICTS = ['对', '不对', '部分对'];
export const TAGS = ['较优不忠于作者', '较劣不像自然写法', '两边意思差不多', '两边都没读到', '其他'];  // Z3 起一对只差一处，「别处被改坏」换成「两边意思差不多」

export class HttpError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

const now = () => new Date().toISOString();

function safeEq(a, b) {
  const x = Buffer.from(String(a)), y = Buffer.from(String(b));
  return x.length === y.length && timingSafeEqual(x, y);
}

let expertsCache = null;
function experts() {
  if (!expertsCache) {
    const raw = process.env.EXPERTS_JSON;
    if (!raw) throw new HttpError(500, '服务端未配置专家名单');
    expertsCache = JSON.parse(raw);
  }
  return expertsCache;
}

function tokenFrom(req) {
  return req.headers['x-review-token'] || (req.query && req.query.k) || (req.body && req.body.k) || '';
}

export function requireExpert(req) {
  const t = tokenFrom(req);
  const e = t ? experts().find(x => safeEq(x.token, t)) : null;
  if (!e) throw new HttpError(403, '链接无效');
  return e;
}

export function requireAdmin(req) {
  const t = req.headers['x-admin-token'] || (req.query && req.query.admin) || '';
  const want = process.env.ADMIN_TOKEN;
  if (!want || !t || !safeEq(want, t)) throw new HttpError(403, 'forbidden');
}

export function expertsPublic() {
  return experts().map(e => ({ id: e.id, name: e.name, n: e.queue.length }));
}
export function expertQueue(id) {
  const e = experts().find(x => x.id === id);
  return e ? e.queue : [];
}

export async function readJSON(pathname) {
  const r = await get(pathname, { access: ACCESS, useCache: false });
  if (!r || r.statusCode !== 200) return null;
  const text = await new Response(r.stream).text();
  return { data: JSON.parse(text), etag: r.blob.etag };
}

// etag 给定：条件写（被别人抢先改过就 409）；etag 为空：只许新建（已存在就 409）。
export async function writeJSON(pathname, data, etag) {
  const opts = { access: ACCESS, contentType: 'application/json; charset=utf-8', addRandomSuffix: false };
  if (etag) opts.ifMatch = etag;
  try {
    return await put(pathname, JSON.stringify(data, null, 1), opts);
  } catch (err) {
    const name = err && err.constructor && err.constructor.name;
    if (name === 'BlobPreconditionFailedError' || /already exists|precondition/i.test(String(err && err.message))) {
      throw new HttpError(409, '这份答卷刚被另一处改过，请刷新页面');
    }
    throw err;
  }
}

let pairsCache = null, pairsAt = 0;
export async function loadPairs() {
  if (pairsCache && Date.now() - pairsAt < 60_000) return pairsCache;
  const r = await readJSON(PAIRS_PATH);
  if (!r) throw new HttpError(500, '服务端没有偏好对');
  const map = new Map(r.data.pairs.map(p => [p.pair_id, p]));
  pairsCache = map; pairsAt = Date.now();
  return map;
}

export async function pairFor(expert, pairId) {
  if (!pairId || !expert.queue.includes(pairId)) throw new HttpError(404, '没有这一对');
  const p = (await loadPairs()).get(pairId);
  if (!p) throw new HttpError(404, '没有这一对');
  return p;
}

// 盲选之前下发的字段：白名单。层级（level）、我们的判断（claim）、原编号、单元号、是否校准对都是模型一侧的信息，不在其中。
export function shownPair(p) {
  const pick = (o, keys) => Object.fromEntries(keys.filter(k => o[k] != null).map(k => [k, o[k]]));
  return {
    pair_id: p.pair_id,
    background: p.background, background_zh: p.background_zh || null,
    quotes: (p.quotes || []).map(q => pick(q, ['n', 'text', 'kind', 'note', 'zh', 'note_zh'])),
    diffs: (p.diffs || []).map(d => pick(d, ['section', 'A', 'B', 'A_zh', 'B_zh'])),
    // Z3：相关的那条链与折叠的其余编码（两侧相同，比较处那一行带 A/B）
    chain: p.chain ? p.chain.map(r => pick(r, ['sec', 'label', 'text', 'zh', 'cmp', 'A', 'B', 'A_zh', 'B_zh'])) : undefined,
    more: p.more ? p.more.map(r => pick(r, ['sec', 'label', 'text', 'zh'])) : undefined,
  };
}

// 盲选之后才下发：我们的判断（含中文）与层级。
export function revealOf(p) {
  const c = p.claim || {};
  return { claim: { better: c.better, text: c.text, text_zh: c.text_zh || null }, level: p.level || null };
}

export const answerPath = (expertId, pairId) => `answers/${expertId}/${pairId}.json`;

export function blankAnswer(expertId, pairId) {
  return {
    pair_id: pairId, expert_id: expertId,
    blind: null, verdict: null, reason: null, tags: [], skipped: false, skip_note: null,
    t_open: null, t_blind: null, t_claim: null, t_submit: null, user_agent: null,
    blind_history: [],
  };
}

export function statusOf(a) {
  if (!a) return 'new';
  if (a.skipped) return 'skipped';
  if (a.verdict) return 'done';
  if (a.t_claim) return 'claim';
  if (a.blind) return 'blind';
  return 'new';
}

// 读—改—条件写；被并发抢先时重试一次。
export async function mutateAnswer(expert, pairId, req, fn) {
  const path = answerPath(expert.id, pairId);
  for (let attempt = 0; ; attempt++) {
    const cur = await readJSON(path);
    const a = cur ? cur.data : blankAnswer(expert.id, pairId);
    const changed = fn(a);              // fn 返回 false 表示无需写
    if (changed === false) return a;
    a.user_agent = String(req.headers['user-agent'] || '').slice(0, 300);
    try {
      await writeJSON(path, a, cur && cur.etag);
      return a;
    } catch (e) {
      if (e.status === 409 && attempt === 0) continue;
      throw e;
    }
  }
}

export async function answersOf(expertId) {
  const out = new Map();
  let cursor;
  do {
    const r = await list({ prefix: `answers/${expertId}/`, cursor, limit: 1000 });
    const got = await Promise.all(r.blobs.map(b => readJSON(b.pathname)));
    got.forEach(g => g && out.set(g.data.pair_id, g.data));
    cursor = r.hasMore ? r.cursor : undefined;
  } while (cursor);
  return out;
}

export async function allAnswers() {
  const out = [];
  let cursor;
  do {
    const r = await list({ prefix: 'answers/', cursor, limit: 1000 });
    const got = await Promise.all(r.blobs.map(b => readJSON(b.pathname)));
    got.forEach(g => g && out.push(g.data));
    cursor = r.hasMore ? r.cursor : undefined;
  } while (cursor);
  return out;
}

export function publicAnswer(a) {
  if (!a) return null;
  const { user_agent, blind_history, ...rest } = a;
  return rest;
}

export function stamp() { return now(); }

export function handler(methods, fn) {
  return async (req, res) => {
    res.setHeader('Cache-Control', 'no-store');
    try {
      if (!methods.includes(req.method)) throw new HttpError(405, 'method not allowed');
      const out = await fn(req, res);
      if (!res.headersSent) res.status(200).json(out);
    } catch (e) {
      const status = e.status || 500;
      if (status === 500) console.error(e);
      res.status(status).json({ error: status === 500 ? '服务端出错' : e.message });
    }
  };
}
