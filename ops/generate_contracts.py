"""Use the committed Zod exports for service validation, including in offline builds."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--check", action="store_true")
args = parser.parse_args()
for name, module in [("AnalyzeRequest", "request"), ("InferenceEvent", "event")]:
    target = root / "services/inference/src/vibechecker_inference" / f"generated_{module}.py"
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / target.name
        subprocess.run(
            [
                sys.executable,
                "-m",
                "datamodel_code_generator",
                "--input",
                str(root / "packages/contracts" / f"{name}.schema.json"),
                "--input-file-type",
                "jsonschema",
                "--output",
                str(output),
                "--output-model-type",
                "pydantic_v2.BaseModel",
                "--target-python-version",
                "3.12",
                "--disable-timestamp",
                "--field-constraints",
                "--use-standard-collections",
                "--use-union-operator",
            ],
            check=True,
        )
        generated = output.read_text(encoding="utf8")
        if args.check:
            if generated != target.read_text(encoding="utf8"):
                sys.exit(f"Regenerate {target.name}")
        else:
            target.write_text(generated, encoding="utf8", newline="\n")
