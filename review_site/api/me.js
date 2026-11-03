import { handler, requireExpert, answersOf, statusOf } from '../lib/common.js';

// 专家本人的队列与每对的状态；前端据此落到第一对没答完的。不含层级（模型一侧的标注，盲选后才随判断下发）。
export default handler(['GET'], async (req) => {
  const e = requireExpert(req);
  const answers = await answersOf(e.id);
  const queue = e.queue.map(id => ({ pair_id: id, status: statusOf(answers.get(id)) }));
  const first = queue.findIndex(q => q.status !== 'done' && q.status !== 'skipped');
  return { expert: { id: e.id, name: e.name }, n: queue.length, queue, first_unanswered: first };
});
