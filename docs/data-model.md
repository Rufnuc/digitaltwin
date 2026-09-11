# Data model & epistemic status

The platform's fundamental rule (spec §49): it must always know the difference
between the kinds of data it holds. This is encoded once, in
`app/core/enums.py`, and used everywhere.

## `DataOrigin`

| Value | Meaning |
|---|---|
| `REAL` | verified real business record |
| `DEMO` | synthetic seed data — never shown as real |
| `ESTIMATED` | derived/imputed where source was incomplete |
| `MISSING` | known-absent; recorded so gaps are explicit |
| `ASSUMPTION` | an input the user/model assumed |
| `MODEL_OUTPUT` | produced by the simulation/analytics engine |
| `FORECAST` | a projected future value with uncertainty |
| `AI_INTERPRETATION` | LLM explanation — never a raw number |

## `VerificationStatus`

`VERIFIED · AI_EXTRACTED · NEEDS_REVIEW · PENDING · REJECTED`

## How it shows up

- **DB**: `ProvenanceMixin` columns on business tables.
- **API**: read models include `data_origin`, `verification_status`, `confidence`;
  `GET /meta/data-origins` returns the whole vocabulary.
- **UI**: a `ProvenanceBadge` on every table row and on computed figures; a
  prominent **DEMO DATA** banner whenever the dataset is demo-only.

## Historical / aggregate data (spec §14)

The schema supports transaction-level data now; aggregate historical periods
(monthly/annual) for very old years will be represented with `ESTIMATED` /
aggregate rows tagged accordingly, so the simulation engine can weight them
differently. Owner recollections live in `owner_knowledge`, tagged as knowledge —
never mixed into transactional fact.
