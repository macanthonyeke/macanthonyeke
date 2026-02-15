# Reentrancy — Senior Auditor Teaching Guide

## 1) Core mental model (no code)

Reentrancy is **control-flow hijacking** through an external call.

As an auditor, think in terms of three facts:

1. **Your contract is not always in control.**
   The moment it performs an external call (`call`, `transfer`, `send`, token hook, etc.), execution can jump into untrusted code.
2. **EVM state updates are not automatically atomic at function boundaries.**
   A function can be interrupted mid-flight by an external call, and then re-entered before internal accounting is finalized.
3. **Security invariants must hold at every reentry point, not just on function exit.**

### Auditor lens: "invariant windows"

Look for windows where this pattern exists:

- **Check** some condition (e.g., `balances[msg.sender] >= amount`)
- **Interact** with untrusted external address
- **Effect** (state update) happens too late

During that window, attacker-controlled code can call back and observe stale state.

### EVM call stack intuition

- Contract A calls Contract B.
- B executes fallback/receive/hook.
- B calls back into A before A finished prior execution frame.
- A now runs another frame with assumptions based on old state.

That is reentrancy: **same contract, overlapping execution frames, stale assumptions**.

### Types auditors care about

- **Single-function reentrancy:** function re-enters itself (e.g., `withdraw -> fallback -> withdraw`).
- **Cross-function reentrancy:** attacker re-enters a different function sharing the same vulnerable state.
- **Cross-contract reentrancy:** shared accounting split across contracts, re-entry happens through partner module.
- **Read-only reentrancy:** no direct write exploit, but manipulated reads/oracles during callback cause wrong pricing/logic elsewhere.

---

## 2) Minimal vulnerable contract

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract VulnerableVault {
    mapping(address => uint256) public balances;

    function deposit() external payable {
        balances[msg.sender] += msg.value;
    }

    function withdraw(uint256 amount) external {
        require(balances[msg.sender] >= amount, "insufficient");

        // Interaction first (danger)
        (bool ok,) = msg.sender.call{value: amount}("");
        require(ok, "transfer failed");

        // Effect after external call (too late)
        balances[msg.sender] -= amount;
    }
}
```

Why vulnerable: the vault sends ETH before decrementing the attacker balance.

---

## 3) Attack simulation (transaction flow)

Assume:

- Attacker deposited 1 ETH.
- Vault total ETH is 10 ETH (from many users).
- `balances[attacker] == 1 ether`.

### Transaction trace

1. **EOA calls attacker contract** to start exploit.
2. Attacker calls `vault.withdraw(1 ether)`.
3. Vault checks `balances[attacker] >= 1 ether` → true.
4. Vault executes `call{value:1 ether}` to attacker.
5. Attacker fallback runs and immediately calls `vault.withdraw(1 ether)` again.
6. Second `withdraw` sees unchanged balance (still 1 ETH) because first call has not decremented yet.
7. Vault sends another 1 ETH.
8. Fallback re-enters repeatedly until vault ETH is drained or gas/loop limit reached.
9. Stack unwinds; decrements happen late and are insufficient to undo drained transfers.

Net: attacker extracts more ETH than their recorded balance.

---

## 4) Two different fixes

## Fix A: Checks-Effects-Interactions (CEI)

```solidity
function withdraw(uint256 amount) external {
    uint256 bal = balances[msg.sender];
    require(bal >= amount, "insufficient");

    // Effect first
    balances[msg.sender] = bal - amount;

    // Interaction after state is safe
    (bool ok,) = msg.sender.call{value: amount}("");
    require(ok, "transfer failed");
}
```

### Why CEI works at EVM level

- The `SSTORE` that updates `balances[msg.sender]` executes **before** the external `CALL` opcode.
- If attacker re-enters, the new execution frame reads updated storage via `SLOAD`; the old balance is no longer visible.
- Reentrant checks fail once allowed amount is exhausted.
- If the later `CALL` fails and `require` reverts, EVM revert semantics roll back prior `SSTORE`, preserving consistency.

## Fix B: Reentrancy guard (mutex lock)

```solidity
bool private locked;

modifier nonReentrant() {
    require(!locked, "reentrant");
    locked = true;
    _;
    locked = false;
}

function withdraw(uint256 amount) external nonReentrant {
    require(balances[msg.sender] >= amount, "insufficient");
    (bool ok,) = msg.sender.call{value: amount}("");
    require(ok, "transfer failed");
    balances[msg.sender] -= amount;
}
```

### Why guard works at EVM level

- On entry, guard does `SLOAD(locked)` then `SSTORE(locked=true)`.
- Any reentrant attempt hits the modifier again in a nested frame and fails `require(!locked)`.
- Nested frame reverts before reaching vulnerable logic.
- After successful completion, `SSTORE(locked=false)` releases the lock.

### Practical audit note

Best practice is often **CEI + nonReentrant** on sensitive flows, because:

- CEI secures ordering/invariants.
- Guard provides a second layer against future refactors, cross-function paths, or overlooked callbacks.

---

## 5) Quiz (5 applied questions)

1. You audit a vault using CEI in `withdraw()`, but `claimRewards()` reads `balances[msg.sender]` and makes an external call before updating `rewardsDebt`. What class of reentrancy risk might still exist and why?
2. A protocol uses `nonReentrant` on `withdraw()`, but `withdraw()` calls internal `_settle()` which externally calls a token with hooks. Where should you verify lock coverage, and what bypass patterns do you check?
3. Why is replacing `.call` with `.transfer` not considered a complete reentrancy defense after gas-cost changes (EIP-1884 and later)?
4. In CEI ordering, if state is updated before transfer and the transfer fails, why does storage remain correct after `require(ok)`?
5. Give one real-world scenario of **read-only reentrancy** where no direct balance theft occurs but protocol economics are still exploited.
