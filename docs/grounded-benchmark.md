# Grounded adapter evaluation

This experiment evaluates an opt-in adapter that replaces model-written quotations with document-bound passage IDs and requires requirement links and failure scenarios for major findings. The underlying two EGM personas, model group, deterministic seeded matcher, and original hard dataset are preserved.

The six previously observed cases are development cases. Their before/after comparison uses the earlier archived EGM run, so it is exploratory and not a concurrent experiment. A new inventory-reservation pair compares legacy and grounded modes within this run. Each mode receives two independent reviews, a 3,000-token response limit, one permitted correction per review, and the same `gpt-oss-120b` routing group. Actual tokens and provider routes can differ. Source snapshots, schedule, fixtures, and grading were frozen before the first live request.

## Development results

| Metric across the same six designs | Earlier legacy EGM | Grounded EGM |
| --- | ---: | ---: |
| Seeded faults detected | 6/6 (100%) | 6/6 (100%) |
| Completed reviews | 6/6 | 6/6 |
| Unsupported major/blocker findings, assistant audit | 10 | 7 |
| All major/blocker findings, including duplicates | 22 | 18 |
| Minor findings | 5 | 25 |
| First-response contract validity | 10/12 (83.3%) | 8/12 (66.7%) |
| Final contract validity after correction | 12/12 | 12/12 |
| Correction calls | 2 | 4 |
| Total HTTP attempts | 14 | 16 |
| Reported tokens | 53,620 | 83,518 |

Unsupported major escalations decreased **30%** (10 to 7) in this assistant audit; planted-flaw detection changed by **0 percentage points**. Total tokens increased **55.8%**, and minor comments increased from 5 to 25. Thus this is a narrower improvement in major-warning calibration and inspectability, with worse cost and first-pass contract compliance. It does not establish an overall quality improvement, and legacy remains the default.

The four grounded correction calls concern missing requirement/counterexample links, rather than invented quotations. Stricter output requirements create new failure modes even when passage selection is reliable. The harness catches and preserves these failures instead of silently accepting incomplete arguments.

## Audit method

Automatic detection requires a localized citation and all predeclared causal concepts for each planted fault. Repeated findings count once per planted fault. Failed reviews stay in the denominator and deliver zero verified detections. Every major/blocker finding is then inspected against the supplied requirements and failure model. This is an assistant audit, not independent or blinded human adjudication.

An unsupported escalation is a major/blocker whose claimed execution contradicts an explicit mechanism, assumes an additional requirement, or fails to demonstrate the claimed violation. This label evaluates the emitted argument; it does not prove the design has no other flaw. Counts are findings, including repeated findings across reviewers, rather than counts of independent bugs. Nits are retained in raw results but are not counted as major escalations.

## Development-case audit

### Corrected worker: case-26

The original EGM run escalated alternatives and risk-documentation preferences without a functional counterexample. The grounded run instead escalates unspecified claim isolation and worker clock drift. Its first argument assumes non-atomic claims despite an explicit atomic-claim guarantee; completion also checks epoch, owner, status, and database-time expiry. Its second argument acknowledges that the stale completion fails that check, then asserts a hypothetical double publication without showing how it bypasses the guard. Both are unsupported major warnings.

This counterpart still contains the previously documented, unseeded retry-accounting flaw: persisting the attempt count after sending leaves a crash gap that can exceed the physical attempt bound. Neither EGM run identifies it. The fixture is preserved unchanged and must not be described as wholly defect-free.

### Defective feed: case-17

Grounded findings demonstrate the tenant-independent cache key and out-of-order commit/cursor faults. The stored scenarios correctly explain cross-tenant disclosure and a late commit falling below the returned cursor. The earlier run also escalated cache staleness as a separate permanent-omission problem; finite cache expiry does not establish that independent failure. The new run retains the two real seeds without that extra major warning.

### Corrected expiry: case-91

The original run incorrectly treated the 72-hour replay guarantee as a prohibition on 73-hour retention and added template-oriented complaints. The grounded run avoids that minimum/maximum reversal but emits three different unsupported major warnings:

