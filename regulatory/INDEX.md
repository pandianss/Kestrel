# Regulatory & Reference Sources

**Last updated:** 2026-07-22

Primary source documents this design's compliance claims rest on. Kept in-repo because **the design has already been wrong twice from working off secondary summaries** — once on algo tagging, once on algo-provider status (doc 11 changelog, passes four and five). A blog post's paraphrase is not a source.

> ⚠️ **These are archival copies, not the authority.** The authority is whatever SEBI, NSE, or Zerodha publishes *today*. Re-fetch before relying on any of it for a live decision — regulation moves and Zerodha's terms are not versioned publicly. Nothing here is legal advice.

---

## What's here

### `sebi/` — the framework

| File | Reference | Date | What it settles |
|---|---|---|---|
| `SEBI-CIR-2025-0000013_…_safer-participation-retail-algo.pdf` | `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/0000013` | 2025-02-04 | **The framework itself.** §I(c) family carve-out · §I(d) OAuth-only, 2FA, static IP, no open APIs · §II(b) tagging · §IV(a)(iii) exchange kill switch · §V white-box vs black-box categorisation |
| `SEBI-CIR-2025-132_…_timeline-extension.pdf` | `SEBI/HO/MIRSD/MIRSD-PoD/P/CIR/2025/132` | 2025-09-30 | **The timeline.** Milestones Oct–Dec 2025, mock session by 2026-01-03, onboarding bar from 2026-01-05, **full applicability w.e.f. 2026-04-01** |

### `nse/` — the operational mechanics

| File | Reference | Date | What it settles |
|---|---|---|---|
| `NSE-INVG-67858_…_algo-implementation-standards.pdf` | `NSE/INVG/67858` (Ref. 471/2025) | 2025-05-05 | **How it actually works.** §A static IP rules · §B TOPS mechanics · §F broker may set a lower client limit · §G tagging below *and* above threshold · §I 5-year audit trail, OAuth, 2FA |

### `zerodha/` — the licence and the cost basis

| File | Source | What it settles |
|---|---|---|
| `kite-connect-terms_2026-07-22.md` | kite.trade/terms | **The data licence.** Public-display limit · India-only scope · the database-building clause · delete-on-termination |
| `zerodha-charges_2026-07-22.md` | zerodha.com/charges | **Transaction cost rates** feeding the P&L model |

`.txt` files alongside PDFs are `pdftotext -layout` extractions — greppable, but **the PDF is the authority** if they ever disagree.

---

## Claim → source map

Every compliance claim in the design, and the document that backs it. If you change a claim, change this table.

| Claim | Where it's used | Source |
|---|---|---|
| Framework in force **1 April 2026** | doc 02 §9, README expiry table | SEBI `CIR/2025/132` ¶8 |
| **Every** API order tagged — below *and* above threshold | doc 02 §9.3, doc 07 §2 (`algo_id` mandatory) | NSE `INVG/67858` §G |
| Registration only **above** the threshold | doc 02 §9.1, G-02 | SEBI `CIR/2025/0000013` §I(c) |
| **Family** = self, spouse, dependent children, dependent parents | doc 02 §9.4, G-02, glossary | SEBI `CIR/2025/0000013` §I(c) |
| Self + family ⇒ **not an algo provider** | doc 02 §9.4, G-02 | SEBI §I(c) + §III |
| TOPS = **10 OPS**, adjustable on notice | doc 02 §9.5, doc 07 §3.3 | NSE §B.2, §F |
| Measured on the **calendar clock second** | doc 07 §3.3 (limiter design) | NSE §B.2 |
| **Broker may set a lower client-level limit** | doc 02 §9.5, G-39, doc 09 Phase 0 | NSE §F |
| Breach ⇒ **broker rejects** excess orders | doc 02 §9.5, doc 07 §3.3 | NSE §B.5 |
| Scope ambiguity: "per exchange" vs "per exchange/segment" | doc 02 §9.5 | NSE §B.2 **vs** §F — *the circular contradicts itself* |
| Up to **two** static IPs; change **once/week**; family sharing | doc 02 §9.1, §9.5, doc 10 §1 | NSE §A.2, §A.6, §A.7 |
| **Exchange holds a kill switch** on our algo ID | G-40, doc 07 | SEBI §IV(a)(iii) + footnote 4 |
| Black-box algos ⇒ Research Analyst registration; re-register on logic change | G-41 | SEBI §V(a)(ii) |
| **OAuth-only**, 2FA on API access | doc 02 §1, §9.1 | SEBI §I(d), NSE §I(c)(d) |
| Audit trail retained **≥ 5 years** | doc 02 §9.5 | NSE §I(a) |
| No display **"to the public at large"** | G-15, doc 10 §4 | Kite ToS §2 |
| Licence is **India-only** | doc 03 §5, doc 10 §3, G-15 | Kite ToS §1 |
| "Build databases" clause — **ambiguous** | doc 02 §9.7, G-15 🔴 | Kite ToS §4(b) |
| Delete stored content **on termination** | doc 02 §9.7, G-15 | Kite ToS §9(b) |

---

## Still missing

Wanted and not obtained. NSE's archive rejected automated fetches for these — they return an HTML error page with a `.pdf` URL, so **verify any download is a real PDF** (`file x.pdf`) before trusting it.

| Document | Why it matters | Where to get it |
|---|---|---|
| Exchange **operational modalities**, 2025-07-22 | Referenced by SEBI `CIR/2025/132` ¶2 as the detailed mechanics; may answer the TOPS scope contradiction | NSE/BSE circular archives |
| `NSE/MSD/67753`, 2025-04-29 | Consolidated IBT/STWT/RMS circular that `INVG/67858` §H defers to | NSE archive |
| `NSE/INVG/66524`, 2025-02-05 | NSE's initial adoption of the SEBI framework | NSE archive |
| SEBI circular, 2025-07-29 | Intermediate extension — **superseded** by `CIR/2025/132`, low value | sebi.gov.in |
| NSE **risk parameter (SPAN) files** | Would inform G-29's margin model | NSE daily risk file downloads |
| Zerodha **Kite Connect API FAQ** | Cited for the data-redistribution position; not archived as a file | support.zerodha.com |

---

## Maintenance

**Re-fetch when:** an exchange gives notice of a TOPS change · Zerodha updates its terms or charges · before any live go/no-go · at the cadence in the README's *Facts with an expiry date* table.

**When you re-fetch:** keep the old copy, add the new one with its retrieval date, and note what changed in doc 11's changelog. The point of an archive is being able to answer *"what did it say when we built this?"*

**Naming:** `ISSUER-REFERENCE_YYYY-MM-DD_short-description.ext` — sortable, self-describing, no ambiguity about which circular is which.

**Two verification habits, both learned the hard way:**

1. **Check the download is real.** `file x.pdf` — NSE returns HTML error pages at `.pdf` URLs, and three "successful" downloads in this batch were error pages. A zero-page PDF that greps clean is worse than a failed download.
2. **Quote from the archived text, not from a summary of it.** Both prior sourcing errors came from trusting a paraphrase. And while writing this index a bad grep pattern briefly suggested two real ToS clauses were fabricated — **having the file locally settled it in seconds.** That is the whole argument for this folder.
