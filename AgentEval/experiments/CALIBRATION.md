# Calibration API / P0

Base: `/experiments/calibration`. All records use the existing workspace JsonStore and memory-only Provider sessions. Legacy records are not migrated or rescored automatically.

| Method/path | Purpose |
| --- | --- |
| GET `/template`, `/history` | Initial unvalidated ecommerce Rubric, safe history summaries |
| POST `/datasets` | Freeze imports and/or selections from immutable retrieval runs |
| GET `/datasets/{id}` | Frozen question, answer, dual evidence, groups and partition |
| POST `/rubrics` | New immutable Rubric; optional parent ID |
| POST `/blind-sessions` | Server-issued blind access record; no machine/human scores |
| POST `/annotations`, `/annotation-imports` | Source/exposure-tagged annotations, partial per-row import receipts |
| GET `/annotations/{dataset_id}?rubric_id=...&actor=...` | Progress for all actors; only reveal judgments for samples already submitted by this actor; record peer exposure |
| POST `/adjudications` | Judgment, original annotation IDs, adjudicator/source and reason |
| POST `/protocols` | Frozen J1/J2/J3, optional declared parent and calibration-only examples |
| POST `/runs` | Fixed-answer CALIBRATION partition only, budget, repetitions, idempotency ID |
| GET `/runs/{id}?actor=...` | Reveal only samples submitted by this actor under this Rubric; audit exposure |
| POST `/comparisons` | Freeze paired runs, reference snapshot and actual protocol differences |
| GET `/comparisons/{id}?actor=...` | Enforce submission and holdout release before returning results |
| POST `/hypotheses` | Multi-select disagreement reasons, explicitly hypotheses rather than established causes |
| POST `/issues` | Open an issue attached to a visible scored sample; layer, owner, description and source run |
| GET `/issues?dataset_id=...&actor=...` | Visible issues and append-only progress events |
| POST `/issues/{id}/events` | Optimistic event identity, explicit change, new-run retest and documented conclusion |
| POST `/validations/lock` | Lock two previously calibrated protocols, reference snapshot, repetitions and total budget |
| POST `/validations/{id}/execute` | Only final operation can score holdout; repeat submission returns existing validation |
| POST `/conclusions` | ADOPT / REVISE / KEEP_BASELINE with rationale and derived research status |
| GET `/conclusions/{id}/export?actor=...` | Frozen Markdown and JSON, subject to the same result access workflow |

## Sample import

Import records declare `origin` as ACTUAL, CONSTRUCTED or AI_GENERATED. Error-injected answers additionally set `diagnostic: true`. Partition is CALIBRATION or HOLDOUT; it is independent from the original test-purpose label.

```json
{
  "name": "My calibration dataset",
  "group_review_confirmed": true,
  "priority_metric": "Reduce critical false passes; observe refusal and coverage",
  "acceptable_cost": "Declare request budget and record available usage",
  "selections": [],
  "samples": [{
    "group_id": "battery-policy-question-family",
    "partition": "CALIBRATION",
    "question": "Replace with the actual question",
    "context": [],
    "answer": "Replace with the already-generated frozen answer",
    "retrieved_evidence": [{"evidence_id":"chunk-1","document_id":"battery","text":"Original retrieved text"}],
    "reference_policy": [{"evidence_id":"battery","document_id":"battery","text":"Complete policy snapshot at that time"}],
    "reference_complete": true,
    "expected_facts": [],
    "origin": "CONSTRUCTED",
    "diagnostic": false,
    "scenario": "多条件",
    "prior_machine_exposure": false,
    "creator_seen_content": true,
    "provenance": {"note":"Replace this example; not real research evidence"}
  }]
}
```

Each retrieval selection has `run_id`, `case_id`, `group_id`, `partition`, `origin`, and `source_viewer` (the actor who saw historical machine results). Same-question variants and shared templates must share `group_id` or `template_id`. The current policy is never substituted for a missing historical policy. Retrieved text and reference policy can differ in normalization and are validated in their own scopes.

## Annotation and Judge output

Four dimensions: `faithfulness`, `conditions`, `relevance`, `actionability`. Each has `score` (integer 0/1/2, INSUFFICIENT or NA), `answer_quotes`, `citations` (scope RETRIEVED or REFERENCE, evidence_id, verbatim quote) and `reason`. A numerical grade requires an answer quote; faithfulness with available retrieved evidence requires a retrieved citation, and conditions with complete reference policy requires a reference citation.

