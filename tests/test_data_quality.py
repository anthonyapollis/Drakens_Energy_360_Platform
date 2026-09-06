
from pathlib import Path
import pandas as pd

DATA = Path("sample_data")

def load(name):
    p = DATA / f"{name}.csv"
    return pd.read_csv(p)

def test_sites_have_keys():
    df = load("dim_site")
    assert df["site_id"].notna().all()
    assert df["site_id"].is_unique

def test_sa_sites_have_province_and_city():
    df = load("dim_site")
    za = df[df["country_code"] == "ZA"]
    assert za["province"].notna().all()
    assert za["city"].notna().all()

def test_retail_positive_litres():
    df = load("fact_retail_fuel_sales")
    assert (df["litres"] > 0).all()

def test_retail_references_site():
    sites = set(load("dim_site")["site_id"])
    fact = load("fact_retail_fuel_sales")
    assert set(fact["site_id"]).issubset(sites)
