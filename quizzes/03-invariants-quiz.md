# Invariants Quiz

1. Your invariant says `assets >= liabilities`, but liabilities exclude pending rewards and liquidation penalties. Provide a scenario where the invariant passes while protocol is economically insolvent.
2. A timelock requires 48 hours before upgrades, but emergency mode can shorten delay. What temporal invariant should be enforced to prevent governance-delay bypass abuse?
3. In Foundry invariant tests, random call sequences never hit a known bug that appears in production bundles. What control-flow assumptions are missing from your harness design?
4. Contract accounting uses internal ledger plus external strategy NAV report. How would you formulate an invariant that tolerates bounded oracle lag but still catches real solvency breaks?
5. A proxy upgrade changes storage layout for `totalDebt` and `totalShares`. Which pre/post-upgrade invariants would you run to detect silent corruption before enabling user actions?
6. System allows admin rescue of stray tokens. Describe a testable invariant that distinguishes legitimate rescue from theft of user-accounted assets.
7. Given sequence `pause -> partial withdraws -> unpause -> liquidations`, what invariant should guarantee user fairness and prevent queue-jumping side effects?
8. During incident response, multiple invariants fail simultaneously. How do you triage root-cause invariant versus downstream symptom invariants to guide safe recovery?
