"""Build Tableau-ready tables from the public Lending Club accepted-loans file.

Input : data_raw/accepted_2007_to_2018Q4.csv  (Lending Club, CC0 via Hugging Face codesignal/lending-club-loan-accepted)
Output: data_tableau/*.csv + data_tableau/reconciliation.md

Tables
  1. sankey_flows.csv      dollars lent 2016-2018 by grade -> outcome (Sankey / "where every dollar went")
  2. loss_triangle.csv     cumulative net principal charge-off % by monthly issue cohort x months on book (2014-2018)
  3. subgrade_risk_return.csv  matured 36-month loans issued 2013-2015: rate charged vs lifetime loss and net return by sub-grade
  4. kpi_summary.csv       headline numbers for the KPI strip

Method notes (also written to reconciliation.md)
  * The file is a single snapshot (latest payment month = AS_OF). It has no monthly status history,
    so charge-off timing is estimated as last payment month + 5 months (Lending Club charged loans off
    at roughly 150 days past due); loans that never paid use issue month + 5.
  * Net principal loss = funded_amnt - total_rec_prncp for Charged Off / Default loans.
"""
import duckdb, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data_raw" / "accepted_2007_to_2018Q4.csv"
OUT = ROOT / "data_tableau"
OUT.mkdir(exist_ok=True)
con = duckdb.connect()

con.execute(f"""
CREATE TABLE loans AS
SELECT
  CAST(id AS VARCHAR)                                    AS id,
  CAST(funded_amnt AS DOUBLE)                            AS funded,
  TRIM(term)                                             AS term,
  CAST(int_rate AS DOUBLE)                               AS int_rate,
  grade, sub_grade, purpose,
  CAST(dti AS DOUBLE)                                    AS dti,
  loan_status,
  strptime(issue_d, '%b-%Y')::DATE                       AS issue_month,
  TRY_CAST(strptime(last_pymnt_d, '%b-%Y') AS DATE)      AS last_pay_month,
  CAST(total_rec_prncp AS DOUBLE)                        AS rec_prncp,
  CAST(total_rec_int AS DOUBLE)                          AS rec_int,
  CAST(total_rec_late_fee AS DOUBLE)                     AS rec_late_fee,
  CAST(recoveries AS DOUBLE)                             AS recoveries,
  CAST(collection_recovery_fee AS DOUBLE)                AS recovery_fee
FROM read_csv('{RAW}', header=true, all_varchar=true, ignore_errors=true, max_line_size=10000000)
WHERE issue_d IS NOT NULL AND funded_amnt IS NOT NULL
""")

con.execute("""
CREATE TABLE l AS
SELECT *,
  CASE
    WHEN loan_status ILIKE '%Fully Paid%'                       THEN 'Paid off'
    WHEN loan_status ILIKE '%Charged Off%' OR loan_status = 'Default' THEN 'Charged off'
    WHEN loan_status = 'Current'                                THEN 'Still paying'
    WHEN loan_status ILIKE '%Late%' OR loan_status ILIKE '%Grace%' THEN 'Late'
    ELSE 'Other' END                                            AS outcome,
  CASE WHEN loan_status ILIKE '%Charged Off%' OR loan_status = 'Default'
       THEN GREATEST(funded - rec_prncp, 0) ELSE 0 END          AS prncp_loss
FROM loans
""")
AS_OF = con.execute("SELECT max(last_pay_month) FROM l").fetchone()[0]
con.execute(f"""
ALTER TABLE l ADD COLUMN co_month DATE;
UPDATE l SET co_month = CASE WHEN outcome='Charged off'
  THEN LEAST(COALESCE(last_pay_month, issue_month) + INTERVAL 5 MONTH, DATE '{AS_OF}') END;
""")

# 1. Sankey flows (2016-2018 originations)
con.execute(f"""
COPY (
  SELECT grade, outcome,
         count(*)                         AS loans,
         round(sum(funded), 2)            AS dollars_lent,
         round(sum(prncp_loss), 2)        AS principal_lost,
         round(sum(recoveries), 2)        AS recoveries
  FROM l WHERE year(issue_month) BETWEEN 2016 AND 2018 AND outcome <> 'Other'
  GROUP BY 1,2 ORDER BY 1,2
) TO '{OUT}/sankey_flows.csv' (HEADER)
""")

# 2. Loss triangle (monthly cohorts 2014-2018, both terms + per term)
con.execute(f"""
CREATE TABLE cohorts AS
SELECT issue_month, term, sum(funded) AS cohort_funded, count(*) AS cohort_loans
FROM l WHERE year(issue_month) BETWEEN 2014 AND 2018 GROUP BY 1,2;
CREATE TABLE co_by_mob AS
SELECT issue_month, term, date_diff('month', issue_month, co_month) AS mob, sum(prncp_loss) AS loss
FROM l WHERE outcome='Charged off' AND year(issue_month) BETWEEN 2014 AND 2018 GROUP BY 1,2,3;
""")
con.execute(f"""
COPY (
  WITH grid AS (
    SELECT c.issue_month, c.term, c.cohort_funded, c.cohort_loans, m.mob
    FROM cohorts c, range(0, 61) m(mob)
    WHERE c.issue_month + to_months(m.mob) <= DATE '{AS_OF}'
  )
  SELECT g.issue_month, g.term, g.mob AS months_on_book, g.cohort_loans,
         round(g.cohort_funded, 2) AS cohort_funded,
         round(sum(COALESCE(x.loss,0)), 2) AS cum_principal_loss,
         round(100 * sum(COALESCE(x.loss,0)) / g.cohort_funded, 3) AS cum_loss_pct
  FROM grid g LEFT JOIN co_by_mob x
    ON x.issue_month = g.issue_month AND x.term = g.term AND x.mob <= g.mob
  GROUP BY g.issue_month, g.term, g.mob, g.cohort_loans, g.cohort_funded ORDER BY 1,2,3
) TO '{OUT}/loss_triangle.csv' (HEADER)
""")

