# Daymark webpage build experiment

Recorded November 3, 2026. One task, one shared initial generation, and one revision opportunity per reviewed branch. The comparison is an inspectable example, not a general model-quality benchmark.

## Inputs and workflow

The brief requests a standalone HTML task planner with inline CSS and vanilla JavaScript. It starts with three specified tasks and supports add, complete, delete, combined search/filter, priorities, accurate global counters, literal text handling, blank-title rejection, keyboard controls, and a responsive layout at 390 px and desktop widths. It specifies an off-white/ink/green design and no external dependencies, network, storage, or backend. State resets on reload. See the [complete brief and protocol](../site/buildoff/protocol.json).

The initial author was instructed to return only a complete HTML document, keep it compact, give all requirements equal importance, and omit references to AI methods or this comparison.

| Version | Input and processing | Output |
| --- | --- | --- |
| A: EGM | Original HTML and requirements; independent comprehension and design-critic reviews in fresh contexts; basic JSON and quotation checks; one author revision using those reviews | Explicit priority-option values and simpler empty-state logic; long-title overflow remains |
| B: Direct API | Requirements and author instruction; no review or revision | Initial working task planner used as the common starting point |
| C: Grounded EGM | Same original HTML and requirements; same reviewer roles, document-bound passage IDs, requirement links, and failure arguments for serious findings; one author revision | Long-title wrapping and flex constraints; explicit filter-button types; live-status attributes on the empty-state message |

The revision instruction tells the author to evaluate comments against the requirements, fix valid issues, preserve working behavior and visual quality, and avoid blindly applying unsupported suggestions. No final output was hand-edited. The comparison wrapper, test bridge, and presentation were authored separately and applied consistently to all three outputs.

The requested model group was `gpt-oss-120b` throughout. Resolved routes included Cloudflare `@cf/openai/gpt-oss-120b`; the EGM branch also used Groq `openai/gpt-oss-120b`. A local compatible endpoint routed these requests to hosted inference. These are adaptations of the repository's design-review workflow to an HTML implementation, not three distinct model checkpoints or the full Google EGM plugin. Original EGM already uses a basic harness; C adds stronger evidence requirements.

## Browser results

| Recorded check | A: EGM | B: Direct | C: Grounded EGM |
| --- | ---: | ---: | ---: |
| Original interaction checks, 837 px | 10/10 | 10/10 | 10/10 |
| Original interaction checks, 390 px | 10/10 | 10/10 | 10/10 |
| Exploratory 140-character unbroken title, 390 px | Fail | Fail | Pass |

The ten original checks cover initial tasks/counts, add, blank rejection, completion/counts, Done and Active filters, case-insensitive combined search/filter, deletion after filtering, literal text, and baseline horizontal overflow. Enter-key task entry was also checked manually on each output. These checks do not cover every requirement, accessibility behavior, browser, or device.

The long-title case was added after the grounded reviewers flagged overflow. It was applied to all outputs and was not fed back to the revision model. A and B produced 1,679 px of content in a 390 px viewport; C stayed within that viewport. This exploratory check is separate from the ten original checks and is not held-out evidence. The [browser record](../site/buildoff/artifacts/browser-verification.json) preserves each observed result.

C demonstrates a specific defect caught and fixed. A's explicit option values improve maintainability but did not establish a functional advantage over B in these checks. The baseline appearance is similar because all branches share the initial implementation and the reviewed branches received one revision.

## Recorded effort

| Measure | A: EGM | B: Direct | C: Grounded EGM |
| --- | ---: | ---: | ---: |
| Reported tokens | 33,487 | 4,847 | 44,494 |
| HTTP attempts, including failures | 8 | 2 | 10 |
| Total elapsed time, seconds | 660.39 | 229.69 | 682.05 |
| Observed HTTP request time, seconds | 578.46 | 229.58 | 571.65 |
| HTML revision passes | 1 | 0 | 1 |
| Review-format/evidence corrections | 1 | 0 | 1 |

Each column includes the shared initial generation as if that method ran independently. Do not sum the three columns to estimate this experiment's unique initial-generation usage. Total time includes configured pacing and recovery. HTTP time measures request duration, including failed calls, not server compute. The comparison site's implementation and manual QA time are excluded. Failed requests did not report token usage, so reported tokens undercount any such consumption. Dollar cost was not reported.

Recovery is preserved in the protocol and metrics:

- The initial generation timed out after 120 seconds. A second attempt used a 300-second timeout and produced the common draft; both attempts and their elapsed time are charged to every column.
- EGM's first review run failed after two HTTP 502 responses; one unchanged restart succeeded.
- Grounded review failed in two runs, each with two HTTP 502 responses. Its third run increased the per-review output cap from 2,300 to 6,000 tokens and succeeded. The cause of the HTTP errors was not established. This is not an equal-budget comparison.

The [combined results JSON](../site/buildoff/results.json) makes the displayed totals and per-version browser evidence accessible without evaluating JavaScript. Per-run metrics, including failures, remain in [artifacts/](../site/buildoff/artifacts/). Individual successful-run metric files exclude earlier failures and shared initial effort; the combined totals include them. The two EGM failure-metric filenames in the archive describe the same failed run and must not be counted twice.

## Interpretation and limits

For this example, grounded EGM produced the most robust output on the observed long-title case; direct generation used the least reported effort. All three retained working baseline behavior. These observations do not establish a general winner, an accuracy percentage, or a causal improvement attributable solely to grounding.

There was one task and one trial, shared initial HTML, unequal output budgets, differing provider routes, and different failed attempts. No independent human scoring or repeatability estimate was collected. Both review modes still emitted irrelevant alternatives-analysis demands inherited from the design-spec rubric. A structurally valid citation does not make a criticism correct. The added live-region attributes were inspected in source, not validated with a screen reader.

To inspect the actual changes, see the [EGM diff](../site/buildoff/artifacts/egm-changes.diff.txt) and [grounded diff](../site/buildoff/artifacts/grounded-changes.diff.txt). To try the saved pages and rerun their browser checks without inference, follow the [website instructions](../site/buildoff/README.md).
