# Access Control

## 1) Title & clear overview
Access control is not just modifiers. It is the protocol’s control plane: who can change risk parameters, pause operations, upgrade logic, and move treasury assets.

Most catastrophic incidents are authorization design failures, privilege escalation sequences, or governance paths with unsafe blast radius.

## 2) Core mental model
Model permissions as a graph:
- Nodes: roles, multisigs, governance executors, proxies, modules
- Edges: privileged function calls and delegated authority

Then test three cases:
1. Direct unauthorized access
2. Indirect escalation via call sequences or upgrade misconfiguration
3. Authorized-but-dangerous actions that violate safety guarantees

## 3) Minimal vulnerable example (Solidity)
```solidity
interface IProxy {
    function upgradeTo(address newImplementation) external;
}

contract ProtocolAdmin {
    address public owner;
    IProxy public proxy;
    uint256 public feeBps;

    function setFee(uint256 newFeeBps) external {
        // Missing auth and bounds.
        feeBps = newFeeBps;
    }

    function emergencyUpgrade(address impl) external {
        require(msg.sender == owner, "not owner");
        // No timelock / no implementation allowlist.
        proxy.upgradeTo(impl);
    }
}
```

## 4) Realistic exploit scenario with step-by-step flow
1. Attacker discovers public `setFee` and sets punitive fee.
2. Users continue trading through integrations, losing value rapidly.
3. During incident response, owner key is compromised/phished.
4. Attacker executes `emergencyUpgrade` to malicious implementation.
5. Malicious logic drains user balances and treasury.
6. Protocol transitions from configuration bug to full control-plane compromise.

## 5) Defensive design patterns + mitigation strategies
- Least privilege by function domain (risk, treasury, upgrades, emergency).
- Timelocks and multisig requirements for high-impact actions.
- Two-step role transfers and revocation hygiene.
- Enforce hard on-chain parameter bounds (fees, LTV, liquidation bonus, mint caps).
- Lock implementation initializers in upgradeable systems.
- Restrict upgrade functions to governance executor only.
- Monitor role changes, upgrade attempts, and parameter deltas in real time.

## 6) EVM-level reasoning and execution nuance
- `delegatecall` executes in caller storage context; unsafe modules can overwrite auth slots.
- Storage collisions in upgrades can silently break role checks.
- Selector clashes and fallback routing can expose unintended privileged surfaces.
- `tx.origin` authorization is bypassable and unsafe.

## 7) Common mistakes developers make
- One omnipotent role for all critical actions.
- Emergency role with unlimited scope and no expiry.
- Uninitialized implementation contracts in proxy systems.
- Missing governance delay constraints for risk-critical changes.
- Failing to analyze sequence attacks where individually valid calls compose into unsafe outcomes.

## 8) Strong, clear invariants that must hold
- No role or sequence of calls should result in unauthorized privileged execution.
- Every privileged state transition must be attributable to an active authorized role.
- Upgrade actions must pass the approved governance path and delay model.
- Safety-critical parameters must remain inside enforced bounds.
- Single-key compromise outside explicit governance controls must not imply protocol-wide irreversible loss.
