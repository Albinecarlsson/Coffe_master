# Isomac Brio Renovation Plan

Target machine: **Isomac Brio** (single group, built-in grinder, 230 V).

## 1. What the machine is

From the manufacturer's spec sheet and the Brio's own spare-parts list:

| Property | Value |
| --- | --- |
| Mains | 230 V, 50 Hz |
| Element | 1000 W (~4.4 A) |
| Boiler | 0.2 L |
| Water tank | 3.5 L |
| Pump | Vibration, 12–14 bar rated |
| Group | Non-E61, ~53 mm portafilter (measure yours) |
| Controls | **Bimetallic thermostats**, not a pressurestat |
| Extras | Manometer, built-in grinder |

Two consequences follow from this and they shape everything below.

**The boiler is very small (0.2 L).** There is almost no thermal mass, so brew
temperature collapses the moment cold water enters. A PID will hold the idle
temperature beautifully and still sag during a shot. Temperature recovery between
shots, not idle stability, is the real problem on this machine.

**Temperature is set by a thermostat.** A thermostat is a bang-bang switch with
several °C of hysteresis. Replacing its *switching action* with an SSR driven by
the PID in this repo is the single largest quality improvement available, and it
is already implemented.

### Verify before ordering anything

The spec sheet is a retailer's, so confirm on the actual machine:

- [ ] Element resistance (~53 Ω for 1000 W at 230 V) and whether the boiler is
      brass or stainless.
- [ ] How many thermostats, and their ratings (the parts list shows a 135 °C one).
      Identify which is the **brew** thermostat and which is the **safety cutout**.
- [ ] Whether there is a **safety/expansion valve** on the boiler.
- [ ] Whether a 3-way solenoid valve is fitted, or only a mechanical group valve.
- [ ] Whether the pump is switched by the brew lever microswitch or by a relay.
- [ ] Whether a low-water / tank-empty switch exists.
- [ ] Portafilter diameter and group gasket dimensions.
- [ ] Whether the grinder motor is mains AC or has its own controller.

Photograph the wiring before disconnecting anything.

### Identifying the thermostats

You do not need to know the model number — you need to know which disc does what.
With the machine unplugged, removed from its casing and the boiler cold:

1. **Count them.** There are usually two or three, each a round disc bolted or
   clamped to the boiler with two spade terminals.
2. **Read the stamp.** The temperature rating is stamped or printed on the disc.
3. **Sort by rating.** Brew is the lowest (typically 90–100 °C). Steam, if fitted,
   is around 125–135 °C. The safety cutout is the highest (135–160 °C) and very
   often has a small manual reset button in the middle.
4. **Trace the wires.** Brew and steam thermostats switch the element for their
   mode. The safety cutout sits in series with the element and switches nothing
   else, so it only ever opens on a fault.
5. **Check it cold.** With the machine unplugged, a multimeter across a healthy
   thermostat reads near 0 Ω.

A 135 °C disc on a 0.2 L boiler may well be the **steam** thermostat rather than
the safety cutout, so do not assume the highest-rated one is the safety device —
confirm with the parts diagram for your model. Whichever disc is the safety cutout
is the one that must stay in series with your SSR, and the one whose wiring you
must not disturb.

---

## 2. Safety — read this first

This appliance stores **boiling water under pressure** and runs on **230 V AC**.
Modifying it is not a low-voltage electronics project.

The decisions that matter:

1. **Never remove the mechanical safety devices.** The safety thermostat, the
   safety/expansion valve and the anti-vacuum valve stay, in series/in place.
   The PID is *added*, it does not replace the last line of defence.
2. **An SSR fails short.** Semiconductors fail closed, so a failed SSR means the
   element is **permanently on**. The PID's own fail-safe (heater to zero) cannot
   help you once the relay is shorted — only the mechanical safety thermostat in
   series can. Size it correctly and never bypass it.
3. **Add a thermal fuse** (e.g. 145–160 °C, one-shot) bonded to the boiler as a
   second, single-fault-independent cutout if the machine lacks one.
4. **Preserve earth continuity.** The metal body must stay bonded to mains earth.
   Measure it after reassembly.
5. **Keep 230 V and the Pi strictly apart.** Opto-isolated SSR inputs, separate
   cable routing, ferrules on stranded wire (never tinned), strain relief, and a
   ventilated enclosure. Nothing on the DC side should touch mains if a wire
   comes loose.
