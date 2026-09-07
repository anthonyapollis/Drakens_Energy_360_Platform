"""Geography reference data for the synthetic downstream-energy network.

South Africa is modelled in full: all nine provinces, with city/town centroids
used only as *clustering anchors*. Every synthetic site coordinate is the
anchor plus random jitter, so no generated point represents a real service
station belonging to any company. See docs/public_reference_notes.md.
"""
from __future__ import annotations

from typing import NamedTuple


class Anchor(NamedTuple):
    """A city/town centroid used to cluster synthetic sites."""

    province: str
    city: str
    latitude: float
    longitude: float
    weight: int          # relative share of synthetic sites
    urban_class: str     # Metro | Urban | Town | Rural
    n1_corridor: bool    # sits on a major national route


# The nine provinces of South Africa.
SA_PROVINCES = [
    "Eastern Cape",
    "Free State",
    "Gauteng",
    "KwaZulu-Natal",
    "Limpopo",
    "Mpumalanga",
    "North West",
    "Northern Cape",
    "Western Cape",
]

# City centroids are public geographic knowledge (town locations), not site data.
SA_ANCHORS: list[Anchor] = [
    # ---------------- Western Cape ----------------
    Anchor("Western Cape", "Cape Town", -33.9249, 18.4241, 46, "Metro", True),
    Anchor("Western Cape", "Bellville", -33.9000, 18.6290, 18, "Metro", True),
    Anchor("Western Cape", "Milnerton", -33.8740, 18.4990, 12, "Metro", False),
    Anchor("Western Cape", "Table View", -33.8230, 18.4900, 10, "Metro", False),
    Anchor("Western Cape", "Somerset West", -34.0794, 18.8570, 11, "Urban", True),
    Anchor("Western Cape", "Paarl", -33.7342, 18.9621, 10, "Urban", True),
    Anchor("Western Cape", "Stellenbosch", -33.9321, 18.8602, 9, "Urban", False),
    Anchor("Western Cape", "Worcester", -33.6465, 19.4485, 7, "Town", True),
    Anchor("Western Cape", "George", -33.9630, 22.4617, 9, "Urban", False),
    Anchor("Western Cape", "Mossel Bay", -34.1831, 22.1460, 6, "Town", False),
    Anchor("Western Cape", "Knysna", -34.0363, 23.0471, 5, "Town", False),
    Anchor("Western Cape", "Hermanus", -34.4187, 19.2345, 4, "Town", False),
    Anchor("Western Cape", "Malmesbury", -33.4608, 18.7280, 4, "Town", True),
    Anchor("Western Cape", "Vredenburg", -32.9068, 17.9926, 3, "Town", False),
    Anchor("Western Cape", "Beaufort West", -32.3567, 22.5833, 4, "Town", True),
    Anchor("Western Cape", "Oudtshoorn", -33.5906, 22.2014, 3, "Town", False),
    # ---------------- Gauteng ----------------
    Anchor("Gauteng", "Johannesburg", -26.2041, 28.0473, 58, "Metro", True),
    Anchor("Gauteng", "Pretoria", -25.7479, 28.2293, 40, "Metro", True),
    Anchor("Gauteng", "Sandton", -26.1076, 28.0567, 26, "Metro", True),
    Anchor("Gauteng", "Soweto", -26.2485, 27.8540, 22, "Metro", False),
    Anchor("Gauteng", "Midrand", -25.9992, 28.1263, 18, "Metro", True),
    Anchor("Gauteng", "Centurion", -25.8603, 28.1894, 17, "Metro", True),
    Anchor("Gauteng", "Roodepoort", -26.1625, 27.8725, 14, "Metro", False),
    Anchor("Gauteng", "Alberton", -26.2679, 28.1223, 13, "Metro", True),
    Anchor("Gauteng", "Benoni", -26.1885, 28.3208, 11, "Urban", False),
    Anchor("Gauteng", "Boksburg", -26.2124, 28.2624, 11, "Urban", True),
    Anchor("Gauteng", "Kempton Park", -26.1000, 28.2300, 12, "Urban", True),
    Anchor("Gauteng", "Vereeniging", -26.6731, 27.9261, 9, "Urban", True),
    Anchor("Gauteng", "Krugersdorp", -26.1000, 27.7667, 9, "Urban", False),
    Anchor("Gauteng", "Vanderbijlpark", -26.7100, 27.8378, 7, "Urban", False),
    Anchor("Gauteng", "Springs", -26.2547, 28.4428, 7, "Urban", False),
    # ---------------- KwaZulu-Natal ----------------
    Anchor("KwaZulu-Natal", "Durban", -29.8587, 31.0218, 40, "Metro", True),
    Anchor("KwaZulu-Natal", "Pietermaritzburg", -29.6006, 30.3794, 16, "Urban", True),
    Anchor("KwaZulu-Natal", "Pinetown", -29.8167, 30.8500, 12, "Metro", True),
    Anchor("KwaZulu-Natal", "Umhlanga", -29.7264, 31.0839, 10, "Metro", False),
    Anchor("KwaZulu-Natal", "Richards Bay", -28.7807, 32.0383, 9, "Urban", False),
    Anchor("KwaZulu-Natal", "Newcastle", -27.7579, 29.9318, 8, "Urban", True),
    Anchor("KwaZulu-Natal", "Ladysmith", -28.5539, 29.7800, 7, "Town", True),
    Anchor("KwaZulu-Natal", "Empangeni", -28.7500, 31.8933, 5, "Town", False),
    Anchor("KwaZulu-Natal", "Port Shepstone", -30.7414, 30.4547, 5, "Town", False),
    Anchor("KwaZulu-Natal", "Estcourt", -29.0089, 29.8756, 4, "Town", True),
    Anchor("KwaZulu-Natal", "Vryheid", -27.7694, 30.7914, 4, "Town", False),
    Anchor("KwaZulu-Natal", "Ulundi", -28.3350, 31.4161, 3, "Rural", False),
    # ---------------- Eastern Cape ----------------
    Anchor("Eastern Cape", "Gqeberha", -33.9608, 25.6022, 20, "Metro", True),
    Anchor("Eastern Cape", "East London", -33.0153, 27.9116, 15, "Urban", True),
    Anchor("Eastern Cape", "Mthatha", -31.5889, 28.7844, 9, "Urban", True),
    Anchor("Eastern Cape", "Uitenhage", -33.7639, 25.3969, 7, "Urban", False),
    Anchor("Eastern Cape", "Queenstown", -31.8976, 26.8753, 5, "Town", True),
    Anchor("Eastern Cape", "Grahamstown", -33.3049, 26.5328, 4, "Town", False),
    Anchor("Eastern Cape", "King William's Town", -32.8797, 27.3961, 4, "Town", False),
    Anchor("Eastern Cape", "Butterworth", -32.3286, 28.1489, 3, "Rural", False),
    Anchor("Eastern Cape", "Cradock", -32.1650, 25.6197, 3, "Town", True),
    # ---------------- Free State ----------------
    Anchor("Free State", "Bloemfontein", -29.0852, 26.1596, 18, "Urban", True),
    Anchor("Free State", "Welkom", -27.9774, 26.7351, 9, "Urban", False),
    Anchor("Free State", "Kroonstad", -27.6497, 27.2317, 7, "Town", True),
    Anchor("Free State", "Bethlehem", -28.2308, 28.3071, 6, "Town", False),
    Anchor("Free State", "Sasolburg", -26.8139, 27.8236, 6, "Town", True),
    Anchor("Free State", "Harrismith", -28.2717, 29.1281, 5, "Town", True),
    Anchor("Free State", "Virginia", -28.1058, 26.8631, 3, "Town", False),
    # ---------------- Mpumalanga ----------------
    Anchor("Mpumalanga", "Mbombela", -25.4753, 30.9694, 13, "Urban", True),
    Anchor("Mpumalanga", "eMalahleni", -25.8728, 29.2553, 11, "Urban", True),
    Anchor("Mpumalanga", "Secunda", -26.5500, 29.1667, 8, "Town", False),
    Anchor("Mpumalanga", "Middelburg", -25.7751, 29.4644, 8, "Town", True),
    Anchor("Mpumalanga", "Ermelo", -26.5333, 29.9833, 5, "Town", True),
    Anchor("Mpumalanga", "Barberton", -25.7869, 31.0525, 3, "Town", False),
    Anchor("Mpumalanga", "Standerton", -26.9500, 29.2400, 4, "Town", True),
    # ---------------- Limpopo ----------------
    Anchor("Limpopo", "Polokwane", -23.9045, 29.4689, 13, "Urban", True),
    Anchor("Limpopo", "Mokopane", -24.1944, 29.0097, 6, "Town", True),
    Anchor("Limpopo", "Makhado", -23.0439, 29.9032, 6, "Town", True),
    Anchor("Limpopo", "Tzaneen", -23.8333, 30.1633, 5, "Town", False),
    Anchor("Limpopo", "Thohoyandou", -22.9456, 30.4850, 5, "Rural", False),
    Anchor("Limpopo", "Bela-Bela", -24.8853, 28.2911, 4, "Town", True),
    Anchor("Limpopo", "Musina", -22.3389, 30.0417, 4, "Town", True),
    Anchor("Limpopo", "Lephalale", -23.6708, 27.7458, 3, "Rural", False),
    # ---------------- North West ----------------
    Anchor("North West", "Rustenburg", -25.6676, 27.2421, 12, "Urban", True),
    Anchor("North West", "Klerksdorp", -26.8521, 26.6667, 9, "Urban", True),
    Anchor("North West", "Mahikeng", -25.8652, 25.6442, 7, "Town", False),
    Anchor("North West", "Potchefstroom", -26.7145, 27.0970, 7, "Urban", True),
    Anchor("North West", "Brits", -25.6347, 27.7803, 5, "Town", False),
    Anchor("North West", "Vryburg", -26.9564, 24.7286, 4, "Town", True),
    Anchor("North West", "Lichtenburg", -26.1519, 26.1594, 3, "Town", False),
    # ---------------- Northern Cape ----------------
    Anchor("Northern Cape", "Kimberley", -28.7282, 24.7499, 9, "Urban", True),
    Anchor("Northern Cape", "Upington", -28.4478, 21.2561, 6, "Town", True),
    Anchor("Northern Cape", "Kathu", -27.6957, 23.0493, 4, "Town", False),
    Anchor("Northern Cape", "Springbok", -29.6643, 17.8865, 3, "Rural", True),
    Anchor("Northern Cape", "De Aar", -30.6497, 24.0122, 3, "Rural", True),
    Anchor("Northern Cape", "Kuruman", -27.4522, 23.4322, 3, "Town", False),
    Anchor("Northern Cape", "Postmasburg", -28.3333, 23.0667, 2, "Rural", False),
]


