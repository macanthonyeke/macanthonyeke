# Reward Accounting

## 1) Title & clear overview
Reward accounting failures are economic correctness failures. Even if arithmetic compiles and unit tests pass, users can be overpaid, underpaid, or selectively paid depending on timing, rounding, and funding gaps.

Critical risk classes:
- Underfunded emissions
- Rounding residue extraction
- Deposit/claim race conditions
- Checkpoint replay issues

## 2) Core mental model
Track four ledgers:
1. Funded rewards
2. Distributed rewards
3. Outstanding liabilities
4. Tracked dust/residuals

A secure system conserves value across these ledgers under adversarial ordering.

## 3) Minimal vulnerable example (Solidity)
```solidity
contract Farm {
    uint256 public accRewardPerShare; // 1e12 precision
    uint256 public fundedRewards;
    uint256 public paidRewards;

    mapping(address => uint256) public amount;
    mapping(address => uint256) public rewardDebt;

    function notifyReward(uint256 amt) external {
        fundedRewards += amt; // missing transfer-in verification
    }

    function claim() external {
        uint256 pending = amount[msg.sender] * accRewardPerShare / 1e12 - rewardDebt[msg.sender];
        rewardToken.transfer(msg.sender, pending);
        paidRewards += pending;
        // rewardDebt not updated: replay claim possible
    }
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Protocol uses coarse precision and frequent reward updates.
2. Attacker splits stake over many addresses to maximize rounding advantage.
3. Bots front-run large reward top-ups with short-duration deposits.
4. Attacker claims repeatedly before checkpoints are correctly advanced.
5. Dust and timing edge compound into meaningful extraction.
6. Funded pool becomes undercollateralized versus liabilities.
7. Late users receive failed or partial payouts.

## 5) Defensive design patterns + mitigation strategies
- Verify funding transfer-in before increasing distributable rewards.
- Use high precision and explicit dust tracking/recycling.
- Strict order: update pool -> settle pending -> mutate stake -> update debt.
- Consider epoch snapshots/minimum staking duration to reduce sniping.
- Enforce `paid + outstanding <= funded - trackedDust`.
- Handle fee-on-transfer/rebasing token behavior explicitly or reject unsupported assets.

## 6) EVM-level reasoning and execution nuance
- Integer truncation is deterministic and can be adversarially harvested at scale.
- Mempool ordering enables timing strategies around index updates.
- External token calls can trigger callbacks/reentrancy in claim flows.
- Partial failures in multi-reward distributions can corrupt liabilities if atomicity is not enforced.

## 7) Common mistakes developers make
- Assuming “small dust” is economically irrelevant.
- Treating funding assumptions as off-chain ops concerns.
- Updating debt after external transfer.
- Not testing address splitting and bundle-based timing attacks.
- Ignoring same-block deposit/claim permutations.

## 8) Strong, clear invariants that must hold
- Total accrued rewards must always be <= funded emissions minus tracked dust.
- Repeated claims without new accrual must produce zero incremental payout.
- Aggregate paid + claimable must reconcile with emissions within documented precision bounds.
- Reward liabilities must remain satisfiable by realizable reserves under supported token semantics.
- No same-block action ordering should create economically free value.
