# Reentrancy Auditor Guide (Advanced)

## 1) Title & clear overview
This guide is a practical audit companion for finding modern reentrancy risk in DeFi systems. It emphasizes multi-function state coupling, callback-driven integrations, and invariant-centric review—areas where superficial CEI checks often fail.

## 2) Core mental model
Think in **reentry windows**:
- A window opens whenever control is transferred to untrusted code.
- The window is dangerous if any callable path can observe or exploit partially applied state.
- Close the window by ensuring global consistency before interaction, or by forbidding reentry into the state domain.

Audit heuristic: “What can the attacker call *right now* before this frame finalizes?”

## 3) Minimal vulnerable example (Solidity)
```solidity
contract Vault {
    mapping(address => uint256) public principal;
    mapping(address => uint256) public rewards;

    function claim() external {
        uint256 amt = rewards[msg.sender];
        rewardToken.transfer(msg.sender, amt); // external call
        rewards[msg.sender] = 0;               // too late
    }
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Attacker contract has positive `rewards` balance.
2. Attacker calls `claim()`.
3. `rewardToken.transfer` triggers callback/hook or malicious token behavior.
4. Callback re-enters `claim()` before `rewards[msg.sender]=0`.
5. Same `amt` is transferred repeatedly.
6. Attacker drains reward reserve and leaves stale accounting for others.

## 5) Defensive design patterns + mitigation strategies
- CEI for every function mutating shared financial state.
- Reentrancy lock across *all* functions in the same accounting domain.
- Pull payment queues for outbound transfers.
- Callback-aware token allowlists or explicit hook-safe design.
- Invariant tests: repeated claim with no accrual should return zero.

## 6) EVM-level reasoning and execution nuance
- Reentrancy is enabled by `CALL` control transfer, not by a specific token standard.
- Nested frames share persistent storage visibility; partial logical transitions are exploitable.
- Revert semantics roll back writes in a frame, but cannot undo value transfers already committed in successful subcalls unless parent reverts.

## 7) Common mistakes developers make
- Checking only direct recursion and ignoring cross-function paths.
- Assuming “ERC20 transfer has no callback.”
- Guarding user endpoints while leaving admin/executor entry points unguarded.
- Failing to fuzz with malicious receiver contracts.

## 8) Strong invariants that must hold
- During any external call, no callable path should observe monetizable inconsistent accounting.
- User cumulative extraction must never exceed entitled principal + accrued rewards.
- Repeating any payout function without new accrual must yield zero net value.
