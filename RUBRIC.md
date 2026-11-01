# Attorney review rubric

Every draft answer and every intake record goes to the review queue. When approving, editing or rejecting, the
reviewing attorney can score the item on five criteria, each **0 / 1 / 2**. Scores are stored with the decision
(`review_items.rubric`) so quality can be tracked over time and compared with the automatic metrics.

| Criterion | 0 | 1 | 2 |
|---|---|---|---|
| **accuracy** | Legally wrong or misleading | Mostly right, needs correction | Correct |
| **grounding** | Claims not supported by the cited sources | Some claims unsupported | Every claim supported by a cited source |
| **citation** | Missing or wrong citations | Right source, imprecise article / extra irrelevant source | Exact, relevant citations |
| **completeness** | Misses the core of the question | Misses a relevant condition or exception | Answers the full question |
| **risk** | Could harm the client if sent | Needs a caveat or follow-up | Safe to send |

Decision guidance: any **0** → reject or edit; **risk < 2** → edit before release.

## Automatic proxies (`python -m legal_rag.evaluate`)

The eval script approximates three of these on a labelled Q&A set so retrieval/prompt changes can be checked before an
attorney sees them:

| Automatic metric | Proxy for | How it is computed |
|---|---|---|
| `grounding` | grounding | share of answer sentences where ≥ 60 % of content stems appear in the chunk they cite |
| `citation_precision` / `citation_recall` | citation | cited vs. expected source IDs |
| `completeness` | completeness | share of required facts (`must_include`) present in the answer |
| `abstention_correct` | risk | the system declines when the corpus does not contain the answer |

Accuracy and risk stay human judgements.
