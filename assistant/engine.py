"""One entry point for the UI and the tests: question in, structured response out.

    resp = Assistant().ask("Can Rajesh Purohit collaborate with Samuel Lalthazuala Rokhum?", state)

state is a plain dict kept in the Streamlit session: {"history": [...], "ctx": {...}}. The response is a dict:
  text (markdown), figures [plotly Figure], tables [DataFrame], evidence [records], tool_calls, results, needs_choice,
  grounding {"ungrounded": [...], "checked": n}, mode ("llm" | "rules").
"""
import re

import pandas as pd

from . import answers, grounding, llm, router
from .tools import run_tool


class Assistant:
    def __init__(self, use_llm=None):
        self.use_llm = llm.available() if use_llm is None else use_llm

    def ask(self, question, state=None):
        state = state if state is not None else {"history": [], "ctx": {}}
        ctx = state.setdefault("ctx", {})
        hist = state.setdefault("history", [])
        plan = router.route(question, ctx)          # entity extraction is always done: it resolves names and context
        if plan["clarify"]:
            resp = self._clarify(plan["clarify"])
            hist += [{"role": "user", "content": question}, {"role": "assistant", "content": resp["text"]}]
            return resp
        state["ctx"] = plan["ctx"]
        if self.use_llm:
            try:
                # earlier people / institutes are passed on only when the question refers back to them ("their", "him", "this paper");
                # a general question ("How many papers were retracted?") must not be narrowed to whoever was discussed before
                refers_back = bool(re.search(r"\b(they|them|their|theirs|both|he|she|his|her|him|this person|that person|those two|these two|"
                                             r"this paper|that paper|this institute|that institute|the same)\b", question.lower()))
                ctx_text = self._ctx_text(plan["ctx"]) if refers_back else ""
                text, results, calls = llm.ask(question, hist if refers_back else hist[-2:], ctx_text)
                if text.startswith(llm.INCOMPLETE) and plan["calls"]:
                    raise RuntimeError("the model did not finish within the allowed tool calls")
                if plan.get("fixes"):
                    text = "*Read " + ", ".join(f"'{a}' as '{b}'" for a, b in plan["fixes"]) + ".*\n\n" + text
                nc = next((r["needs_choice"] for r in results if r.get("needs_choice")), None)
                resp = self._pack(text, results, calls, "llm")
                resp["needs_choice"] = nc
                resp["grounding"] = grounding.check(text, results, question)
                resp["follow_ups"] = self.follow_ups(results)
                hist += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
                return resp
            except Exception as e:                  # API failure or unfinished analysis: fall back to the deterministic answers, and say so
                why = "it did not finish the analysis" if isinstance(e, RuntimeError) else f"it is unavailable ({type(e).__name__})"
                note = f"(The language model could not answer this one: {why}. Showing the built-in analysis instead.)\n\n"
        else:
            note = ""
        results, calls = [], []
        for tool, args in plan["calls"]:
            r = run_tool(tool, args)
            results.append(r)
            calls.append({"tool": tool, "args": args})
        if plan.get("fixes"):
            note += "*Read " + ", ".join(f"'{a}' as '{b}'" for a, b in plan["fixes"]) + ".*\n\n"
        if not results:
            text = router.HELP if not plan["ctx"].get("faculty") else "I could not map that to an analysis. " + router.HELP
        else:
            text = note + "\n\n---\n\n".join(answers.render(r) for r in results)
        resp = self._pack(text, results, calls, "rules")
        resp["needs_choice"] = next((r["needs_choice"] for r in results if r.get("needs_choice")), None)
        resp["grounding"] = {"ungrounded": [], "checked": 0, "note": "deterministic answer: every number is copied from the tool result"}
        resp["follow_ups"] = self.follow_ups(results)
        hist += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
        return resp

    @staticmethod
    def follow_ups(results):
        """Up to three next questions built from the names in the answer, so every suggestion is one the assistant can answer."""
        if not results or not results[0].get("ok", True):
            return []
        r = results[0]
        t, d = r["tool"], r.get("data") or {}
        out = []
        if t == "get_faculty_profile":
            n = d.get("name")
            out = [f"Suggest collaborators for {n}", f"Show the collaboration network around {n}"]
            if d.get("retracted_papers_not_counted"):
                out.append(f"Which papers of {n} were retracted?")
        elif t in ("assess_collaboration", "get_shortest_collaboration_path", "get_common_collaborators") and isinstance(d.get("a"), dict):
            a, b = d["a"]["name"], d["b"]["name"]
            out = ["Who are their mutual collaborators?", "Show the shortest path between them", f"Compare {a} and {b}"]
        elif t == "recommend_collaborators" and d.get("suggestions"):
            me = next((e["label"].split(" (")[0] for e in r.get("evidence", []) if e.get("type") == "faculty"), None)
            s = d["suggestions"][0]["name"]
            out = [f"Tell me about {s}"] + ([f"Can {me} collaborate with {s}?"] if me else [])
        elif t == "top_faculty" and d.get("rows"):
            out = [f"Tell me about {d['rows'][0]['name']}", f"Suggest collaborators for {d['rows'][0]['name']}"]
        elif t == "compare_institutes":
            out = ["Why does NIT Silchar publish more papers than the other institutes?", "Do the institutes collaborate mostly within their own region?",
                   "Which department has the highest median h-index?"]
        elif t == "regional_collaboration" and d.get("institutes"):
            x = d["institutes"][0]
            if x["top_home_partners"]:
                out = [f"Which faculty collaborate with {x['top_home_partners'][0]['partner']}?"]
            out.append("Which partner countries and Indian states raise the institutes' impact the most?")
        elif t == "department_stats" and d.get("rows"):
            x = d["rows"][0]
            out = [f"Who are the top faculty in {x['department']} at {x['institution']}?"]
        elif t == "retracted_papers" and d.get("rows"):
            names = [n for row in d["rows"] for n in row["faculty"].split("; ") if n]
            if names:
                out = [f"Tell me about {names[0]}"]
        return [q for q in out if q][:3]

    @staticmethod
    def _ctx_text(ctx):
        from .data import store
        bits = []
        if ctx.get("faculty"):
            f = store().faculty
            bits.append("faculty under discussion: " + "; ".join(f"{f.at[i, 'faculty_name']} ({f.at[i, 'institution']})" for i in ctx["faculty"] if i in f.index))
        if ctx.get("institute"):
            bits.append("institute: " + ctx["institute"])
        return "; ".join(bits)

    @staticmethod
    def _clarify(c):
        if not c["candidates"]:          # a name that matches nobody: say so, never answer about someone else instead
            text = (f"**I could not find '{c['query']}' among the verified faculty of MANIT Bhopal, NIT Jamshedpur and NIT Silchar.** "
                    "Check the spelling, or add the institute, for example *Name (NIT Silchar)*. People from other institutes are only known "
                    "as co-authors on joint papers; ask about their institute instead, for example *Which faculty collaborate with IIT Guwahati?*")
            return {"text": text, "figures": [], "tables": [], "evidence": [], "tool_calls": [], "results": [], "needs_choice": None,
                    "grounding": {"ungrounded": [], "checked": 0}, "mode": "rules"}
        lines =[f"- {x['name']} ({x['institution']}, {x['department']}; {x['papers']} papers, h-index {x['h_index']})" for x in c["candidates"]] if c["entity"] == "faculty" else [f"- {x}" for x in c["candidates"]]
        text = f"**'{c['query']}' matches more than one {c['entity']}.** Which one do you mean?\n\n" + "\n".join(lines) + "\n\nReply with the full name and institute, for example *Name (NIT Silchar)*."
        return {"text": text, "figures": [], "tables": [], "evidence": [], "tool_calls": [], "results": [], "needs_choice": c, "grounding": {"ungrounded": [], "checked": 0}, "mode": "rules"}

    @staticmethod
    def _pack(text, results, calls, mode):
        figs = [r["figure"] for r in results if r.get("figure") is not None]
        seen, ev = set(), []
        for r in results:
            for e in r.get("evidence", []):
                if (e["type"], e["id"]) not in seen:
                    seen.add((e["type"], e["id"]))
                    ev.append(e)
        tables = []
        for r in results:
            d = r.get("data", {})
            for k in ("rows", "suggestions", "table", "pairs", "papers", "communities"):
                if isinstance(d.get(k), list) and d[k] and isinstance(d[k][0], dict):
                    tables.append((k, pd.DataFrame(d[k])))
                    break
        links, seen_l = [], set()
        for r in results:
            for l in r.get("links", []):
                if l["hash"] not in seen_l:
                    seen_l.add(l["hash"])
                    links.append(l)
        return {"text": text, "figures": figs, "tables": tables, "evidence": ev, "links": links[:5], "tool_calls": calls, "results": results, "needs_choice": None, "mode": mode}
