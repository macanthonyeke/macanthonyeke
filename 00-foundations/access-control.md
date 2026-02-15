# Access Control: Capability Boundaries, Not Just Modifiers

## 1) Overview
Access control failures are frequently root-cause multipliers: a minor configuration endpoint becomes a protocol-wide kill switch when privilege boundaries are weak. Modern audits must evaluate not only direct role checks, but also **privilege escalation sequences**, **role hierarchy design**, and **governance parameter abuse paths**.

## 2) Core Mental Model
Model privileges as graph edges over critical state transitions:
- Nodes: roles, contracts, governance executors, upgrade proxies.
- Edges: callable privileged functions and delegated authority.

Then ask three questions:
1. Can an untrusted actor reach a privileged edge directly?
2. Can they reach it indirectly via role escalation, upgrade flow, or misconfigured proxy?
3. Can a *legitimate* role legally execute a sequence that violates user safety constraints?

Access control is secure only if both **authorization** and **blast radius** are controlled.

## 3) Minimal Vulnerable Example (upgrade + admin exposure)
```solidity
interface IProxy {
    function upgradeTo(address impl) external;
}

contract ConfigurableVault {
    address public owner;
    IProxy public proxy;
    uint256 public feeBps;

    function setFee(uint256 newFeeBps) external {
        // Missing authorization and bounds.
        feeBps = newFeeBps;
    }

    function emergencyUpgrade(address newImpl) external {
        require(msg.sender == owner, "not owner");
        proxy.upgradeTo(newImpl); // no timelock / no implementation allowlist
    }
}
```

## 4) Realistic Exploit Scenario (step-by-step)
1. Team deploys with owner EOA and no timelock; `setFee` is accidentally public.
2. Attacker sets fee to punitive value and routes victim order flow through integrators.
3. Protocol operators attempt hotfix via upgrade, but owner key is phished.
4. Attacker calls `emergencyUpgrade` to malicious implementation.
5. Malicious logic drains treasury/user funds through crafted storage writes and transfer hooks.
6. Incident escalates from “misconfigured fee function” to total control-plane compromise.

Common real-world pattern: harmless-looking admin/config paths become exploitable because they can alter oracle source, collateral factors, pause permissions, or implementation logic.

## 5) Defensive Design Patterns + Mitigation Strategies
- **Least privilege by risk domain**: separate parameter admin, pause authority, treasury ops, and upgrade authority.
- **Role hierarchy hygiene**: avoid cyclic admin roles and broad `DEFAULT_ADMIN_ROLE` usage.
- **Privileged action friction**:
  - timelock for upgrades/risk params,
  - multi-sig execution,
  - two-step role transfer/acceptance.
- **Upgradeable hardening**:
  - lock implementation initializers,
  - restrict upgrade entry points to governance executor only,
  - validate storage layout before upgrades,
  - allowlist implementation bytecode hashes where feasible.
- **Parameter safety envelopes**: enforce on-chain bounds for fees, LTVs, liquidation bonuses, mint caps.
- **Operational controls**: real-time monitoring on privileged calls, role changes, and emergency actions.

## 6) EVM-Level Reasoning and Execution Nuance
- `delegatecall` executes callee code in caller storage context; one bad upgrade/plugin can overwrite auth slots.
- Proxy admin slot corruption or storage collisions can silently nullify access checks.
- `msg.sender`-based checks fail if trust assumptions about relayers/forwarders are wrong.
- `tx.origin`-based authorization is bypassable and should never gate privilege.
- Function selector collisions and fallback routing in proxies can expose unintended privileged code paths.

## 7) Common Developer Mistakes
- Treating access control as `onlyOwner` boilerplate instead of end-to-end threat modeling.
- Leaving implementation contracts uninitialized in upgradeable systems.
- Granting emergency roles unrestricted permanent powers.
- Missing upper/lower bounds on governance-controlled risk parameters.
- Forgetting to revoke deployment-time elevated roles.
- Ignoring sequence attacks where individually authorized calls compose into unauthorized outcomes.

## 8) Invariants That Must Hold
- No role or sequence of calls should lead to unauthorized access of a privileged function.
- Every privileged state transition must be attributable to an authorized role active at execution time.
- Upgrade operations must be executable only through the approved governance path and delay model.
- Governance/admin parameter changes must remain inside explicitly defined safety limits.
- Compromise of any single non-governance key must not permit irreversible protocol-wide fund loss.
