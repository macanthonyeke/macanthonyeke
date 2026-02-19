# Invariants

## 1) Title & clear overview
Invariants convert security intent into testable guarantees. They are not prose aspirations; they are properties that must hold across every reachable state and call sequence.

In practice, strong audits pair invariants with fuzzing, stateful property tests, and adversarial sequence generation.

## 2) Core mental model
Classify invariants into:
- State invariants (always true after each transition)
- Temporal invariants (true over time windows)
- Control-flow invariants (true regardless of function sequencing)

If a claim depends on order, delays, or role transitions, encode that explicitly.

## 3) Minimal vulnerable example (Solidity)
```solidity
contract Vault {
    uint256 public accountedAssets;
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
        accountedAssets += msg.value;
    }

    function sweep(address to, uint256 amt) external onlyOwner {
        payable(to).transfer(amt);
        // missing accountedAssets decrement => solvency signal drift
    }
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Users deposit; protocol reports healthy collateralization.
2. Owner/governance performs treasury sweep.
3. Internal accounting remains unchanged while real assets drop.
4. Integrators keep allowing borrows/withdrawals based on stale solvency metrics.
5. Stress event triggers failed withdrawals and cascading liquidations.

## 5) Defensive design patterns + mitigation strategies
- Write invariants as executable checks in Foundry/Echidna.
- Assert properties after every mutating entry point.
- Add temporal invariants for governance delays and emissions caps.
- Use compositional accounting checks (ledger vs actual balances vs model assumptions).
- Gate critical transitions with explicit invariant assertions and emergency breakers.

## 6) EVM-level reasoning and execution nuance
- Forced transfers and token quirks break naive `balance == accounting` assumptions.
- Delegatecall upgrades can alter storage semantics and invalidate previous invariants.
- Multi-call bundles can violate properties that hold in isolated unit tests.
- Control-flow integrity matters: same calls in different order can break temporal guarantees.

## 7) Common mistakes developers make
- Vague invariants that cannot be tested.
- Checking only end-of-test states rather than per-transition safety.
- Omitting governance/admin paths from invariant scope.
- Assuming token balance equals realizable asset value under all conditions.
- Stopping at unit tests without adversarial sequence fuzzing.

## 8) Strong, clear invariants that must hold
- Internal liabilities must map to realizable on-chain assets within defined model assumptions.
- Privileged and user call sequences must preserve solvency and authorization properties.
- Reward emissions over any interval must stay within configured caps and funded limits.
- Governance actions must satisfy delay/quorum constraints before effect.
- No reachable sequence should violate documented safety properties.

### Practical testable examples
- `sumUserBalances <= totalLiabilities`
- `paidRewards + outstandingRewards <= fundedRewards + dustTolerance`
- `queuedTimestamp + timelockDelay <= executionTimestamp`
- `if insolvencyPause then newDebtMint == 0`
