import { handler, requireExpert, pairFor, mutateAnswer, statusOf, publicAnswer, stamp, HttpError, VERDICTS, TAGS } from '../lib/common.js';

// ② 对我们判断的裁决：对 / 不对 / 部分对；后两者必须写一句理由。提交后不可改。
export default handler(['POST'], async (req) => {
  const e = requireExpert(req);
  const body = req.body || {};
  const { pair_id, verdict } = body;
  await pairFor(e, pair_id);
  if (!VERDICTS.includes(verdict)) throw new HttpError(400, '裁决只能是 对 / 不对 / 部分对');
  const reason = String(body.reason || '').trim().slice(0, 1000);
  if (verdict !== '对' && !reason) throw new HttpError(400, '选「不对」或「部分对」时请写一句理由');
  const tags = Array.isArray(body.tags) ? [...new Set(body.tags)] : [];
  if (tags.some(t => !TAGS.includes(t))) throw new HttpError(400, '标签不在可选范围内');
  const a = await mutateAnswer(e, pair_id, req, a => {
    if (a.skipped) throw new HttpError(409, '这一对已跳过');
    if (a.verdict) throw new HttpError(409, '这一对已经提交过');
    if (!a.t_claim) throw new HttpError(409, '还没看我们的判断');
    a.verdict = verdict; a.reason = reason || null; a.tags = tags; a.t_submit = stamp();
  });
  return { status: statusOf(a), answer: publicAnswer(a) };
});
