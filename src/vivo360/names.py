"""Plausible South African names for people and businesses.

Placeholder strings like "Synthetic Customer 0112573" make a dataset unusable
for demonstration: a dashboard full of them reads as unfinished, and nobody
can judge whether a customer-segmentation view actually works. This module
produces names that look like a real South African customer book.

Two constraints shape the design:

* **Nothing here names a real organisation or person.** Company names are
  built by combining invented stems with sector words, giving a namespace of
  hundreds of thousands of combinations that are unlikely to collide with a
  registered entity. Any resemblance to an actual business is coincidental
  and unintended.
* **Person names reflect South Africa.** Drawing only Anglophone names would
  produce a customer book that looks nothing like the country being modelled,
  so given names and surnames span Afrikaans, English, Zulu, Xhosa, Sotho,
  Tswana, Venda, Tsonga, and South African Indian naming traditions.
"""
from __future__ import annotations

import numpy as np

# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------
GIVEN_NAMES = [
    # Nguni
    "Thabo", "Sipho", "Nomsa", "Thandeka", "Lungile", "Sibusiso", "Zanele",
    "Bongani", "Nokuthula", "Mandla", "Ayanda", "Sanele", "Nonhlanhla",
    "Themba", "Andile", "Zodwa", "Musa", "Phumzile", "Siyabonga", "Lindiwe",
    "Nkosinathi", "Buhle", "Sizwe", "Nandi", "Khanyisile", "Mthunzi",
    "Anele", "Sithembiso", "Zinhle", "Luyanda",
    # Sotho / Tswana / Pedi
    "Kagiso", "Lerato", "Tshepo", "Palesa", "Kabelo", "Mpho", "Refilwe",
    "Katlego", "Dineo", "Neo", "Tumelo", "Boitumelo", "Karabo", "Reneilwe",
    "Ofentse", "Lesego", "Itumeleng", "Mokgadi", "Tebogo", "Keabetswe",
    # Venda / Tsonga
    "Rudzani", "Mulalo", "Tshifhiwa", "Rifumo", "Hlengani", "Nyeleti",
    "Vhutshilo", "Rhulani",
    # Afrikaans
    "Johan", "Pieter", "Annelie", "Marius", "Elmarie", "Hendrik", "Susanna",
    "Dirk", "Marlize", "Jaco", "Riaan", "Anja", "Wilhelm", "Christel",
    "Frikkie", "Lize", "Stefan", "Marike", "Gerhard", "Nadia",
    # English
    "James", "Sarah", "Michael", "Claire", "Daniel", "Emma", "Peter", "Kate",
    "Andrew", "Rachel", "Simon", "Laura", "Grant", "Bridget", "Warren",
    # South African Indian
    "Priya", "Ravi", "Anisha", "Deshan", "Kavitha", "Yusuf", "Zainab",
    "Naeem", "Fatima", "Riaz", "Shireen", "Imraan", "Aisha", "Devan",
    # Cape / other
    "Chad", "Shireen", "Ashwin", "Bianca", "Ruan", "Zaine", "Megan",
]

SURNAMES = [
    # Nguni
    "Dlamini", "Nkosi", "Mkhize", "Ndlovu", "Zulu", "Khumalo", "Mthembu",
    "Sithole", "Cele", "Ngcobo", "Buthelezi", "Zwane", "Mazibuko", "Gumede",
    "Shabalala", "Nyawo", "Xaba", "Hadebe", "Mabaso", "Ntuli", "Zondi",
    "Mahlangu", "Msimang", "Ndaba", "Vilakazi",
    # Xhosa
    "Mbeki", "Sisulu", "Jonas", "Nogwaza", "Mgxaji", "Mtshali", "Tshabalala",
    "Nomvete", "Sonjica", "Mabandla",
    # Sotho / Tswana / Pedi
    "Molefe", "Mokoena", "Sithole", "Moloi", "Motaung", "Mahlaba", "Sekhukhune",
    "Ramaphakela", "Modise", "Segale", "Mogale", "Phiri", "Letsoalo",
    "Maluleke", "Rakgoale", "Motsepe", "Kgatle", "Mothibi",
    # Venda / Tsonga
    "Mudau", "Netshitenzhe", "Ramaite", "Mabasa", "Chauke", "Baloyi",
    "Nkuna", "Rikhotso",
    # Afrikaans
    "van der Merwe", "Botha", "Pretorius", "van Wyk", "Nel", "Fourie",
    "Steyn", "Coetzee", "du Plessis", "Venter", "Kruger", "Joubert",
    "Swanepoel", "le Roux", "Erasmus", "Bezuidenhout", "Oosthuizen",
    "Viljoen", "Marais", "Snyman",
    # English
    "Smith", "Jones", "Anderson", "Bailey", "Clarke", "Fraser", "Hughes",
    "Naylor", "Robertson", "Whitfield", "Sinclair", "Bennett",
    # South African Indian / Cape Malay
    "Naidoo", "Pillay", "Govender", "Moodley", "Reddy", "Padayachee",
    "Singh", "Maharaj", "Ebrahim", "Osman", "Cassim", "Adams", "Isaacs",
    "Jacobs", "Petersen", "Fortuin", "September", "Booysen",
]


