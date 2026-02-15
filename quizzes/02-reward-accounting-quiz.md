# Reward Accounting Quiz

1. A farm updates `accRewardPerShare` every block with 1e12 precision. An attacker splits stake across 1,000 addresses and claims frequently. What rounding-residue strategy could generate measurable edge, and what invariant would expose it?
2. Rewards are funded weekly, but claims are always allowed. Describe a transaction sequence that turns temporary underfunding into selective payout unfairness between early and late claimants.
3. In a pool with fee-on-transfer staking token, deposits credit `amount` before measuring actual received balance. How can this distort both principal and reward liabilities over time?
4. A protocol settles pending rewards after increasing user stake in `deposit()`. Under what market timing does this create a front-run deposit/claim race exploitable around large reward top-ups?
5. Multi-reward pool distributes Token A and Token B; transfer of B may fail silently on some tokens. What accounting divergence appears if A succeeds and B fails, and how would an attacker weaponize it?
6. Given state transitions `notifyReward -> deposit -> claim -> withdraw` in same block, which ordering-sensitive invariant should be asserted to prevent free value extraction?
7. Treasury reports funded rewards = 10M, paid rewards = 9.8M, but aggregate user claimable = 500k. Which accounting assumptions are likely wrong, and what test would reproduce the mismatch?
8. A team argues dust is negligible. Design a stress scenario where dust accumulation becomes economically relevant enough to justify an exploit bot.
