"""LLM orchestration with allowlisted tool use (Anthropic Messages API).

Configuration (never hard-coded, never in the browser): environment variable or Streamlit secret GEMINI_API_KEY (preferred; optional GEMINI_MODEL, tried first, then gemini-3.5-flash-lite, gemini-3.5-flash, gemini-3.8-flash)
or ANTHROPIC_API_KEY (optional ANTHROPIC_MODEL, default claude-sonnet-5-5). The model can only call the tools in tools.TOOLS; their results are the only facts
it may use. Figures stay on the server side: the model receives a text summary of each tool result, the UI shows the figures.
"""
import json
import os

from .tools import TOOLS, run_tool

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
MAX_TOOL_ROUNDS = 6
INCOMPLETE = "I could not finish the analysis"
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
12. Use the conversation context for follow-ups ("their mutual collaborators") by calling tools with the names already resolved.
13. Retracted and withdrawn papers are excluded from every metric. For questions about retractions call retracted_papers; say that a retraction does not by itself mean the authors did something wrong.
14. get_faculty_profile may return affiliation_check (a person who moved to another institute) and retracted_papers_not_counted: mention them when relevant, with the sources given.
15. Pass only the filters the user asked for (field, department, years, scope, institute). Do not add a filter on your own, for example a field taken from the person's department: it silently narrows the answer.
20. Answer each question as asked. Earlier turns matter only when the question refers back to them (they, their, him, this paper). A general question such as 'How many papers were retracted?' or 'the top PageRank paper' is about all three institutes, never only the person or institute discussed before.
21. Do not explain why a data field has its value unless a tool says why (e.g. a faculty_status of 'current'); use the explanation the tool gives.
22. For 'can A collaborate with B', open with the tool's relationship field (e.g. 'no joint paper yet; weakly connected'), not a bare 'Yes': anyone can collaborate, the question is how likely and well-matched it is. Describe research overlap with topic_overlap and topic_cosine, follow how_to_read (a high field_cosine alone is not shared research), and report the model with in_top_suggested_pairs.
23. Write for a reader, not a programmer: never show internal field names (topic_cosine, field_cosine, in_top_suggested_pairs, hop_distance) or code formatting for numbers; say 'topic similarity 0.087', 'broad-field similarity 0.955'.
24. For any question about a journal or conference ('who publishes in X', 'papers in X', 'how many papers in X', 'top faculty in journal X') call journal_papers ONCE with the whole name as the user wrote it (a journal name can contain 'and' or '&': never split it into two journals); it corrects spelling against the journal names in the data. If the context gives the matched journal name, use exactly that name. Never say a journal is not in the data without calling journal_papers first, and never answer a journal question with find_experts (a keyword search counts topic matches, not papers in the journal). If journal_papers returns needs_choice, list the options and ask which one is meant. Describe only what journal_papers returns (counts, faculty, institutes, citations, top papers); do not characterise the journal's topics or say why people publish there.
18. Never compute new figures (sums, differences, remainders): use the fields the tools return, e.g. own_state_and_region_% and national_body_or_unmapped_%. In recommend_collaborators, connected_in_network false (hops null) means there is no path at all: say 'not connected yet', never give a hop count.
19. find_experts reports papers_matched_per_term: prefer specific terms; a broad term (e.g. 'renewable energy') can match off-topic papers.
17. Keep the interpretation consistent with the tool data. If a shortest path exists, the two people are in the same connected network: call them distant (n steps apart), never 'disconnected' or 'separate clusters'. Only say 'disconnected' when the tool reports no path.
16. For 'do the institutes collaborate within their region / state / nearby' call regional_collaboration; for department rankings or comparisons call department_stats. Mention the caveats these tools return."""


# Google retires model names, and a model can be briefly overloaded (503): try these in order. GEMINI_MODEL (env or secret) goes first.
# flash-lite first: on the free tier it answers in 1-2 s and picks the right tools; the larger models are often rate-limited (429) or overloaded (503).
# Accuracy does not depend on the model size: the model only chooses allowlisted tools and writes up their results, which grounding.py then checks.
GEMINI_FALLBACKS = ["gemini-3.5-flash-lite", "gemini-3.5-flash", "gemini-3.8-flash"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL") or GEMINI_FALLBACKS[0]
LAST_MODEL = {"name": None}          # the model that answered last (shown in the UI caption)


_BUSY = {}                            # model -> time until which it is skipped after an overload / rate-limit failure


def _gemini_models():
    import time
    first = os.environ.get("GEMINI_MODEL") or GEMINI_MODEL
    order = [first] + [m for m in GEMINI_FALLBACKS if m != first]
    if LAST_MODEL["name"] in order:       # keep using the model that answered last
        order.remove(LAST_MODEL["name"])
        order.insert(0, LAST_MODEL["name"])
    ready = [m for m in order if _BUSY.get(m, 0) <= time.time()]
    return ready or order


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


def _gemini_call(client, contents, cfg, tries=2):
    """Try each model in turn: a retired name (404) moves on at once; overload or rate limit (429/5xx) is retried briefly, then the next model."""
    import time
    from google.genai import errors
    last = None
    for model in _gemini_models():
        for i in range(tries):
            try:
                resp = client.models.generate_content(model=model, contents=contents, config=cfg)
                LAST_MODEL["name"] = model
                return resp
            except (errors.ServerError, errors.APIError) as e:
                last = e
                code = getattr(e, "code", 500)
                if code == 404:
                    break                       # this model name no longer exists: next model
                if code not in (429, 500, 502, 503, 504):
                    raise                       # bad key, bad request: no point trying other models
                if i < tries - 1:
                    time.sleep(2)
        _BUSY[model] = time.time() + 300        # overloaded / rate-limited: skip it for five minutes
    raise last


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
    return INCOMPLETE + " within the allowed number of tool calls; here is what I found so far.", results, calls


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
    return INCOMPLETE + " within the allowed number of tool calls; here is what I found so far.", results, calls
