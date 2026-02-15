# Reward Accounting Quiz

1. A pool uses `1e12` precision and frequent micro-emissions. How can address-splitting turn rounding residue into extractable value?
2. Rewards are announced before transfer-in funding is verified. What race condition can allow early claimers to externalize losses?
3. A user deposits immediately before a large reward update and withdraws shortly after. What ordering bug would make this profitable?
4. In fee-on-transfer staking tokens, how does crediting nominal deposit rather than received amount corrupt reward liabilities?
5. A system supports two reward tokens and one transfer can fail silently. What accounting drift appears and how might attackers exploit it?
6. Which invariant best prevents repeat-claim extraction when checkpoint updates are incorrectly ordered?
7. Given `funded=10M`, `paid=9.7M`, `claimable=600k`, what potential accounting error classes should you test first?
8. Design a fuzz test that proves no same-block deposit/claim ordering can mint free reward value.