# Public/legacy South African fuel terminal and depot location seeds. These are
# town names only. Capacities, ownership and operating status are synthetic and
# current operational status must be independently validated.
SA_TERMINAL_TOWNS: list[tuple[str, str, str]] = [
    ("Gauteng", "Alberton", "Alrode"),
    ("Gauteng", "Johannesburg", "Langlaagte"),
    ("Gauteng", "Pretoria", "Waltloo"),
    ("KwaZulu-Natal", "Durban", "Wentworth"),
    ("KwaZulu-Natal", "Ladysmith", "Ladysmith"),
    ("Western Cape", "Cape Town", "Montague Gardens"),
    ("Western Cape", "Mossel Bay", "Mossel Bay"),
    ("Free State", "Bethlehem", "Bethlehem"),
    ("Free State", "Bloemfontein", "Bloemfontein"),
    ("Free State", "Kroonstad", "Kroonstad"),
    ("Eastern Cape", "East London", "East London"),
    ("Eastern Cape", "Gqeberha", "Port Elizabeth"),
    ("North West", "Klerksdorp", "Klerksdorp"),
    ("North West", "Rustenburg", "Rustenburg"),
    ("North West", "Vryburg", "Vryburg"),
    ("Limpopo", "Makhado", "Makhado"),
    ("Limpopo", "Mokopane", "Mokopane"),
    ("Northern Cape", "Kimberley", "Kimberley"),
    ("Northern Cape", "Upington", "Upington"),
    ("Mpumalanga", "Mbombela", "Nelspruit"),
    ("Mpumalanga", "Secunda", "Secunda"),
    ("Mpumalanga", "eMalahleni", "Witbank"),
]


