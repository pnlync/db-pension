# Raw downloads (not committed)

Third-party source files, downloaded manually by the owner. Everything in this folder except this README is gitignored. The transcribed, cleaned files in `data/market/` are committed and each states its source and dates. Retrieval date for the first set: 2026-09-27.

| # | Save as | Source | Used for |
|---|---|---|---|
| 1 | `ilt15_2005-2007.pdf` | CSO, Irish Life Tables No. 15: https://www.cso.ie/en/media/csoie/releasespublications/documents/birthsdm/2007/irishlife_2005-2007.pdf | base mortality table for every basis (SPEC §7.1) |
| 2 | `ILT2015-2017_TBL1.xlsx`, `ILT2015-2017_TBL2.xlsx` | CSO, Irish Life Tables No. 17 (copied from `../assurance/data/raw/`) | comparison only |
| 3 | `sai_mva.html` | SAI, Section 34 MVA factors: https://web.actuaries.ie/public/standards-regulation/mva (browser: File > Save Page As, format "Web Page, HTML Only") | MVA table, OAT 2032 yields |
| 4 | `asp_pen3_v4.1.pdf` | SAI, ASP PEN-3 v4.1: https://web.actuaries.ie/sites/default/files/asp/ASP%20PEN-3/211209%20ASP%20PEN-3%20with%20amended%20explanatory%20note%20%281%29.pdf | FS rules, fixed-increase appendix table |
| 5 | `section34_guidance_v02.pdf` | Pensions Authority, Section 34 prescribed guidance v02: https://pensionsauthority.ie/wp-content/uploads/2023/06/section_34_of_the_pensions_act_1990_version_2_oct_2016_.pdf | statutory TV basis, MVA formulas, date rule |
| 6 | `ecb_yc_2024-12-30.csv` | ECB Data Portal API: https://data-api.ecb.europa.eu/service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.?startPeriod=2024-12-30&endPeriod=2024-12-30&format=csvdata | opening AAA curve (no ECB curve published on 2024-12-31) |
| 7 | `ecb_yc_2025-12-31.csv` | same, with `startPeriod=2025-12-31&endPeriod=2025-12-31` | closing AAA curve |
| 8 | `cso_cpm01.csv` | CSO PxStat CPM01 (monthly CPI): https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/CPM01/CSV/1.0/en | deferred revaluation, 2025 experience |
| 9 | `sw19_rates_of_payment_2026.pdf` | Department of Social Protection, Rates of Payment 2026 (SW19, May 2026): https://assets.gov.ie/static/documents/9c18b85f/20260520_Rates_of_Payment_Booklet_-_SW19_-_2026_May.pdf | SPC 2026: EUR 299.30/week (2025-12-31 valuation) |
| 10 | `sw19_rates_of_payment_2025.pdf` | Department of Social Protection, Rates of Payment 2025 (SW19): https://assets.gov.ie/316129/3bed9acc-015f-4161-8221-8eaa444f917c.pdf | SPC 2025: EUR 289.30/week (2024-12-31 valuation) |
| 11 | `msci_world_eur_factsheet.pdf` | MSCI World Index (EUR) factsheet, current month (its annual performance table shows calendar year 2025): https://www.msci.com/www/index-factsheets/msci-world-index/08490663 (use the "Net" EUR factsheet PDF) | M8: 2025 equity total return in EUR |
| 12 | `ecb_estr_2025.csv` | ECB Data Portal API, €STR daily: https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT?startPeriod=2025-01-01&endPeriod=2025-12-31&format=csvdata | M8: 2025 cash return |
| 13 | `EIOPA_RFR_20251231.zip` | EIOPA risk-free rate publication for 2025-12-31 (copied from `../assurance/data/raw/`) | M11: buy-in BEL (RFR + VA) |
