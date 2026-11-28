#!/usr/bin/env python3
"""Export ColdTrace into the MMC Google Cloud Launchpad Showcase layout.

    python3 tools/showcase_export.py <showcase-clone>/2026-cohort/<folder-name>

Creates:
    <folder>/README.md   project overview, rewritten for the src/ + docs/ layout
    <folder>/LICENSE     MIT
    <folder>/src/        code, infrastructure, CI, tools, data (CSV shipped gzipped)
    <folder>/docs/       brief, deck, research, plan, security, screenshots, walkthrough

Only files tracked by git are copied, so .env, .venv and caches never leave the repo.
The 63 MB CSV is replaced by its 22 MB .gz copy; README tells readers to unzip it.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIG_CSV = "Backend/data/cold_chain_labeled_2022_2026.csv"
ROOT_GZ = "cold_chain_labeled_2022_2026.csv.gz"

# repo path prefix -> showcase destination (first match wins)
DOCS = {
    "PROJECT_DOCS/": "docs/",
    "SECURITY.md": "docs/SECURITY.md",
    "Weekly schedule/": "docs/weekly-schedule/",
}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], check=True, capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p]


def destination(path: str) -> str | None:
    if path in ("README.md", "LICENSE"):
        return path
    if path in (BIG_CSV, ROOT_GZ):
        return None  # handled separately
    for prefix, dest in DOCS.items():
        if path == prefix or path.startswith(prefix):
            return dest + path[len(prefix):] if prefix.endswith("/") else dest
    return "src/" + path


SHOWCASE_TREE = """```text
team-coldtrace/                                            # this showcase folder
├── README.md                                              # Project overview, GCP services, setup, Future Ideas
├── LICENSE                                                # MIT License
├── docs/
│   ├── ColdTrace_Brief.pdf · BRIEF.md · .docx             # 3-page brief
│   ├── RESEARCH_SUMMARY.md                                # Research & evaluation summary
│   ├── IMPLEMENTATION_PLAN.md                             # Timeline, owners, progress, risk register
│   ├── USER_RESEARCH.md                                   # Personas, interview guide & evidence log
│   ├── SECURITY.md                                        # Endpoint access, audit chain, secrets
│   ├── ColdTrace — Cold-Chain Operations Console (1).pptx # 8-slide presentation deck
│   ├── Screenshots and walkthrough/                       # 83 s silent walkthrough + console screenshots
│   └── weekly-schedule/                                   # Team weekly plan & checklists
└── src/
    ├── env.example                                        # Sample environment variables (never commit .env)
    ├── .github/workflows/ci-deploy.yml                    # CI/CD as used in the team repo (reference)
    ├── terraform/                                         # Infrastructure as Code (project, IAM, WIF, Pub/Sub, budget)
    ├── Validation_coldtrace.sql · bq_load_coldtrace.sh    # BigQuery load & validation queries
    ├── tools/                                             # Team git CLI and export script
    └── Backend/
        ├── coldtrace/                                     # FastAPI app, features, RF/SOP models, NIM, validation, cases, Pub/Sub
        ├── config/thresholds.json                         # Versioned thresholds & SLAs
        ├── data/cold_chain_labeled_2022_2026.csv.gz       # 2022–2026 labelled dataset (gunzip before running)
        ├── data/reference/                                # Locations, batches, shipments
        ├── frontend/                                      # Console UI (index.html, app.js)
        ├── artifacts/                                     # Trained Random Forest model & evaluation outputs
        ├── scripts/                                       # Data generation, training/eval, replay & NIM scripts
        ├── tests/                                         # Automated pytest suite
        ├── Dockerfile                                     # Production container for Cloud Run
        └── requirements.txt                               # Python 3.12 dependencies
```"""


def rewrite_readme(text: str, folder: str) -> str:
    # Replace the repository tree with the showcase layout (before path rewriting).
    start = text.find("```text\ncoldtrace/\n")
    if start != -1:
        end = text.find("```", start + 7) + 3
        text = text[:start] + "@@TREE@@" + text[end:]
    # Links and inline paths to documents.
    text = text.replace("PROJECT_DOCS/", "docs/")
    text = text.replace("](SECURITY.md)", "](docs/SECURITY.md)")
    # Code paths now live under src/.
    text = re.sub(r"(?<![\w/.-])(Backend/|terraform/|tools/ctpush|\.github/workflows/)", r"src/\1", text)
    text = re.sub(r"(?<![\w/.-])(Validation_coldtrace\.sql|bq_load_coldtrace\.sh)(?![\w])", r"src/\1", text)
    text = text.replace("@@TREE@@", SHOWCASE_TREE.replace("team-coldtrace/", folder + "/", 1))
    # Local setup: run from src/Backend and unzip the dataset first.
    text = text.replace(
        "   cd Backend\n   python3 -m venv .venv",
        "   cd src/Backend\n   gunzip -k data/cold_chain_labeled_2022_2026.csv.gz   # 22 MB → 63 MB labelled dataset\n   python3 -m venv .venv",
    )
    # The showcase asks for a "Future Ideas" section.
    text = text.replace("### 17.3 What's Next After BUILD", "### 17.3 Future Ideas (what's next after BUILD)")
    return text


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1]).expanduser().resolve()
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty; remove it or pick another folder.")
    out.mkdir(parents=True, exist_ok=True)

    count = 0
    for rel in tracked_files():
        dest = destination(rel)
        if dest is None:
            continue
        src = ROOT / rel
        if not src.is_file():
            continue
        target = out / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel == "README.md":
            target.write_text(rewrite_readme(src.read_text(encoding="utf-8"), out.name), encoding="utf-8")
        else:
            shutil.copy2(src, target)
        count += 1

    gz = ROOT / ROOT_GZ
    if gz.is_file():
        target = out / "src" / "Backend" / "data" / gz.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(gz, target)
        count += 1

    for required in ("README.md", "LICENSE", "src", "docs"):
        if not (out / required).exists():
            sys.exit(f"missing {required} in export")
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
    print(f"Exported {count} files ({size:.1f} MB) to {out}")


if __name__ == "__main__":
    main()
