# How to review Kestrel

**Last updated:** 2026-07-22

This repo is design documentation for a system that does not exist yet. Its purpose is to be **attacked before it is built**, when a finding costs an edit instead of a rewrite — or a loss.

If you are an agent or a human doing a review pass, this file tells you what is useful and what is noise.

---

## What we want

**In rough order of value:**

1. **Facts that have changed.** This documentation restates external facts — broker limits, API behaviour, regulation, pricing. Those go stale silently. The 2026-07-22 review found five errors, and three were facts that were true when written. **Check the [facts with an expiry date](../README.md#facts-with-an-expiry-date) table first** — it is the highest hit-rate work in the repo.
2. **Gaps in the lifecycle, not the architecture.** The two 🔴 gaps that review found (no exit path, no margin model) were both invisible when reading component-by-component. They appeared when tracing *one position from entry to close*. Trace flows, not boxes.
3. **Contradictions between documents.** Doc 05 said doing nothing was always safe; doc 07 implied otherwise. Both were internally consistent. Cross-document claims are where inconsistency hides.
4. **Undefined behaviour where the "how" is hard.** The design says *what* in many places. Flag the ones where *how* is genuinely non-trivial — those are unspecified, not merely unwritten.
5. **Things a five-line calculation would settle.** Gap G-16 sat open for want of arithmetic anyone could have done. If a question can be closed on paper, close it on paper.

## What we don't want

- **Style, formatting, and wording preferences** unless they cause a misreading.
- **Restating a gap the register already has** without adding information. Adding evidence, a number, or a consequence to an existing gap **is** valuable — say so explicitly.
- **Generic advice** ("consider adding tests", "think about security"). Point at a specific place with a specific consequence.
- **Findings without a failure scenario.** If you cannot say what breaks and when, it is an observation, not a finding.

---

## Where to start

| If you have… | Read |
|---|---|
| 10 minutes | [README](../README.md) → [doc 11 register table](11-open-questions-and-gaps.md#register-at-a-glance) |
| An hour | Add [doc 02](02-kite-connect-constraints.md) (constraints) and [doc 03](03-architecture.md) (architecture) |
| A domain background in Indian markets | [doc 02](02-kite-connect-constraints.md) and [doc 07](07-execution-plane.md) — the highest density of things that can be wrong in a costly way |
| A distributed-systems background | [doc 03](03-architecture.md) §2.1, [doc 06](06-data-plane.md) §2.1, [doc 10](10-prerequisites-and-ops.md) §3.1 — failure modes and recovery |
| Web access and an hour | Verify the [facts with an expiry date](../README.md#facts-with-an-expiry-date) table. Genuinely the best use of it |

---

## Adding a gap

Add to [doc 11](11-open-questions-and-gaps.md): a row in the register table **and** a section in the matching lettered part. Next free ID — never reuse one, even for a deleted gap.

```markdown
### G-NN <severity> — <one-line title> *(new)*
**Status:** OPEN · **Resolve by:** <phase or milestone>

<What is missing, wrong, or undecided. Two or three sentences.>

*Why it matters:* <the concrete failure. What breaks, when, and how expensive it is
to find out later. If you cannot fill this in, reconsider whether it is a finding.>

*Evidence:* <link to the source, or the calculation, or the two documents that
disagree. Assertions without evidence are the thing this register exists to remove.>

*Proposed direction:* <a suggestion, explicitly not a decision. Someone else decides.>
```

**Severity:** 🔴 blocker (must resolve before or at its phase; can invalidate work already done) · 🟠 significant (real cost if missed, not fatal) · 🟡 to firm up (known, bounded, needs a decision).

**Calibration:** 🔴 means *building further on this produces work that has to be thrown away or results that cannot be trusted*. G-28 was 🔴 because paper P&L generated without an exit path would have been meaningless. If in doubt, propose 🔴 and argue for it — under-rating is more expensive than over-rating.

**Also update:** the register table, the change log at the bottom, and the counts in "Where the register stands."

---

## Changing an existing gap

Never delete or silently rewrite one. The register's history is part of its value — it shows what we believed and when.

- **Adding evidence:** append a dated note (`*2026-07-22 note:* …`). Keep the original text.
- **Closing:** set `Status: CLOSED`, and **record the resolution** — what was checked, what was found, what changed. A gap closed without a recorded reason is indistinguishable from one that was forgotten.
- **Accepting:** set `Status: ACCEPTED`, say what risk we are carrying and why it is tolerable, and note what would force a revisit.
- **Re-rating:** state the old severity, the new one, and why. See G-17.

---

## Adding or challenging a decision

Design decisions live in [doc 13](13-decision-log.md), separately from gaps. A gap is *"we don't know"*; a decision is *"we chose, and here's what we gave up."*

To challenge one, work against the recorded **Cost** and **Reversibility** rather than restating the alternatives. The useful argument is not "Rust is heavy" — D-02 already says so — but "here is a cost that was not accounted for," or "here is why reversal is more expensive than the log claims."

If you find a decision the project is making **by default rather than deliberately**, add it with `Status: OPEN`. D-09 is the model: build order was never actually chosen, only assumed.

---

## Verifying a fact

Every external fact should carry a source and a verification date. When you check one:

- ✅ **Correct:** add or refresh `✅ *(verified YYYY-MM-DD)*` with a link to the primary source.
- ❌ **Wrong:** correct it, and **leave a note saying what it used to say.** A silent correction hides that the document was trustable-looking and wrong — which is itself the finding.
- ⚠️ **Unverifiable:** mark it ⚠️, say where you looked, and state what the design should do if the assumption fails. Doc 02 §5's historical day-caps are the pattern: unpublished, so the backfill discovers them at runtime instead of hard-coding them.

**Prefer primary sources.** Official docs, the broker's own announcements, regulator circulars. Forum posts and blogs are leads, not evidence — and note that this documentation's own restatement of a fact is *not* a source.

**Check [`regulatory/`](../regulatory/INDEX.md) first — the circulars are already archived**, with a claim→source map. Grep the local `.txt` extractions rather than re-researching; it is faster and it is the actual text.

**Compliance facts require a primary source, full stop.** A 2026-07-22 review recorded that API orders below a rate threshold "are not tagged as algo." That was never true — it came from a secondary summary that compressed *"no strategy registration required"* into *"not treated as an algo."* The distinction is the entire obligation. Had it shipped, every order would have gone out untagged.

Two lessons worth generalizing:

- **The expiry-date discipline does not catch this class of error.** Verification dates catch facts that *went* stale; they do nothing for a fact that was misread on first reading. A ✅ marker means "checked against a source," not "correctly understood."
- **Watch for compressed negations.** "X is not required" and "X does not apply" are different claims, and summaries routinely collapse them. When a fact removes an obligation, go find the sentence that removes it — in the circular, not in a blog post about the circular.

---

## A note on scope

This design is deliberately **strategy-agnostic plumbing**. The trading edge is not defined (G-01), and that is the largest known gap in the project.

That means "this won't make money" is true but not actionable — it is already recorded. What *is* actionable: **anywhere the missing strategy is quietly load-bearing.** Places where the design has committed to something that only makes sense for a particular kind of strategy, without saying so. Those commitments are the ones that will be expensive to undo when a strategy finally arrives.
