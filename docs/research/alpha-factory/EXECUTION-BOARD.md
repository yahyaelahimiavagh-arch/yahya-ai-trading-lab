# YATL Alpha Factory — Execution Board

Status date: **2026-09-30**
Mode: **PAPER / RESEARCH ONLY**
Authority: **LIVE_MASTER_LOCK=OFF / P11 LOCKED**

This board is the operational view of
`ALPHA-FACTORY-MASTER-PLAN-v1.0.md`. It should stay short and should always
answer four questions:

The final section dated 2026-09-30 supersedes older `CURRENT` markers in this
file when they conflict with the latest repository state.

1. What is open now?
2. What is next?
3. What is locked?
4. What evidence closes the current checkpoint?

## Current position

### CLOSED — AF-00 Governance Closeout

Objective:
- establish Alpha Factory as the authoritative program layer;
- preserve all frozen Generation protocols;
- commit the machine-readable stage contract;
- obtain a green Final HEAD.

Artifacts:
- `docs/research/alpha-factory/ALPHA-FACTORY-MASTER-PLAN-v1.0.md`
- `docs/research/alpha-factory/ALPHA-FACTORY-STAGE-GATES-v1.0.json`
- authoritative summary in `docs/MASTER-PLAN.md`

Closeout gate:
- documents present and internally consistent;
- no mutation of frozen GEN2-MASTER-001;
- GitHub Actions green on Final HEAD.

### CANONICAL CLOSED — GEN2-001

State:
- stop overlay;
- 0 proposals;
- retained negative evidence;
- no same-evidence rescue.

### CANONICAL CLOSED — GEN2-002

State:
- volatility scaling;
- `INVALIDATED_BEFORE_ECONOMIC_EVALUATION`;
- 40 structurally incomplete estimator windows;
- 0 proposals;
- no same-evidence target/window/EWMA rescue.

## CLOSED — AF-03A Source Unblock Sprint

Closeout:
- `RIE-CAND-0011` → `BLOCKED_REPRODUCIBILITY`
- `RIE-CAND-0022` → `BLOCKED_SOURCE`
- `RIE-CAND-0027` → `METHOD_SPECIFIED`

AF-03A performed zero performance runs.

Because 0027's original source-method blocker is now resolved, the preregistered
availability-skip rule returns priority to 0027.

### CANONICAL CLOSED — GEN2-003 / RIE-CAND-0027

State:
- downside-volatility scaler vs total-volatility comparator;
- single canonical Development run complete;
- `FAIL / 0 proposals`;
- all six opportunity failures were `VALID_SCALE_DECISION_FRACTION_LOW`;
- directional entries/trades were preserved;
- downside scaling improved control economics and median drawdown;
- total-volatility comparator outperformed downside scaling in base and stress;
- primary Blind-Spot classification: `REDUNDANT_EDGE`;
- secondary mechanism: `ESTIMATOR_AVAILABILITY_LIMITATION`;
- no same-evidence rescue, threshold relaxation, estimator retune, or post-hoc
  total-vol promotion.

Canonical closeout:
- `GEN2-003-CANONICAL-RESULT-v0.1.0.json`;
- `GEN2-003-CANONICAL-CLOSEOUT-v0.1.0.md`;
- artifact SHA-256 `c9e864aa24e4b722671001af42f2165e608078fe7865bebdc02f8d26d4fa2255`.

Fresh OOS / recent reserve / P10 remained untouched.

## PARALLEL DESIGN LANE — AF-01 / AF-02

These tasks may be designed without spending sealed evidence:

### AF-01 Opportunity Data Design
- point-in-time liquid Spot universe;
- symbol eligibility/listing history;
- gap-aware policies;
- capacity/liquidity metadata;
- no Futures execution capability.

### AF-02 Registry v2
Add:
- `alpha_family_id`;
- `economic_mechanism_id`;
- opportunity frequency;
- turnover expectation;
- capacity sensitivity;
- regime dependence;
- duplication/common-factor fingerprint.

No mass data expansion or migration happens before these designs are accepted.

## AFTER THAT — AF-03B Independent Alpha Sweep #2

Priority families deliberately outside the current trend-overlay cluster:

1. mean reversion;
2. crash/rebound/dislocation;
3. volume-conditioned signals;
4. liquidity regimes;
5. recurring session/time effects;
6. relative strength / lead-lag on a point-in-time liquid Spot universe.

Trend/regime research may continue, but it cannot dominate candidate count while
these families remain unexplored.

## Locked gates

### AF-07 Portfolio / Ensemble
LOCKED until standalone component evidence exists.

