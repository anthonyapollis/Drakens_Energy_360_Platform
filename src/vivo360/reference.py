"""Product master and enumerated reference lists.

Product names describe generic downstream-energy commodities (petrol, diesel,
jet fuel, LPG, lubricants, convenience lines). Brand labels applied to
synthetic sites are fictional and do not represent any company's real network.
"""
from __future__ import annotations

from typing import NamedTuple


class Product(NamedTuple):
    product_id: str
    product_name: str
    category: str        # Fuel | LPG | Lubricant | Convenience | Energy
    subcategory: str
    uom: str
    # indicative synthetic ZAR unit economics
    base_price_zar: float
    base_cost_zar: float
    regulated: bool      # SA fuel prices are regulated; margins are thin


PRODUCTS: list[Product] = [
    # ------------------------- road fuels -------------------------
    Product("F001", "Premium Unleaded 95", "Fuel", "Petrol", "L", 24.10, 21.90, True),
    Product("F002", "Unleaded 93", "Fuel", "Petrol", "L", 23.60, 21.50, True),
    Product("F003", "Low Sulphur Diesel 50ppm", "Fuel", "Diesel", "L", 22.85, 20.85, True),
    Product("F004", "Diesel 500ppm", "Fuel", "Diesel", "L", 22.35, 20.45, True),
    Product("F008", "Illuminating Paraffin", "Fuel", "Paraffin", "L", 15.40, 13.90, True),
    # ------------------------- aviation / marine -------------------------
    Product("F005", "Jet A-1", "Fuel", "Aviation", "L", 19.80, 17.60, False),
    Product("F009", "Avgas 100LL", "Fuel", "Aviation", "L", 32.50, 28.40, False),
    Product("F006", "Marine Gas Oil", "Fuel", "Marine", "L", 18.90, 16.80, False),
    Product("F007", "Very Low Sulphur Fuel Oil", "Fuel", "Marine", "L", 16.20, 14.30, False),
    # ------------------------- LPG -------------------------
    Product("LPG01", "LPG Bulk", "LPG", "Bulk", "KG", 28.50, 23.80, True),
    Product("LPG02", "LPG Cylinder 9kg", "LPG", "Cylinder", "KG", 34.20, 27.10, True),
    Product("LPG03", "LPG Cylinder 19kg", "LPG", "Cylinder", "KG", 32.60, 26.20, True),
    Product("LPG04", "LPG Cylinder 48kg", "LPG", "Cylinder", "KG", 31.10, 25.40, True),
    # ------------------------- lubricants -------------------------
    Product("L001", "Passenger Vehicle Engine Oil", "Lubricant", "Automotive", "L", 92.00, 58.00, False),
    Product("L002", "Heavy Duty Diesel Engine Oil", "Lubricant", "Transport", "L", 78.50, 49.00, False),
    Product("L003", "Hydraulic Oil", "Lubricant", "Industrial", "L", 68.00, 43.00, False),
    Product("L004", "Marine Cylinder Oil", "Lubricant", "Marine", "L", 105.00, 71.00, False),
    Product("L005", "Automatic Transmission Fluid", "Lubricant", "Automotive", "L", 118.00, 74.00, False),
    Product("L006", "Mining Gear Oil", "Lubricant", "Mining", "L", 88.00, 56.00, False),
    Product("L007", "Grease Cartridge", "Lubricant", "Industrial", "KG", 96.00, 61.00, False),
    # ------------------------- convenience retail -------------------------
    Product("S001", "Cold Beverage", "Convenience", "Beverage", "EA", 22.00, 13.60, False),
    Product("S002", "Snack", "Convenience", "Food", "EA", 18.50, 10.80, False),
    Product("S003", "Prepared Food", "Convenience", "QSR", "EA", 62.00, 33.00, False),
    Product("S004", "Coffee", "Convenience", "Hot Beverage", "EA", 31.00, 12.40, False),
    Product("S005", "Automotive Accessory", "Convenience", "Automotive", "EA", 145.00, 96.00, False),
    Product("S006", "Tobacco", "Convenience", "Tobacco", "EA", 58.00, 49.00, False),
    Product("S007", "Grocery Essential", "Convenience", "Grocery", "EA", 41.00, 30.50, False),
    Product("S008", "Car Wash Service", "Convenience", "Service", "EA", 95.00, 38.00, False),
    # ------------------------- new energy -------------------------
    Product("E001", "EV DC Fast Charge", "Energy", "EV", "KWH", 7.60, 3.10, False),
    Product("E002", "EV AC Charge", "Energy", "EV", "KWH", 5.40, 2.30, False),
    Product("E003", "Solar Generation", "Energy", "Solar", "KWH", 0.00, 0.00, False),
]

PRODUCT_BY_ID = {p.product_id: p for p in PRODUCTS}