# 3. Sub-grade risk vs return (matured 36-month loans issued 2013-2015)
con.execute(f"""
COPY (
  SELECT grade, sub_grade,
         count(*)                                                  AS loans,
         round(sum(funded), 2)                                     AS dollars_lent,
         round(sum(int_rate * funded) / sum(funded), 3)            AS avg_int_rate_pct,
         round(100 * sum(prncp_loss) / sum(funded), 3)             AS lifetime_principal_loss_pct,
         round(100 * (sum(rec_int + rec_late_fee + recoveries - recovery_fee) - sum(prncp_loss)) / sum(funded), 3)
                                                                   AS lifetime_net_return_pct,
         round(100 * avg(CASE WHEN outcome IN ('Still paying','Late') THEN 1 ELSE 0 END), 3)
                                                                   AS pct_not_yet_resolved
  FROM l WHERE term = '36 months' AND year(issue_month) BETWEEN 2013 AND 2015
  GROUP BY 1,2 ORDER BY 2
) TO '{OUT}/subgrade_risk_return.csv' (HEADER)
""")

# 4. KPI summary (2016-2018 originations)
con.execute(f"""
COPY (
  SELECT count(*) AS loans_issued,
         round(sum(funded),2) AS dollars_lent,
         round(sum(prncp_loss),2) AS principal_lost,
         round(100*sum(prncp_loss)/sum(funded),3) AS principal_lost_pct,
         round(sum(recoveries),2) AS recoveries,
         round(100*sum(recoveries)/NULLIF(sum(prncp_loss),0),3) AS recoveries_pct_of_loss,
         round(100*sum(CASE WHEN grade IN ('E','F','G') THEN funded END)/sum(funded),3) AS efg_share_of_dollars_pct,
         round(100*sum(CASE WHEN grade IN ('E','F','G') THEN prncp_loss END)/sum(prncp_loss),3) AS efg_share_of_losses_pct,
         DATE '{AS_OF}' AS as_of_month
  FROM l WHERE year(issue_month) BETWEEN 2016 AND 2018 AND outcome <> 'Other'
) TO '{OUT}/kpi_summary.csv' (HEADER)
""")

# Reconciliation
raw_rows = con.execute("SELECT count(*) FROM loans").fetchone()[0]
status = con.execute("SELECT loan_status, outcome, count(*) n FROM l GROUP BY 1,2 ORDER BY n DESC").fetchall()
s_tot = con.execute(f"SELECT count(*), sum(funded) FROM l WHERE year(issue_month) BETWEEN 2016 AND 2018 AND outcome<>'Other'").fetchone()
s_csv = con.execute(f"SELECT sum(loans), sum(dollars_lent) FROM read_csv_auto('{OUT}/sankey_flows.csv')").fetchone()
tri = con.execute(f"SELECT count(*), count(DISTINCT issue_month), max(months_on_book) FROM read_csv_auto('{OUT}/loss_triangle.csv')").fetchone()
sg = con.execute(f"SELECT count(*), sum(loans), round(max(pct_not_yet_resolved),2) FROM read_csv_auto('{OUT}/subgrade_risk_return.csv')").fetchone()
excluded = con.execute("SELECT count(*) FROM l WHERE outcome='Other'").fetchone()[0]
with open(OUT / "reconciliation.md", "w") as f:
    f.write(f"# Reconciliation ({datetime.date.today()})\n\n")
    f.write(f"- Loans read from source: {raw_rows:,}\n- Data as-of (latest payment month): {AS_OF}\n")
    f.write(f"- Loans with unmapped status (excluded): {excluded:,}\n")
    f.write(f"- Sankey 2016-2018: source {s_tot[0]:,} loans / ${s_tot[1]:,.0f}; table {int(s_csv[0]):,} loans / ${s_csv[1]:,.0f} -> {'MATCH' if int(s_csv[0])==s_tot[0] and abs(s_csv[1]-s_tot[1])<1 else 'MISMATCH'}\n")
    f.write(f"- Loss triangle: {tri[0]:,} rows, {tri[1]} issue months, max months on book {tri[2]}\n")
    f.write(f"- Sub-grade table: {sg[0]} sub-grades, {int(sg[1]):,} loans; max share not yet resolved {sg[2]}%\n\n")
    f.write("## Status mapping\n\n| loan_status | outcome | loans |\n|---|---|---|\n")
    for a, b, n in status: f.write(f"| {a} | {b} | {n:,} |\n")
    f.write("\n## Method notes\n\n- Single snapshot file; charge-off month estimated as last payment month + 5 months (never-paid loans: issue month + 5), capped at the as-of month.\n- Net principal loss = funded amount minus principal received, for Charged Off / Default loans.\n- Sub-grade lifetime metrics use 36-month loans issued 2013-2015 so nearly all have resolved.\n")
print(open(OUT / "reconciliation.md").read())
