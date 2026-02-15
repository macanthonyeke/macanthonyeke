# Reward Accounting Lesson (Audit-Ready)

## 1) Title & clear overview
Reward accounting is a solvency and fairness system, not just arithmetic. Protocols fail when liabilities accrue faster than funded emissions, when rounding favors strategic actors, or when update ordering enables timing extraction.

## 2) Core mental model
Track four ledgers explicitly:
1. funded emissions,
2. distributed payouts,
3. outstanding user liabilities,
4. residual dust.

A secure design guarantees these ledgers reconcile under adversarial ordering.

## 3) Minimal vulnerable example (Solidity)
```solidity
function claim() external {
    uint256 pending = stake[msg.sender] * acc / 1e12 - debt[msg.sender];
    reward.transfer(msg.sender, pending);
    // debt not updated => replay claim
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Attacker stakes minimal amount before a large reward top-up transaction.
2. Due to ordering, attacker is credited for rewards intended for prior stakers.
3. Attacker claims rapidly across split addresses to maximize rounding residue.
4. Repeated claims exploit stale debt updates.
5. Treasury becomes underfunded; late users receive reduced/failed payouts.

## 5) Defensive design patterns + mitigation strategies
- Funding-first reward notifications with transfer-in verification.
- High-precision accumulators plus explicit dust tracking/recycling.
- Strict sequence: update global index -> settle user -> mutate stake -> update debt.
- Epoch snapshots or vesting windows to reduce reward sniping.
- Underfunding circuit breaker and liability caps.

## 6) EVM-level reasoning and execution nuance
- Integer truncation creates predictable edge exploitable via granular account splitting.
- Same-block ordering and MEV bundling allow deterministic timing games around reward updates.
- External token calls can create reentrancy during claim unless state is finalized.

## 7) Common mistakes developers make
- Ignoring underfunding as an “ops issue” instead of an exploitable design fault.
- No dust accounting policy.
- Assuming one-account behavior represents adversarial strategy.
- Missing invariants in tests for cumulative liabilities.

## 8) Strong invariants that must hold
- `distributed + outstanding <= funded + toleratedDust`.
- Repeated claim without new accrual yields zero payout.
- Aggregate user entitlements track global emission schedule within documented rounding tolerance.
- Reward liabilities are always satisfiable by realizable reserves under supported token semantics.
