"""One definition for each headline metric, imported wherever the metric is computed, so every table and chart agrees.

journal_q1_share   Q1 journal papers / journal papers that HAVE a journal quartile (Q1-Q4).
                   Conference papers are never in the numerator or the denominator; their ranks (CORE, Scopus proceedings
                   quartile) are reported separately. Returns (q1, ranked, share_percent, coverage_percent).
h_index            largest h such that h papers have at least h citations.
gini               Gini coefficient of a non-negative distribution (0 = equal, 1 = one holder has everything).
"""
import numpy as np

JOURNAL_QUARTILES = ("Q1", "Q2", "Q3", "Q4")


def journal_q1_share(df, type_col="type", q_col="quartile"):
    j = df[df[type_col] == "journal"]
    ranked = j[j[q_col].isin(JOURNAL_QUARTILES)]
    q1 = int((ranked[q_col] == "Q1").sum())
    share = round(q1 / len(ranked) * 100, 1) if len(ranked) else None
    coverage = round(len(ranked) / len(j) * 100, 1) if len(j) else None
    return q1, len(ranked), share, coverage


def h_index(cites):
    c = sorted((int(x) for x in cites), reverse=True)
    return sum(1 for i, x in enumerate(c, 1) if x >= i)


def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    if len(x) == 0 or x.sum() == 0:
        return float("nan")
    n = len(x)
    return float((2 * np.arange(1, n + 1) - n - 1).dot(x) / (n * x.sum()))
