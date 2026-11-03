// 生成专家名单（含口令）与管理口令，只写进 gitignore 的本地文件；口令不打印。
// 用法（在 web/ 下）：
//   node scripts/make_experts.mjs            —— 真实专家 X1–X3，队列＝data/pairs.real.json 的全部对，各自独立打乱；写 data/experts.json
//   node scripts/make_experts.mjs --demo     —— 演示专家 E1–E3，用 data/pairs.demo.json；写 data/experts.demo.json
// 名单已存在则拒绝覆盖（加 --force 才重写，旧链接会失效）。管理口令 secrets/admin_token.txt 只在缺失时生成，不随名单重写。
import { randomBytes } from 'node:crypto';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';

const demo = process.argv.includes('--demo');
const EXPERTS = demo ? 'data/experts.demo.json' : 'data/experts.json';
const PAIRS = demo ? 'data/pairs.demo.json' : 'data/pairs.real.json';
const ADMIN = 'secrets/admin_token.txt';
if (existsSync(EXPERTS) && !process.argv.includes('--force')) {
  console.error(`${EXPERTS} 已存在，拒绝覆盖（加 --force 重写，旧链接会失效）`); process.exit(1);
}
const tok = () => randomBytes(24).toString('base64url'); // 32 字符
const pairIds = JSON.parse(readFileSync(PAIRS, 'utf8')).pairs.map(p => p.pair_id);
const shuffle = a => { a = [...a]; for (let i = a.length - 1; i > 0; i--) { const j = randomBytes(4).readUInt32BE() % (i + 1); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const who = demo
  ? [{ id: 'E1', name: '演示专家甲' }, { id: 'E2', name: '演示专家乙' }, { id: 'E3', name: '演示专家丙' }]
  : [{ id: 'X1', name: '专家一' }, { id: 'X2', name: '专家二' }, { id: 'X3', name: '专家三' }];
const experts = who.map(e => ({ ...e, token: tok(), queue: shuffle(pairIds) }));
if (new Set(experts.map(e => e.token)).size !== experts.length) throw new Error('口令撞了');
mkdirSync('data', { recursive: true });
writeFileSync(EXPERTS, JSON.stringify(experts, null, 2) + '\n', { mode: 0o600 });
if (!existsSync(ADMIN)) {
  mkdirSync('secrets', { recursive: true });
  writeFileSync(ADMIN, tok() + '\n', { mode: 0o600 });
  console.log(`新写了 ${ADMIN}`);
}
console.log(`写好 ${EXPERTS}（${experts.length} 位，每位 ${pairIds.length} 对，顺序各自打乱）；口令不打印。`);
