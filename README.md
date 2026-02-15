# Smart Contract Security Playbook

**A practical Web3 security curriculum for aspiring auditors and protocol engineers.**

## Motivation
Smart contract vulnerabilities are rarely caused by a single missing check; they are usually caused by broken assumptions between accounting, authorization, and adversarial incentives. This playbook exists to help intermediate Solidity engineers transition into security-focused thinking.

This repository is for:
- Engineers moving from protocol development into auditing
- Early-career auditors building a repeatable reasoning framework
- Security-minded contributors reviewing DeFi and onchain systems

## Structure
The curriculum is organized as progressive modules:

- `00-foundations/` — first-principles attack surfaces (reentrancy, access control)
- `01-accounting/` — state correctness, reward logic, and invariants
- `02-economic-attacks/` — adversarial game theory and incentive exploits
- `quizzes/` — applied drills to test attacker and defender intuition

## How to Read the Playbook
Use each topic in this sequence:
1. Understand the concept and core mental model
2. Study the vulnerable pattern and transaction-level exploit flow
3. Map the failure to EVM behavior and storage transitions
4. Apply defensive patterns and codify explicit invariants
5. Validate your understanding with the related quiz

Recommended order:
1. `00-foundations/reentrancy.md`
2. `00-foundations/access-control.md`
3. `01-accounting/reward-accounting.md`
4. `01-accounting/invariants.md`
5. `02-economic-attacks/economic-exploitation-patterns.md`

## How to Use the Quizzes
Each quiz contains 8 scenario-driven questions with no answers included.

Suggested method:
- Answer in writing before looking at codebases
- Defend your answer using state transitions and attacker capabilities
- Compare your reasoning with peers during review sessions
- Convert weak areas into implementation and test exercises

## Contribution Guidelines
Contributions are welcome from security researchers and engineers.

When adding a new topic:
1. Place it in the correct numbered module directory
2. Include: overview, mental model, vulnerable example, exploit flow, defenses, EVM reasoning, mistakes, and invariants
3. Add a corresponding quiz with 8 applied questions and no answers
4. Prefer realistic DeFi or protocol scenarios over toy-only examples
5. Keep explanations technically rigorous but accessible

## Minimal Code of Conduct
- Be respectful and professional in discussions and reviews
- Critique ideas and implementations, not people
- Cite evidence when disagreeing on security claims
- Avoid sharing unverified exploit claims as facts

## Quick Start Example
To start with reentrancy:

```bash
cd 00-foundations
cat reentrancy.md
```

Then validate your understanding with:

```bash
cat ../quizzes/00-reentrancy-quiz.md
```
