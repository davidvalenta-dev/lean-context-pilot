"""Replay and score the small Lean context pilot. Summary needs only Python."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONDITIONS = ("baseline", "remove_relevant", "remove_unrelated")
MODEL_ID = "EPFL-LARA/lean-encoder-modernbert-large"
REVISION = "1b6fcc6dc53f237abc0226744b79ee3b86ec8e98"
LEAN_VERSION = "leanprover/lean4:v4.15.0"


def candidates():
    for case in json.loads((ROOT / "cases.json").read_text()):
        for condition in CONDITIONS:
            edit = {
                "baseline": "",
                "remove_relevant": f"attribute [-simp] {case['name']}\n",
                "remove_unrelated": "attribute [-simp] Nat.add_zero\n",
            }[condition]
            source = ("import Lean\nimport Std\n\n" + edit +
                      f"\ntheorem target {case['binders']} : {case['target']} := by\n  simp\n")
            filename = case["name"].replace(".", "_") + f"__{condition}__automatic__no_print.lean"
            yield dict(seed=case["name"], condition=condition, source_file=filename,
                       model_input=source)


def summarize(rows):
    complete = [r for r in rows if r.get("accepted") is not None]
    by = {(r["seed"], r["condition"]): r for r in complete}
    triples = []
    for seed in sorted({r["seed"] for r in complete}):
        if any((seed, c) not in by for c in CONDITIONS):
            continue
        a, r, u = [by[seed, c] for c in CONDITIONS]
        if not (a["accepted"] and not r["accepted"] and u["accepted"]):
            continue
        triple = {"seed": seed}
        if all("probability_valid" in x for x in (a, r, u)):
            ap, rp, up = [x["probability_valid"] for x in (a, r, u)]
            triple.update(baseline_p=ap, relevant_p=rp, unrelated_p=up,
                          correct_flip_direction=ap > rp,
                          specific_direction=up > rp,
                          both_classifications_correct=ap >= .5 and rp < .5)
        triples.append(triple)
    summary = dict(records=len(rows), compiler_verdicts=len(complete),
                   theorem_families=len({r["seed"] for r in rows}),
                   positive_labels=sum(r["accepted"] for r in complete),
                   flip_pairs=len(triples))
    if complete and all("probability_valid" in r for r in complete):
        summary.update(
            correct=sum((r["probability_valid"] >= .5) == r["accepted"] for r in complete),
            correct_flip_direction=sum(t["correct_flip_direction"] for t in triples),
            specific_direction=sum(t["specific_direction"] for t in triples),
            both_classifications_correct=sum(t["both_classifications_correct"] for t in triples),
        )
    return {"summary": summary, "triples": triples}


def lean_command(explicit):
    if explicit:
        command = [str(Path(explicit).expanduser().resolve())]
    else:
        elan = shutil.which("elan") or str(Path.home() / ".elan/bin/elan")
        if not Path(elan).is_file():
            raise SystemExit("Install Lean's elan manager first, or pass --lean /path/to/lean.")
        command = [elan, "run", LEAN_VERSION, "lean"]
    version = subprocess.check_output(command + ["--version"], text=True).strip()
    if "version 4.15.0," not in version:
        raise SystemExit(f"This reproduction expects Lean 4.15.0; found: {version}")
    return command, version


def replay(out, explicit):
    command, version = lean_command(explicit)
    source_dir = out / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for row in candidates():
        path = source_dir / row["source_file"]
        path.write_text(row["model_input"])
        try:
            proc = subprocess.run(command + [str(path)], capture_output=True,
                                  text=True, timeout=30)
        except subprocess.TimeoutExpired:
            # A timeout is not a negative correctness label.
            row.update(status="timeout", accepted=None)
            rows.append(row)
            continue
        log = proc.stdout + proc.stderr
        path.with_suffix(".log").write_text(log)
        row.update(compile_exit=proc.returncode,
                   accepted=proc.returncode == 0 and "error:" not in log and "sorryAx" not in log,
                   status="completed")
        rows.append(row)
    result = dict(compiler_version=version, **summarize(rows), rows=rows)
    (out / "replay.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def score(result, out, model_dir):
    try:
        import torch
        import transformers
        from huggingface_hub import snapshot_download
        from transformers import AutoTokenizer, AutoModelForSequenceClassification
    except ImportError as exc:
        raise SystemExit("Scoring requires: pip install -r requirements.txt") from exc
    provenance = json.loads((ROOT / "recorded/provenance.json").read_text())
    if model_dir:
        model_dir = Path(model_dir).expanduser().resolve()
    else:
        model_dir = ROOT / ".cache/model"
        snapshot_download(MODEL_ID, revision=REVISION, local_dir=model_dir,
                          allow_patterns=["config.json", "model.safetensors", "tokenizer.json",
                                          "tokenizer_config.json", "special_tokens_map.json",
                                          "predict.py", "README.md"])
    for file, expected in [("model.safetensors", provenance["model_weights_sha256"]),
                           ("predict.py", provenance["preprocessing_sha256"])]:
        if sha256(model_dir / file) != expected:
            raise SystemExit(f"{file} does not match the recorded checkpoint.")
    # Load the author's exact preprocessing from the pinned, hash-checked artifact.
    spec = importlib.util.spec_from_file_location("released_predict", model_dir / "predict.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_dir, local_files_only=True, dtype=torch.float32,
        attn_implementation="sdpa").eval()
    rows = result["rows"]
    for begin in range(0, len(rows), 8):
        batch = rows[begin:begin + 8]
        inputs = module.encode_head_tail(tokenizer, [r["model_input"] for r in batch],
                                        max_length=8192, head_fraction=.25)
        with torch.inference_mode():
            ps = model(**inputs).logits.float().softmax(-1)[:, 1].tolist()
        for row, p in zip(batch, ps):
            row.update(probability_valid=p, predicted_valid=p >= .5)
    result = dict(model_id=MODEL_ID, model_revision=REVISION, device="cpu", dtype="float32",
                  torch=torch.__version__, transformers=transformers.__version__,
                  compiler_version=result["compiler_version"], **summarize(rows), rows=rows)
    (out / "scored.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("summary", "replay", "score"), nargs="?", default="summary")
    parser.add_argument("--out", type=Path, default=ROOT / "runs/latest")
    parser.add_argument("--lean", help="Explicit path to Lean 4.15.0, instead of elan run")
    parser.add_argument("--model-dir", help="Reuse an existing pinned model directory")
    args = parser.parse_args()
    if args.action == "summary":
        rows = json.loads((ROOT / "recorded/results.json").read_text())["rows"]
        result = summarize(rows)
    else:
        args.out = args.out.expanduser().resolve()
        result = replay(args.out, args.lean)
        if args.action == "score":
            result = score(result, args.out, args.model_dir)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