### AF-08 Fresh OOS
SEALED until a survivor or portfolio is frozen.

### AF-09 Crisis Certification
LOCKED until OOS survival.

### AF-10 Independent Audit
LOCKED until crisis certification.

### AF-11 Forward Opportunity Validation
LOCKED for new Alpha Factory candidates until independent audit.

### AF-12 Capacity / Capital Scaling
LOCKED until a Forward-capable edge exists.

### Live
NOT AUTHORIZED.

## Parallel P10 lane

Existing P10 real-forward evidence collection continues independently.

Alpha Factory:
- does not read P10 for Development selection;
- does not write P10;
- does not modify P10 candidates/gates/windows;
- does not convert historical success into P10 acceptance.

## Work-unit discipline

Every research work unit must close with:

1. work-unit ID;
2. exact repository HEAD;
3. protocol/specification identity;
4. tests/CI state;
5. evidence boundary used;
6. canonical artifact/result when applicable;
7. closeout state;
8. explicit next allowed action.

No work unit remains in an ambiguous “almost done” state.

## Director command semantics

- “ادامه / بریم” = continue the current authorized research/work unit.
- “مرج” = explicit merge authorization for the current accepted branch/PR.
- “مرج و ادامه” = merge current accepted work, then start the next authorized
  checkpoint.
- no merge is inferred from successful tests or CI.

## Current immediate queue

1. GEN2-001 / GEN2-002 / GEN2-003 canonical outcomes remain immutable.
2. RIE-CAND-0028 exact source/method assessment.
3. AF-01 Opportunity Data Design.
4. AF-02 Registry v2 design.
5. AF-03B independent Alpha Sweep #2.
6. AF-04 standalone Development for the next preregistered candidate.
7. AF-06 independence/cluster gate when survivors exist.
8. AF-07+ only when unlocked.

## Execution mode checkpoint

Authoritative matrix:
`EXECUTION-MODE-MATRIX-v1.0.md`

Current package:
- **RIE-CAND-0028 exact source/method assessment**
- Mode: `CHAT_DIRECTOR`
- Goal: determine whether the pre-existing 3-state HMM regime candidate is
  reproducible enough for a bounded preregistration.
- No performance run is authorized during source/method assessment.
- Work is not required unless later implementation becomes substantial.

Upcoming required-mode gates:
1. **AF-01B Opportunity data implementation** → `⚠️ WORK GATE`
2. **AF-02B Registry migration/classification** → `⚠️ WORK GATE`
3. **AF-03C Deep Alpha Sweep** → `⚠️ WORK GATE`
4. **AF-03D Corpus Synthesis Checkpoint** → `⚠️ WORK + ASTRA GATE` when threshold fires
5. **AF-10B Corpus-scale independent audit** → `⚠️ WORK + ASTRA GATE`

The Director must show the relevant warning before execution begins. A generic
continue command does not cross these gates.

Astra threshold counters to track:
- deep-reviewed sources since prior Astra synthesis;
- reproducible methods since prior Astra synthesis;
- total registered candidates;
- survivor variants;
- independent mechanism clusters;
- completed generations;
- negative-evidence records.

## Cross-cutting governance — Blind spots / conditional edges

Authoritative document:
BLIND-SPOT-AND-CONDITIONAL-EDGE-GOVERNANCE-v1.0.md

Rules now active for future research closeouts:
- gate failure is not automatically NO_EDGE;
- every meaningful rejection receives a failure classification;
- rejection closeout includes a salvage review;
- new conditional logic requires a new candidate/protocol and cannot rescue the
  failed candidate on spent evidence;
- candidates may ultimately be ALL_REGIME_EDGE or REGIME_CONDITIONAL_EDGE;
- conditional edges require explicit operating-envelope and detector metrics;
- crisis failure remains negative evidence even when a conditional-edge
  hypothesis is opened.

The six HSSE-004A survivors remain NOT all-regime certified. Their possible
normal-regime/conditional use is an untested future hypothesis, not approval.

### Work conservation

Default mode for governance/review/design remains CHAT_DIRECTOR.

Do not invoke Work merely because a task touches multiple documentation files.
Use Work for substantial implementation, bulk data, large numerical analysis,
repository-wide migration, or heavy test/build execution.

Before each Work gate, first ask whether Chat can complete the task safely.



## Mass Candidate Factory status — 2026-09-27

### MCF-00 — CLOSED
Governance and mass-factory architecture accepted.

### MCF-01 — CLOSED
Family manifest/candidate identity schema and initial mechanism catalog accepted.

### MCF-02 — IMPLEMENTATION ACCEPTED / MERGED