# The wider Africa/Europe market footprint. Coordinates are capital-city
# centroids, again used purely as clustering anchors.
MARKETS: list[tuple[str, str, str, float, float]] = [
    # (iso2, country_name, market_group, lat, lon)
    ("ZA", "South Africa", "Southern Africa", -26.2041, 28.0473),
    ("BW", "Botswana", "Southern Africa", -24.6282, 25.9231),
    ("NA", "Namibia", "Southern Africa", -22.5609, 17.0658),
    ("LS", "Lesotho", "Southern Africa", -29.3151, 27.4869),
    ("SZ", "Eswatini", "Southern Africa", -26.3054, 31.1367),
    ("ZW", "Zimbabwe", "Southern Africa", -17.8252, 31.0335),
    ("ZM", "Zambia", "Southern Africa", -15.3875, 28.3228),
    ("MZ", "Mozambique", "Southern Africa", -25.9692, 32.5732),
    ("MW", "Malawi", "Southern Africa", -13.9626, 33.7741),
    ("KE", "Kenya", "East Africa", -1.2921, 36.8219),
    ("TZ", "Tanzania", "East Africa", -6.7924, 39.2083),
    ("UG", "Uganda", "East Africa", 0.3476, 32.5825),
    ("RW", "Rwanda", "East Africa", -1.9441, 30.0619),
    ("MG", "Madagascar", "Indian Ocean", -18.8792, 47.5079),
    ("MU", "Mauritius", "Indian Ocean", -20.1609, 57.5012),
    ("RE", "Reunion", "Indian Ocean", -20.8789, 55.4481),
    ("YT", "Mayotte", "Indian Ocean", -12.7806, 45.2278),
    ("GH", "Ghana", "West Africa", 5.6037, -0.1870),
    ("CI", "Cote d'Ivoire", "West Africa", 5.3600, -4.0083),
    ("SN", "Senegal", "West Africa", 14.7167, -17.4677),
    ("ML", "Mali", "West Africa", 12.6392, -8.0029),
    ("BF", "Burkina Faso", "West Africa", 12.3714, -1.5197),
    ("GN", "Guinea", "West Africa", 9.6412, -13.5784),
    ("CV", "Cape Verde", "West Africa", 14.9331, -23.5133),
    ("GA", "Gabon", "Central Africa", 0.4162, 9.4673),
    ("CD", "Democratic Republic of Congo", "Central Africa", -4.4419, 15.2663),
    ("MA", "Morocco", "North Africa", 33.5731, -7.5898),
    ("TN", "Tunisia", "North Africa", 36.8065, 10.1815),
    ("JO", "Jordan", "Middle East", 31.9539, 35.9106),
]

