# Lean Context Pilot

A small exploratory experiment: does a learned Lean evaluator distinguish a context edit that breaks a proof attempt from an unrelated edit that leaves it valid?

This repository contains the **45-program source-format-control experiment shown in slides 8 and 10** of the research discussion. It is a cleaned-up, portable runner plus the original recorded results. It does not train a model.

## The example

The goal is `(xs ++ ys).length = xs.length + ys.length`, with candidate proof `simp`.

| Context | Lean 4.15.0 | Recorded validity score |
| --- | --- | ---: |
| Original | Accepts | 0.523 |
| Remove `List.length_append` from `simp` | Rejects this attempt | 0.067 |
| Remove unrelated `Nat.add_zero` from `simp` | Accepts | 0.031 |

The full source, including the edited attribute command, is visible to the model. The theorem remains provable using an explicit named theorem even when the automatic attempt fails.

Across **15 theorem families**, the three conditions yield **45 programs**. Relevant removal changes the compiler verdict for **11** families. The score decreases for the broken version on **10/11**, but the valid control scores above the broken version on only **3/11**. At the released 0.5 threshold, overall accuracy is **24/45**; always predicting valid would get **34/45**. These aggregate counts describe this deliberately selected set only.

## Start with the recorded results

No dependencies or downloads required; Python 3.12 was used for the original run.

```bash
python3 run.py summary
```

- `recorded/results.json`: original source-format-control artifact, including all 45 complete inputs, scores, compiler labels, and paired diagnostics.
- `recorded/provenance.json`: model revision, hashes, versions, and experiment dates.
- `examples/`: the three list-length candidates in the table above.
- `cases.json`: the 15 included theorem seeds.
- `run.py`: generate candidates, replay Lean, and optionally score the released model.

## Replay Lean

Install [elan](https://github.com/leanprover/elan), then install the exact toolchain. This does not change your default Lean version.

```bash
elan toolchain install leanprover/lean4:v4.15.0
python3 run.py replay
```

Generated source and compiler logs go into `runs/latest/sources/`. Compiler verdicts go into `runs/latest/replay.json`. Failed proof attempts are expected. Timeouts remain separate from negative correctness labels.

For an explicit compiler path:

```bash
python3 run.py replay --lean /path/to/lean-4.15.0/bin/lean
```

## Reproduce model scoring

This downloads approximately 0.8 GB of model files unless `--model-dir` is supplied. Model files and generated runs are ignored by Git.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py score
```

The command first replays Lean, then scores all 45 inputs using CPU float32 and the author's preprocessing. It downloads the upstream `predict.py` at the pinned revision, checks its SHA-256, and loads its `encode_head_tail` function. The repository does not redistribute upstream code or model weights. New scores go into `runs/latest/scored.json`; recorded results stay unchanged. Small numerical differences across hardware/library versions are possible.

To reuse already downloaded files:

```bash
python run.py score --model-dir /path/to/pinned-model
```

## Verification

The packaged runner was replayed and rescored locally on November 15, 2026. All 45 generated inputs matched the recorded inputs byte for byte, all 45 compiler verdicts matched, and all 45 model scores matched within `1e-6` using the original checkpoint and software environment. This verifies the packaging, not generalization to new examples.

## Scope and limitations

- These are hand-selected Std-library fixtures, not a random sample or a natural failure-rate estimate.
- Only one released evaluator is tested. This is not a reproduction of its published miniF2F/ProofNet benchmark.
- The source-format check followed inspection of an earlier format; it is not independent held-out replication.
- The original larger pilot had 128 candidates, with a 120-candidate main cohort. This simple repository focuses on the **45-candidate control**, so its accuracy denominator differs from the larger pilot.
- The original Array reverse theorem family is excluded because it was unavailable under the older imports. The exact compiler version matters.
- No new algorithm, novel training objective, model improvement, or proof-search speedup is established.
- Lean checks the actual proof attempt. A model score is a prediction, not proof acceptance.
- The experiment and packaging used AI-assisted tooling. Original measurements date to November 12–13, 2026.

## Upstream model and close prior work

- [EPFL-LARA Lean encoder](https://huggingface.co/EPFL-LARA/lean-encoder-modernbert-large), revision `1b6fcc6dc53f237abc0226744b79ee3b86ec8e98`. The upstream model is Apache-2.0 licensed; consult its model card for details.
- [Learning Lean Feedback](https://arxiv.org/abs/2610.21881)
- [LeanContext](https://arxiv.org/abs/2611.08277)
- [CertJudge](https://github.com/ehersch/CertJudge-Poster)
- [Data for Mathematical Copilots](https://arxiv.org/abs/2412.15184)

Context dependence and metamorphic evaluation have substantial prior work. This repository records a small controlled test, not a claim of worldwide novelty.
