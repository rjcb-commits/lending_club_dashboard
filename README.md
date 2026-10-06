# Lending Club Portfolio Dashboard

A Tableau dashboard on how $20.9B of Lending Club consumer loans (2016-2018 originations) performed: where the dollars ended up, how loss rates developed by issue month, and whether higher interest rates covered higher losses by sub-grade.

## Findings

- Grades E-G = 7.6% of dollars lent but 24% of principal lost
- Mid-2016 batches were the worst; 2017+ improved after credit tightened
- Returns peak at sub-grade B4 (9.5%) and fall beyond grade E; only F5 and G5 lose money

## Recommendation

Reprice or cap F-G, grow B-C, use the loss triangle to catch bad batches early.

## Data

- Source: Lending Club accepted loans, 2007 to 2018 Q4 (public, CC0, via Hugging Face `codesignal/lending-club-loan-accepted`)
- 2,260,668 loans, single snapshot with latest payment month March 2019
- The raw file (1.6 GB) is not stored in this repo. Download it from https://huggingface.co/datasets/codesignal/lending-club-loan-accepted to `data_raw/accepted_2007_to_2018Q4.csv` to rebuild the tables.

## Repo layout

```
prep/
  build_tables.py           raw CSV -> Tableau tables + reconciliation report (DuckDB SQL)
  build_sankey_polygons.py  pre-computes Sankey curves as polygon vertices for Tableau
data_tableau/
  kpi_summary.csv           headline numbers for the KPI tiles
  sankey_flows.csv          dollars lent by grade -> outcome
  sankey_polygons.csv       polygon vertices for the flow diagram
  sankey_labels.csv         node label positions
  loss_triangle.csv         cumulative principal loss % by issue month x months on book
  subgrade_risk_return.csv  rate charged vs lifetime loss and net return by sub-grade
  reconciliation.md         row and dollar checks back to source
dashboard/                  Tableau workbook
images/                     dashboard screenshots
```

## Rebuild

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python prep/build_tables.py
python prep/build_sankey_polygons.py
```

## Dashboards

1. **Where the money went.** Sankey from total dollars lent, through grade A to G, to outcome (paid off, still paying, late, charged off), with KPI tiles.
2. **Loss triangle.** Monthly issue cohorts 2014-2018 against months on book, colored by cumulative principal loss %, with a 36 / 60 month term toggle.
3. **Risk vs return.** Matured 36-month loans issued 2013-2015, average interest rate against lifetime net return for each of the 35 sub-grades.

## Key numbers (2016-2018 originations)

| Metric | Value |
|---|---|
| Loans issued | 1,373,228 |
| Dollars lent | $20.92B |
| Principal lost | $1.43B (6.8% of dollars lent) |
| Recoveries | $130M (9.1% of principal lost) |
| Grades E-G share of dollars lent | 7.6% |
| Grades E-G share of principal lost | 24.0% |

Other figures from the tables:

- 36-month loans issued Jan 2014 had lost 5.1% of principal by month 24. Loans issued Jul 2016 had lost 9.1%.
- Among matured 36-month loans, lifetime net return was highest for sub-grade B4 (9.5% on an 11.8% average rate). F5 and G5 were the only sub-grades with a negative net return, both on small volumes (300 and 9 loans).

## Method

- Outcome mapping: Fully Paid -> Paid off; Charged Off and Default -> Charged off; Current -> Still paying; Late and In Grace Period -> Late. The full mapping with counts is in `data_tableau/reconciliation.md`.
- Principal loss = funded amount minus principal received, for charged-off and defaulted loans.
- Net return = (interest + late fees + recoveries - collection fees - principal loss) / dollars lent.
- The source is a single snapshot with no monthly status history. Charge-off month is estimated as last payment month + 5 months (issue month + 5 for loans that never paid), capped at the as-of month.
- Sub-grade lifetime metrics use 36-month loans issued 2013-2015 so that almost all have resolved (at most 1.46% still open in any sub-grade).

## Reconciliation

`prep/build_tables.py` writes `data_tableau/reconciliation.md` on every run. It checks that the Sankey table matches source loan counts and dollars exactly (1,373,228 loans / $20,921,761,925) and reports row counts and coverage for the other tables.

## Limitations

- Charge-off timing is estimated, so the loss triangle shows approximate timing, not reported charge-off dates.
- 2017-2018 cohorts were still young at the March 2019 snapshot, so their losses are incomplete.
- Recoveries are as recorded at the snapshot date and may understate final recoveries.