# --------------------------------------------------------------------------
# Businesses
# --------------------------------------------------------------------------
# Invented stems. Deliberately compounded so the resulting names sit in a very
# large namespace and are unlikely to match a registered company.
STEM_A = [
    "Thaba", "Rietkop", "Umzansi", "Kalahari", "Highveld", "Bosveld",
    "Karoo", "Drakens", "Zambesi", "Maluti", "Overberg", "Vaalkop",
    "Motheo", "Ntsika", "Khanya", "Ilanga", "Vukani", "Sondela",
    "Bloukrans", "Waterkloof", "Sandspruit", "Groenvlei", "Rooiberg",
    "Witkoppie", "Modderfontein", "Nkanyezi", "Amanzi", "Sekhaya",
    "Tswelopele", "Lehlabile", "Mzansi", "Kopano", "Ubuntu", "Sizanani",
    "Phakama", "Masakhane", "Lethabo", "Isibani", "Nkululeko", "Simunye",
    "Silverstroom", "Blesbok", "Kudu", "Springbok", "Rooikrans",
    "Duineveld", "Sandveld", "Hartland", "Vryheid", "Kameelkop",
]

STEM_B = [
    "", "", "", "", "",              # many names use a single stem
    "Ridge", "Valley", "Bay", "Park", "Point", "Kop", "Vlei", "Rand",
    "Fontein", "Poort", "Kloof", "Berg", "Drift", "Pan", "Nek",
]

BUSINESS_SUFFIX = [
    "(Pty) Ltd", "(Pty) Ltd", "(Pty) Ltd", "CC", "Group", "Holdings",
    "SA", "Enterprises",
]

# Sector-appropriate trade words, so a mining customer does not end up called
# "Fresh Produce" and the segmentation views stay legible.
SECTOR_WORDS = {
    "Road Transport": ["Logistics", "Transport", "Freight", "Haulage",
                       "Carriers", "Distribution", "Fleet Services",
                       "Cartage", "Linehaul"],
    "Mining": ["Minerals", "Mining", "Resources", "Colliery", "Platinum",
               "Mining Supplies", "Exploration", "Ore Services"],
    "Construction": ["Civils", "Construction", "Projects", "Earthworks",
                     "Contractors", "Plant Hire", "Roadworks"],
    "Power Generation": ["Power", "Energy", "Generation", "Utilities",
                         "Power Solutions", "Grid Services"],
    "Aviation": ["Aviation", "Air Charter", "Flight Services", "Airways",
                 "Air Cargo", "Aviation Services"],
    "Marine": ["Marine", "Shipping", "Maritime", "Fishing", "Trawlers",
               "Port Services", "Bunkering"],
    "Agriculture": ["Boerdery", "Farms", "Agri", "Landgoed", "Agriculture",
                    "Farming", "Estates", "Produce"],
    "Manufacturing": ["Manufacturing", "Industries", "Works", "Fabrication",
                      "Industrial", "Processing"],
    "Government": ["Regional Services", "District Works", "Public Fleet",
                   "Roads Authority", "Infrastructure Services"],
    "Reseller": ["Trading", "Wholesale", "Distributors", "Supply Co",
                 "Traders", "Merchants"],
    "SME": ["Trading", "Services", "Enterprises", "Solutions", "Supplies"],
    "Fishing": ["Fishing", "Trawlers", "Seafoods", "Marine Harvest"],
    "Industrial": ["Industrial", "Works", "Engineering", "Plant Services"],
}

SUPPLIER_WORDS = {
    "Refinery": ["Refining", "Petroleum Refining", "Processing"],
    "Importer": ["Trading", "Commodities", "Imports", "Petroleum Trading"],
    "Pipeline Operator": ["Pipelines", "Pipeline Services", "Conveyance"],
    "Road Transporter": ["Logistics", "Haulage", "Transport", "Carriers"],
    "Rail Operator": ["Rail", "Rail Freight", "Rail Logistics"],
    "Packaging": ["Packaging", "Containers", "Drums and Packaging"],
    "Food & Beverage": ["Foods", "Beverages", "Fresh Produce", "Provisions"],
    "Maintenance Contractor": ["Maintenance", "Technical Services",
                               "Engineering", "Site Services"],
}

CARRIER_WORDS = ["Logistics", "Transport", "Haulage", "Carriers",
                 "Freight", "Distribution", "Bulk Transport"]

