# review_site/: blind A/B review app

A small Vercel app (static page + serverless functions + private Vercel Blob storage) for expert review of preference pairs. UI text is in Chinese.

**Flow for each pair**
1. `GET /api/pair`: sends context, quotes and the two sides, in an A/B order randomised when the pairs are built. It sends only an allow-listed set of fields: no intended side, level, source id or calibration flag.
2. `POST /api/blind`: the blind pick (A, B or about the same). The pick can change until the reveal and then locks. Every change is kept with a timestamp.
3. `POST /api/claim`: only after the blind pick, reveals which side was intended as better.
4. `POST /api/verdict`: *correct / partly correct / not correct*. The last two require a one-line reason. A verdict cannot be changed after submission.
5. `POST /api/skip`, `GET /api/progress`, `GET /api/me`, `GET /api/export` (admin): skip, progress, identity, export.

**Access.** Each reviewer has a private link with a random token (`scripts/make_experts.mjs`). Tokens are kept in an environment variable and compared in constant time. Each reviewer has their own queue order. Answers are stored per reviewer and per pair in private Blob storage.

**Upload gate.** `scripts/seed_pairs.mjs` refuses to upload real pairs unless the latest supervision audit has passed and lists the file's current sha256. The audit file lives in the private tree.

**Not included.**
- Reviewer tokens and `.env.local`.
- The real pairs (`data/pairs.real*.json`) and the answer sheets.
- The answer key `lib/pi_meta.js`; a stub stands in for it.

`data/pairs.demo.json` is entirely fictional demo content.

Run locally with demo data: `node scripts/make_experts.mjs --demo`, then `vercel dev` (needs a Blob store token in `.env.local`).