- PR #144 merged.
- implementation Final HEAD:
  `637b865c097246a901c937bb1de8fc4b90c8f8c3`
- merged main:
  `2adb89eb2eae1c3160e0adb66aabbb2c2dd85f66`
- Actions run `36332442478`: green.
- engineering calibration only; no production selection batch.

Authoritative closeout:
`MCF-02-IMPLEMENTATION-CLOSEOUT-v1.0.md`

### AF-02B — BOUNDED MIGRATION COMPLETE

31/31 legacy candidates migrated conservatively to Registry v2.

- no candidate ID lost;
- no performance authorization granted;
- GEN2-001/002/003 canonical evidence linked;
- RIE-CAND-0028 source/adaptation split preserved.

Artifacts:
- `CANDIDATE-REGISTRY-V2-v1.0.json`
- `AF-02B-REGISTRY-V2-MIGRATION-CLOSEOUT-v1.0.md`

### Current production blocker

The Mass Candidate Engine is ready, but the first true mass Development
selection batch remains locked until AF-01B point-in-time opportunity data
foundation is implemented/accepted and production family/trial/evidence
manifests are frozen.

### Current next package

AF-01B Opportunity Data Foundation implementation.

Mode:
`WORK_REQUIRED`

Reason:
multi-file point-in-time universe/data loader, manifests, eligibility history,
gap-aware research API and bulk data plumbing.

No Work is required for per-candidate execution after the shared foundation is
built.


## Production Readiness checkpoint — 2026-09-27

### AF-01B — IMPLEMENTATION ACCEPTED / MERGED

Merged main:
`d6b0c2662d7c92123a099fd1e9cf79d16c0f3b5e`

Final reviewed implementation HEAD:
`7a34dc9a2d30d95b8d6461dc07f60bf2d32f9437`

Final Actions:
`36341399844` — green.

Director hardening before merge:
- stale interval eligibility blocked;
- MULTI_ASSET requires all policy-required intervals.

Authoritative closeout:
`AF-01B-IMPLEMENTATION-CLOSEOUT-v1.0.md`

### MCF-PROD-001 — PRE-OUTCOME GOVERNANCE FROZEN

Development boundary:
- population: 2020-01-01 through 2023-01-01 exclusive;
- scored search: 2020-03-01 through 2023-01-01 exclusive;
- Fresh OOS/recent reserve/P10 remain unread.

Production universe:
- Binance Spot / USDT;
- dynamic monthly top-50 by lagged trailing-30d quote volume;
- 60d minimum admitted history;
- 99.5% trailing continuity;
- ordinary Spot only;
- unresolved product classification blocked.

Search budget:
- target raw candidates: 8,000–12,000;
- hard cap: 12,000;
- 12 initial mechanism families;
- no survivor quota;
- zero survivors valid;
- no family may dominate the generation.

Frozen domain-plan:
- 9,176 raw Cartesian combinations before structural filtering;
- 8,640 expected structurally-valid combinations before any performance.

### AF-01C — CLOSED / IMPLEMENTATION ACCEPTED / POPULATION RECONCILED

Accepted main merge commit:
`ccb8eda76c63da9a164de59432bbe09d926b9d1f`

Implementation/reconciliation-fix HEAD:
`f6098c0b823cc98e33fcd9ca014512dd51026140`

Final population:
- 9,306 / 9,306 identities complete;
- 6,443 MONTHLY_SUCCESS;
- 2,863 preserved source-gap/failure identities;
- final status SHA:
  `59ef745317bb6e11c9bfad0e99643333d3611449332ec2da975fde9b1bd86703`;
- reconciliation:
  `POPULATION_COMPLETE_WITH_SOURCE_GAPS`;
- population reconciliation SHA:
  `1ecf1cbeec6473414d559fa433c0bda2e86de02cd89ab3a6f455dcf2af45dc17`.

Authoritative closeout:
`AF-01C-HISTORICAL-UNIVERSE-CLOSEOUT-v1.0.md`

No source-gap, timestamp-anomaly or invalid-schema evidence was repaired,
interpolated or deleted.

### MCF-03 — NEXT IMPLEMENTATION BLOCKER

Contract:
`MCF-03-PRODUCTION-INTEGRATION-CONTRACT-v1.0.md`

Adds:
- dynamic point-in-time universe binding;
- normalized per-symbol accounting;
- exact F0-F3 production runner;
- daily return artifacts for statistical adjudication.

### MCF-04 — NEXT IMPLEMENTATION BLOCKER

Contract:
`MCF-04-STATISTICAL-ADJUDICATION-CONTRACT-v1.0.md`

