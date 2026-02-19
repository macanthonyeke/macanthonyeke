# Reentrancy Quiz

1. A vault uses CEI in `withdraw()` but `claimRewards()` transfers tokens before updating debt. What exact reentry sequence drains rewards without re-entering `withdraw()`?
2. A contract has `nonReentrant` on user functions, but an admin executor path calls the same internal accounting logic without a lock. How can this still be exploited?
3. Given a receiver contract with ERC777 hooks, what observable storage conditions indicate a callback can double-claim?
4. A protocol spans two contracts with shared accounting. Which cross-contract call graph would you test first for reentrancy windows?
5. How can read-only reentrancy cause liquidations at unfair discounts even if no write happens in the callback?
6. In a multicall environment, what sequence creates state inconsistency even when each function appears locally CEI-compliant?
7. If an incident shows nested calls but no direct ETH drain, what secondary extraction vectors should you investigate?
8. Design one invariant-based fuzz property that would reliably detect callback-driven reentrancy profit.