6. **Never heat a dry boiler.** If the machine has no low-water sensing, add it
   *before* automating pours. This is the failure mode that destroys elements.
7. **Water and steam always find the electronics.** The tank, wand and group all
   drip. Route cabling with a drip loop and keep the Pi out of the condensate path.
8. Work unplugged, verify dead with a tester, and **have an electrician inspect
   the mains work before first power-up.** Your insurance, your responsibility.

---

## 3. Renovation plan

Phased so that each step is useful on its own and the machine is never
half-converted and unusable.

### Phase 0 — Service and repair (before any electronics)

Do this first; there is no point controlling a machine that leaks.

- Descale the boiler. On a 0.2 L boiler, scale has an outsized effect.
- Replace the group head gasket, shower screen and dispersion plate.
- Replace boiler and element gaskets (parts list: OR177 boiler, 000121 element).
- Replace the anti-vacuum valve — a stuck one causes airlocks and hissing.
- Reseal the steam valve; replace its O-rings.
- Backflush with a blind basket and detergent.
- Fit water filtration/softening. Swedish water is hard enough that this pays
  for itself; it also protects the new element.

### Phase 1 — Electrical safety and measurement

- Add the thermal fuse and a properly rated fuse for the element.
- Fit the SSR with a heatsink and thermal paste, in series with the safety
  thermostat.
- Add low-water sensing if absent.
- Fit a fused 5 V supply for the Pi, kept physically separate from mains.

### Phase 2 — Temperature control (software already written)

- PT100/PT1000 probe in the boiler + MAX31865 breakout.
  The driver is implemented in `src/espresso_mod/hal/rtd_max31865.py`.
- SSR driven by the PID in `src/espresso_mod/services/control.py`.
- Tune the PID gains for this boiler — the defaults are deliberately
  conservative and will need work on a 0.2 L boiler.

This is the step that changes the coffee. Everything after it is convenience.

### Phase 3 — Sensing

- **Brew pressure**: 0–16 bar transducer on the group circuit, via an ADS1115
  (I²C, no extra SPI bus contention with the RTD). Gives you real pressure
  feedback instead of a needle.
- **Flow**: a food-grade turbine flow meter inline on the brew path. This is what
  turns "pour for N seconds" into "pour exactly 40 ml".
- **Weight**: a load cell under the drip tray is the most accurate dosing method
  and the standard upgrade on machines of this class.

### Phase 4 — Dosing and drinks (partly written)

- Pump and valve relays, so the machine can start and stop a pour itself.
- Volumetric or gravimetric dosing — `src/espresso_mod/services/doser.py`.
- A drink catalogue with one-touch selection — `src/espresso_mod/domain/drinks.py`.
- Hot-water path for americanos and tea. The Brio has one brew path plus a steam
  wand; hot water needs a second valve wired, so americanos are deferred.
- Preinfusion: the solenoid is binary and the vibration pump runs at a fixed speed,
  so the only way to wet the puck gently is to **pulse the pump** (say 1 s on,
  2 s off, then continuous). That is why the built-in shot profiles are single
  full-flow pours today. Worth doing here, because it also gives the small boiler
  a head start on recovery before the main pour.

The solenoid gets no hidden throttling: any non-zero demand opens it fully, and
the software no longer pretends otherwise.

### Phase 5 — Grinder integration

The Brio's grinder is built into the chassis, so this is not a separate appliance to
wire up — it is a second motor inside the machine you already have open. That makes
it easier mechanically and *harder* to get right, because you are adding a second
mains load to the same enclosure.

- **Find out how the motor is switched.** Most built-in grinders use a momentary
  push-button or the doser lever, often switching the live side. Note whether there
  is a run capacitor: a single-phase induction motor is not a simple resistive load.
- **Switch it with a proper relay**, rated for an inductive motor load, and fit a
  snubber. Do not rely on a cheap SSR rated only for resistive heaters.
- **Never automate the motor without a hopper-empty check** — running a burr grinder
  dry is noisy and wears the burrs.
- **Decide the dose control.** Grind-by-time is trivial (run the motor for *N*
  seconds) but drifts as the beans age and the burrs wear. Grind-by-weight needs a
  load cell under the portafilter fork or the dosing cup, and is far more repeatable.
  Weight is the upgrade that actually improves the coffee.
- Keep the manual button working. A grinder you cannot operate when the Pi is down
  is a grinder you will resent.