Adds severe filters:
- 50%+ local neighbor stability;
- Deflated Sharpe confidence >= 0.95;
- family PBO <= 0.20;
- required bootstrap reality-check diagnostic;
- |rho| >= 0.80 common-factor clustering;
- one deterministic representative per qualifying cluster.

No MCF-PROD-001 performance may be exposed before MCF-03 and MCF-04 are
implementation-accepted.

### Current execution route

1. AF-01C historical archive adapter and bulk population — **COMPLETE / ACCEPTED**.
2. Implement MCF-03 + MCF-04 production runner/statistical layer — **WORK_REQUIRED**.
3. Freeze exact generated candidate count/spec SHAs before performance.
4. Run MCF-PROD-001 Development — **MANUAL_VPS / DIRECTOR-SUPERVISED**.
5. Apply F0-F7 and freeze only qualifying independent representatives.
6. Fresh OOS remains sealed until step 5 completes.

No production performance run is authorized by this checkpoint alone.


## Production Readiness checkpoint — 2026-09-29 update

This section supersedes the older MCF-03/MCF-04 "next blocker" wording above
for current execution status.

### MCF-03 / MCF-04 — IMPLEMENTATION ACCEPTED / MERGED

PR #159 merged.

Accepted main merge commit:
`7ccefe3386947b5e6ef13c649629d9fdec55ec04`

Accepted implementation Final HEAD:
`cbb282ca008d90a8c610c426e32350b6d7fc9e7b`

Final implementation Actions run #372: **SUCCESS**.

No MCF-PROD-001 performance was exposed by implementation acceptance.

### MCF-PROD-001 — PRE-OUTCOME CANDIDATE FREEZE ACCEPTED

PR #160 merged.

Accepted main merge commit:
`69dc1c6d167b216bf26e2a8ade42e55f845dd417`

Frozen executable identities:

- raw candidates: 9,176;
- structurally valid: 8,640;
- implementation-blocked: 1,788;
- executable candidates: 6,852;
- candidate ledger SHA:
  `084150778f2270c2ce96dac631f2e0fb1e6f84fed3325a197a80aa3d59db8e73`;
- neighbor graph SHA:
  `4eb36ca827b5b458147e6ba2a74308353dfa047cd368d72e106f568b1f4fc4bb`;
- executable freeze SHA:
  `84d4f8ec6234ffb5afccf44ea044661d72af8b4de525b111118ae087907d1dc6`.

### MCF-PROD-001 — VPS FREEZE MATERIALIZER ACCEPTED

PR #161 merged.

Accepted main merge commit:
`f3803ebe0bd9ec43f71940d463098fde58aa4d1d`

The repository now has a fail-closed, immutable/idempotent VPS materializer and
read-back verifier for the accepted pre-outcome candidate freeze.

### CURRENT — Production Binding Preflight

Current work unit:
**MCF-PROD-001 production-binding preflight**

Current branch:
`mcf-prod-001-production-binding-preflight`

Purpose:

- scan the accepted AF-01C P-C corpus symbol-at-a-time;
- apply frozen 60-day history and 99.5% trailing-30d continuity rules;
- identify product-classification blockers before monthly top-50 ranking;
- reject current `exchangeInfo` as historical classification evidence;
- prevent unresolved high-liquidity symbols from being silently excluded;
- emit no candidate performance.

### Updated execution route

1. MCF-03/MCF-04 implementation — **COMPLETE / ACCEPTED**.
2. Exact 6,852-candidate/spec/neighbor freeze — **COMPLETE / ACCEPTED**.
3. VPS pre-outcome freeze materializer — **COMPLETE / ACCEPTED**.
4. Production binding preflight / historical product classification — **CURRENT**.
5. Freeze exact monthly point-in-time membership snapshots.
6. Materialize selected-union Development 15m/1h/4h runtime bars.
7. Freeze Development runner input manifest.
8. Run 6,852-candidate MCF-PROD-001 Development — **MANUAL VPS / DIRECTOR-SUPERVISED**.
9. Apply F0-F7 and freeze qualifying independent representatives.
10. Fresh OOS remains sealed until step 9 completes.

No Development strategy outcome is authorized before steps 4-7 close.


### MCF-PROD-001 — PRODUCTION BINDING PREFLIGHT ACCEPTED / MERGED

PR #162 merged.

Accepted main merge commit:
`8faaa84038aa1614a0964b35788390f949d18626`

Accepted implementation Final HEAD:
`ed7995ec12438cf0059be3cccb6c37d0a8c52f34`

Final Actions run #383: **SUCCESS**.

Real VPS audit on the accepted AF-01C P-C corpus returned:

- state: `CLASSIFICATION_INCOMPLETE`;
- symbols scanned: 413;
- unresolved data-eligible symbols: 384;
- preliminary raw classification frontier: 174;
- performance/Fresh OOS/recent reserve/P10 reads: false.

The monthly eligibility anomalies were independently reconciled to the accepted
AF-01C ledger:
6,443 MONTHLY_SUCCESS and 2,863 preserved non-success identities.

### CURRENT — Classification Frontier Closure

Current branch:
`mcf-prod-001-classification-frontier-closure`

Purpose:

- make the classification wave reflect the first 50 *potentially ordinary*
  symbols rather than raw top-50 rows that may include confirmed nonordinary
  products;
- allow deterministic wave expansion after a frontier symbol resolves
  nonordinary;
- stop classification once unresolved lower-ranked symbols cannot change any
  monthly membership;
- preserve `classification_complete` separately from
  `membership_resolved`;
- freeze zero-data-eligible source-gap months as explicit empty membership
  rather than treating them as integrity errors;
- emit no candidate performance.

Contract:
`MCF-PROD-001-HISTORICAL-PRODUCT-CLASSIFICATION-FRONTIER-v1.0.md`

Next acceptance evidence:

1. green CI;
2. exact Final HEAD;
3. real VPS rerun against the accepted P-C corpus;
4. corrected first frontier count and symbols;
5. safety flags remain false for performance/Fresh OOS/recent reserve/P10.

Historical source acquisition begins only after this implementation is accepted
and is a separate **WORK_REQUIRED** work unit.


### MCF-PROD-001 — CLASSIFICATION FRONTIER CLOSURE ACCEPTED / MERGED

PR #163 merged.

Accepted main merge commit:
`6420b34f32db6a0773b16962edb4269409e9c3b9`

Accepted implementation Final HEAD:
`afd3669d7185ddad1b1e5bd14c70aede06302a6b`

Final Actions run #385: **SUCCESS**.

Real VPS rerun:

- preflight SHA:
  `eff8f60b4a92be2a2e3266de86f9ad5a7c0bb9aaa8f25dc1a4a35805f058aa34`;
- unresolved data-eligible symbols: 384;
- corrected next classification frontier: 176;
- membership resolved: false;
- performance/Fresh OOS/recent reserve/P10 reads: false.

### CURRENT — Historical Product Classification Wave 001 Input Freeze

Current branch:
`mcf-prod-001-classification-wave-001`

Purpose:

- freeze the exact 176-symbol first acquisition wave;
- bind it to the accepted real-VPS preflight;
- prohibit current-status/ticker-only inference;
- freeze the historical source-admissibility hierarchy;
- validate the manifest and safety boundary before bulk acquisition.

Frozen manifest:

`MCF-PROD-001-CLASSIFICATION-WAVE-001.json`

Expected SHA-256:

`1a2a2b35efbec3a1cd96174e190d5dce0352e2a43d6da7a975928062c5aaad58`

Next execution gate:

`⚠️ WORK_REQUIRED — MCF-PROD-001-CLASSIFICATION-WAVE-001-ACQUISITION`

Bulk historical source acquisition has not started in this checkpoint.
No strategy performance is authorized.

## Director checklist — 2026-09-30

### وضعیت قطعی تا این لحظه

- [x] جمعیت تاریخی با ۹٬۳۰۶ هویت ماهانه کامل و آشتی داده شده است.
- [x] رانر تولیدی و داوری آماری پذیرفته شده‌اند.
- [x] ۶٬۸۵۲ نامزد اجرایی قبل از مشاهده نتیجه منجمد شده‌اند.
- [x] موج اول طبقه‌بندی تاریخی ۱۷۶ نماد را تعیین تکلیف کرده است.
- [x] موج دوم فقط دو نماد تصمیم‌ساز را تعیین تکلیف کرده است.
- [x] نقشه طبقه‌بندی تجمعی با **۱۷۸ ورودی** روی سرور ساخته شده است.
- [x] پیش‌بررسی نهایی روی سرور اجرا شده است.
- [x] پیش‌بررسی نهایی:
  - وضعیت آماده برای بستن ورودی تولیدی؛
  - ۳۴ ماه؛
  - مرز طبقه‌بندی بعدی صفر؛
  - عضویت ماهانه حل‌شده؛
  - اجتماع نمادهای انتخاب‌شده برابر **۱۷۵ نماد**.
- [x] ۲۰۶ نماد داده‌پذیر پایین‌تر هنوز طبقه‌بندی نشده‌اند، اما طبق قاعده مرز
  دیگر نمی‌توانند هیچ عضویت ماهانه پنجاه‌تایی را تغییر دهند.
