# Reconciliation (2026-10-03)

- Loans read from source: 2,260,668
- Data as-of (latest payment month): 2019-03-01
- Loans with unmapped status (excluded): 0
- Sankey 2016-2018: source 1,373,228 loans / $20,921,761,925; table 1,373,228 loans / $20,921,761,925 -> MATCH
- Loss triangle: 4,014 rows, 60 issue months, max months on book 60
- Sub-grade table: 35 sub-grades, 546,165 loans; max share not yet resolved 1.46%

## Status mapping

| loan_status | outcome | loans |
|---|---|---|
| Fully Paid | Paid off | 1,076,751 |
| Current | Still paying | 878,317 |
| Charged Off | Charged off | 268,559 |
| Late (31-120 days) | Late | 21,467 |
| In Grace Period | Late | 8,436 |
| Late (16-30 days) | Late | 4,349 |
| Does not meet the credit policy. Status:Fully Paid | Paid off | 1,988 |
| Does not meet the credit policy. Status:Charged Off | Charged off | 761 |
| Default | Charged off | 40 |

## Method notes

- Single snapshot file; charge-off month estimated as last payment month + 5 months (never-paid loans: issue month + 5), capped at the as-of month.
- Net principal loss = funded amount minus principal received, for Charged Off / Default loans.
- Sub-grade lifetime metrics use 36-month loans issued 2013-2015 so nearly all have resolved.