The judgment also contains `critical_errors` (Rubric IDs), `error_tags`, `verdict` (PASS/FAIL/PENDING), `task_resolved`, `faithful_to_available` (YES/NO/INSUFFICIENT), `task_failure_reasons`, `insufficient_items` and a short `reason`. The backend checks the frozen final rule. Citation provenance checks are not semantic correctness checks.

Offline annotation imports add `dataset_id`, `sample_id`, `rubric_id`, `annotator_id`, `source` (HUMAN/AI/CODEX), `mode: IMPORT`, `seen_machine`, `seen_peer` (defaults false for compatibility), `labeled_at` and `judgment`. Source must be explicitly declared. A blinded page uses its issued `blind_access_id`. Exposed reviews and AI/Codex records never enter independent-human denominators. Reading another actor's judgment records ANNOTATION_VIEW; later revisions are reviews, while original independent records remain preserved. Rubric changes require fresh annotation under the new ID; old annotations do not unlock the new version's machine results.

## Fragment citation protocol (2026-10-14)

POST `/protocols` accepts `citation_mode: VERBATIM | FRAGMENT_IDS`. API default VERBATIM preserves existing callers. The local UI defaults to FRAGMENT_IDS for newly created protocols. Old protocols, scores and snapshots remain version 1.

FRAGMENT_IDS freezes input `FROZEN_FRAGMENT_CATALOG_V2`, output `CALIBRATION_FRAGMENT_JUDGMENT_V2`, parser `2`. Input contains source-bound ANSWER, RETRIEVED and REFERENCE fragments. Each dimension outputs `score`, `answer_fragment_ids`, `evidence_fragment_ids`, `reason`; other top-level Judgment fields keep their meanings. The server resolves current-sample IDs to exact original quotations, validates existing score/range rules and retains ID, source hash and original character positions in `citation_provenance`. It rejects unknown, duplicate and cross-scope IDs. It does not accept paraphrases, infer support from citation existence, or replace historical failures.

Blind sessions additionally return `fragments` and `prior_peer_exposure`, without changing the original `sample` structure. The shared human/adjudication form uses exact original text and normal Judgment imports, so it is compatible with either machine protocol.

## Issue lifecycle and health

Issue statuses follow OPEN → REPRODUCED → CHANGED → RETESTED → CLOSED, with UNRESOLVED available and re-entry through REPRODUCED. CHANGED requires an actual change description. RETESTED requires a sealed, different run in the same dataset containing the same sample and an outcome FIXED/NOT_FIXED/INCONCLUSIVE. A failed or unavailable score cannot support FIXED. CLOSED requires the preceding retest to support improvement; it remains an explicit researcher decision, not automatic causal proof. Events carry `previous_event_id`; stale submissions conflict instead of overwriting progress.

Current issues track fixed-answer calibration repairs. Direct linkage to new retrieval runs and automatic application of a calibrated Judge to Agent experiments remain future work. Conclusions freeze issues/events as they existed at save time.

Metrics additionally report independent-human coverage, unavailable predictions within human pass/fail groups, repeat completeness/stability, machine decision counts and input/output reconciliation. Reconciliation compares sample/repetition identities, rejecting duplicate events from usable coverage even when counts match. Historical metric keys and denominators remain available.

## Freeze and accounting

Artifacts are append-only except RUNNING-to-terminal run sealing and LOCKED-to-RUNNING-to-terminal validation transitions. A run's `request_id` binds its complete request hash; duplicates return its existing identity, conflicting payloads reject before requests. The Provider has no automatic retries. Case status is SUCCESS, INTERFACE_ERROR, PARSE_ERROR, CONTENT_INVALID or NOT_RUN. Evidence-insufficient judgments are tracked separately from execution errors.

Fractions retain numerator, denominator, value and drill-down identities. Empty denominators yield null. False-pass denominator is all valid independent-human FAILs, including cases without machine decisions; these unavailable predictions are also explicitly counted and never treated as correct. Human/AI exposure is scoped to actor; identities are declarations, not authenticated accounts. Multi-annotator reference disagreements require adjudication.

The holdout is unavailable for normal scoring or protocol examples. Final execution releases its results and writes an access event. Reuse of released question families as new independent holdout is blocked; a REVISE decision additionally records invalidation. Local developers can inspect files: this is workflow isolation only.
