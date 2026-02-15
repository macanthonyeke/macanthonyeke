# Reward Accounting in DeFi Staking Systems (Auditor-Style Lesson)

## 1) Core mental model: how staking reward systems actually work

At audit depth, a staking system is not about “who staked first” or “who clicks claim.” It is about **state transitions over discrete time windows** and whether accounting remains correct under adversarial ordering.

The practical model:

- A protocol has a **reward emission source** (fixed schedule, per-block mint, or externally funded pool).
- Users hold **stake balances** that define their share of emission.
- Rewards are tracked as **cumulative entitlement per unit stake**.
- Each user tracks the portion already “accounted for.”
- Any action (`deposit`, `withdraw`, `claim`) must reconcile the user against global cumulative accounting first.

Think in these layers:

1. **Global accumulator layer**: “How much reward has each 1 unit of stake earned so far?”
2. **User snapshot layer**: “At what accumulator value was this user last settled?”
3. **Pending layer**: “What is owed right now as the delta between current and snapshot?”

If these three layers are correct, most orderings become safe.

---

## 2) `accRewardPerShare` and `rewardDebt` (deep dive)

### `accRewardPerShare`

`accRewardPerShare` is the cumulative rewards earned **per unit of staked token**.

Typical scaled formula:

```text
accRewardPerShare += (newRewards * PRECISION) / totalStaked
```

Where:

- `newRewards` = rewards introduced since last update.
- `totalStaked` = aggregate stake during that accounting interval.
- `PRECISION` = scaling factor (e.g., `1e12` or `1e18`) to reduce integer truncation.

Interpretation: if `accRewardPerShare = 5e12` with `PRECISION=1e12`, each 1 token stake has cumulatively earned 5 reward tokens.

### `rewardDebt`

For each user:

```text
rewardDebt = user.amount * accRewardPerShare / PRECISION
```

`rewardDebt` is the user’s “already-accounted” portion at their last interaction.

Pending reward is usually:

```text
pending = user.amount * accRewardPerShare / PRECISION - user.rewardDebt
```

### Why this works

- `accRewardPerShare` moves global time forward.
- `rewardDebt` pins a user’s last settled checkpoint.
- Delta = what they earned since checkpoint.

### Correct interaction order (critical)

For `deposit` / `withdraw` / `claim`:

1. Update global accumulator (`updatePool`)
2. Compute and optionally transfer pending
3. Mutate user stake amount
4. Recompute user `rewardDebt` using new amount + latest accumulator

Any deviation from this order is a red flag.

---

## 3) Three common accounting mistakes that cause exploits

### Mistake A: Updating user amount before settling pending

If you increase `user.amount` first, then compute pending, user may get credit for past rewards they did not actually backstop with capital.

**Exploit pattern**: attacker deposits right before `claim` and harvests historical emissions.

---

### Mistake B: Accumulator update when `totalStaked == 0` is handled incorrectly

If contract keeps accruing rewards while no one is staked and later applies them to first staker, first staker can capture an unfair windfall.

**Exploit pattern**: wait through idle emission period, stake tiny amount, claim massive carry-over rewards.

Mitigation: if `totalStaked == 0`, advance `lastRewardTime` but do not increase `accRewardPerShare`.

---

### Mistake C: No cap against actual reward token balance / funding

Math says rewards are owed, but reward pool is underfunded. If implementation does unsafe transfer logic, this can create partial-pay griefing, insolvency weirdness, or “first claimer drains everything.”

Mitigation: enforce funded emission model, clamp `claimable = min(pending, fundedAvailable)`, and track unpaid carry-forward explicitly.

---

## 4) Realistic underfunded `rewardPool` exploit

Scenario:

- Promised emission: 100 tokens/day.
- Actual funded rewards in contract: only 1,000 tokens.
- UI still shows APY as if fully funded for 30 days.
- Stakers join and grow claimable balances (book liabilities).

Attack path:

1. Sophisticated user monitors `rewardToken.balanceOf(staking)` and total pending.
2. User claims frequently and early, while pool still has tokens.
3. Late users’ claims revert or get partial payouts (depending on implementation).
4. Protocol socializes losses to slower users.

Why this is an exploitable design failure:

- Not necessarily a code bug in arithmetic, but a **solvency/accounting bug**.
- “Fastest claimant wins” creates adversarial race conditions and unfair extraction.

Auditor controls:

- Compare cumulative emitted liability vs funded assets.
- Ensure claim path has deterministic handling of shortfall.
- Ensure docs specify whether unpaid rewards accrue as debt or are forfeited.

---

## 5) Rounding-error-based exploit