Dose repeatability is the largest single variable in espresso on this class of
machine — larger than temperature. If you only automate one more thing, automate
this after the temperature loop.

### Phase 6 — Display, enclosure and UX

- Touchscreen on the Pi, running the kiosk UI served at `/kiosk`.
- Enclosure considerations: the Pi 4/5 self-heats and a machine enclosure is
  already warm, so plan ventilation or use a Pi Zero 2 W.
- Mount the screen **away from the group head and steam wand** — heat and
  condensate kill displays faster than anything else.
- Consider a physical emergency stop for the element that does not depend on
  software.

---

## 4. Shopping list

Prices are rough SEK ranges for planning, not quotes. Buy the machine-specific
parts against your model's parts list, not from a generic listing.

### Machine service parts

| Item | Why | Rough |
| --- | --- | --- |
| Group head gasket + shower screen | Leaks and channeling | 150–350 |
| Boiler gasket, element gasket | Seepage after descaling | 100–250 |
| Anti-vacuum valve | Airlocks, hissing | 150–300 |
| Steam valve seal kit / O-rings | Dripping wand | 100–250 |
| Descaling agent (citric or proprietary) | 0.2 L boiler scales fast | 100–200 |
| Water filter / softener | Protects element | 200–500 |
| Food-grade silicone grease | Seal assembly | 100–150 |
| Food-grade silicone tubing | Replace hardened lines | 100–200 |

### Electronics and control

| Item | Why | Rough |
| --- | --- | --- |
| Raspberry Pi 4 (2–4 GB) or 5 | The brain. Zero 2 W is enough and cooler | 600–1200 |
| microSD **or** USB SSD | SD cards die in hot, write-heavy use | 150–600 |
| 7" DSI touchscreen | Single cable, no HDMI, no USB | 700–1100 |
| 5 V 3–5 A supply | Pi power, fused | 150–350 |
| MAX31865 breakout + PT100 (4-wire) | Boiler temperature, **driver written** | 250–500 |
| SSR 25 A, 230 V, opto-isolated, zero-cross | Element switching | 150–400 |
| Heatsink + thermal paste | SSR runs hot | 100–200 |
| Pump relay (opto-isolated SSR or mechanical) | Start/stop pours | 100–250 |
| Grinder motor relay | Phase 5 only | 100–250 |
| Thermal fuse 145–160 °C | Independent cutout | 50–150 |
| Fuse holders, fuses, ferrules, glands | Mains safety | 200–400 |
| 0–16 bar pressure transducer + ADS1115 | Real pressure feedback | 400–800 |
| Turbine flow meter (food grade) | True volumetric dosing | 400–900 |
| Load cell + HX711 | Gravimetric dosing (best quality) | 200–500 |
| Tank level switch | Dry-fire protection | 100–250 |
| Enclosure, DIN rail, WAGO terminals | Tidiness and safety | 300–600 |

### Tools

| Item | Why |
| --- | --- |
| CAT III digital multimeter | Measuring 230 V safely |
| Non-contact voltage tester | Confirming dead before touching |
| Crimp tool + ferrule assortment | Proper stranded-wire terminations |
| Soldering iron + heat-shrink | Board work |
| Insulated screwdriver set | Mains-side fasteners |
| Small torque wrench | Boiler and group fittings |
| Espresso scale, 0.1 g | Calibrating dose regardless of automation |
| Backflush disc + group brush | Maintenance |
| Bench PSU or 5 V adapter for prototyping | Bring-up without mains |

---

## 5. What the software already covers

| Capability | Status |
| --- | --- |
| PID temperature control | `services/control.py` |
| MAX31865 RTD sensor (PT100/PT1000, 2/3/4-wire, fault decoding) | `hal/rtd_max31865.py` |
| SSR heater, time-proportioned, with a command watchdog | `hal/gpio.py` |
| Solenoid valve over GPIO | `hal/gpio.py` |
| Thermal simulation for development without hardware | `hal/sim.py` |
| HTTP API + touch UI | `api.py`, `ui/` |
| Drink catalogue and dosing | `domain/drinks.py`, `services/doser.py` |
| Kiosk UI for drink selection | `ui/kiosk.html` |
| Pressure sensing | Not implemented — Phase 3 |
| Flow meter / gravimetric dosing | Not implemented — Phase 3 |
| Hot-water path | Not implemented — Phase 4 |
| Grinder control | Not implemented — Phase 5 |
