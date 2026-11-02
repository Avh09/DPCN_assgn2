"""Grounding check: every number in an answer must be traceable to a tool result.

The check is deliberately simple and conservative. It extracts the numbers of the answer text, flattens all numbers in the tool
results (including numbers written inside strings), and accepts a number when it equals one of them after rounding (so 0.762
matches 0.7623, and 12 matches 12.0 or 1.2e1), or equals one times 100 (a share written as a percentage). Years (1990-2100)
and the digits of list markers are ignored. Numbers that cannot be found are returned so the UI can warn the user.
"""
import json
import math
import re

NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def _numbers_in(text):
    out = []
    for m in NUM.findall(str(text)):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def collect(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for v in obj.values():
            collect(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect(v, acc)
    elif isinstance(obj, bool) or obj is None:
        pass
    elif isinstance(obj, (int, float)):
        if not (isinstance(obj, float) and math.isnan(obj)):
            acc.add(float(obj))
    else:
        acc.update(_numbers_in(obj))
    return acc


def _match(x, pool):
    for p in pool:
        for v in (p, p * 100, p / 100, p * 1000, p / 1000):
            if v == 0 and x == 0:
                return True
            if v == 0:
                continue
            for d in range(0, 6):
                if round(v, d) == round(x, d) and (d > 0 or abs(v - x) < 0.5):
                    # a number written with k decimals matches a value that rounds to it
                    if abs(round(v, d) - x) < 1e-9:
                        return True
    return False


def check(answer_text, tool_results):
    """Returns {"ungrounded": [numbers], "checked": n}."""
    pool = set()
    for r in tool_results:
        collect({k: r.get(k) for k in ("summary", "data", "coverage")}, pool)
    nums = []
    for line in answer_text.splitlines():
        line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s+", "", line)           # list markers
        line = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", line)                # links
        line = re.sub(r"\b(19|20)\d\d\s*[-\u2013]\s*(\d{2}|\d{4})\b", " ", line)   # year ranges such as 2016-20 or 2021-2025
        for m in NUM.findall(line):
            try:
                x = float(m.replace(",", ""))
            except ValueError:
                continue
            if 1990 <= x <= 2100 and float(x).is_integer():
                continue
            nums.append(x)
    bad = sorted({x for x in nums if not _match(x, pool)})
    return {"ungrounded": bad, "checked": len(nums)}
