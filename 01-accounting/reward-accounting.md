# Reward Accounting: Economic Correctness Under Adversarial Ordering

## 1) Overview
Reward systems fail when accounting precision, funding assumptions, or update ordering diverge from actual token flows. In production, this manifests as repeat claims, unfair dilution, underfunded pools, and slow insolvency via rounding/dust extraction.

## 2) Core Mental Model
A robust reward engine is a conservation system:
- **Funding source** defines maximum distributable emissions.
- **Global index/accumulator** maps time and stake to entitlement.
- **User checkpoints** prevent replay or double-counting.
- **Residual dust accounting** tracks truncation remainder explicitly.

Audit question: can any user action sequence produce reward outflow that exceeds funded entitlement after rounding and fees?

## 3) Minimal Vulnerable Example (underfunding + checkpoint flaw)
```solidity
contract Farm {
    uint256 public accRewardPerShare; // scaled by 1e12
    uint256 public totalStaked;
    uint256 public fundedRewards;     // tokens funded by treasury
    uint256 public paidRewards;

    mapping(address => uint256) public stake;
    mapping(address => uint256) public rewardDebt;

    function notifyReward(uint256 amount) external {
        fundedRewards += amount;
        // Missing transfer-in verification and emission cap coupling.
    }

    function claim() external {
        uint256 pending = (stake[msg.sender] * accRewardPerShare) / 1e12 - rewardDebt[msg.sender];
        rewardToken.transfer(msg.sender, pending);
        paidRewards += pending;
        // Missing rewardDebt update => repeat claim possibility.
    }
}
```

## 4) Realistic Exploit Scenario (rounding + race + underfunding)
1. Pool uses low-precision index scaling and frequent small emissions.
2. Attacker splits stake across many addresses to maximize favorable rounding on each claim path.
3. Attacker bots monitor `notifyReward` and front-run with minimal stake right before index update, then claim immediately.
4. Due to poor checkpoint ordering, attacker repeatedly captures dust and short-window emissions disproportionately.
5. Treasury accounting assumes nominal emissions, but actual claimable outflow drifts higher over time.
6. Pool becomes underfunded; late honest claimants are reverted or partially paid.

This is economically severe even without an obvious “drain in one tx” exploit.

## 5) Defensive Design Patterns + Mitigation Strategies
- **Funding-first discipline**: require verified reward token transfer-in before increasing distributable emissions.
- **High-precision math + dust buckets**: track cumulative residuals and recycle dust deterministically.
- **Strict checkpoint ordering**:
  - settle pending rewards,
  - mutate stake,
  - update reward debt/index snapshots.
- **Front-run resistance**:
  - epoch-based accrual snapshots,
  - minimum staking duration for rewards,
  - anti-sniping windows where appropriate.
- **Underfunding guards**: enforce `paidRewards + outstandingLiabilities <= fundedRewards`.
- **Token-behavior handling**: support fee-on-transfer/rebasing tokens explicitly or reject them.

## 6) EVM-Level Reasoning and Execution Nuance
- Integer truncation is deterministic but exploitable when users can choose action granularity and timing.
- External token calls can re-enter accounting paths if hooks/callback standards are used.
- Mempool ordering enables strategic deposits/claims around emission update transactions.
- Multi-token reward distribution must be atomic or compensating; partial success can corrupt liabilities.

## 7) Common Developer Mistakes
- Assuming reward funding and reward accounting are naturally synchronized.
- Not tracking dust explicitly; writing it off as negligible.
- Updating debt/index after external transfers.
- Ignoring address-splitting strategies in fairness analysis.
- Designing tests for “average user” behavior only, not adversarial timing sequences.

## 8) Invariants That Must Hold
- Total accrued rewards must always be <= funded emissions minus tracked dust.
- For any user, repeated `claim()` without new accrual must produce zero net payout.
- Sum of all users’ claimable + already paid rewards must match funded emissions within explicit dust tolerance.
- Reward liabilities must remain satisfiable by on-chain reserves under defined token-behavior assumptions.
- Ordering of deposit/withdraw/claim in the same block must not create economically free value.