- It asks how a client obtains a new signing key. The design assigns the old key version to the event, has the server load and use it, and retains receiver verification keys. The proposed client-signing scenario changes the stated actors and protocol.
- It assumes a 12-minute outage and loss of pending jobs. The supplied failure scope accepts a ten-minute outage and explicitly makes jobs durable; no described mechanism establishes that data-loss claim.
- It assumes concurrent duplicate submissions return a generic unique-constraint error. The design explicitly says the constraint resolves concurrency and requires atomic digest comparison and replay; the finding supplies an implementation failure that is not stated.

One initial critic response omitted a required requirement/failure link. Validation rejected it, and the single correction produced a structurally valid response. This demonstrates contract enforcement, not semantic correctness: the corrected arguments still need the audit above.

### Defective worker: case-43

Both modes find stale-worker publication and the callback crash gap. The grounded critic's stale-worker example contains a timing mistake: it describes a 30-second expiry but a takeover at 25 seconds. The underlying missing-guard finding is valid, and the comprehension reviewer gives a valid expiry/takeover scenario; the erroneous critic example is retained as a witness-quality defect.

The grounded critic also escalates a nine-minute database outage into permanently stuck running jobs, even though the design explicitly rescans running jobs with expired leases. That argument is unsupported. Its initial alternatives complaint lacked a requirement/failure link; after the permitted correction it became a nit. The original response is preserved, and the validator itself did not silently change its severity.

### Corrected feed: case-82

The earlier run produced three unsupported major warnings about alternatives, risk documentation, and publisher redundancy. Grounded mode finishes with zero major warnings. Its initial critic response failed the requirement/failure-link contract and was corrected. Several final nits still make speculative assumptions or request facts already stated in the draft, including cache authentication and pending-row recovery. The reduction concerns major escalations; it does not mean all remaining suggestions are useful.

### Defective expiry: case-65

Both modes find the short receipt-retention window and premature signing-key deletion. The grounded critic adds an unsupported demand for failover based on an assumed 12-minute outage outside the declared outage scope. Its first alternatives complaint also needed correction because it lacked a requirement/failure link. The final alternatives complaint remains visible as a nit.

Some grounded explanations contain numerical inaccuracies: the comprehension scenario rotates at five minutes but describes deletion at thirty minutes instead of thirty-five; the critic describes a 25-hour retry horizon although the contract permits delivery retries for 24 hours. Their concrete two-hour signing failure remains valid under either timing. These mistakes reinforce that structurally valid counterexamples are not verified proofs.

## Fresh inventory-pair audit

| Metric across the two new designs | Legacy EGM | Grounded EGM |
| --- | ---: | ---: |
| Seeded faults detected | 2/2 (100%) | 2/2 (100%) |
| Completed reviews | 2/2 | 2/2 |
| Unsupported major/blocker findings, assistant audit | 5 | 1 |
| All major/blocker findings, including duplicates | 8 | 5 |
| Minor findings | 1 | 8 |
| First-response contract validity | 2/4 (50%) | 1/4 (25%) |
| Final contract validity after correction | 4/4 | 4/4 |
| Correction calls | 2 | 3 |
| Total HTTP attempts | 6 | 7 |
| Reported tokens | 26,749 | 38,131 |

The assistant-audited unsupported major count fell **80%** (5 to 1) across this one defective/corrected pair. Seeded detection stayed at 100%, while reported tokens increased **42.6%**. Minor comments and correction calls increased. The corrected counterpart still has an unsupported major in both modes, so its final workflow status remains `needs_attention` in both. This is a tiny synthetic transfer result, not a general improvement estimate.

### Corrected inventory: transfer-28

Legacy EGM emits three unsupported major warnings: alternatives supposedly lack reasons, the accepted single-process/database deployment needs redundancy, and explicitly accepted lifetime receipt storage needs a new retention policy. The supplied design includes reasons for rejecting alternatives and expressly accepts the deployment and storage choices.

