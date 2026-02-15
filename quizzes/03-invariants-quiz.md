# Invariants Quiz

1. A protocol invariant states `assets >= liabilities`, but liabilities exclude pending rewards. Describe a failing scenario where this invariant passes.
2. How would you encode a temporal invariant that enforces governance delay across queue/cancel/requeue edge cases?
3. Why can per-function unit tests pass while sequence-level invariants fail in production bundles?
4. A vault receives forced ETH. How should solvency invariants be reframed to tolerate this without masking real insolvency?
5. What pre- and post-upgrade invariants should run to detect storage layout corruption before reopening user actions?
6. How do you define an invariant that allows token rescue operations but forbids rescue of user-accounted assets?
7. In pause/unpause workflows, what invariant prevents queue-jumping and unfair withdrawal ordering?
8. During an incident with many broken properties, how do you isolate root-cause invariant breach from downstream symptoms?
