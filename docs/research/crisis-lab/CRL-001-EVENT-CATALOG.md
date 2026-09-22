# CRL-001 — Versioned Crisis Event Catalog

Goal: build a source-backed catalog of crisis/regime windows without using future
knowledge in the decision stream.

For every event record:
- event_id and version;
- neutral event name/category;
- authoritative source references;
- first publicly knowable timestamp;
- pre-event, event and aftermath windows;
- timezone normalized to UTC;
- research/development or blind-holdout designation;
- market/regime hypotheses recorded before replay;
- no outcome-derived window trimming.

Initial research families:
- COVID crash;
- Russia–Ukraine war shock;
- Terra/LUNA;
- FTX;
- banking/liquidity stress;
- major Middle East geopolitical shocks;
- large energy/oil shocks;
- non-news crypto-native dislocations.

Exit gate:
catalog schema frozen, source/timestamp rules accepted and first catalog batch
ready for CRL-002. Event labels are context only and may not enter the trading
decision engine.