CURRENCY_BY_COUNTRY: dict[str, str] = {
    "ZA": "ZAR", "BW": "BWP", "NA": "NAD", "LS": "LSL", "SZ": "SZL",
    "ZW": "USD", "ZM": "ZMW", "MZ": "MZN", "MW": "MWK", "KE": "KES",
    "TZ": "TZS", "UG": "UGX", "RW": "RWF", "MG": "MGA", "MU": "MUR",
    "RE": "EUR", "YT": "EUR", "GH": "GHS", "CI": "XOF", "SN": "XOF",
    "ML": "XOF", "BF": "XOF", "GN": "GNF", "CV": "CVE", "GA": "XAF",
    "CD": "CDF", "MA": "MAD", "TN": "TND", "JO": "JOD",
}

# Indicative synthetic local-currency units per ZAR. Not market rates.
FX_TO_ZAR: dict[str, float] = {
    "ZAR": 1.00, "BWP": 1.35, "NAD": 1.00, "LSL": 1.00, "SZL": 1.00,
    "USD": 18.20, "ZMW": 0.72, "MZN": 0.29, "MWK": 0.0105, "KES": 0.141,
    "TZS": 0.0069, "UGX": 0.0049, "RWF": 0.0135, "MGA": 0.0040,
    "MUR": 0.395, "EUR": 19.75, "GHS": 1.22, "XOF": 0.0301, "GNF": 0.0021,
    "CVE": 0.179, "XAF": 0.0301, "CDF": 0.0064, "MAD": 1.84, "TND": 5.85,
    "JOD": 25.70,
}

