"""AI Research Assistant for the Group 15 research-network dashboard.

Design: an LLM (optional) turns a natural-language question into calls of ALLOWLISTED analysis tools (tools.py) that read the
real tables and graphs (data.py). The tools return structured results with evidence, coverage notes and optional figures;
the answer is written only from those results (llm.py) and checked for ungrounded numbers (grounding.py). Without an API
key a deterministic router (router.py) answers the same questions from the same tools.
"""
