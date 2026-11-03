import { handler, requireAdmin, allAnswers, loadPairs } from '../lib/common.js';

// 管理：全部答卷，一个 JSON 数组。_pair 是导出时按偏好对现拼的（原编号、单元、层级、是否校准、我们判断的较优侧），不在答卷里。
export default handler(['GET'], async (req) => {
  requireAdmin(req);
  const [answers, pairs] = await Promise.all([allAnswers(), loadPairs()]);
  answers.sort((x, y) => (x.expert_id + x.pair_id).localeCompare(y.expert_id + y.pair_id));
  return answers.map(a => {
    const p = pairs.get(a.pair_id);
    return { ...a, _pair: p ? { source_pair_id: p.source_pair_id ?? null, unit_id: p.unit_id ?? null, level: p.level, calibration: !!p.calibration, claim_better: p.claim?.better ?? null } : null };
  });
});
