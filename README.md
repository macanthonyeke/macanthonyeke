# Smart Contract Security Playbook

**An audit-ready Web3 curriculum for Solidity engineers becoming security reviewers.**

## Why this exists
Most protocol losses are not caused by syntax mistakes. They come from broken assumptions between control flow, accounting, and incentives under adversarial execution.

This playbook is designed for:
- Intermediate Solidity developers transitioning into auditing
- Junior auditors building repeatable analysis workflows
- Protocol engineers who want to ship with stronger safety guarantees

## Curriculum layout
- `00-foundations/`
  - `reentrancy.md`
  - `access-control.md`
- `01-accounting/`
  - `reward-accounting.md`
  - `invariants.md`
- `02-economic-attacks/`
  - `economic-exploitation-patterns.md`
- `quizzes/`
  - `00-reentrancy-quiz.md`
  - `01-access-control-quiz.md`
  - `02-reward-accounting-quiz.md`
  - `03-invariants-quiz.md`
  - `04-economic-exploitation-quiz.md`

## How to read this playbook
For each topic:
1. Build the core mental model first.
2. Walk the vulnerable example until you can explain the break condition.
3. Replay the exploit flow as transaction/state transitions.
4. Map mitigations to concrete failure modes.
5. Convert invariants into property tests.
6. Validate understanding with the matching quiz.

Recommended sequence:
1. `00-foundations/reentrancy.md`
2. `00-foundations/access-control.md`
3. `01-accounting/reward-accounting.md`
4. `01-accounting/invariants.md`
5. `02-economic-attacks/economic-exploitation-patterns.md`

## How to use quizzes
Each quiz has 8 scenario-based questions with no answers.

Recommended practice:
- Answer in writing with attacker and defender perspectives.
- Justify claims using state transitions and invariants.
- Turn weak answers into Foundry invariant/fuzz tests.

## Contribution guidelines
When adding a topic:
1. Keep the numbered module structure.
2. Include: overview, mental model, vulnerable example, exploit flow, defenses, EVM nuance, mistakes, invariants.
3. Add a paired quiz with 8 applied questions and no answers.
4. Prefer realistic DeFi patterns over toy-only examples.
5. Write in a professional auditor tone, but keep it accessible.

## Minimal code of conduct
- Be respectful in technical debate.
- Critique claims with evidence.
- Avoid personal attacks.
- Do not present unverified exploit rumors as facts.

## Quick start
```bash
cd 00-foundations
cat reentrancy.md
cat ../quizzes/00-reentrancy-quiz.md
```
