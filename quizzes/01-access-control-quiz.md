# Access Control Quiz

1. A protocol has roles: `DEFAULT_ADMIN`, `RISK_ADMIN`, and `PAUSER`. `RISK_ADMIN` can set LTV up to 98%, and `PAUSER` can unpause without delay. What role sequence could still produce catastrophic unauthorized-like outcomes while each call is technically authorized?
2. You audit an upgradeable proxy where implementation initializer is callable and sets `owner`. What exploit timeline would let an attacker pivot from implementation ownership to protocol fund theft?
3. Governance is timelocked, but an emergency multisig can upgrade instantly. What concrete guardrails would you require so emergency powers cannot become a permanent governance bypass?
4. A plugin system uses `delegatecall` into third-party modules approved by admin vote. What storage-level privilege escalation checks would you perform before approving this architecture?
5. A token bridge controls privileged minting on destination chain via relayer signatures. If relayer quorum degrades during outage, what access-control invariant can break first, and how?
6. Assume parameter bounds exist on-chain, but governance can change those bounds. How can this meta-privilege invalidate the original safety model?
7. A protocol uses EIP-2771 trusted forwarder support. How could misconfigured forwarder trust produce unauthorized privileged execution despite role checks on `_msgSender()`?
8. Post-mortem shows no unauthorized function calls, yet users lost funds after “legitimate” admin operations. How would you distinguish an authorization bug from an overpowered-role design flaw?
