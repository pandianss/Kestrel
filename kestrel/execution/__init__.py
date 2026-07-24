"""The execution plane (paper backend) — deterministic exits and honest fills.

Scope: the end-of-day positional slice (D-16). Entries are decided upstream (a
factor, later an LLM overlay); this plane owns what happens *after* an entry —
the deterministic exit path (D-07, closing G-28) and a cash/margin model
(closing G-29) — on daily bars. The tick-level microstructure in doc 07 §4.1
is the live-phase model; here fills are daily-bar granularity with conservative
gap handling.
"""
