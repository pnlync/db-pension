# M7 口径桥：IAS 19 DBO → Funding Standard 负债（图 2）

> 成员数据是合成的。市场数据截至 2025-12-31，MVA 取 2025-11-30 的值。

## 这一步做了什么

从 IAS 19 DBO 出发，按固定顺序每次只换一样东西，每一步都完整重估一次，最后正好到 FS 负债。每一步的差额就是这样东西的影响；最后一步等于独立算出的 FS 负债，所以没有残差。

**Bridge effects are sequential rather than unique standalone decompositions.** 顺序变了，各步大小会变，所以顺序固定下来。

## 结果（`outputs/bridge_2025.json`，图 2）

| 步骤 | 改了什么 | 影响谁 | €m | 原型 | 为什么是这个方向 |
|---|---|---|---|---|---|
| 0 | IAS 19 DBO | 全部 | 206.8 | 206.9 | 起点 |
| 1 | 在职成员改为今天离职：不再加薪，也没有离职率 | 在职 | −10.1 | −6.4 | 用今天的工资，而不是 65 岁时的预计工资 |
| 2 | 改用 Section 34 死亡率和年金上调 | 非退休 | +0.2 | −4.7 | 见下 |
| 3 | 重估和增长改为 1.5% | 非退休 | −6.5 | −6.8 | IAS 19 用 1.87% |
| 4 | 贴现改为 6% / 4.25% × MVA | 非退休 | −2.5 | −13.2 | 见下 |
| 5 | 退休成员改为年金购买成本 | 退休 | +11.1 | +16.4 | 保险公司价格：贴现率更低、寿命更长 |
| 6 | 清盘费用 | 全部 | +4.0 | +3.8 | 2% × 199.0 |
| = | FS 负债 | | 203.0 | 196.1 | 残差 0.00 |

**和原型的两处明显不同，都来自真实数据：**
- **第 2 步几乎为 0（原型 −4.7）。** 校准后的 IAS 19 死亡率是 66% / 75% ILT15、改善 0.9%，男性 e65 22.1 年，比原型假设的短。Section 34 退休后是 58% / 62%，再加每年 0.36% 的年金上调，大致和它持平。原型的 IAS 19 寿命更长，所以换成 Section 34 时负债下降。
- **第 4 步只有 −2.5（原型 −13.2）。** 2025 年底 IAS 19 的 SEDR 已经是 4.37%，原型约 3.75%。Section 34 对 65 岁前用 6%、65 岁后用 4.25%，再乘 MVA（离 65 岁远的成员是 1.086；65 岁时 MVA2 为 1.237），和 4.37% 的差距已经不大。

**净结果**：FS 比 IAS 19 低 €3.8m，但这是两股方向相反的力量相抵：非退休成员合计 −€18.8m，退休成员加清盘费用合计 +€15.1m。所以"哪个口径高"取决于成员结构。面试时的说法不是"贴现率不同"，而是"衡量目的不同，所以待遇处理、假设和方法都不同"。

## 代码结构

- `src/pension/bridge.py`：`run` 逐步构造 Basis（IAS 19 → 离职口径 → Section 34 死亡率 → 1.5% → 分段贴现 × MVA），退休成员单独换成年金成本，最后加清盘费用。
- `src/pension/figures.py`：`fig2_bridge`。
- `src/pension/pipeline.py`：`run_bridge`、`run_cv_numbers`。

## 验证结果（3 个测试全部 PASS）

- 第 0 步 = IAS 19 DBO。
- 各步之和 = FS − IAS 19，残差为 0（误差 1e-6 以内）。
- 顺序固定；方向：离职口径 < 0，1.5% < 0，年金成本 > 0，清盘费用 > 0。

## 理解检查（自测）

1. **每一步的方向和原因？** 见上表。
2. **为什么不能把各步分开、各自从 IAS 19 出发算一遍？** 那样各步之和不等于总差距，会有交叉项。依次替换能保证没有残差，代价是每一步的大小取决于顺序。
3. **为什么这次第 4 步比原型小很多？** 2025 年底利率比原型假设的高，IAS 19 贴现率已经接近法定利率乘 MVA 之后的水平。

## 面试要点

- "Same members, different purpose, different number: going-concern IAS 19 against a wind-up test; the non-pensioner steps take off EUR 19m and the annuity price plus wind-up costs add EUR 15m, netting to a EUR 4m gap."
- "Each step is a full revaluation in a fixed order, so the bridge closes with zero residual."