# Fictional retail banners for the synthetic forecourt network. Invented so no
# generated site can be mistaken for a real branded station.
SITE_BANNERS = ["Kalahari Fuels", "Karoo Motion", "Highveld Energy",
                "Cape Route Fuels", "Zambesi Fuels", "Drakens Petroleum"]

VESSEL_PREFIX = ["MV", "MT"]
VESSEL_NAMES = [
    "Agulhas Star", "Table Bay Trader", "Cape Point", "Southern Cross",
    "Benguela Wind", "Indian Dawn", "Mossel Pioneer", "Algoa Spirit",
    "Richards Venture", "Saldanha Pride", "Kowie Explorer", "Tsitsikamma",
    "Robben Horizon", "Knysna Voyager", "Umgeni Trader", "Breede Runner",
]

AIRLINE_NAMES = [
    "Aurora Air", "Zenith Airways", "Sable Air", "Meridian Airlines",
    "Cirrus Air Cargo", "Kestrel Aviation", "Solstice Airways",
    "Halo Air Charter", "Vantage Air", "Corvus Cargo", "Nimbus Air",
    "Vector Airlines", "Beacon Air", "Talon Air Freight", "Skyward Charter",
    "Lumen Airways", "Onyx Air Cargo", "Pinnacle Charter",
]


# --------------------------------------------------------------------------
# Generators
# --------------------------------------------------------------------------
def person_names(rng: np.random.Generator, n: int) -> np.ndarray:
    """Full names drawn across South African naming traditions."""
    given = rng.choice(GIVEN_NAMES, n)
    surname = rng.choice(SURNAMES, n)
    return np.char.add(np.char.add(given.astype(str), " "), surname.astype(str))


def _stems(rng: np.random.Generator, n: int) -> np.ndarray:
    a = rng.choice(STEM_A, n).astype(str)
    b = rng.choice(STEM_B, n).astype(str)
    joined = np.where(b == "", a, np.char.add(np.char.add(a, " "), b))
    return joined


def company_names(rng: np.random.Generator, sectors, n: int) -> np.ndarray:
    """Sector-appropriate business names.

    `sectors` is an array of sector labels the same length as `n`; each name
    is built from an invented stem plus a trade word that suits the sector, so
    a mining account reads like a mining account.
    """
    stems = _stems(rng, n)
    words = np.empty(n, dtype=object)
    default = SECTOR_WORDS["SME"]
    for sector in set(np.asarray(sectors).tolist()):
        mask = np.asarray(sectors) == sector
        choices = SECTOR_WORDS.get(sector, default)
        words[mask] = rng.choice(choices, int(mask.sum()))

    suffix = rng.choice(BUSINESS_SUFFIX, n)
    # Not every business carries a legal suffix, which is also true in life.
    keep = rng.random(n) < 0.72
    out = np.char.add(np.char.add(stems, " "), words.astype(str))
    return np.where(keep, np.char.add(np.char.add(out, " "), suffix.astype(str)), out)


def supplier_names(rng: np.random.Generator, supplier_types, n: int) -> np.ndarray:
    stems = _stems(rng, n)
    words = np.empty(n, dtype=object)
    default = ["Trading", "Services", "Supply Co"]
    for stype in set(np.asarray(supplier_types).tolist()):
        mask = np.asarray(supplier_types) == stype
        choices = SUPPLIER_WORDS.get(stype, default)
        words[mask] = rng.choice(choices, int(mask.sum()))
    suffix = rng.choice(BUSINESS_SUFFIX, n)
    out = np.char.add(np.char.add(stems, " "), words.astype(str))
    keep = rng.random(n) < 0.80
    return np.where(keep, np.char.add(np.char.add(out, " "), suffix.astype(str)), out)


def carrier_names(rng: np.random.Generator, n: int) -> np.ndarray:
    stems = _stems(rng, n)
    words = rng.choice(CARRIER_WORDS, n).astype(str)
    suffix = rng.choice(["(Pty) Ltd", "(Pty) Ltd", "CC", ""], n).astype(str)
    out = np.char.add(np.char.add(stems, " "), words)
    return np.where(suffix == "", out, np.char.add(np.char.add(out, " "), suffix))


def terminal_names(rng: np.random.Generator, towns: list[str]) -> list[str]:
    """Terminals are named for the town they serve, which is normal practice."""
    return [f"{town} Fuel Terminal" for town in towns]


def vessel_names(rng: np.random.Generator, n: int) -> np.ndarray:
    prefix = rng.choice(VESSEL_PREFIX, n).astype(str)
    base = rng.choice(VESSEL_NAMES, n).astype(str)
    # A hull number keeps names distinguishable across a large fleet.
    number = rng.integers(1, 40, n).astype(str)
    named = np.char.add(np.char.add(prefix, " "), base)
    return np.where(rng.random(n) < 0.55, named,
                    np.char.add(np.char.add(named, " "), number))
