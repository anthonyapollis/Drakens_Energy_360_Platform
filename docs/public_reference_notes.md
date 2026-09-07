# Public reference notes

**Accessed 2026-09-06.**

This repository is an **independent synthetic portfolio project**. It contains
no internal Vivo Energy, Engen, Shell or Vitol data, and has no affiliation
with, endorsement from, or connection to any of them.

This note records exactly what public information was used, and — more
importantly — what was *not* taken from it.

---

## What public information shaped

Only the **shape of the business domain**: which product lines exist, which
customer sectors a downstream energy business serves, and roughly what scale a
Southern African network operates at. That is the kind of information a first
week on any such project would establish from a company website.

| Used for | Source |
|---|---|
| Downstream business model: supply → storage → distribution → retail → commercial | [vivoenergy.com/en/about-us/our-business-model](https://www.vivoenergy.com/en/about-us/our-business-model) |
| Commercial sectors: road transport, mining, construction, power, aviation, marine; LPG to consumer and commercial customers | [vivoenergy.com/en/our-business/commercial](https://www.vivoenergy.com/en/our-business/commercial) |
| Retail offer: fuel, lubricants, convenience, quick-service restaurants, car wash, LPG | [vivoenergy.com/en/our-business/retail](https://www.vivoenergy.com/en/our-business/retail) |
| Growth lines: LPG, solar, EV charging, new mobility | [vivoenergy.com/en/about-us/strategy](https://www.vivoenergy.com/en/about-us/strategy) |
| Order-of-magnitude network scale across markets | [vivoenergy.com/en/about-us](https://www.vivoenergy.com/en/about-us) |
| Order-of-magnitude South African network size (~1,000+ stations) | [engen.co.za media release](https://www.engen.co.za/media/media-release/engen-celebrates-grand-opening-flagship-site-sandton-and-marks-100th-woolworths-foodstop) |

South African town and city locations, province boundaries, airport IATA codes
and port names are public geographic reference data, used as clustering anchors
only.

Legacy public material once listed South African fuel terminal towns —
Alrode, Langlaagte, Waltloo, Wentworth, Ladysmith, Montague Gardens, Mossel
Bay, Bethlehem, Bloemfontein, Kroonstad, East London, Port Elizabeth,
Klerksdorp, Rustenburg, Vryburg, Makhado, Mokopane, Kimberley, Upington,
Nelspruit, Secunda and Witbank. These are used **as town names only**.
Capacities, ownership, connectivity and operating status attached to them in
this project are entirely generated, and current operational status of any real
facility must be independently verified.

---

## What is generated

Everything else. Specifically:

- **Every site.** Names, coordinates, ownership model, offer mix, opening
  dates, forecourt size, operating status.
- **Every customer, supplier, employee, driver, carrier, vessel and airline.**
  Names, sectors, segments, credit terms, contracts.
- **Every transaction.** Volumes, prices, margins, payment methods, timestamps.
- **Every asset.** Tanks, pumps, chargers, inverters, their ages, failure rates
  and maintenance history.
- **Every incident, inspection, permit and training record.**
- **Every financial figure.** Revenue, cost, ledger entries, budgets, forecasts,
  cash flow, working capital.

---

## Naming

Retail banners in this project — *Kalahari Fuels*, *Karoo Motion*, *Highveld
Energy*, *Cape Route Fuels*, *Zambesi Fuels*, *Drakens Petroleum* — are
**invented for this project**. No generated site carries a real brand.

Business names are constructed by combining an invented stem with a
sector-appropriate trade word (`src/vivo360/names.py`), giving a namespace of
hundreds of thousands of combinations. Person names are drawn from South
African given names and surnames across Afrikaans, English, Nguni,
Sotho/Tswana, Venda/Tsonga and South African Indian naming traditions, so the
customer book looks like the country being modelled rather than like a US
sample dataset.

**Any resemblance to a real company or individual is coincidental and
unintended.** If a generated combination happens to match a registered entity,
that is chance, and no data in this project relates to it.

---

## Coordinates

This is the point most worth being unambiguous about.

Every synthetic site coordinate is a **town centroid plus random jitter** — a
normal draw of roughly 0.03 degrees in metros and 0.075 elsewhere, which is a
scatter of a few kilometres. `tests/test_generator.py` asserts that no
generated site lands exactly on a centroid.

**No coordinate in this repository represents a real service station**
belonging to Vivo Energy, Engen, Shell, Vitol or anyone else. The map in the
case study is a map of invented places.

---

## Prices and volumes

South African fuel prices are regulated and adjusted monthly, which is why the
generator models price as a monthly step function rather than per-transaction
noise. The *mechanism* is drawn from how the market publicly works; the
*values* are generated, and the levels used here should not be read as any
real price at any real date.

The same applies to margins, levies, tariffs and every other rand figure.

---

## Reuse

The code and the synthetic data may be reused freely. **The disclaimer must be
preserved**, because the value of this project depends on being unambiguous
about what the data is and is not. A synthetic dataset that loses its
disclaimer becomes a misleading one.
