# Invariants: From Security Intent to Testable Guarantees

## 1) Overview
Invariants are enforceable statements about protocol safety that must hold across *all* reachable states, not just happy-path tests. Strong audits translate informal claims (“we are solvent”) into machine-checkable properties suitable for Foundry invariants, Echidna campaigns, and symbolic analysis.

## 2) Core Mental Model
Treat protocol behavior as a state machine with adversarial scheduling.

Practical classification:
- **State invariants**: always true in every post-state.
- **Temporal invariants**: true across time windows/order constraints.
- **Control-flow invariants**: true regardless of path composition across multiple functions/contracts.

If a property depends on call order, role sequence, or time delay, encode that explicitly.

## 3) Minimal Vulnerable Example (solvency desync)
```solidity
contract Vault {
    mapping(address => uint256) public shares;
    uint256 public totalShares;
    uint256 public accountedAssets;

    function deposit() external payable {
        shares[msg.sender] += msg.value;
        totalShares += msg.value;
        accountedAssets += msg.value;
    }

    function sweep(address to, uint256 amt) external onlyOwner {
        payable(to).transfer(amt);
        // accountedAssets not decremented => accounting no longer maps to real assets
    }
}
```

## 4) Realistic Exploit / Failure Scenario (step-by-step)
1. Users deposit and system reports healthy collateralization from `accountedAssets`.
2. Governance executes treasury sweep during market stress.
3. Real balance drops, but liabilities and health metrics keep using stale accounting.
4. Integrators continue allowing borrowing/withdrawals on false solvency signal.
5. Cascade emerges: failed withdrawals, liquidations at bad prices, and governance panic actions.

No single user function is “broken” in isolation; the invariant failed across privileged and user paths.

## 5) Defensive Design Patterns + Mitigation Strategies
- **Write invariants as executable specs** in tests and docs.
- **Cross-function assertion design**: validate properties after every mutating entry point.
- **Temporal guards**:
  - governance delay invariants (e.g., min timelock before execution),
  - emission-rate bounds per epoch,
  - cooldown constraints on sensitive transitions.
- **Composable accounting checks**: distinguish internal ledger, token balances, and unrealized PnL assumptions.
- **Failure-domain partitioning**: isolate non-critical functions so invariant breach cannot spread instantly.

### Example testable invariants (audit-ready)
- `sum(userBalances) <= totalAccountedLiabilities`
- `paidRewards + outstandingRewards <= fundedRewards + dustTolerance`
- `queuedUpgradeTimestamp + delay <= executionTimestamp`
- `if pausedForInsolvency then newDebtMint == 0`

## 6) EVM-Level Reasoning and Execution Nuance
- Forced ETH transfers and unusual token semantics can invalidate naive balance equality checks.
- Delegatecall/proxy upgrades can alter storage interpretation; invariants must be upgrade-aware.
- Reentrancy and multi-call composition break assumptions that hold per-function but fail per-transaction path.
- Control-flow integrity matters: the same set of calls in different order can violate temporal safety constraints.

## 7) Common Developer Mistakes
- Defining invariants too vaguely (“system remains safe”) to test.
- Testing only end-of-test conditions instead of checking after each state transition.
- Ignoring governance/admin paths when writing user-facing invariants.
- Assuming on-chain token balances perfectly represent realizable assets without liquidity/penalty considerations.
- Treating invariant testing as optional once unit tests pass.

## 8) Strong Invariants That Must Hold
- Internal accounting must map to on-chain realizable balances within explicit model assumptions.
- Privileged and user call sequences must preserve solvency, authorization, and payout correctness.
- Emissions and rewards over any time window must remain within configured caps and funded reserves.
- Governance actions must satisfy declared delay and quorum constraints before taking effect.
- No reachable control-flow path should produce a state that violates documented safety properties.
