# Crisis Lab directory layout

Canonical organization:

```text
docs/research/crisis-lab/
  README.md
  DIRECTORY-LAYOUT.md
  CRL-000-CHARTER.md
  CRL-001-EVENT-CATALOG.md
  EVENT-CATALOG-v0.1.0.json
  CRL-002-DATA-ACQUISITION.md
  DATA-ACQUISITION-REGISTER-v0.1.0.json
  CRL-002-VPS-RUNBOOK.md
  CRL-003-DATA-QUALITY-MANIFEST.md
  CRL-004-HISTORICAL-REPLAY.md
  CRL-005-CONTROLS-BASELINES.md
  CRL-006-SYNTHETIC-STRESS.md
  CRL-007-SEVERITY-RANDOM-WINDOWS.md
  CRL-008-SHADOW-CHALLENGER.md
  CRL-009-SURVIVAL-CERTIFICATE.md
  CRL-010-INDEPENDENT-AUDIT.md
  RESEARCH-LOG.md
  RESULTS-INDEX.md

research/crisis_lab/            # active CRL-002+ research-only code; never imported by production yatl
data/research/crisis-lab/       # local/VPS runtime data; ignored by Git
artifacts/research/crisis-lab/  # generated evidence; publish only bounded/canonical subsets
```

Rules:
- production YATL modules must not import from the research tree;
- runtime datasets remain outside Git;
- only bounded manifests, indexes and intentionally published evidence enter Git;
- one event/window/scenario identity must be stable across replay;
- any future code directory is opened only by its own CRL checkpoint.
