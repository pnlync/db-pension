# M12 打包：trustee memo、README、网页

> 所有数字都由 `uv run python -m pension.pipeline` 从 `outputs/` 写进文档，没有手写数字。

## 这一步做了什么

| 交付物 | 位置 | 内容 |
|---|---|---|
| Trustee memo（英文，约 2 页） | `reports/trustee_memo.md` | 目的和关键数字；两个口径为什么不同；2025 年发生了什么；主要风险；三个方案；建议（限定在合成情景内）；局限 |
| IAS 19 披露附注 | `reports/disclosure_note.md` | 表 1–7 齐全（表 2–4 来自 M8） |
| README | `README.md` | 业务问题和答案、五张图、验证了什么、怎么运行、仓库结构、免责声明 |
| 网页（GitHub Pages） | `docs/index.html` | 六个发现、两种负债估值、2025 年变化、风险、决策、buy-in、验证、局限；五张图加 tornado；可以下载 Excel 复算工作簿；链接 memo、披露附注、代码仓库和作品集主页 |
| CV 数字 | `outputs/cv_numbers.json` | CV、README、memo 用到的每个数字 |

网页和寿险项目用同一套样式（`docs/styles/site.css`），不需要 JavaScript，手机宽度下没有横向滚动。发布方式也和寿险项目一样：推送到 main 后，GitHub Actions（`.github/workflows/deploy-pages.yml`）把 `docs/` 发布到 `gh-pages` 分支。

## memo 的建议（限定在合成情景内）

- 采用调仓 + 每年 €3.5m 补亏供款：3 年内恢复 FS + FSR，现金成本最低。
- 更长期的投资策略要再评估：10 年期限下，少掉的股票回报比 FSR 的降低更贵。
- 暂不按示意条款做 pensioner buy-in：先拿保险公司报价，用报价校准 FS 的年金基础；如果要做，用卖股票的钱付保费。

## 验证结果（8 个测试全部 PASS）

- README、memo、网页里的每个数字，都能在 `outputs/*.json` 或 `config/*.yaml` 里找到（年份、图号、条款号等结构性数字除外）。
- `cv_numbers.json` 的每个值都能在 outputs 里找到。
- 每张图都标注 "Synthetic members" 和市场数据日期。
- 网页的所有链接都有效：页内锚点、`docs/` 下的文件、指向仓库的链接。
- 披露附注表 1–7 齐全。
- 凡是提到 buy-in 损失的文档，都写明了"合格保单、完全匹配"的前提。

## 面试时 30 秒的介绍

> I built a member-level model of a synthetic Irish final-salary scheme. It values the same benefits for IAS 19 and for the Irish Funding Standard, explains the gap step by step, rolls the scheme through 2025 on actual market data, and compares three ways to rebuild the funding standard reserve: contributions, moving equities into long sovereigns, and a pensioner buy-in priced from an insurer's Solvency II view.