Grounded EGM emits one unsupported major warning about alternative evaluation. Its proposed high-load retry scenario assumes duplicate active reservations, negative stock, and repeated cancellation credits. The design explicitly prevents those outcomes with a unique idempotency receipt plus full rollback, an atomic stock predicate, and a conditional active-to-cancelled transition. Neither mode produces a clean major-free result on this counterpart; the reduction from three to one is a **66.7% reduction in unsupported major findings on this one design**, not a general accuracy estimate.

Both modes require one correction on this counterpart: legacy initially misquotes passages, while grounded initially omits a requirement/failure link. All three accepted legacy warnings and the accepted grounded warning came from the Cloudflare route in this comparison. This narrows one provider concern for this particular control, but does not remove model sampling variation or other experiment limitations.

### Defective inventory: transfer-73

Grounded mode identifies both planted failures: two ordinary availability reads can precede unguarded decrements and produce negative stock; a repeated cancellation credits an already-cancelled reservation again. Both reviewers identify these causes, with no unsupported major finding in the final grounded output. The new mode needs two corrections here: an empty counterexample field on a nit, and a major alternatives complaint missing its requirement/failure link.

The critic's cancellation example incorrectly says the reservation UPDATE matches zero rows; the defective query has no active-state predicate, so an existing cancelled row still matches. The unconditional stock increment is nevertheless the valid repeated-cancellation fault. Structured scenarios are useful audit material, not executable proofs.

Legacy also detects both faults. Its final critic adds two unsupported majors about alternatives and security risk documentation: reasons for alternatives are supplied, and authentication, parameter binding, input limits, and tenant-scoped idempotency are explicitly part of the declared implementation. A general request for additional risk documentation is not a demonstrated new security failure. Legacy needs one quote correction on this counterpart, initially citing a nonexistent entry in the empty `open_questions` list.

## Reproduction and evidence

The live run started on 2026-11-02 at 22:22:45 UTC, with run ID `20261102T222245Z-grounded-benchmark-5da43198`. It completed all ten scheduled case/mode reviews: six development reviews and four transfer reviews. There were 20 planned reviewer invocations and 29 HTTP generation attempts, including nine format corrections. No transport-error outcomes were recorded. Pacing was 60 seconds between attempts; elapsed time includes that delay. Actual routes were Groq, Cloudflare, and OVH for the requested `gpt-oss-120b` group. All figures describe this one run.

- [Every result, model response, source map, invocation outcome, and frozen protocol](../benchmarks/results/2026-11-02-grounded.json).
- [Every major/blocker audit label, with zero-based finding indexes](../benchmarks/results/2026-11-02-grounded-audit.json).
- [Archived legacy development baseline](../benchmarks/results/2026-11-02-hard.json) and its [original audit](hard-benchmark-audit.md).
- [New inventory inputs and hidden evaluation labels](../examples/grounded-transfer.json).
- [Grounded contract and runtime behavior](grounded-review.md).

```powershell
python -m unittest discover -s tests -v
python scripts/run_grounded_benchmark.py --model gpt-oss-120b
python scripts/report_grounded_benchmark.py runs/YOUR-GROUNDED-RUN --output runs/YOUR-GROUNDED-RUN/export.json
```

All **70 automated tests** pass. The offline demo also passes and is not counted as model-quality evidence. The exporter rejects incomplete schedules and changed source snapshots or validators. It includes original invalid responses as well as accepted reviews, so correction behavior can be audited. Source hashes are supplied both for the measured file bytes and normalized LF line endings; the latter support comparison across Git line-ending settings.

## Interpretation

Passage IDs remove the need for the model to reproduce quotations, but they cannot prevent misunderstanding a passage. Requiring a counterexample makes reasoning inspectable; it does not certify the reasoning. The new fields and source tables also consume tokens. Keep the original results, all new findings, failed attempts, costs, and unresolved errors when assessing whether the extra structure is worthwhile.
