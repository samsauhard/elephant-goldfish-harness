# Semantic audit notes

The protocol, dataset, prompts, and automatic matcher were frozen before generation. These notes preserve discoveries during inspection without changing any automatic result.

## Case 26: corrected worker counterpart

The first generic reviewer identified a legitimate additional fault: the design retains "Retry bookkeeping is persisted after the sender starts an attempt." A crash between the network send and persisting the count can lose an attempt, allowing more than the contract's five physical attempts. This fault is outside the two predeclared seeds (stale worker publication and lost completion notice).

This counterpart repairs the seeded faults but is not wholly defect-free. Its major-alert count must not be called a false-positive count. Keep this case in the full results and explicitly distinguish seeded detection from additional valid findings. The fixed dataset should address this timing in a future version; do not edit this experiment's frozen inputs after observing outputs.

This is an assistant audit against the declared failure model, not independent human adjudication.

The EGM critic's two major/blocker findings on this counterpart concerned alternatives and risk mitigation. The source already gives reasons for the selected design and rejected alternatives, and explicitly accepts a ten-minute outage. These findings do not demonstrate an allowed execution violating the stated functional requirements. Record them as unsupported escalations in this audit, not as extra detected seeded faults. The generic reviewers' additional retry-accounting fault is more substantive than those two template-oriented complaints.

## Case 17: defective feed

Both generic and EGM outputs identify the two seeded executions: a tenant-independent cache key exposes another tenant's response, and allocation-order IDs allow a later commit to fall below an already advanced cursor. These automatic hits describe the stored counterexamples rather than merely mentioning the right keywords. Each two-call arm required one quote correction.

## Case 91: corrected expiry counterpart

EGM labels a 73-hour receipt lifetime a blocker because the client guarantee is 72 hours. The requirement guarantees replay within 72 hours; it does not require rejection immediately afterward. The design explicitly gives a clock-skew margin. Treating that longer retention as a violation reverses a minimum guarantee into a maximum and is unsupported.

EGM's alternatives/risk complaints again do not identify a concrete violation under the stated scope. Generic complaints about encrypted keys needing decryption and unspecified handling of uniqueness conflicts are implementation-detail concerns; the design explicitly requires atomic digest comparison/replay and signing with available secret bytes. They are not evidence that either of the corrected seeded expiry faults remains. These observations do not establish that the document is flawless or yield an independently adjudicated precision estimate.

## Case 43: defective worker

Both methods identify stale-worker publication after lease transfer and the crash between completion commit and an in-memory callback enqueue. Their matched findings describe the expected executions. Duplicate findings across reviewers earn no extra hits. EGM also repeats the template-oriented alternatives complaint; it is not a third seeded defect or evidence of extra recall.

## Case 82: corrected feed counterpart

The generic first reviewer escalates a 30-second stale empty cache response as a threat to eventual visibility. The cache has a finite expiry and the design deliberately permits delayed freshness. The finding does not demonstrate permanent omission under the stated contract; its recommendation demands earlier visibility than the guarantee requires.

The EGM critic escalates alternatives, risk-documentation, and a single publisher's possible outage. The design explicitly accepts the small deployment and bounded outage assumption. These findings do not identify a failure of the repaired tenant cache or serialized publication protocol. Its comprehension reviewer produced no major finding. This illustrates why unioning all reviewers' major findings can retain unsupported warnings even when another reviewer is appropriately restrained.

## Case 65: defective expiry contract

Both generic and EGM findings correctly identify the two stored counterexamples: a receipt disappears during the allowed 72-hour replay window, and the assigned secret disappears during the 24-hour delivery window. All six automatic seeded hits per method were inspected and describe the expected faults. No score adjustment or matcher edit was needed.

## Observed harness repair benefit

Across the 24 distinct reviewer invocations, 20 first responses passed the JSON/exact-quote contract. Four initial responses failed quotation validation. The allowed correction repaired all four, so 24 final responses passed. Both the generic and EGM paths use the same validator and repair mechanism. This is a 16.7 percentage-point increase in contract-compliant outputs, not a measured increase in semantic correctness or an advantage of the EGM personas. There were 28 actual HTTP attempts, including the four correction calls. The one-review baseline reuses first generic reviews and must not be counted again in that total.
