# Z6 直出 — 最终导出（2026-11-03T08:42:52 ）

主文件 `pairs.csv` / `pairs.jsonl`：**8021** 对；标记另存 `pairs_flagged.csv` / `.jsonl`：172 对（flag 列写原因）。
单元：v1（含试跑）959，v2 976。

列：原文, chosen, rejected, 版本, 类型(深读/抓重点/缺陷/对照), 缺陷标签, 说话人(匿名 S-<文章>-<n>), pair_id, 文章id, unit_id, 差异说明。

标记规则（零调用，两版同一套）：严格 R1（label 里的实词须见于所引引语，或闭集虚词/报告动词，或背景卡专名）；丢关键词（label 覆盖的小句里的群体词/量词须保留）；dup_span（label 里自带 «…»/[n] 或 span 自身重复）。

## 计数（主文件，版本×类型）

| 版本/类型 | 对数 |
|---|---|
| v1/对照 | 648 |
| v1/深读 | 1367 |
| v1/缺陷 | 1850 |
| v2/对照 | 332 |
| v2/抓重点 | 566 |
| v2/深读 | 845 |
| v2/缺陷 | 2413 |

标记原因：{'lost_keyword': 76, 'R1_strict': 95, 'dup_span': 1}

## 缺陷占比（F）

- v1：outside_word 20.4%，lost_qualifier 20.0%，lost_in_vivo 19.6%，overgeneralization 18.1%，misattached_connective 11.8%，category_confusion 10.2%
- v2：imposed_connective 18.2%，outside_word 17.6%，lost_in_vivo 15.8%，overgeneralization 15.8%，lost_qualifier 15.4%，misattached_connective 10.4%，category_confusion 6.8%

## 长度 AUC / 词袋 AUC（chosen vs rejected；0.5＝无偏）

| 版本/类型 | n | 长度 AUC | 词袋 AUC |
|---|---|---|---|
| v1/深读 | 1367 | 1.0 | 0.915 |
| v1/缺陷 | 1850 | 0.374 | 0.674 |
| v1/对照 | 648 | 0.989 | 0.92 |
| v1/全部 | 3865 | 0.699 | 0.719 |
| v2/深读 | 845 | 1.0 | 0.922 |
| v2/抓重点 | 566 | 0.115 | 0.703 |
| v2/缺陷 | 2413 | 0.351 | 0.722 |
| v2/对照 | 332 | 0.98 | 0.88 |
| v2/全部 | 4156 | 0.501 | 0.648 |

## 调用与花费（台账 out/claude_ledger.jsonl）

| 部分 | 调用 | 美元 |
|---|---|---|
| A/B v2 | 121 | 5.74 |
| v1 全量 | 2335 | 93.36 |
| v2 全量 | 2485 | 100.35 |
| 其他(探针/译文等) | 3 | 0.01 |
| 试跑 | 73 | 3.17 |
| 合计 | 5017 | 202.64 |

cost = API 等价美元（claude -p 报的 total_cost_usd）；订阅额度内的调用不另收费，额外用量（extra credit）部分实付

## 注意：深读/对照有长度与词面偏置

v1 的深读对 chosen 几乎总比 rejected 长（长度 AUC≈1.0），对照对也接近 1.0，词袋 AUC 也高——模型可以只学「长的/带 because 的更好」。用 v1 训练时建议：用带长度归一的目标（SimPO、R-DPO），或只用 v1 的缺陷(F)对。

v2 拆出类型后，v2 的「深读」（只剩 reason 型）和「对照」（只剩 flatten 型）单看仍有同样的长度偏置（≈1.0）；v2 整体长度 AUC≈0.50，是因为「抓重点」方向相反（rejected 更长）、imposed_connective 缺陷对也是 rejected 更长，互相抵消。所以 v2 要整体混着用才平衡；只取 v2 深读或对照训练时同样建议 SimPO/R-DPO。
