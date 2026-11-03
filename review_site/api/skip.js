import { handler, requireExpert, pairFor, mutateAnswer, statusOf, publicAnswer, stamp, HttpError } from '../lib/common.js';

// 「不熟，跳过」：可附一句备注；已提交裁决的对不能再跳过。
export default handler(['POST'], async (req) => {
  const e = requireExpert(req);
  const { pair_id } = req.body || {};
  await pairFor(e, pair_id);
  const note = String((req.body || {}).note || '').trim().slice(0, 1000);
  const a = await mutateAnswer(e, pair_id, req, a => {
    if (a.verdict) throw new HttpError(409, '这一对已经提交过');
    if (a.skipped) return false;
    const t = stamp();
    a.skipped = true; a.skip_note = note || null; a.t_submit = t; a.t_open = a.t_open || t;
  });
  return { status: statusOf(a), answer: publicAnswer(a) };
});