- [x] هیچ موج طبقه‌بندی جدیدی لازم نیست.

پیش‌بررسی منبع:

`f0a177cc98d3946ead55dc69016d65178539ecd0c778c9c4ae0a193e3ba61cfc`

نقشه طبقه‌بندی:

`e19cb8539c29e6a95c453b6a680b56b5b88bddad65df8a67ca32a14ceab41012`

### کار جاری

- [ ] پیاده‌سازی ابزار **انجماد دقیق ۳۴ عضویت ماهانه**.
- [ ] آزمون شود که ورودی فقط از پیش‌بررسی آماده و تغییرناپذیر پذیرفته می‌شود.
- [ ] برای هر ماه، فهرست نمادها و هش همان عضویت قفل شود.
- [ ] اجتماع ۱۷۵ نماد داخل همان خروجی ثبت شود.
- [ ] ماه خالی، اگر وجود داشته باشد، به‌صورت صریح و معتبر حفظ شود.
- [ ] آزمون نهایی شاخه سبز شود.
- [ ] ادغام فقط با اجازه صریح مدیر انجام شود.

### بلافاصله پس از انجماد عضویت ماهانه

- [ ] اجرای واقعی ابزار روی سرور و ثبت هش خروجی.
- [ ] اجتماع دقیق نمادهای انتخاب‌شده از خروجی منجمد بازخوانی شود.
- [ ] مادی‌سازی داده‌های اجرایی ۱۵ دقیقه، ۱ ساعت و ۴ ساعت فقط برای همان اجتماع.
- [ ] پوشش زمانی و شکاف‌های هر نماد/بازه زمانی بررسی و بدون ترمیم ساختگی ثبت شود.
- [ ] فهرست ورودی دقیق رانر توسعه منجمد شود.
- [ ] اتصال رانر به همین ورودی منجمد و نه هیچ منبع دیگری اثبات شود.

### شرط شروع اجرای ۶٬۸۵۲ نامزد

اجرای نتیجه عملکردی فقط وقتی مجاز است که همه موارد زیر بسته شده باشند:

- [x] هویت ۶٬۸۵۲ نامزد منجمد؛
- [x] جهان ماهانه از نظر طبقه‌بندی حل‌شده؛
- [ ] ۳۴ عضویت ماهانه منجمد؛
- [ ] اجتماع داده اجرایی مادی‌سازی و بررسی شده؛
- [ ] ورودی رانر توسعه منجمد؛
- [ ] آزمون اتصال رانر به همان ورودی منجمد سبز.

تا قبل از بسته‌شدن همه موارد بالا، هیچ نتیجه عملکردی نامزدها مجاز نیست.

### پس از اجرای عملکرد

- [ ] فیلترهای از پیش ثبت‌شده از مرحله صفر تا هفت اجرا شوند.
- [ ] نامزدهای ضعیف، کم‌فرصت، ناپایدار و تکراری حذف شوند.
- [ ] فقط نمایندگان مستقل واجد شرایط منجمد شوند.
- [ ] داده واقعاً ندیده‌شده فقط بعد از انجماد نمایندگان مستقل بررسی شود.

### مسیر موازی آینده‌نگر

- [x] جمع‌آورنده آینده‌نگر روی سرور فعال است.
- [x] پایش و پیام‌رسانی فقط خواندنی فعال است.
- [ ] نخستین خلاصه واقعی پس از گرم‌شدن جداگانه بررسی شود.
- [ ] داوری نهایی قبل از حداقل ۹۰ روز و شرط تعداد معامله انجام نشود.
- [ ] هیچ تنظیم دوباره نامزد یا آستانه از روی شواهد جاری انجام نشود.
- [ ] مرحله زنده بعدی تا داوری کامل قفل بماند.

### ممنوعیت‌های جاری

- اجرای زودهنگام ۶٬۸۵۲ نامزد؛
- خواندن داده واقعاً ندیده‌شده؛
- استفاده از ذخیره اخیر؛
- استفاده از مسیر آینده‌نگر برای انتخاب تاریخی؛
- تغییر آستانه‌ها بعد از دیدن نتیجه؛
- افزودن نماد خارج از عضویت منجمد؛
- اجرای واقعی.



## به‌روزرسانی ۳۰ سپتامبر ۲۰۲۶ — داده اجرایی و انجماد ورودی رانر

واحد کاری: `MCF-PROD-001-RUNTIME-DATA-MATERIALIZATION-AND-RUNNER-INPUT-FREEZE`.
این بخش وضعیت جاری قبلی درباره انجماد عضویت ماهانه را جایگزین می‌کند.

