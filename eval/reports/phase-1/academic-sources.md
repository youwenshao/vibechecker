# Academic source record

Seven matched pairs entered stack training and five entered calibration. Four additional published abstracts were reserved for an independent check of human false positives. Each fitting pair contains a RAID rewrite of a machine-generated abstract and a native journal abstract from a different paper in the same field. The native label identifies the text deposited by the publisher. Publication date and named authors do not establish what editorial assistance an author received. [Study protocol](academic-addition-protocol.md) · [Counts and SHA-256 commitments](academic-sources.json)

| Role | Pairs or references | Field coverage | Native words | Machine words |
| --- | ---: | --- | ---: | ---: |
| Stack training | 7 pairs | 4 vision, 1 biomedical vision, 1 machine learning, 1 network security | 313–407 | 326–406 |
| Calibration | 5 pairs | 4 vision, 1 machine learning | 301–411 | 301–376 |
| Human development | 4 references | 2 vision, 2 machine learning | 306–321 | — |

## Source records and rights

**RAID.** The pinned train shard supplied 48 machine-origin DIPPER paraphrases per fitting role, one per source. Generator-balanced selection happened before scoring. Each child links to its clean machine parent and the original arXiv abstract through publisher IDs. All 96 original human abstracts were below the 300-word gate. The source record matched 92 of 96 original titles to arXiv DOI registrations. All 12 machine sources used in fitting have verified first-submission dates. The dataset card lists MIT, underlying source rights vary, and this projection is restricted to research. [RAID paper](https://aclanthology.org/2024.acl-long.674/) · [Publisher dataset card](https://huggingface.co/datasets/liamdugan/raid/blob/main/README.md) · [Pinned inputs](../../registry.yaml) · [DataCite registration metadata](https://support.datacite.org/docs/api)

**Native journal abstracts.** The search yielded 111 eligible records from 5,736 distinct Crossref DOIs and 12 more from 150 PMC article headers. Of the 16 selected papers, 14 retain publisher-deposited Crossref abstracts and two retain publisher JATS abstracts from PMC. Every paper has a DOI, author attribution and an explicit CC BY 4.0 license. Thirteen Crossref licenses specify the version of record. One specifies the license while leaving the version unspecified. Both PMC licenses appear in the article's permissions element. The private projection preserves each attribution, license URL and source checksum. [Crossref license fields](https://www.crossref.org/documentation/schema-library/markup-guide-metadata-segments/license-information/) · [PMC Open Access Subset](https://pmc.ncbi.nlm.nih.gov/tools/openftlist/) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

## Matching and exclusions

The source projection matched field, a year difference of at most one, and a word-count difference of at most 40 words or 10% of the machine passage, whichever was larger. The largest observed differences were 30 words in stack training and 35 in calibration. The native papers in these roles were published in 2014–2019 and 2018–2019 respectively. The four development references came from four journals in 2017 and 2019. They were reserved by DOI hash before matching and contributed no fitting rows. The source and year distributions limit what this comparison can say about other disciplines and human-origin paraphrases. [Role distributions](academic-sources.json)

Of 123 eligible native papers, 37 lacked a mapped field and 12 shared a known author key with a machine source. The final screen required every known author key of a matched machine source to be exclusive to that paper among the 96 candidates. The selected native papers shared no author keys. Document checks covered 873,746 normalized texts and source-title checks covered 13,218 normalized RAID titles. Historical and prospective reservations contributed only identity checks. Author overlap with legacy corpora is unknown where author metadata is unavailable. [Isolation counts](academic-sources.json)

## Verify the frozen inputs

The private M6 study directory is `~/vibechecker/phase1-check/calibration-v4-academic/`. Its archive `academic-source-selection-scripts-v1.tar.gz` contains the extraction and matching code. The JSON record lists the archive and member hashes, publisher metadata snapshots, projections and study receipts. It commits to all 34 frozen Crossref responses. The upstream APIs can update records over time. The frozen responses and projections preserve the study used here.

From the repository root, run the following against the study directory to verify the frozen input files, archived selection code and original Crossref responses. Replaying the study's `bind` and `plan` commands with these inputs reproduces the 7/5/4 role counts. [Operator commands](academic-addition-protocol.md)

```sh
python - "$HOME/vibechecker/phase1-check/calibration-v4-academic" <<'PY'
import gzip
import hashlib
import json
import sys
import tarfile
from pathlib import Path

study = Path(sys.argv[1])
record = json.loads(Path("eval/reports/phase-1/academic-sources.json").read_text())
archive = record["private_script_archive"]
expected = {archive["name"]: archive["sha256"]}
for group in record["snapshot_files_sha256"].values():
    expected.update(group)
for name, checksum in expected.items():
    if hashlib.sha256((study / name).read_bytes()).hexdigest() != checksum:
        raise SystemExit(f"Checksum mismatch in {name}")

with tarfile.open(study / archive["name"], "r:gz") as bundle:
    actual = {f.name: hashlib.sha256(bundle.extractfile(f).read()).hexdigest() for f in bundle}
if actual != archive["members_sha256"]:
    raise SystemExit("Selection scripts differ from their source record")

intake = json.loads((study / "human-crossref-intake-v1.json").read_text())
responses = {q["query_sha256"]: q["response_sha256"] for q in intake["query_plan"] if "response_sha256" in q}
if len(responses) != record["crossref_response_cache"]["file_count"]:
    raise SystemExit("Unexpected number of publisher responses")
for key, checksum in responses.items():
    path = study / "crossref-queries-v1" / f"{key}.json.gz"
    if hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest() != checksum:
        raise SystemExit(f"Checksum mismatch in {path.name}")
PY
```
