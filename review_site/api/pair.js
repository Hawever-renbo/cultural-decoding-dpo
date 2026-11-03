import { handler, requireExpert, pairFor, mutateAnswer, statusOf, publicAnswer, stamp, shownPair, revealOf, readJSON, answerPath } from '../lib/common.js';
import PI_META from '../lib/pi_meta.js';

// 下发一对：背景、引语、差异（含中文）；只按白名单下发，不含我们的判断、层级、原编号、是否为校准对。首次打开记 t_open。
// 2026-11-02：只有 PI 口令另带 pi 字段（轮次、对型、真正较优侧、我们的判断、专家一的盲选／裁决／理由，只读）；其他口令的返回与以前完全一样。
export default handler(['GET'], async (req) => {
  const e = requireExpert(req);
  const id = req.query.id;
  const p = await pairFor(e, id);
  const a = await mutateAnswer(e, id, req, a => {
    if (a.t_open) return false;
    a.t_open = stamp();
  });
  const out = { index: e.queue.indexOf(id), n: e.queue.length, pair: shownPair(p), status: statusOf(a), answer: publicAnswer(a) };
  if (e.id === 'PI') {
    const x = await readJSON(answerPath('X1', id));
    const xa = x ? x.data : null;
    out.pi = { meta: PI_META[id] || null, reveal: revealOf(p),
               x1: xa ? { blind: xa.blind, verdict: xa.verdict, reason: xa.reason, tags: xa.tags || [], skipped: xa.skipped, skip_note: xa.skip_note, t_submit: xa.t_submit } : null };
  }
  return out;
});
