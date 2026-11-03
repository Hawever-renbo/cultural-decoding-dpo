import { handler, requireAdmin, expertsPublic, expertQueue, answersOf, statusOf } from '../lib/common.js';

// 管理：每位专家的进度计数。
export default handler(['GET'], async (req) => {
  requireAdmin(req);
  return Promise.all(expertsPublic().map(async e => {
    const answers = await answersOf(e.id);
    const c = { new: 0, blind: 0, claim: 0, done: 0, skipped: 0 };
    for (const id of expertQueue(e.id)) c[statusOf(answers.get(id))]++;
    return { expert_id: e.id, name: e.name, n: e.n, done: c.done, skipped: c.skipped,
             in_progress: c.blind + c.claim, untouched: c.new, opened: answers.size };
  }));
});
