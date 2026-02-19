# Reentrancy

## 1) Title & clear overview
Reentrancy is a control-flow integrity failure: a contract hands execution to untrusted code before finalizing critical state, and the callee re-enters vulnerable paths while assumptions are stale.

Modern reentrancy is broader than the classic DAO drain. Audits must cover:
- Single-function reentrancy
- Cross-function reentrancy
- Cross-contract reentrancy
- Read-only reentrancy
- Token-hook callback reentrancy (ERC777/erc1155 receiver hooks)

## 2) Core mental model
Treat every external interaction as `yield_to_adversary()`.

Audit workflow:
1. Identify shared financial state domains (balances, debt, reward indexes, collateral health).
2. Mark every external call edge.
3. Ask: “What paths can be re-entered before this frame commits?”
4. Check whether any intermediate inconsistent state is economically exploitable.

CEI is necessary but not always sufficient. If multiple entry points share state, you usually need lock domains and/or pull settlement architecture.

## 3) Minimal vulnerable example (Solidity)
```solidity
interface IERC777Like {
    function send(address to, uint256 amount, bytes calldata data) external;
}

contract Vault {
    IERC777Like public rewardToken;
    mapping(address => uint256) public principal;
    mapping(address => uint256) public rewards;

    function claimAndWithdraw(uint256 amount) external {
        require(principal[msg.sender] >= amount, "insufficient");

        uint256 payout = rewards[msg.sender];

        // External call before state finalization.
        rewardToken.send(msg.sender, payout, ""); // may trigger tokensReceived callback

        rewards[msg.sender] = 0;
        principal[msg.sender] -= amount;
    }
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Attacker accumulates rewards and principal in the vault.
2. Attacker uses a receiver contract implementing callback hooks.
3. `claimAndWithdraw` triggers token send, invoking attacker callback.
4. Callback re-enters `claim()`/`withdraw()` while old `rewards` and `principal` are still visible.
5. Attacker extracts additional payout or bypasses accounting checks.
6. Original frame resumes and writes stale values, cementing desync.
7. Result: over-withdrawal, double-claim, or solvency drift.

## 5) Defensive design patterns + mitigation strategies
- Enforce CEI in every mutating path.
- Use reentrancy locks on all functions sharing the same accounting domain.
- Prefer pull-based claims/withdrawals where possible.
- Treat hook-enabled token standards as arbitrary code execution boundaries.
- Minimize external calls in sensitive paths and isolate settlement phases.
- Add adversarial fuzzing with malicious callbacks across all entry points.

## 6) EVM-level reasoning and execution nuance
- `CALL` transfers control and gas to arbitrary code.
- Nested frames can observe persistent storage as currently written, including partially applied transitions.
- Read-only reentrancy can still break downstream risk logic if transient state is consumed by dependent contracts.
- Proxy systems increase reentrancy reachability because many selectors write shared storage.

## 7) Common mistakes developers make
- Protecting only `withdraw` but leaving correlated functions unguarded.
- Assuming ERC20 transfers are always callback-free in integrated environments.
- Believing CEI in one function secures all related functions.
- Ignoring read-only reentrancy against pricing/health checks.
- Treating reentrancy as a legacy-only issue.

## 8) Strong, clear invariants that must hold
- During any external call, internal accounting must remain globally consistent for all reachable paths.
- A user’s cumulative extraction cannot exceed principal plus legitimate accrual.
- Repeated claim/withdraw calls without new accrual must return zero incremental value.
- No callback path may observe monetizable partially applied state transitions.
- Protocol solvency must hold at every externally reachable reentry point, not only at transaction end.
