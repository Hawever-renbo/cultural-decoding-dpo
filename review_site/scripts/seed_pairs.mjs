// 把偏好对上传到私有 Blob 的 config/pairs.json（覆盖）。上传前先校验格式。
// 用法（在 web/ 下）：node --env-file=.env.local scripts/seed_pairs.mjs [data/pairs.real.json] [--experts data/experts.json]
// .env.local 由 `vercel env pull .env.local` 生成（含 BLOB_READ_WRITE_TOKEN，已 gitignore）。
// 给了 --experts 时，还查每位专家的队列都指向这份文件里的对。
// 真实对（文件名含 pairs.real）上站前须先过后训练监督（D-176）：报告追加进 ../out/监督/上站_监督.md，
// 最近一次审查结论为「通过」且列出这份文件的当前 sha256；确有理由跳过，加 --skip-audit "理由"。
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { put } from '@vercel/blob';

const args = process.argv.slice(2);
const ei = args.indexOf('--experts');
const expertsFile = ei >= 0 ? args.splice(ei, 2)[1] : null;
const si = args.indexOf('--skip-audit');
const skipAudit = si >= 0 ? args.splice(si, 2)[1] : null;
const file = args[0] || 'data/pairs.real.json';
if (file.includes('pairs.real')) {
  const audit = '../out/监督/上站_监督.md', HEAD = '# 监督审查';
  const sha = createHash('sha256').update(readFileSync(file)).digest('hex');
  const last = existsSync(audit) ? HEAD + readFileSync(audit, 'utf8').split(HEAD).pop() : '';
  const probs = [];
  if (!last) probs.push(`没有监督审查记录 ${audit}`);
  else {
    if (!/^结论：\s*通过/m.test(last)) probs.push('最近一次监督审查的结论不是「通过」');
    if (!last.includes(`sha256=${sha}`)) probs.push(`${file} 的当前哈希不在最近一次审查里（没审，或审完又改过）`);
  }
  if (probs.length && !skipAudit) { console.error('✗ 上站前须先过后训练监督：\n  - ' + probs.join('\n  - ')); process.exit(1); }
  if (probs.length) console.warn(`⚠ 未经监督审查上站：${skipAudit}`);
}
const doc = JSON.parse(readFileSync(file, 'utf8'));
const LEVELS = ['open', 'axial', 'selective'], KINDS = ['participant', 'block', 'inline', 'fieldnote'];
const SEC = /^(open code \S+|category \S+|relation \S+|core|storyline)$/;
const str = x => typeof x === 'string' && x.trim().length > 0;
const ids = new Set();
for (const p of doc.pairs) {
  const bad = m => { throw new Error(`${p.pair_id}: ${m}`); };
  if (!p.pair_id || ids.has(p.pair_id)) bad('pair_id 缺失或重复'); ids.add(p.pair_id);
  if (!LEVELS.includes(p.level)) bad('level');
  if (!str(p.background)) bad('background');
  if (!Array.isArray(p.quotes) || !p.quotes.every(q => Number.isInteger(q.n) && str(q.text) && KINDS.includes(q.kind))) bad('quotes');
  if (!Array.isArray(p.diffs) || !p.diffs.length || !p.diffs.every(d => SEC.test(d.section) && 'A' in d && 'B' in d && d.A !== d.B)) bad('diffs');
  if (!p.claim || !['A', 'B'].includes(p.claim.better) || !str(p.claim.text)) bad('claim');
  // Z3：链里恰好一行是比较处，且与 diffs 的那一处一致；其余行都是两侧共用的文字
  if (p.chain) {
    const cmp = p.chain.filter(r => r.cmp);
    if (cmp.length !== 1 || p.diffs.length !== 1 || cmp[0].A !== p.diffs[0].A || cmp[0].B !== p.diffs[0].B) bad('chain 比较处');
    if (![...p.chain, ...(p.more || [])].every(r => r.cmp || str(r.text))) bad('chain 共用行');
  }
  if (typeof p.calibration !== 'boolean') bad('calibration');
  // 有中文就得齐：背景、每条引语、每处差异两边、判断
  const anyZh = 'background_zh' in p || p.quotes.some(q => 'zh' in q) || p.diffs.some(d => 'A_zh' in d) || 'text_zh' in p.claim;
  if (anyZh) {
    if (!str(p.background_zh)) bad('background_zh');
    if (!p.quotes.every(q => str(q.zh) && (!q.note || str(q.note_zh)))) bad('quotes zh');
    if (!p.diffs.every(d => (!str(d.A) || str(d.A_zh)) && (!str(d.B) || str(d.B_zh)))) bad('diffs zh');
    if (p.chain && ![...p.chain, ...(p.more || [])].every(r => r.cmp ? (str(r.A_zh) && str(r.B_zh)) : str(r.zh))) bad('chain zh');
    if (!str(p.claim.text_zh)) bad('claim.text_zh');
  }
}
if (expertsFile) {
  const ex = JSON.parse(readFileSync(expertsFile, 'utf8'));
  for (const e of ex) {
    const miss = e.queue.filter(id => !ids.has(id));
    if (miss.length) throw new Error(`专家 ${e.id} 的队列里有文件中没有的对：${miss.join(', ')}`);
  }
  console.log(`专家队列校验通过（${ex.length} 位）`);
}
await put('config/pairs.json', JSON.stringify(doc), { access: 'private', contentType: 'application/json; charset=utf-8', addRandomSuffix: false, allowOverwrite: true });
console.log(`已上传 ${doc.pairs.length} 对到 config/pairs.json（private），来源 ${file}`);
