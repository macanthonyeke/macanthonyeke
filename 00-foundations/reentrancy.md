# Reentrancy: Beyond CEI

## 1) Overview
Reentrancy is not one bug pattern; it is a family of control-flow integrity failures where untrusted code regains execution before the caller has finalized state and risk boundaries. The classic DAO pattern still appears, but modern incidents are more often **cross-function**, **callback-driven**, or **read-only invariant bypasses** that slip past simplistic `nonReentrant` usage.

### Reentrancy Taxonomy (audit checklist)
- **Single-function reentrancy**: same function re-entered before state update.
- **Cross-function reentrancy**: function A makes external call, attacker re-enters function B sharing mutable state.
- **Cross-contract reentrancy**: shared accounting split across contracts; callback re-enters peer contract path.
- **Read-only reentrancy**: reentrant reads observe transient state and manipulate downstream pricing/liquidation decisions.
- **Token-hook reentrancy**: callback standards (ERC777 `tokensReceived`, ERC1155 receiver hooks) re-enter protocol logic mid-flow.

## 2) Core Mental Model
Treat every external interaction as `yield_to_adversary()`.

A robust auditor model:
1. Identify the **critical invariant set** for the function family (not just one function).
2. Mark every external call edge (`call`, token `transfer`, hook-invoking mint/burn, oracle callback surfaces).
3. Ask: “If control returns here through any public/external entry point, which invariants are temporarily false?”
4. If any temporary inconsistency can be monetized, reentrancy risk exists even when CEI appears locally correct.

**Why CEI alone is incomplete:** CEI protects local ordering, but does not automatically secure:
- cross-function state coupling,
- cross-contract shared accounting,
- callback-heavy token flows,
- read-only assumptions consumed by other contracts in the same transaction.

## 3) Minimal Vulnerable Example (token callback reentrancy)
```solidity
// Simplified vulnerable vault integrating an ERC777-like token.
interface IERC777Like {
    function send(address to, uint256 amount, bytes calldata data) external;
}

contract Vault {
    IERC777Like public rewardToken;
    mapping(address => uint256) public shares;
    mapping(address => uint256) public rewards;

    function claimAndExit(uint256 shareAmount) external {
        require(shares[msg.sender] >= shareAmount, "insufficient shares");

        uint256 payout = rewards[msg.sender];

        // External interaction before state finalization.
        rewardToken.send(msg.sender, payout, ""); // triggers tokensReceived hook

        // Too late: callback can re-enter and claim again through another path.
        rewards[msg.sender] = 0;
        shares[msg.sender] -= shareAmount;
    }
}
```

## 4) Realistic Exploit Scenario (step-by-step)
1. Attacker acquires shares and accumulates claimable rewards.
2. Attacker calls `claimAndExit` from a contract wallet implementing `tokensReceived`.
3. Vault calls `rewardToken.send`, which invokes attacker hook.
4. Hook re-enters vault through `claimRewards()` or `withdraw()` path that still sees old `rewards[msg.sender]` / `shares[msg.sender]`.
5. Second path transfers additional assets or updates accounting in attacker-favorable order.
6. Original frame resumes and performs stale post-call state writes.
7. Net effect: double-claim, share/accounting desync, or solvency breach.

Historical context: The DAO established the canonical pattern, but modern protocols still ship exploitable variants because audits and tools often focus on direct same-function recursion while missing multi-function/callback state coupling.

## 5) Defensive Design Patterns + Mitigations
- **Layered defense, not single primitive:**
  - CEI at each mutation site,
  - reentrancy mutexes on all functions sharing critical state,
  - pull-payment withdrawal queues for value transfer.
- **State partitioning:** segregate reward accrual, principal accounting, and settlement into explicitly ordered phases.
- **Callback-aware integrations:** treat ERC777/1155 hooks as adversarial code execution points.
- **Cross-function lock domains:** one lock per state domain (e.g., `accountingLock`, `governanceLock`) when function families interdepend.
- **Read-only hardening:** avoid exposing transient values used by downstream protocols mid-update; snapshot at stable checkpoints.
- **Adversarial testing:** fuzz with malicious receiver/hook contracts across all externally callable paths.

## 6) EVM-Level Reasoning and Execution Nuance
- `CALL` transfers control and gas; caller cannot assume linear execution.
- Reentrant frames read globally shared storage state as-of current writes; uncommitted logical assumptions are exploitable.
- `STATICCALL` is non-mutating for callee, but can still be abused via read-only reentrancy against time-sensitive pricing logic consumed elsewhere.
- Token transfers are not “just balance moves” in hook-enabled standards; they are arbitrary code execution opportunities.
- Proxy architectures increase reentrancy surface by multiplying reachable entry points into shared storage.

## 7) Common Developer Mistakes
- Guarding only `withdraw` while `claim`, `deposit`, or `harvest` mutate correlated state unguarded.
- Assuming ERC20 transfers are side-effect free across all integrations.
- Applying CEI in one function but violating it in helper paths called indirectly.
- Forgetting read-only reentrancy impact on oracle-dependent liquidations.
- Treating reentrancy as a “legacy DAO-only” issue rather than a control-flow class.

## 8) Invariants That Must Hold
- During any external call, internal state must be globally consistent for all callable paths.
- A user’s cumulative withdrawals + claims must never exceed their realizable entitlement.
- Repeating any claim/withdraw path without new accrual must yield zero incremental value.
- Cross-function execution ordering must preserve protocol solvency at every reentry point, not only at transaction end.
- No callback path may observe a partially applied state transition that can be monetized.
