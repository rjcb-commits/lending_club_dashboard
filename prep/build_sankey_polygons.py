"""Pre-compute Sankey polygons so Tableau can draw the 'where every dollar went' flow
with a plain Polygon mark (no data densification tricks needed).

Input : data_tableau/sankey_flows.csv
Output: data_tableau/sankey_polygons.csv  (one row per polygon vertex)
        data_tableau/sankey_labels.csv    (node label positions)

Tableau: Columns = X (continuous), Rows = Y (continuous, reversed), Mark = Polygon,
Path = Point Order, Detail = Shape ID, Color = Color Group.
"""
import csv, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
T = ROOT / "data_tableau"
GRADES = list("ABCDEFG")
OUTCOMES = ["Paid off", "Still paying", "Late", "Charged off"]
N = 40                      # points per curve edge
GAP_G, GAP_O = 0.35, 1.0    # $B gaps between grade / outcome nodes
X_SRC, X_G, X_O, W = 0, 50, 100, 2.5

flows = {}
for r in csv.DictReader(open(T / "sankey_flows.csv")):
    flows[(r["grade"], r["outcome"])] = float(r["dollars_lent"]) / 1e9
gtot = {g: sum(flows.get((g, o), 0) for o in OUTCOMES) for g in GRADES}
otot = {o: sum(flows.get((g, o), 0) for g in GRADES) for o in OUTCOMES}
TOTAL = sum(gtot.values())

# node positions (y grows downward)
src = (0.0, TOTAL + GAP_G * (len(GRADES) - 1))
gy, y = {}, 0.0
for g in GRADES:
    gy[g] = [y, y + gtot[g]]; y += gtot[g] + GAP_G
oy, y = {}, (src[1] - (TOTAL + GAP_O * 3)) / 2
for o in OUTCOMES:
    oy[o] = [y, y + otot[o]]; y += otot[o] + GAP_O

rows, labels = [], []
def sig(t): return 1 / (1 + math.exp(-12 * (t - 0.5)))
def band(sid, group, grade, outcome, dollars, x0, a0, a1, x1, b0, b1):
    pts = []
    for i in range(N + 1):                       # top edge left -> right
        t = i / N; pts.append((x0 + (x1 - x0) * t, a0 + (b0 - a0) * sig(t)))
    for i in range(N, -1, -1):                   # bottom edge right -> left
        t = i / N; pts.append((x0 + (x1 - x0) * t, a1 + (b1 - a1) * sig(t)))
    for k, (x, yv) in enumerate(pts):
        rows.append([sid, "link", group, grade, outcome, round(dollars, 4), k, round(x, 4), round(yv, 4)])
def rect(sid, group, grade, outcome, dollars, x, y0, y1):
    for k, (px, py) in enumerate([(x, y0), (x + W, y0), (x + W, y1), (x, y1)]):
        rows.append([sid, "node", group, grade, outcome, round(dollars, 4), k, px, round(py, 4)])

# source -> grade links (source stacked without gaps, grades spread with gaps)
scale = src[1] / TOTAL
y_s = 0.0
for g in GRADES:
    h = gtot[g] * scale
    band(f"S-{g}", f"Grade {g}", g, "", gtot[g], X_SRC + W, y_s, y_s + h, X_G, gy[g][0], gy[g][1]); y_s += h
rect("N-SRC", "Source", "", "", TOTAL, X_SRC, 0, src[1])
labels.append(["Source", f"${TOTAL:.1f}B lent", X_SRC, -0.6])
# grade -> outcome links
cur_o = {o: oy[o][0] for o in OUTCOMES}
for g in GRADES:
    cur_g = gy[g][0]
    for o in OUTCOMES:
        d = flows.get((g, o), 0)
        if d <= 0: continue
        band(f"L-{g}-{o}", o, g, o, d, X_G + W, cur_g, cur_g + d, X_O, cur_o[o], cur_o[o] + d)
        cur_g += d; cur_o[o] += d
    rect(f"N-{g}", f"Grade {g}", g, "", gtot[g], X_G, gy[g][0], gy[g][1])
    labels.append([f"Grade {g}", g, X_G - 1.5, (gy[g][0] + gy[g][1]) / 2])
for o in OUTCOMES:
    rect(f"N-{o}", o, "", o, otot[o], X_O, oy[o][0], oy[o][1])
    labels.append([o, f"{o}  ${otot[o]:.2f}B ({100*otot[o]/TOTAL:.0f}%)", X_O + W + 1.5, (oy[o][0] + oy[o][1]) / 2])

with open(T / "sankey_polygons.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["shape_id", "shape_type", "color_group", "grade", "outcome", "dollars_b", "point_order", "x", "y"]); w.writerows(rows)
with open(T / "sankey_labels.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["node", "label", "x", "y"]); w.writerows(labels)
print(f"{len(rows):,} vertices, total ${TOTAL:.2f}B")