عضویت ماهانه بسته است و انجماد واقعی VPS در شواهد پذیرفته‌شده PR #168 ثبت شده است:

- main پذیرفته‌شده مبنا: `b71ae8fee40ab0b80c3dbc0349fbe7fb3b8be55a`؛
- آزمون نهایی PR #168: اجرای GitHub #398، شناسه `36687440489`، موفق؛
- هش عضویت: `c75aa5c4347dff5daeed1ca2625fb86e2df3f4e105fde55aed0248df4ce868b7`؛
- ۳۴ ماه و اجتماع دقیق ۱۷۵ نماد؛
- ۲۲ ماه با ۵۰ نماد، ۱۱ ماه صریحاً خالی، ۱ ماه با ۱۵ نماد؛
- `classification_complete=false` و `membership_resolved=true` عمدی و پذیرفته‌شده‌اند؛
- ۲۰۶ نماد پایین‌تر در تصمیم عضویت تأثیر ندارند و موج طبقه‌بندی دیگری لازم نیست.

مرحله جاری: **مادی‌سازی داده اجرایی + انجماد ورودی دقیق رانر**.
کد reusable در `production_runtime_data.py`، `production_runner_input.py` و
`production_input_vps.py` قرار دارد. داده بازار فقط برای اجتماع منجمد از AF-01C
خوانده می‌شود؛ اسکن خارج از اجتماع فقط هویت دفتر ماهانه را با آشتی پذیرفته‌شده
تطبیق می‌دهد. ۱ ساعت و ۴ ساعت با منطق پذیرفته‌شده `opportunity_data.views.derive`
و فقط bucket کامل ساخته می‌شوند. شکاف‌های ابتدا، انتها، ماه فاقد داده و bucket
ناقص به‌صورت صریح ثبت می‌شوند. هیچ شکافی ترمیم نمی‌شود.

رانر تولیدی ورودی آزاد نمی‌پذیرد. مسیر `ProductionRuntime.from_frozen_input`
فقط ماتریس نماد/بازه، عضویت، هزینه، نامزدها و داده دارای هش منجمد را مصرف می‌کند.
حالت آزمون مصنوعی به یک نامزد و شناسه داده `SYNTHETIC-` محدود است و freeze
تولیدی پذیرفته‌شده را قبول نمی‌کند. `run()` تولیدی پیش‌فرض بسته است و مجوز صریح
Director را لازم دارد؛ ابزارهای مادی‌سازی، freeze و verify هرگز آن را صدا نمی‌زنند.

وضعیت واقعی این PR: زیرساخت و تست، نه اجرای حجیم واقعی VPS.
تا دریافت خروجی واقعی VPS، داده ۵۲۵ مجموعه و هش نهایی runner input اثبات نشده‌اند.

- [x] عضویت ماهانه منجمد و شواهد واقعی VPS پذیرفته‌شده؛
- [x] ابزار reusable داده و انجماد ورودی رانر در این واحد کاری پیاده‌سازی شده؛
- [ ] مادی‌سازی واقعی ۱۷۵ × ۳ مجموعه روی VPS؛
- [ ] آشتی واقعی پوشش و شکاف‌ها و ثبت هش index؛
- [ ] انجماد واقعی runner input و ثبت هش مستقل؛
- [ ] verify روی همان HEAD بررسی‌شده و ثبت خروجی واقعی؛
- [ ] پذیرش صریح Director برای هر اجرای عملکرد بعدی.

**اجرای ۶٬۸۵۲ نامزد همچنان ممنوع است.** performance read=false؛ Fresh OOS و
recent reserve بسته و نخوانده؛ P10 read/write=false؛ LIVE_MASTER_LOCK=OFF؛
P11 قفل؛ PAPER/RESEARCH ONLY. شاخه RIE-006 و PR #152 دست‌نخورده می‌مانند.
قرارداد و دستور VPS در
`docs/research/alpha-factory/MCF-PROD-001-RUNTIME-INPUT-CONTRACT-v1.0.md` ثبت شده است.


## به‌روزرسانی ۳۰ سپتامبر ۲۰۲۶ — PR #169 بسته / Capacity Gate جاری

PR #169 با مجوز صریح Director پذیرفته و squash-merge شد.

- main جدید: `ab3eea1436cc72c8e0a33631215bc649192c7c95`;
- Final PR HEAD: `f86c62c042ee9630c36828e99cb1ace0217e1b22`;
- GitHub Actions #402 / `36742674671`: **SUCCESS**؛
- runner-input نهایی:
  `3d089036d8a2e3b91f2efe3190c0775bbcb957a76ff352b647cfb177e9587cd3`;
