# Landed-cost questions for the import/clearing expert

**Why this matters:** Right now the system knows what we pay the supplier for a part,
but not the extra costs to get it into our warehouse in Nigeria (shipping, customs
duty, clearing, FX buffer). Those extra costs are the difference between the sticker
price abroad and the *true* cost of the part. Once we have the expert's numbers, the
reorder, margin and pricing figures become accurate for imported parts.

Ask the expert the questions below. For each, we mainly need: **the number, and
whether it's a flat amount or a percentage of the goods' value.**

---

## 1. Freight (shipping)
- Roughly what does sea freight cost from **China → Lagos** and **Turkey → Lagos**?
- Is it charged **per container** (20ft/40ft), per **CBM (volume)**, per **kg**, or as a
  **% of the goods' value**?
- For a typical mixed container of auto parts, what does freight work out to as a
  **percentage of the goods' value** (a rough average is fine)?
- Is **marine insurance** included, or separate? If separate, what %?

## 2. Import duty
- What is the **import duty rate (%)** for the auto parts we bring in?
- Does it **vary by part type** (e.g. filters vs. electrical vs. body parts)? If so,
  what are the main rates and which parts fall into each?
- Is duty calculated on the **goods value only**, or on **goods + freight + insurance
  (CIF value)**?

## 3. Government levies and taxes (on top of duty)
- Do any of these apply, and at what %?
  - **VAT** (7.5%?) — on what base?
  - **ETLS / ECOWAS levy**
  - **Import surcharge / port levy**
  - **CISS (inspection) fee**
- Are these on the goods value, or on the CIF value, or on value + duty?

## 4. Clearing and handling at the port (Apapa / Tin Can)
- Typical **clearing agent fee** — flat per container, or a range?
- **Terminal handling charges**, shipping-line local charges, documentation fees —
  roughly per container?
- Any usual **demurrage / storage** we should budget as an average?
- **Inland transport** from the port to our warehouse — per container?

## 5. Foreign exchange (FX)
- When we cost an imported part, which **exchange rate** should we use — the
  **official/CBN rate** or the **parallel-market rate** we actually buy dollars at?
- Should we add an **FX buffer (%)** to protect against the naira weakening between
  ordering and paying? If so, how much?

## 6. Quality / returns (optional)
- Do we lose a rough **% to defective or wrong parts** that we can't sell? If so, what %?

---

## The single most useful answer
If the expert can only give us one thing, ask:

> "For a typical container of our auto parts, once everything is paid — freight,
> duty, levies, clearing, transport — what is the **total landed cost as a
> percentage on top of the supplier's price**? And how much of that is fixed
> per container vs. a percentage of value?"

That single "uplift %" lets the system estimate landed cost immediately; the
detailed breakdown above lets us make it precise and split it correctly by part
type later.

---

## What we do with the answers
- Percentages (freight %, duty %, levies %, FX buffer %) go into the system's
  landed-cost settings.
- Flat per-container amounts get spread across the units in a shipment.
- Until then, the system shows landed cost with **PLACEHOLDER** values clearly
  marked, and does **not** use them in reorder/margin decisions — so nothing is
  silently wrong.
