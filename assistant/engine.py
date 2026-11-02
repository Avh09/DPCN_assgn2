"""One entry point for the UI and the tests: question in, structured response out.

    resp = Assistant().ask("Can Rajesh Purohit collaborate with Samuel Lalthazuala Rokhum?", state)

state is a plain dict kept in the Streamlit session: {"history": [...], "ctx": {...}}. The response is a dict:
  text (markdown), figures [plotly Figure], tables [DataFrame], evidence [records], tool_calls, results, needs_choice,
  grounding {"ungrounded": [...], "checked": n}, mode ("llm" | "rules").
"""
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
                ctx_text = self._ctx_text(plan["ctx"])
                text, results, calls = llm.ask(question, hist, ctx_text)
                nc = next((r["needs_choice"] for r in results if r.get("needs_choice")), None)
                resp = self._pack(text, results, calls, "llm")
                resp["needs_choice"] = nc
                resp["grounding"] = grounding.check(text, results)
                hist += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
                return resp
            except Exception as e:                  # API failure: fall back to the deterministic answers, and say so
                note = f"(The language model is unavailable: {type(e).__name__}. Showing the deterministic analysis instead.)\n\n"
        else:
            note = ""
        results, calls = [], []
        for tool, args in plan["calls"]:
            r = run_tool(tool, args)
            results.append(r)
            calls.append({"tool": tool, "args": args})
        if not results:
            text = router.HELP if not plan["ctx"].get("faculty") else "I could not map that to an analysis. " + router.HELP
        else:
            text = note + "\n\n---\n\n".join(answers.render(r) for r in results)
        resp = self._pack(text, results, calls, "rules")
        resp["needs_choice"] = next((r["needs_choice"] for r in results if r.get("needs_choice")), None)
        resp["grounding"] = {"ungrounded": [], "checked": 0, "note": "deterministic answer: every number is copied from the tool result"}
        hist += [{"role": "user", "content": question}, {"role": "assistant", "content": text}]
        return resp

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
        lines = [f"- {x['name']} ({x['institution']}, {x['department']}; {x['papers']} papers, h-index {x['h_index']})" for x in c["candidates"]] if c["entity"] == "faculty" else [f"- {x}" for x in c["candidates"]]
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
