import { handler, requireExpert, pairFor, mutateAnswer, statusOf, publicAnswer, stamp, HttpError, BLIND_CHOICES } from '../lib/common.js';

// ① 盲选：A / B / neither。看过我们的判断之后不得再改。
export default handler(['POST'], async (req) => {
  const e = requireExpert(req);
  const { pair_id, blind } = req.body || {};
  await pairFor(e, pair_id);
  if (!BLIND_CHOICES.includes(blind)) throw new HttpError(400, '盲选只能是 A / B / neither');
  const a = await mutateAnswer(e, pair_id, req, a => {
    if (a.skipped) throw new HttpError(409, '这一对已跳过');
    if (a.t_claim) throw new HttpError(409, '已看过我们的判断，盲选不能再改');
    const t = stamp();
    a.blind = blind; a.t_blind = t;
    a.t_open = a.t_open || t;
    a.blind_history.push({ blind, t });
  });
  return { status: statusOf(a), answer: publicAnswer(a) };
});
