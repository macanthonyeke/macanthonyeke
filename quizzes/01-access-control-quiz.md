# Access Control Quiz

1. A protocol uses `DEFAULT_ADMIN_ROLE` as admin for every role. Which sequence of valid calls can produce practical superuser compromise without an explicit auth bug?
2. How can an uninitialized implementation contract in a UUPS setup become a stepping stone to upgrade control?
3. Governance is timelocked, but an emergency role can perform instant upgrades. What controls would you require to keep this safe?
4. A plugin architecture relies on `delegatecall` to approved modules. Which storage-level checks are required to prevent privilege overwrite?
5. Parameter bounds exist, but governance can change the bounds. How does this meta-permission alter your threat model?
6. A trusted forwarder is misconfigured. How can `_msgSender()`-based auth be bypassed in privileged paths?
7. In a bridge-controlled mint system, what invariant should hold when relayer quorum degrades?
8. How would you distinguish “authorized misuse” from “unauthorized access” in a post-incident control-plane analysis?
