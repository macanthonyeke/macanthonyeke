# TikTok Placards: Ownable vs AccessControl

## Placard 1 — Hook
**Title:** Who really controls the contract?

**Next card text:**
**Ownable vs AccessControl**

**Voiceover idea:**
"When you use a protocol, who actually has power behind the scenes? Let’s break it down simply."

---

## Placard 2 — What is Ownable?
**Title:** Ownable = ONE boss

**Body:**
- One address has full control
- That address can change parameters
- That address can pause / upgrade / withdraw (depending on code)

**In simple words:**
👉 If the owner key is compromised, the whole system is at risk.  
👉 If the owner goes rogue, users depend on trust.

**Close line:**
It’s simple. But it’s centralized power.

**Voiceover idea:**
"Ownable is easy to deploy and easy to reason about — but it concentrates power in one key."

---

## Placard 3 — What is AccessControl?
**Title:** AccessControl = different roles, different powers

**Body:**
Instead of one boss, you define roles like:
- Admin role
- Pauser role
- Upgrader role
- Treasury manager role

Each role can only do specific things.

**In simple terms:**
👉 Power is separated  
👉 Damage is limited  
👉 One compromise doesn’t mean total collapse

**Voiceover idea:**
"AccessControl spreads authority so one mistake or hack is less likely to break everything."

---

## Placard 4 — Real Difference (Non-Technical)
**Title:** The real difference

**Body:**
**Ownable:** “One person holds all the keys.”  
**AccessControl:** “Different keys open different doors.”

That’s it.

**Voiceover idea:**
"If you remember one thing, remember this: single key versus segmented keys."

---

## Placard 5 — Why It Matters
**Title:** Architecture > slogans

**Body:**
If a protocol says “trust us” but one wallet can change everything instantly…

That’s not decentralization.

Good architecture:
- separates authority
- limits damage
- delays critical changes
- reduces blind trust

**Voiceover idea:**
"Real decentralization is not a marketing word — it’s how power and risk are designed."

---

## Placard 6 — Closing
**Title:** Security is also about power design

**Body:**
Security isn’t just about preventing hacks.

It’s about reducing power concentration.

We’re not coding like it’s 2016 anymore.

**Caption idea:**
Ownable is simple. AccessControl is safer at scale when roles are designed properly.  
Want a part 2 on multisig + timelock + DAO governance?