# Airports and ports used by the aviation and marine domains. Town-level public
# geography only; all uplift, bunker and customer data is synthetic.
SA_AIRPORTS: list[tuple[str, str, str, str]] = [
    ("JNB", "OR Tambo International", "Gauteng", "Kempton Park"),
    ("CPT", "Cape Town International", "Western Cape", "Cape Town"),
    ("DUR", "King Shaka International", "KwaZulu-Natal", "Durban"),
    ("PLZ", "Chief Dawid Stuurman International", "Eastern Cape", "Gqeberha"),
    ("ELS", "East London Airport", "Eastern Cape", "East London"),
    ("BFN", "Bram Fischer International", "Free State", "Bloemfontein"),
    ("GRJ", "George Airport", "Western Cape", "George"),
    ("KIM", "Kimberley Airport", "Northern Cape", "Kimberley"),
    ("PTG", "Polokwane International", "Limpopo", "Polokwane"),
    ("MQP", "Kruger Mpumalanga International", "Mpumalanga", "Mbombela"),
    ("RCB", "Richards Bay Airport", "KwaZulu-Natal", "Richards Bay"),
    ("UTN", "Upington Airport", "Northern Cape", "Upington"),
]

SA_PORTS: list[tuple[str, str, str, str]] = [
    ("ZADUR", "Port of Durban", "KwaZulu-Natal", "Durban"),
    ("ZARCB", "Port of Richards Bay", "KwaZulu-Natal", "Richards Bay"),
    ("ZACPT", "Port of Cape Town", "Western Cape", "Cape Town"),
    ("ZASDB", "Port of Saldanha Bay", "Western Cape", "Vredenburg"),
    ("ZAPLZ", "Port of Gqeberha", "Eastern Cape", "Gqeberha"),
    ("ZANGQ", "Port of Ngqura", "Eastern Cape", "Gqeberha"),
    ("ZAELS", "Port of East London", "Eastern Cape", "East London"),
    ("ZAMZY", "Port of Mossel Bay", "Western Cape", "Mossel Bay"),
]


def province_weights() -> dict[str, int]:
    """Total anchor weight per province, used for sanity checks and docs."""
    out: dict[str, int] = dict.fromkeys(SA_PROVINCES, 0)
    for a in SA_ANCHORS:
        out[a.province] += a.weight
    return out


def validate() -> None:
    """Fail loudly if the geography seed drifts away from the spec."""
    covered = {a.province for a in SA_ANCHORS}
    missing = set(SA_PROVINCES) - covered
    if missing:
        raise ValueError(f"provinces missing from SA_ANCHORS: {sorted(missing)}")
    unknown = covered - set(SA_PROVINCES)
    if unknown:
        raise ValueError(f"unknown provinces in SA_ANCHORS: {sorted(unknown)}")
    for a in SA_ANCHORS:
        if not (-35.0 <= a.latitude <= -22.0):
            raise ValueError(f"{a.city}: latitude {a.latitude} outside South Africa")
        if not (16.0 <= a.longitude <= 33.5):
            raise ValueError(f"{a.city}: longitude {a.longitude} outside South Africa")
    if {m[0] for m in MARKETS} != set(CURRENCY_BY_COUNTRY):
        raise ValueError("MARKETS and CURRENCY_BY_COUNTRY are out of sync")
    for ccy in CURRENCY_BY_COUNTRY.values():
        if ccy not in FX_TO_ZAR:
            raise ValueError(f"currency {ccy} missing from FX_TO_ZAR")