FUEL_IDS = [p.product_id for p in PRODUCTS if p.category == "Fuel"]
ROAD_FUEL_IDS = [p.product_id for p in PRODUCTS if p.subcategory in ("Petrol", "Diesel")]
SHOP_IDS = [p.product_id for p in PRODUCTS if p.category == "Convenience"]
LPG_IDS = [p.product_id for p in PRODUCTS if p.category == "LPG"]
LUBE_IDS = [p.product_id for p in PRODUCTS if p.category == "Lubricant"]
AVIATION_IDS = [p.product_id for p in PRODUCTS if p.subcategory == "Aviation"]
MARINE_IDS = [p.product_id for p in PRODUCTS if p.subcategory == "Marine"]
EV_IDS = [p.product_id for p in PRODUCTS if p.subcategory == "EV"]

PRODUCT_BRANDS = ["Helix Synthetic", "Rimula Synthetic", "Tellus Synthetic", "Unbranded"]

# Fictional retail banner names for synthetic sites. Deliberately invented so
# no generated site can be read as a real branded station.
SITE_BANNERS = ["Kalahari Fuels", "Karoo Motion", "Highveld Energy", "Cape Route Fuels"]

SITE_TYPES = [
    "Highway Service Station",
    "Urban Service Station",
    "Township Service Station",
    "Rural Service Station",
    "Truck Stop",
    "Marine Bunkering Point",
    "Airport Fuel Farm",
]

OWNERSHIP_MODELS = ["COCO", "CODO", "DODO"]  # company/dealer owned & operated

CUSTOMER_SECTORS = [
    "Road Transport", "Mining", "Construction", "Power Generation",
    "Aviation", "Marine", "Agriculture", "Manufacturing",
    "Government", "Reseller", "SME", "Fishing",
]

CUSTOMER_SEGMENTS = ["Strategic", "Key Account", "Mid Market", "Small Business", "Spot"]

CHANNELS = ["Retail Forecourt", "Commercial Direct", "Distributor", "Digital App", "Wholesale"]

PAYMENT_METHODS = ["Card", "Cash", "Fleet Card", "Mobile App", "Account", "Voucher"]

SUPPLIER_TYPES = [
    "Refinery", "Importer", "Pipeline Operator", "Road Transporter",
    "Rail Operator", "Packaging", "Food & Beverage", "Maintenance Contractor",
]

CONTRACT_TYPES = ["Long-term Supply", "Annual Tender", "Spot", "Consignment", "Framework"]

INCIDENT_TYPES = [
    "Slip Trip Fall", "Vehicle Incident", "Fuel Spill", "Fire", "Electrical",
    "Manual Handling", "Chemical Exposure", "Security", "Process Safety",
]

INCIDENT_SEVERITIES = ["Near Miss", "Minor", "Moderate", "Serious", "Major"]

MAINTENANCE_TYPES = ["Preventive", "Corrective", "Predictive", "Statutory Inspection", "Breakdown"]

FAILURE_MODES = [
    "Seal Leak", "Pump Motor Failure", "Nozzle Wear", "Sensor Drift",
    "Corrosion", "Electrical Fault", "Software Fault", "Blockage",
]

ASSET_TYPES = [
    "Dispensing Pump", "Underground Tank", "Aboveground Tank", "Generator",
    "POS Terminal", "EV Charger", "Solar Inverter", "Compressor",
    "Fire Suppression System", "Canopy Lighting", "Car Wash Unit", "Forecourt Controller",
]

DELIVERY_STATUSES = ["Planned", "Dispatched", "In Transit", "Delivered", "Short Delivered", "Failed"]

ORDER_STATUSES = ["Draft", "Confirmed", "Allocated", "Delivered", "Partial", "Cancelled", "Invoiced"]

REASON_CODES = [
    "Stock Out", "Vehicle Breakdown", "Traffic Delay", "Customer Site Closed",
    "Documentation Error", "Quality Hold", "Weather", "Access Restriction", "None",
]

SHIFTS = ["Morning", "Afternoon", "Night"]

DEVICE_TYPES = ["Android Phone", "iPhone", "Tablet", "Desktop Web", "Mobile Web", "Kiosk"]

DIGITAL_EVENT_TYPES = [
    "app_open", "site_search", "price_view", "loyalty_check", "offer_view",
    "offer_redeem", "payment_started", "payment_completed", "ev_session_start",
    "feedback_submitted", "account_update", "app_close",
]

CAMPAIGN_CHANNELS = ["Push Notification", "Email", "SMS", "In-App", "Forecourt Screen", "Radio"]

ENERGY_SOURCES = ["Grid", "Solar PV", "Diesel Generator", "Battery Storage"]

GL_ACCOUNTS: list[tuple[str, str, str]] = [
    ("400100", "Fuel Revenue", "Revenue"),
    ("400200", "Shop Revenue", "Revenue"),
    ("400300", "Lubricant Revenue", "Revenue"),
    ("400400", "LPG Revenue", "Revenue"),
    ("400500", "Aviation Revenue", "Revenue"),
    ("400600", "Marine Revenue", "Revenue"),
    ("400700", "EV Charging Revenue", "Revenue"),
    ("500100", "Fuel Cost of Sales", "COGS"),
    ("500200", "Shop Cost of Sales", "COGS"),
    ("500300", "Lubricant Cost of Sales", "COGS"),
    ("600100", "Site Operating Costs", "Opex"),
    ("600200", "Transport and Distribution", "Opex"),
    ("600300", "Employee Costs", "Opex"),
    ("600400", "Maintenance", "Opex"),
    ("600500", "Energy and Utilities", "Opex"),
    ("600600", "Marketing", "Opex"),
    ("600700", "IT and Digital", "Opex"),
    ("700100", "Depreciation", "Opex"),
    ("800100", "Capital Expenditure", "Capex"),
    ("900100", "Working Capital Movement", "Balance Sheet"),
]

