# Initial verification record

Date: November 2, 2026. Environment: Windows, Python 3.9.13. This section preserves the initial setup results. Subsequent review comparisons are documented in [the harder benchmark](hard-benchmark.md). Harness checks and model-quality measurements are distinct; neither establishes production readiness.

## Automated checks

`python -m unittest discover -s tests -v` passed 47 tests. These cover context isolation, structured contracts, exact evidence validation, revision state, malformed model outputs, request budgets, retry cooldowns and pacing, partial artifact retention, credential handling, and the seeded evaluation runner. Tests use fixtures and mock HTTP responses; they make no model API calls.

`python -m harness_lab demo` completed a draft, two reviews, revision, and two fresh reviews using explicitly scripted responses. It reached `ready_for_human_review`. This establishes orchestration behavior, not model intelligence or design quality.

## Live integration

The existing FreeLLMAPI endpoint at loopback port 3002 accepted OpenAI-compatible chat requests with JSON response mode. A minimal live check returned `{"ok":true}`. The `auto:business-free` router selected Groq's `openai/gpt-oss-120b`; later calls also selected `openai/gpt-oss-20b`. The endpoint is local but these generations used hosted inference.

Three full-workflow attempts exposed meaningful limits:

| Attempt | Generation HTTP attempts | Reported tokens | Outcome |
| --- | ---: | ---: | --- |
| Initial, before pacing | 5 | 13,122 | Author and comprehension review completed, including one quote correction; critic received HTTP 429 twice. Run failed and retained partial artifacts. |
| With 30-second pacing | 3 | 12,900 | Comprehension reviewer quoted text under the wrong section; the single correction did not fully resolve it. Run failed validation. |
| With 60-second pacing and more specific correction feedback | 7 | 28,247 | Author, both initial reviewers, and revision completed. Re-review still contained a quote under the wrong section after one correction. Run failed validation. No HTTP 429 occurred in this particular run. |

Reported usage is the sum supplied by successful HTTP responses; it may omit provider work behind rejected requests. No dollar cost was reported or estimated. These attempts differ in configuration and prompts and are not a controlled before/after study. Full autonomous completion with the current free router has not been established by these three runs.

A targeted live evaluation then completed successfully: `python -m harness_lab evaluate --case cross-customer-read`. Both independent reviewers returned valid responses in 2 generation requests using `openai/gpt-oss-120b`, with 5,498 reported tokens. The evaluator detected the single seeded cross-customer access flaw (1 of 1) and recorded 4 major findings in total. Status was correctly `needs_attention`, since a known-defective design should not be approved. This one positive diagnostic does not establish recall or precision; the other two seeded cases and repeated trials have not yet been run live.

## Measured improvement

Improvement in final designs over an author-only baseline is **unknown**. No baseline comparison had been run at this initial verification point. Later reviewer comparisons do not measure final design quality. Unknown is not a measured zero-percent gain.

| Observation | Result | Interpretation |
| --- | --- | --- |
| Seeded flaw detection in the targeted live diagnostic | 1/1 (100% on this one case) | Too small to establish general recall, accuracy, or improvement |
| Completed full live workflows during development | 0/3 (0% of these attempts) | Configurations differed; this is not a general reliability estimate |
| Automated harness checks | 47 passed | Mock/fixture checks establish implementation behavior, not design quality |

The four major findings in the diagnostic have not been independently graded for correctness. There is no measured reduction in defects or increase in accepted designs.

A controlled comparison should use held-out tasks, the same fixed model, repeated trials, and blinded human scoring of author-only designs versus designs after isolated review and revision. Record final design acceptance, missed defects, false alarms, workflow completion, tokens, and latency. Include a comparable-budget single-review baseline to distinguish context isolation from additional generation effort. Count failed workflows explicitly. Report both the absolute percentage-point difference and relative change, with uncertainty, only after collecting results.

## What changed because of the failures

1. **Rate limits:** every HTTP attempt consumes budget; transient responses get bounded retries; `Retry-After` is honored up to 60 seconds, and longer cooldowns stop the run. The development configuration now spaces dispatches by 60 seconds. Pacing carries across evaluation cases.
2. **Quote reliability:** the review adapter asks for a small number of focused findings and short continuous quotes. Validation identifies every mismatched finding index and section in the correction request, without accepting approximate or invented evidence.
3. **Observable failure:** invalid or incomplete review rounds never become a clean result. Valid earlier drafts/reviews remain on disk and can seed a new run. One corrected response per logical model call prevents an unlimited repair loop.

## Known limits and next experiment

- Exact evidence quotes establish textual grounding, not whether a criticism is correct. They also expose a model capability bottleneck: the free model sometimes quotes real text but labels the wrong section.
- A useful next experiment is a deterministic passage-ID interface, compared with free-form quotations on a held-out task set. It is not implemented in this version; do not claim its benefits.
- The reviewer may overstate minor issues or request unnecessary complexity. A human must decide whether findings warrant changes.
- Auto routing can change models within one run. Use fixed IDs and repeated trials for controlled model/harness comparisons.
- The three seeded evaluation fixtures are diagnostics, not a representative benchmark. Expected labels are hidden from requests; detection uses category and evidence overlap and needs manual auditing.
- Artifacts preserve completed steps but are not transactionally crash-safe checkpoints. Automatic resume and arbitrary code execution are outside this version's scope.

Local raw traces are excluded from the public repository. Reproduce with `python -m harness_lab run` after configuring an available compatible API. Live outputs are nondeterministic and quotas vary.
