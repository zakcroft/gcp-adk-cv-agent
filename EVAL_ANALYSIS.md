# Eval Analysis Log

Running log of dataset-experiment results and what they mean. Newest first.
Scores: correctness / faithfulness / hallucination / completeness /
misrepresentation / tailoring (all 0-1, higher is better).

## 2026-08-05 — run `verifier-in-loop-new-misrenpresentaion-judge` (rerun, all 8 items)

Experiment `1b49ca223f2ec0db`. First full clean run with the verifier in the
loop; no 429 failures, no hangs.

| Item | corr | faith | hall | comp | misrep | tailor | Analysis |
|---|---|---|---|---|---|---|---|
| case-senior-frontend | 1.0 | 1.0 | 0.9 | 1.0 | 1.0 | 0.9 | Clean pass. Well-matched CV/JD; minor verb-strengthening only. |
| case-agentic-ai | 0.8 | 1.0 | 0.9 | 1.0 | 1.0 | 0.9 | Clean pass. Correctness dip is phrasing/structure drift vs expected output, not a fact issue. |
| case-senior-match | 1.0 | 1.0 | 0.9 | 1.0 | 1.0 | 0.72 | Mild summary overstatement ("specialising in", "designing REST APIs") — small grounding-gate residue. |
| case-overqualified | 0.8 | 1.0 | 0.6 | 1.0 | 1.0 | 0.67 | The one real defect: overemphasises incident response / "methodical frameworks" beyond the source. Stays under the misrepresentation bar (seniority kept — the old demotion bug is gone) but embellishes. Grounding-gate territory. |
| case-career-switch | 0.7 | 1.0 | 0.9 | 1.0 | 1.0 | **0.35** | Honest-by-design low: no real SQL/Python/Power BI evidence in the source, so tailoring can't close the gap without inventing. Verifier holds; judge records the gap. |
| case-sparse-cv | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | **0.3** | Honest-by-design low: near-verbatim copy of the thin CV. Hallucination 1.0 *because* it refused to pad. Fix is presenter phase 2 elicitation, not the loop. |
| nofiles-improve_cv_missing_files | 1.0 | — | — | — | — | — | Correct "please upload" reply. |
| nofiles-list_files | 1.0 | — | — | — | — | — | Correct. |

**Read:** truth metrics (faithfulness / misrepresentation / completeness) are
1.0 on every case — the verifier truth gate is holding, including on the two
adversarial cases it was built for. Low tailoring on career-switch and
sparse-cv is the honesty trade-off working as designed. The remaining defect
class is mid-level embellishment (overqualified hallucination 0.6) that an
LLM verifier structurally lets through.

**Next step:** build the deterministic grounding gate (technology/term diff
of output vs source CV) — this run is the evidence for it.

## 2026-08-03 — run `hallucination-judge-v2` (pre-verifier baseline, all 7 items)

Experiment `7c43c3408980c3a8`. Last complete run BEFORE the verifier truth
gate — the critic still held `exit_loop`, and there was no misrepresentation
judge yet. This is the baseline the verifier was built against.

| Item | corr | faith | hall | comp | misrep | tailor | Analysis |
|---|---|---|---|---|---|---|---|
| case-senior-frontend | 1.0 | 1.0 | 0.8 | 1.0 | n/a | 0.93 | Clean pass even pre-verifier; well-matched cases were never the problem. |
| case-agentic-ai | 0.9 | 1.0 | 0.9 | 1.0 | n/a | 0.86 | Clean pass. |
| case-senior-match | 1.0 | 0.8 | **0.6** | 1.0 | n/a | 0.6 | Inflation: "specialising in", "scalable backend systems", added Express as a fact. Faithfulness dips below 1 — invention got through. |
| case-overqualified | 0.7 | 0.8 | **0.1** | 1.0 | n/a | 0.7 | The headline failure: staff engineer rewritten as "seeking a Junior Support Engineer role" — seniority misrepresented to fit the JD. Motivated the verifier. |
| case-career-switch | 0.8 | 0.9 | 0.8 | 1.0 | n/a | 0.45 | Ungrounded analytics vocabulary added ("data-driven", "statistical significance") to fake the career bridge. |
| nofiles-improve_cv_missing_files | 1.0 | — | — | — | — | — | Correct. |
| nofiles-list_files | 1.0 | — | — | — | — | — | Correct. |

**Read:** under tailoring pressure the critic-gated loop invented — three of
five CV cases shipped with faithfulness < 1.0 or hallucination ≤ 0.6.
Compare with 08-05 above: after the verifier took `exit_loop`, faithfulness
and misrepresentation went to 1.0 across the board, and the cost surfaced
honestly as low tailoring on the mismatch cases instead of hidden invention.
