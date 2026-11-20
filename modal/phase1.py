"""On-demand Phase 1 research jobs sharing the inference image and weight volume."""

import os
from pathlib import Path

from fallback import app, image, weights

FALCON = (
    ("tiiuae/falcon-7b", "ec89142b67d748a1865ea4451372db8313ada0d8"),
    ("tiiuae/falcon-7b-instruct", "8782b5c5d8c9290412416618f36a133653e85285"),
)


@app.function(
    image=image.env({"HF_HUB_OFFLINE": "0"}),
    gpu="L40S",
    volumes={"/weights": weights},
    timeout=7200,
)
def run_reference(pairs: int, seed: int):
    import subprocess

    from huggingface_hub import snapshot_download

    root = Path("/weights/phase1")
    root.mkdir(exist_ok=True)
    env = os.environ.copy()
    for role, (repo, revision) in zip(("OBSERVER", "PERFORMER"), FALCON, strict=True):
        dest = root / (repo.split("/")[-1] + "-" + revision)
        snapshot_download(
            repo,
            revision=revision,
            local_dir=dest,
            allow_patterns=["*.json", "*.safetensors"],
            ignore_patterns=["*/*"],
        )
        env["VIBECHECKER_PAIR_" + role] = str(dest)
    report = root / "reference.json"
    try:
        subprocess.run(
            [
                "vibechecker-eval",
                "falcon-reference",
                "--pairs",
                str(pairs),
                "--seed",
                str(seed),
                "--cache",
                "/weights/eval-cache",
                "--out",
                str(report),
            ],
            env=env,
            check=True,
        )
        return report.read_text()
    finally:
        weights.commit()


@app.local_entrypoint()
def reproduce(pairs: int = 64, seed: int = 42):
    print(run_reference.remote(pairs, seed))


@app.function(image=image, gpu="L4", volumes={"/weights": weights}, timeout=86400)
def train(args: list[str], observer: str, performer: str):
    import subprocess

    env = {
        **os.environ,
        "VIBECHECKER_PAIR_OBSERVER": observer,
        "VIBECHECKER_PAIR_PERFORMER": performer,
    }
    try:
        subprocess.run(["vibechecker-eval", "deep", *args], check=True, env=env)
    finally:
        weights.commit()


@app.local_entrypoint()
def fit(
    observer: str,
    performer: str,
    version: str = "phase-1",
    limit: int = 64,
    commercial_only: bool = False,
    bf16: bool = False,
    validation: bool = False,
    pair_family: str = "",
):
    if not observer.startswith("/weights/") or not performer.startswith("/weights/"):
        raise ValueError("Supply pair directories on the mounted weight volume")
    root = "/weights/phase1"
    cohort = "validation" if validation else "test"
    args = [
        "--model-out",
        f"{root}/{version}.joblib",
        "--version",
        version,
        "--cache",
        "/weights/eval-cache",
        "--reports",
        f"{root}/reports",
        "--cohort",
        cohort,
        "--limit-per-class",
        str(limit),
        "--trace-out",
        f"{root}/{version}.{cohort}.cuda.json",
    ]
    if commercial_only:
        args.append("--commercial-only")
    if pair_family:
        args.extend(["--pair-family", pair_family])
    job = train.with_options(gpu="L40S") if bf16 else train
    job.remote(args, observer, performer)
