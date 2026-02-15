# Reentrancy Quiz

1. A vault protects `withdraw()` with `nonReentrant`, but `harvest()` and `claim()` both mutate the same reward debt and are unguarded. Given a malicious ERC777 reward token, what exact call sequence would you try to produce a double-claim?
2. In a lending protocol, `liquidate()` makes an external token transfer before updating borrower health data, while `borrowMore()` reads that data. How can cross-function reentrancy break solvency assumptions without re-entering `liquidate()` itself?
3. You see CEI in every function, but the protocol spans two contracts sharing accounting through external calls. Describe a cross-contract reentrancy path and the invariant you expect to fail first.
4. A strategy contract exposes `previewWithdraw()` used by integrators during the same tx as state-mutating calls. How could read-only reentrancy create profitable mispricing for a sophisticated attacker?
5. An ERC1155 receiver hook calls back into a staking contract during `safeTransferFrom`. Which state transitions must be finalized before transfer, and what is the smallest exploitable inconsistency?
6. Given this sequence: `deposit -> external call -> update shares`, what fuzz harness constraints would you add to reliably detect reentrancy profit opportunities across multi-call bundles?
7. During an incident, traces show repeated nested calls but no obvious net ETH drain. What non-obvious value extraction channels (e.g., reward index skew, liquidation discount abuse) would you investigate?
8. A team proposes “we use pull payments so we’re safe.” Under what conditions can pull-payment architecture still be reentrancy-relevant, and how would you test it?
