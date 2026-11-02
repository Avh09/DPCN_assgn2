"""LLM orchestration with allowlisted tool use (Anthropic Messages API).

Configuration (never hard-coded, never in the browser): environment variable or Streamlit secret GEMINI_API_KEY (preferred; optional GEMINI_MODEL, default gemini-3.8-flash)
or ANTHROPIC_API_KEY (optional ANTHROPIC_MODEL, default claude-sonnet-5-5). The model can only call the tools in tools.TOOLS; their results are the only facts
it may use. Figures stay on the server side: the model receives a text summary of each tool result, the UI shows the figures.
"""
import json
import os

from .tools import TOOLS, run_tool

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 6
SYSTEM = """You are the research analyst for the DPCN Group 15 dashboard: verified faculty, papers, citations and collaboration networks of MANIT Bhopal, NIT Jamshedpur and NIT Silchar (OpenAlex data, 2016-2026; 2026 is partial).

Rules you must follow:
1. Answer ONLY from tool results. Call tools to get facts; never answer a data question from memory, never invent faculty, papers, collaborators, institutions, citations or graph links.
2. If a tool returns needs_choice (an ambiguous name), do not guess: ask the user which candidate they mean, listing the candidates.
3. If the data cannot answer something (for example faculty of an outside institute), say so plainly and say what data would be needed.
4. Separate observed facts, computed statistics, model predictions and interpretation. Link-prediction output is a ranking score, not a probability, unless a tool says it is calibrated. Never say a collaboration will happen.
5. Do not treat network measures as research quality. In-corpus PageRank/in-degree are mostly author self-citation, not influence; a citation in/out ratio below 1 is not low quality; the corpus h-index is a 2016-2026 h-index, not a career h-index.
6. Every number you write must appear in a tool result. Do not compute new figures yourself beyond trivial rounding.
7. Format substantial answers as: **Direct answer**, **Supporting evidence**, **Network interpretation**, **Limitations**. Keep simple questions short. A figure produced by a tool is shown to the user automatically; refer to it ("see the network figure") instead of describing coordinates.
8. Questions about collaboration with an OUTSIDE institute (IIITH, Jadavpur, any IIT/NIT/CSIR...) are answerable: call partner_institutes. Only say the data cannot answer when that tool finds nothing.
9a. For 'which countries/states/places raise or lower the institutes’ impact (FWCI)' call partner_place_impact; for 'who cites an institute more than it cites them', 'do private universities cite the institutes' call citation_give_take. State they are associations and that the private-university grouping is approximate.
9. For 'why does institute X publish more' or any yearly-output question call explain_output_difference. Give the measured drivers, then the institute_context_nirf figures (NIRF rank, PhD scholars, sponsored research, consultancy, lab equipment spend) as NIRF-reported context, noting they are partial per institute. Only teaching load, faculty qualifications and department-level labs are unavailable; never invent those. Say a measured gap or a NIRF figure shows context, not proven cause.
9b. partner_institutes also returns the NAMED co-authors from the outside institute (data.people): when asked to name professors/people from IIITH or any institute, list them from there, say they are co-authors on joint papers with the faculty of the three institutes (title unknown), and never claim the institute has no listed people. Do not narrow to one of the three institutes unless the user named it.
10. For 'who should I collaborate with / approach on topic X' call find_experts with synonym keywords: it matches PAPERS first, then ranks the faculty who wrote them. Never conclude that nobody works on a topic from a faculty-name or keyword search alone.
11. Tool results carry links into the dashboard; the UI shows them as buttons. When useful, say that the dashboard has more detail (year trends, partner profile) instead of describing links yourself.
12. Use the conversation context for follow-ups ("their mutual collaborators") by calling tools with the names already resolved."""


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")


def _gemini_key():
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def available():
    return bool(_gemini_key() or os.environ.get("ANTHROPIC_API_KEY"))


def _tool_specs():
    return [{"name": n, "description": d, "input_schema": s} for n, (_, d, s) in TOOLS.items()]


def _payload(res, limit=14000):
    d = {k: res.get(k) for k in ("ok", "tool", "summary", "data", "coverage", "needs_choice")}
    t = json.dumps(d, default=str)
    return t if len(t) <= limit else t[:limit] + "...[truncated]"


def _gemini_call(client, contents, cfg, tries=3):
    """Retry transient Google-side failures (5xx / rate limit) with a short backoff."""
    import time
    from google.genai import errors
    for i in range(tries):
        try:
            return client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=cfg)
        except (errors.ServerError, errors.APIError) as e:
            if i == tries - 1 or getattr(e, "code", 500) not in (429, 500, 502, 503, 504):
                raise
            time.sleep(2 * (i + 1))


def _ask_gemini(question, history, ctx_text=""):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_gemini_key(), http_options={"timeout": 45000})
    decls = [types.FunctionDeclaration(name=n, description=d, parameters_json_schema=sc) for n, (_, d, sc) in TOOLS.items()]
    cfg = types.GenerateContentConfig(system_instruction=SYSTEM, tools=[types.Tool(function_declarations=decls)], max_output_tokens=2500,
                                      automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
    contents = [types.Content(role="user" if m["role"] == "user" else "model", parts=[types.Part(text=m["content"])]) for m in history[-8:]]
    contents.append(types.Content(role="user", parts=[types.Part(text=(f"[context from earlier turns: {ctx_text}]\n" if ctx_text else "") + question)]))
    results, calls = [], []
    for _ in range(MAX_TOOL_ROUNDS):
        resp = _gemini_call(client, contents, cfg)
        cand = resp.candidates[0].content if resp.candidates else None
        parts = (cand.parts or []) if cand else []
        fcs = [p.function_call for p in parts if p.function_call]
        if not fcs:
            return "".join(p.text for p in parts if p.text), results, calls
        contents.append(cand)
        outs = []
        for fc in fcs:
            args = dict(fc.args or {})
            r = run_tool(fc.name, args)
            results.append(r)
            calls.append({"tool": fc.name, "args": args})
            outs.append(types.Part.from_function_response(name=fc.name, response={"result": _payload(r)}))
        contents.append(types.Content(role="user", parts=outs))
    return "I could not finish the analysis within the allowed number of tool calls; here is what I found so far.", results, calls


def ask(question, history, ctx_text=""):
    if _gemini_key():
        return _ask_gemini(question, history, ctx_text)
    return _ask_anthropic(question, history, ctx_text)


def _ask_anthropic(question, history, ctx_text=""):
    """history: [{"role": "user"|"assistant", "content": str}] of earlier turns. Returns (answer_text, [tool results], [tool calls])."""
    import anthropic
    client = anthropic.Anthropic()
    messages = [{"role": m["role"], "content": m["content"]} for m in history[-8:]]
    messages.append({"role": "user", "content": (f"[context from earlier turns: {ctx_text}]\n" if ctx_text else "") + question})
    results, calls = [], []
    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.messages.create(model=MODEL, max_tokens=1800, system=SYSTEM, tools=_tool_specs(), messages=messages)
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            return "".join(b.text for b in resp.content if b.type == "text"), results, calls
        messages.append({"role": "assistant", "content": resp.content})
        outs = []
        for u in uses:
            r = run_tool(u.name, dict(u.input))
            results.append(r)
            calls.append({"tool": u.name, "args": dict(u.input)})
            outs.append({"type": "tool_result", "tool_use_id": u.id, "content": _payload(r)})
        messages.append({"role": "user", "content": outs})
    return "I could not finish the analysis within the allowed number of tool calls; here is what I found so far.", results, calls