COST_CENTRES = [
    "Retail Operations", "Commercial Sales", "Supply and Distribution",
    "Terminals", "Fleet", "Lubricants", "LPG", "Aviation", "Marine",
    "New Energy", "HSSEQ", "Finance", "IT and Digital", "Human Resources",
]

BUSINESS_UNITS = [
    ("BU01", "Retail", "Downstream"),
    ("BU02", "Commercial", "Downstream"),
    ("BU03", "Lubricants", "Downstream"),
    ("BU04", "LPG", "Downstream"),
    ("BU05", "Aviation", "Downstream"),
    ("BU06", "Marine", "Downstream"),
    ("BU07", "Supply and Distribution", "Supply"),
    ("BU08", "New Energy", "Growth"),
]

ROLES = [
    "Site Manager", "Forecourt Attendant", "Cashier", "Area Manager",
    "Terminal Operator", "Driver", "Maintenance Technician", "HSSEQ Officer",
    "Account Manager", "Planner", "Analyst", "Finance Officer",
]

WEATHER_CONDITIONS = ["Clear", "Cloudy", "Rain", "Heavy Rain", "Wind", "Fog", "Heat Wave"]

SCENARIOS = ["Actual", "Base Case", "Upside", "Downside", "Stress"]

DATA_SOURCES = [
    ("SRC01", "Forecourt POS", "Batch File", "Retail"),
    ("SRC02", "Shop POS", "Batch File", "Retail"),
    ("SRC03", "Tank Gauge Telemetry", "Event Stream", "Supply"),
    ("SRC04", "Fleet GPS Telemetry", "Event Stream", "Logistics"),
    ("SRC05", "EV Charge Point OCPP", "Event Stream", "New Energy"),
    ("SRC06", "Solar Inverter Telemetry", "Event Stream", "New Energy"),
    ("SRC07", "ERP Sales and Distribution", "CDC", "Commercial"),
    ("SRC08", "ERP Finance", "CDC", "Finance"),
    ("SRC09", "CRM", "API", "Commercial"),
    ("SRC10", "Loyalty Platform", "API", "Retail"),
    ("SRC11", "Mobile App Analytics", "Event Stream", "Digital"),
    ("SRC12", "Maintenance Management System", "Batch File", "Assets"),
    ("SRC13", "HSSEQ Reporting Portal", "API", "HSSEQ"),
    ("SRC14", "Terminal Automation System", "CDC", "Supply"),
]

# --------------------------------------------------------------------------
# Demand shape parameters used by the fact generators
# --------------------------------------------------------------------------

# Relative fuel demand by hour of day (0-23): morning and evening commute peaks.
HOUR_WEIGHTS = [
    0.22, 0.14, 0.10, 0.10, 0.18, 0.45, 0.95, 1.55, 1.70, 1.25, 1.05, 1.10,
    1.25, 1.15, 1.05, 1.15, 1.45, 1.85, 1.70, 1.20, 0.85, 0.62, 0.45, 0.30,
]

# Relative demand by weekday (Mon=0 ... Sun=6).
DOW_WEIGHTS = [1.00, 0.98, 1.01, 1.06, 1.24, 1.18, 0.79]

# Relative demand by calendar month (Jan=1 ... Dec=12). December holiday travel
# and the Easter period lift volumes; February is short and quiet.
MONTH_WEIGHTS = {
    1: 1.02, 2: 0.90, 3: 1.05, 4: 1.08, 5: 0.97, 6: 0.94,
    7: 1.00, 8: 0.98, 9: 1.02, 10: 1.05, 11: 1.06, 12: 1.28,
}

# South African public holidays in the modelled window. Travel days lift
# highway volumes and depress urban commuter volumes.
SA_PUBLIC_HOLIDAYS = {
    "2024-01-01", "2024-03-21", "2024-03-29", "2024-04-01", "2024-04-27",
    "2024-05-01", "2024-06-16", "2024-06-17", "2024-08-09", "2024-09-24",
    "2024-12-16", "2024-12-25", "2024-12-26",
    "2025-01-01", "2025-03-21", "2025-04-18", "2025-04-21", "2025-04-27",
    "2025-04-28", "2025-05-01", "2025-06-16", "2025-08-09", "2025-09-24",
    "2025-12-16", "2025-12-25", "2025-12-26",
    "2026-01-01", "2026-03-21", "2026-04-03", "2026-04-06", "2026-04-27",
    "2026-05-01", "2026-06-16", "2026-08-09", "2026-08-10",
}