- runtime index:
  `55c8c476cd5043a652c09f060e2a58b6b1dd9cfd9bffef33e3d8ff7a3a6092c3`;
- ۵۲۵ dataset = ۱۷۵ نماد × ۳ timeframe؛
- verify مستقل:
  `RUNNER_INPUT_VERIFIED_NO_PERFORMANCE`.

بنابراین شروط قدیمی شروع performance از نظر membership/runtime/input بسته شده‌اند، اما
اجرای کامل ۶٬۸۵۲ نامزد هنوز مجوز ندارد.

### CURRENT — Capacity Benchmark Gate

واحد کاری جاری:

`MCF-PROD-001-CAPACITY-BENCHMARK-GATE`

هدف:
- اجرای blind و ثابت ۲۴ نامزد فقط برای اندازه‌گیری throughput/CPU/RAM؛
- انتخاب زیرمجموعه فقط از metadata منجمد و بدون outcome؛
- عدم چاپ/ذخیره PnL، return، trade count، drawdown، ranking یا survivor state؛
- استفاده نتیجه فقط برای تصمیم زیرساخت، shard size و worker count؛
- عدم تغییر candidate/family/threshold/evidence بر اساس benchmark.

اجرای کامل ۶٬۸۵۲ نامزد، F0-F7، Fresh OOS و هر promotion همچنان نیازمند gate و
مجوز صریح جداگانه Director است.

قرارداد:
`docs/research/alpha-factory/MCF-PROD-001-CAPACITY-BENCHMARK-GATE-v1.0.md`.


## به‌روزرسانی ۳۰ سپتامبر ۲۰۲۶ — OOM ظرفیت تأیید شد

نخستین benchmark واقعی ۲۴ نامزد روی main
`21aa64e774f54b0399c561dab3f33e47d17630ff`
در ۸/۲۴ با `RC=137` متوقف شد.

شاهد kernel:
- `oom-killer` فعال شد؛
- Python PID 48793 کشته شد؛
- anonymous RSS حدود `3,586,144 KiB`؛
- RAM VPS حدود 3.7 GiB؛
- swap صفر.

طبقه‌بندی Director:
`CONFIRMED_OOM / ENGINEERING_CAPACITY_FAILURE / NO_SELECTION_OUTCOME`.

هیچ نتیجه اقتصادی نامزد برای انتخاب منتشر یا ذخیره نشد.

کار جاری:
`MCF-PROD-001-BOUNDED-MEMORY-RUNTIME`

الزام‌ها:
- purge feature/liquidity derived cache بعد از هر candidate؛
- حفظ source bars و frozen input؛
- ثبت RSS در progress benchmark؛
- rerun همان benchmark ثابت ۲۴ نامزد پس از CI و merge؛
- full 6,852 همچنان قفل؛
- full runner نهایی علاوه بر purge، shard + process restart + checkpoint/resume
  خواهد داشت.


## به‌روزرسانی ۳۰ سپتامبر ۲۰۲۶ — Distributed Foundation در حال ساخت

PR #172 bounded-memory:
- HEAD: `4dc1cdbf4862dd398c408438b5bdc8dcd68ed3d2`;
- Actions #405: **SUCCESS**؛
- merge همچنان نیازمند اجازه صریح Director است.

PR #174 distributed execution foundation:
- سه node هدف: VPS / LAPTOP / WORKPC؛
- ۶٬۸۵۲ نامزد -> ۱۴ batch منطقی؛
- B001-B013 هرکدام ۵۰۰؛ B014 برابر ۳۵۲؛
- micro-shard حداکثر ۲۵؛
- claim/lease/heartbeat؛
- pause/resume و crash recovery؛
- resultهای content-addressed؛
- coordinator محلی SQLite؛
- Cloudflare Worker + D1 control plane؛
- worker client HTTPS؛
- node enrollment + hardware preflight؛
- worker bundle شامل runner input + دقیقاً ۵۲۵ data + ۵۲۵ gap map؛
- compact result projection برای حذف payloadهای سنگین غیرلازم MCF-04؛
- هیچ production performance command در Foundation وجود ندارد.

بعد از پذیرش #172:
1. runner-input جدید با code identity پذیرفته‌شده refreeze شود؛
2. benchmark ثابت ۲۴ نامزد دوباره روی VPS اجرا شود؛
3. concurrency واقعی از RSS/CPU تعیین شود؛
4. Foundation توزیع‌شده CI/merge شود؛
5. auto-ingest relay و full runner با process restart/checkpoint بسته شوند؛
6. اجرای ۶٬۸۵۲ فقط با مجوز جداگانه Director.
