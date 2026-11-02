# State-transition review benchmark

This benchmark compares an ordinary reviewer with the two isolated EGM reviewers on six synthetic API designs. Three designs contain two seeded faults each; three counterparts repair those faults under the same requirements. It tests interactions between statements, rather than conspicuous sentences that explicitly announce an unsafe behavior.

## Cases

| Family | Faults in the defective variant | Corrected counterpart |
| --- | --- | --- |
| Incremental feed | Shared cache omits tenant identity; allocation-order cursor skips a transaction that commits late | Tenant-partitioned cache; feed sequence assigned in serialized publication transactions |
| Export worker | Expired worker can overwrite a newer result; completion commit can lose its callback after a crash | Conditional completion with epoch/owner/expiry checks; transactional durable outbox |
| Event lifecycle | Receipt expires before the allowed idempotency retry window; retired signing key disappears before delivery retries finish | Receipt and key retention cover their respective contracts and clock skew |

The requirements explicitly accept a small deployment and bounded infrastructure downtime. Reviewers should not demand multi-region operation or extra infrastructure merely to produce findings. The corrected variants still need human review; an unexpected finding may reveal a real limitation of the fixture rather than a reviewer error.

`benchmarks/hard_cases.py` defines the fixtures and minimal executable counterexample illustrations. These are toy state-transition witnesses, not production implementations or exhaustive model checking. The generated dataset is `examples/hard-evaluation.json`.

## Run

```powershell
python -m unittest discover -s tests -v
python scripts/run_hard_benchmark.py --model gpt-oss-120b
```

Use a model ID supported by the configured local OpenAI-compatible endpoint. The runner uses `config.local.json`, including its credential source and pacing. It defaults to one trial and accepts `--trials 2` or `--trials 3`. Two-reviewer cases need at least two requests; corrections and transport retries can add more. At 60-second pacing, one trial over all cases needs at least 24 generation requests and roughly 24 minutes. Provider latency and corrections can extend this.

## Comparison

- **Generic one:** the first generic review, reused from the two-call arm. It is not an independent repeat.
- **Generic two:** two fresh generic reviews with identical instructions and separate request contexts.
- **EGM two:** the existing comprehension and design-critic personas, with no revision and no changes to runtime validation.

Both two-call arms have the same number of logical calls, output-token limit, correction allowance, and HTTP request budget. Their actual token use can differ because their prompts and responses differ. This controls call count, not compute or dollar cost. Every reviewer receives the same draft and references. Expected labels, counterexamples, case IDs, and previous reviews are excluded from its messages.

The runner alternates method order, preserves all cases, and writes the protocol, source hashes, dataset, prompt source, runtime source, and grader source before its first generation request. Outputs include raw traces, actual model/provider routing, validation failures, intermediate reviews, and incremental comparison results. Failures remain in the denominator. A router may serve the same model family through different providers; inspect traces before interpreting a difference as a harness effect.

## Scoring

The primary diagnostic is **delivered seeded-defect detection**: matched faults in completed review cases divided by all expected faults. Multiple reviewers identifying the same fault still earn one hit. A failed case contributes no verified detections, even when partial findings exist.

The frozen matcher requires a quotation from the affected passage and all specified causal concepts in the issue/recommendation. A general security comment or quotation alone is insufficient. This heuristic can miss a valid paraphrase or credit a superficially matching finding; inspect matched findings and misses against the stored counterexamples. Any later semantic audit must be recorded separately from the automatic score rather than silently changing the grader.

Also report completion, major-alert rate on corrected controls, actual tokens, and validation corrections. A major alert on a corrected design is a false-positive candidate, not an automatically proven error. Finding counts alone do not measure usefulness.

These are constructed development cases with only three independent scenario families. Repeating them does not create new independent tasks. Results cannot establish a general quality improvement, statistical superiority, or production reliability.

## Recorded run: November 2, 2026

One live trial used the pinned `gpt-oss-120b` model group. The router served the generic reviews through Groq and some EGM responses through Cloudflare; provider variation limits causal attribution. The dataset, prompts, runtime, and matcher stayed unchanged throughout generation. All six planted detections per method were inspected against the stored counterexamples; no automatic score was adjusted.

| Metric | One generic review | Two generic reviews | Two EGM reviews |
| --- | ---: | ---: | ---: |
| Seeded faults detected | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| Case reviews completed | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| Corrected counterparts with major alerts | 3/3 | 3/3 | 3/3 |
| Reported tokens | 19,845 | 35,329 | 53,620 |
| HTTP attempts, including corrections | 8 | 14 | 14 |

**Measured EGM seeded-detection uplift: 0 percentage points (0% relative).** EGM consumed approximately 2.70 times the tokens of one generic review, and 1.52 times those of the two-review baseline. No extra seeded faults were detected. The generic one-review result reuses the first review in each two-review case and is not additional independent evidence.

**Observed harness benefit: exact-output reliability.** Across 24 distinct logical reviews, 20 initial responses passed JSON and exact-citation validation (83.3%). Four quote errors were detected and repaired within the existing one-correction allowance. All 24 final responses passed (100%): **+16.7 percentage points**, with four additional HTTP calls. Both the generic and EGM arms benefit from this shared validation mechanism. Passing it does not establish that a criticism is correct.

Major-alert rates on the corrected counterparts are **not false-positive rates**. One counterpart retains an additional unseeded retry-accounting flaw that a generic reviewer correctly found. Other alerts were unsupported escalations, including an EGM complaint that 73-hour retention violated a 72-hour minimum guarantee. See the [semantic audit](hard-benchmark-audit.md). No precision or general accuracy percentage is claimed.

The code and scoring checks pass **54 automated tests**. [Machine-readable results, findings, protocol, and repair measurements](../benchmarks/results/2026-11-02-hard.json) preserve all cases. The record includes raw frozen-source hashes and LF-normalized hashes for verification across Windows and Unix checkouts; local raw traces remain excluded from source control.

These results support investing in scope calibration and evidence handling. They do not support claiming that adding the EGM personas makes this model better at detecting the tested defects.
