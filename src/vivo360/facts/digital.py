"""Loyalty, digital and campaign facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_loyalty_transactions")
def loyalty_transactions(rng, ctx, profile):
    members = ctx.loyalty
    member_ids = members["loyalty_member_id"].to_numpy()
    # Higher tiers transact far more often than Blue members.
    tw = members["tier"].map({"Blue": 1.0, "Silver": 2.6, "Gold": 5.4,
                              "Platinum": 11.0}).to_numpy(dtype=float)
    tw = tw / tw.sum()
    tier_lookup = members.set_index("loyalty_member_id")["tier"]

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        mids = rng.choice(member_ids, n, p=tw)
        tiers = tier_lookup.loc[mids].to_numpy()
        is_earn = rng.random(n) < 0.78
        spend = rng.gamma(3.4, 190, n).clip(15, 20_000)
        rate = pd.Series(tiers).map({"Blue": 1.0, "Silver": 1.25,
                                     "Gold": 1.6, "Platinum": 2.2}).to_numpy()
        points = np.where(is_earn, spend * 0.01 * rate * 100,
                          -rng.gamma(2.0, 900, n))
        df = pd.DataFrame({
            "loyalty_transaction_id": c.seq_ids("LT", offset, n),
            "transaction_ts": ts,
            "date_key": c.date_key(ts),
            "loyalty_member_id": mids,
            "tier": tiers,
            "site_id": c.weighted_sites(rng, ctx, n),
            "transaction_type": np.where(is_earn, "Earn", "Burn"),
            "qualifying_spend_zar": np.where(is_earn, spend, 0.0).round(2),
            "points_delta": points.round(0).astype("int32"),
            "points_value_zar": (np.abs(points) * 0.01).round(2),
            "earn_category": rng.choice(
                ["Fuel", "Shop", "Car Wash", "Partner", "Bonus"], n,
                p=[0.54, 0.28, 0.06, 0.07, 0.05]),
            "channel": rng.choice(["Forecourt", "Mobile App", "Partner"], n,
                                  p=[0.66, 0.28, 0.06]),
        })
        return c.add_audit_columns(df, "SRC10")

    return make_chunk


@fact("fact_loyalty_points_balance")
def loyalty_points_balance(rng, ctx, profile):
    member_ids = ctx.loyalty["loyalty_member_id"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        opening = rng.gamma(2.2, 2_600, n).clip(0, 400_000)
        earned = rng.gamma(1.8, 420, n)
        burned = rng.gamma(1.4, 300, n)
        expired = np.where(rng.random(n) < 0.08, rng.gamma(1.2, 180, n), 0.0)
        df = pd.DataFrame({
            "points_balance_id": c.seq_ids("LPB", offset, n),
            "snapshot_date": ts,
            "date_key": c.date_key(ts),
            "loyalty_member_id": rng.choice(member_ids, n),
            "opening_points": opening.round(0).astype("int32"),
            "points_earned": earned.round(0).astype("int32"),
            "points_burned": burned.round(0).astype("int32"),
            "points_expired": expired.round(0).astype("int32"),
            "closing_points": (opening + earned - burned - expired).round(0).astype("int32"),
            "liability_zar": ((opening + earned - burned - expired) * 0.01).round(2),
        })
        return c.add_audit_columns(df, "SRC10")

    return make_chunk


@fact("fact_digital_events")
def digital_events(rng, ctx, profile):
    users = ctx.digital_user["digital_user_id"].to_numpy()
    events = np.array(ref.DIGITAL_EVENT_TYPES)
    # A funnel: many opens, progressively fewer conversions.
    ep = np.array([0.19, 0.12, 0.14, 0.09, 0.10, 0.045, 0.055, 0.04,
                   0.02, 0.015, 0.015, 0.155])
    ep = ep / ep.sum()

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        etype = rng.choice(events, n, p=ep)
        df = pd.DataFrame({
            "digital_event_id": c.seq_ids("DEV", offset, n),
            "event_ts": ts,
            "date_key": c.date_key(ts),
            "time_key": c.time_key(ts),
            "digital_user_id": rng.choice(users, n),
            "session_id": c.seq_ids("SES", offset // 6, n, 12),
            "event_type": etype,
            "device_type": rng.choice(ref.DEVICE_TYPES, n,
                                      p=[0.43, 0.24, 0.06, 0.09, 0.16, 0.02]),
            "app_version": rng.choice(["3.2.1", "3.3.0", "4.0.2", "4.1.0"], n,
                                      p=[0.08, 0.17, 0.39, 0.36]),
            "site_id": np.where(rng.random(n) < 0.42,
                                rng.choice(ctx.site_ids, n), None),
            "screen_name": rng.choice(
                ["Home", "Station Finder", "Prices", "Loyalty", "Offers",
                 "Payment", "Profile", "EV"], n),
            "duration_ms": rng.gamma(2.0, 1600, n).clip(30, 180_000).round(0).astype("int32"),
            "is_conversion": np.isin(etype, ["payment_completed", "offer_redeem"]),
            "network_type": rng.choice(["4G", "5G", "WiFi", "3G"], n,
                                       p=[0.44, 0.19, 0.31, 0.06]),
        })
        return c.add_audit_columns(df, "SRC11")

    return make_chunk


@fact("fact_digital_sessions")
def digital_sessions(rng, ctx, profile):
    users = ctx.digital_user["digital_user_id"].to_numpy()

    def make_chunk(offset, n):
        start = c.sample_timestamps(rng, n)
        events = rng.geometric(0.16, n).clip(1, 90)
        secs = events * rng.gamma(2.0, 14, n)
        df = pd.DataFrame({
            "session_id": c.seq_ids("SES", offset, n),
            "session_start_ts": start,
            "session_end_ts": start + pd.to_timedelta(secs.round(0), unit="s"),
            "date_key": c.date_key(start),
            "digital_user_id": rng.choice(users, n),
            "device_type": rng.choice(ref.DEVICE_TYPES, n,
                                      p=[0.43, 0.24, 0.06, 0.09, 0.16, 0.02]),
            "event_count": events.astype("int16"),
            "duration_seconds": secs.round(1),
            "screens_viewed": np.minimum(events, rng.integers(1, 14, n)).astype("int16"),
            "is_bounce": events <= 1,
            "converted": rng.random(n) < 0.086,
            "acquisition_channel": rng.choice(
                ["Organic", "Push Notification", "Email", "Paid Social", "Referral"],
                n, p=[0.46, 0.21, 0.12, 0.14, 0.07]),
        })
        return c.add_audit_columns(df, "SRC11")

    return make_chunk


@fact("fact_mobile_payments")
def mobile_payments(rng, ctx, profile):
    users = ctx.digital_user["digital_user_id"].to_numpy()

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        amount = rng.gamma(3.6, 210, n).clip(20, 18_000)
        approved = rng.random(n) < 0.968
        df = pd.DataFrame({
            "mobile_payment_id": c.seq_ids("MP", offset, n),
            "payment_ts": ts,
            "date_key": c.date_key(ts),
            "digital_user_id": rng.choice(users, n),
            "site_id": c.weighted_sites(rng, ctx, n),
            "amount_zar": amount.round(2),
            "payment_instrument": rng.choice(
                ["Stored Card", "Wallet", "EFT", "Voucher"], n,
                p=[0.61, 0.22, 0.12, 0.05]),
            "is_approved": approved,
            "decline_reason": np.where(
                approved, None,
                rng.choice(["Insufficient Funds", "Card Expired", "Fraud Rule",
                            "Network Timeout"], n)),
            "processing_ms": rng.gamma(2.6, 380, n).clip(90, 30_000).round(0).astype("int32"),
            "is_flagged_fraud": rng.random(n) < 0.0042,
        })
        return c.add_audit_columns(df, "SRC11")

    return make_chunk


@fact("fact_campaign_responses")
def campaign_responses(rng, ctx, profile):
    campaigns = ctx.campaign["campaign_id"].to_numpy()
    users = ctx.digital_user["digital_user_id"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        delivered = rng.random(n) < 0.94
        opened = delivered & (rng.random(n) < 0.38)
        clicked = opened & (rng.random(n) < 0.26)
        redeemed = clicked & (rng.random(n) < 0.31)
        df = pd.DataFrame({
            "campaign_response_id": c.seq_ids("CR", offset, n),
            "response_ts": ts,
            "date_key": c.date_key(ts),
            "campaign_id": rng.choice(campaigns, n),
            "digital_user_id": rng.choice(users, n),
            "channel": rng.choice(ref.CAMPAIGN_CHANNELS, n),
            "was_delivered": delivered,
            "was_opened": opened,
            "was_clicked": clicked,
            "was_redeemed": redeemed,
            "incremental_spend_zar": np.where(
                redeemed, rng.gamma(3.0, 160, n), 0.0).round(2),
            "attribution_model": rng.choice(["Last Touch", "Linear", "Time Decay"], n),
        })
        return c.add_audit_columns(df, "SRC10")

    return make_chunk
