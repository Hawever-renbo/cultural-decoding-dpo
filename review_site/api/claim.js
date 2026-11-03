import { handler, requireExpert, pairFor, mutateAnswer, statusOf, publicAnswer, stamp, HttpError, revealOf } from '../lib/common.js';

// 盲选已存之后才下发我们的判断（含中文）与层级；首次下发记 t_claim，从此盲选锁定。
export default handler(['GET'], async (req) => {
  const e = requireExpert(req);
  const id = req.query.id;
  const p = await pairFor(e, id);
  const a = await mutateAnswer(e, id, req, a => {
    if (!a.blind) throw new HttpError(409, '先提交盲选，才能看我们的判断');
    if (a.t_claim) return false;
    if (a.skipped) throw new HttpError(409, '这一对已跳过');
    a.t_claim = stamp();
  });
  return { ...revealOf(p), status: statusOf(a), answer: publicAnswer(a) };
});