Classic dust-harvesting vector:

- `pending = amount * acc / PRECISION - debt` truncates down.
- If protocol rounds in user-favorable direction in one path and neutral/unfavorable in another, attacker can cycle deposit/withdraw across many addresses to repeatedly capture dust.

Example pattern:

1. Split stake across many accounts.
2. Trigger reward updates frequently.
3. Claim tiny rounded-up fragments repeatedly.
4. Aggregate dust into meaningful amount.

Mitigations:

- Use consistent rounding direction across all reward paths.
- Keep precision high (`1e18` where safe).
- Optionally accumulate residual dust at pool level rather than user level.
- Fuzz for conservation: emitted ≈ claimed + outstanding (+ bounded dust).

---

## 6) Early-exit / griefing vector

A realistic griefing design flaw:

- Protocol has lockup but updates accounting only on `claim`, not `withdraw`.
- Early withdrawer takes principal with penalty, but reward debt not properly reset.
- Attacker repeatedly stakes/withdraws to manipulate denominator (`totalStaked`) timing and reduce others’ effective rewards or cause revert storms.

Another version:

- `withdraw` executes external token transfer before accounting updates.
- Malicious token hook or reentrancy path re-enters reward logic with stale debt.

Mitigations:

- Uniform settle logic on **every** balance-changing action.
- Checks-effects-interactions ordering + reentrancy guard.
- Penalty logic should not bypass reward accounting paths.

---

## 7) Invariant properties that must always hold

Use these as audit invariants (math-level, not implementation-specific):

1. **Monotonic accumulator**
   - `accRewardPerShare` never decreases.

2. **No retroactive reward theft**
   - New stake cannot earn rewards emitted strictly before stake timestamp.

3. **Conservation (bounded by rounding)**
   - `totalClaimed + totalPending` should track `totalEmitted` within bounded dust.

4. **User solvency bound**
   - For each user, `pending >= 0` and cannot exceed modeled entitlement.

5. **Funding safety**
   - If design guarantees full payout, then `rewardBalance + recoverables >= totalPending` always.

6. **Idempotent claim**
   - Two immediate consecutive claims without time/state change: second claim = 0.

7. **Zero-stake neutrality**
   - Emission during `totalStaked == 0` is either burned/paused/escrowed by explicit rule, not accidentally gifted.

8. **Order robustness**
   - For any two users, permutation of independent actions should not violate fairness model.

---

## 8) Test cases to detect invariant violations

### Unit tests (deterministic)

1. **Deposit-after-emission test**
   - Emit rewards with Alice staked.
   - Bob deposits later.
   - Assert Bob cannot claim pre-deposit rewards.

2. **Zero-stake interval test**
   - Advance time with no stakers.
   - First staker deposits.
   - Assert no windfall from idle period unless explicitly intended.

3. **Back-to-back claim test**
   - Claim twice in same block/timestamp.
   - Second claim must be zero.

4. **Underfunded pool behavior test**
   - Configure accrued pending > reward token balance.
   - Assert behavior matches spec: revert, partial payout + debt, or capped claim.

5. **Withdraw-settle consistency test**
   - Compare `claim+withdraw` vs `withdraw+claim` outcomes.
   - Assert equivalent results per design.

### Property/Fuzz tests

6. **Action-sequence fuzzing**
   - Randomized sequences of deposit/withdraw/claim across N users.
   - Invariants: monotonic accumulator, no negative pending, conservation bound.

7. **Rounding adversary fuzz**
   - Random stake splits across many addresses with tiny amounts.
   - Assert dust extraction remains bounded and non-amplifiable.

8. **Permutation fairness test**
   - Same set of actions reordered.
   - Compare final rewards against mathematically expected tolerance.

### Differential / model-based test

9. **Reference model parity**
   - Build simple Python model of ideal math.
   - Replay on-chain action traces in tests.
   - Assert implementation deviation stays within rounding tolerance.

---

## 9) Applied quiz (5 questions)

1. A pool emits rewards continuously. `totalStaked` is zero for 7 days, then one user stakes 1 token. Should they receive the 7-day emission? Explain based on your chosen economic rule and accounting implementation.

2. In a contract, `deposit()` updates `user.amount` before paying pending rewards. Construct a minimal exploit timeline with two users that shows unfair capture.

3. You discover `totalPending > rewardToken.balanceOf(pool)` in production. Give three safe mitigation options and tradeoffs for each.

4. How can inconsistent rounding between `claim()` and `withdraw()` become extractable when the attacker sybils into many wallets?

5. Write two invariants and one fuzz strategy that would have detected a historical “first claimer drains underfunded pool” failure mode.

