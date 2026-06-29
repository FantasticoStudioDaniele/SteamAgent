"""Generate a self-contained DEMO database so anyone can explore the dashboard
without a Steam partner account.

It writes two artifacts (both gitignored, safe to regenerate):

    data/demo.db            -- a SQLite warehouse filled with *fake* data
    config/games.demo.yaml  -- the matching demo portfolio catalog

Then run the dashboard against them, leaving your real DB and catalog untouched:

    # macOS / Linux
    DATABASE_URL=sqlite:///data/demo.db STEAM_GAMES_PATH=config/games.demo.yaml \
        STUDIO_NAME="Pixel Forge Studio (demo)" \
        uv run streamlit run dashboard/app.py

    # Windows (PowerShell)
    $env:DATABASE_URL="sqlite:///data/demo.db"; $env:STEAM_GAMES_PATH="config/games.demo.yaml"; `
        $env:STUDIO_NAME="Pixel Forge Studio (demo)"; uv run streamlit run dashboard/app.py

The numbers are invented by a seeded RNG (reproducible) and resemble a small
indie portfolio. Nothing here comes from a real account.
"""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

import yaml
from sqlalchemy import create_engine

from steam_agent.settings import CONFIG_DIR, DATA_DIR
from steam_agent.storage.models import (
    Base,
    GameSnapshot,
    MarketingCountry,
    MarketingDaily,
    MarketingOwners,
    PlayersDaily,
    PlaytimeSnapshot,
    Review,
    SalesByCountry,
    TrafficDaily,
    WishlistDaily,
)

RNG = random.Random(7)
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()

DEMO_DB = DATA_DIR / "demo.db"
DEMO_GAMES = CONFIG_DIR / "games.demo.yaml"

# (appid, name, days-since-launch, popularity scale) — clearly fictional titles.
GAMES = [
    (900101, "Neon Aether", 700, 1.6),
    (900102, "Turnip Knights", 520, 1.0),
    (900103, "Starfarer Tactics", 410, 1.3),
    (900104, "Moonlit Cove", 250, 0.7),
    (900105, "Hexa Forge", 130, 0.9),
]

COUNTRIES = [
    ("United States", 0.30), ("Germany", 0.13), ("United Kingdom", 0.09),
    ("France", 0.07), ("Canada", 0.06), ("China", 0.10), ("Japan", 0.06),
    ("Brazil", 0.05), ("Australia", 0.04), ("Poland", 0.04),
]
PLATFORMS = [("Windows", 0.82), ("macOS", 0.10), ("Linux", 0.08)]
MK_SOURCES = [
    "Steam Store Home", "Discovery Queue", "Search Results",
    "External Website", "Wishlists", "Bot Traffic",
]
TRAFFIC_FEATURES = [
    ("Steam", "Store Home Page"), ("Steam", "Discovery Queue"),
    ("Steam", "Search"), ("Steam", "Wishlist"),
    ("External", "Other Websites"), ("External", "Direct Navigation"),
]
REVIEW_SNIPPETS = [
    ("Brilliant gameplay loop, lost 40 hours without noticing.", True, "english"),
    ("Charming art and tight controls. Worth every cent.", True, "english"),
    ("Crashes on launch since the last patch — please fix.", False, "english"),
    ("Bel gioco ma manca il supporto al controller.", True, "italian"),
    ("Tolles Spiel, aber der Schwierigkeitsgrad ist brutal.", True, "german"),
    ("Fun for a couple hours then gets repetitive.", False, "english"),
    ("Best soundtrack in any indie game this year.", True, "english"),
    ("Le matchmaking est trop lent en soirée.", False, "french"),
    ("Surprisingly deep crafting system. Recommended.", True, "english"),
    ("Refunded — too many bugs at this price.", False, "english"),
]


def _seasonal(day: date) -> float:
    """Mild yearly seasonality + a weekend bump."""
    doy = day.timetuple().tm_yday
    season = 1.0 + 0.18 * math.sin(2 * math.pi * doy / 365.0)
    weekend = 1.15 if day.weekday() >= 5 else 1.0
    return season * weekend


def _launch_curve(days_after: int) -> float:
    """Launch spike that decays toward a long-tail baseline."""
    spike = 6.0 * math.exp(-days_after / 21.0)
    return 0.5 + spike + 0.6 * math.exp(-days_after / 240.0)


def build() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if DEMO_DB.exists():
        DEMO_DB.unlink()

    DEMO_GAMES.write_text(
        yaml.safe_dump(
            {"games": [{"appid": a, "name": n} for a, n, _, _ in GAMES]},
            allow_unicode=True, sort_keys=False,
        ),
        encoding="utf-8",
    )

    engine = create_engine(f"sqlite:///{DEMO_DB.as_posix()}", future=True)
    Base.metadata.create_all(engine)

    wishlist: list[dict] = []
    players: list[dict] = []
    marketing: list[dict] = []
    traffic: list[dict] = []
    sales: list[dict] = []
    reviews: list[dict] = []
    owners: list[dict] = []
    countries: list[dict] = []
    playtime: list[dict] = []
    snapshots: list[dict] = []

    for appid, name, age, scale in GAMES:
        launch = TODAY - timedelta(days=age)

        # ---- daily series: wishlist + players (full history since launch) ----
        for d in range(age + 1):
            day = launch + timedelta(days=d)
            curve = _launch_curve(d) * _seasonal(day) * scale
            adds = max(0, int(RNG.gauss(70, 18) * curve))
            wishlist.append({
                "app_id": appid, "date": day,
                "adds": adds,
                "deletes": int(adds * RNG.uniform(0.18, 0.34)),
                "purchases_activations": int(adds * RNG.uniform(0.05, 0.15)),
                "gifts": int(adds * RNG.uniform(0.0, 0.04)),
                "collected_at": NOW,
            })
            dau = max(0, int(RNG.gauss(900, 160) * curve))
            players.append({
                "app_id": appid, "date": day,
                "daily_active_users": dau,
                "peak_concurrent_users": int(dau * RNG.uniform(0.10, 0.22)),
                "collected_at": NOW,
            })

        # ---- marketing daily: per source + a 'Total' (KPIs read 'Total') ----
        for d in range(age + 1):
            day = launch + timedelta(days=d)
            curve = _launch_curve(d) * _seasonal(day) * scale
            for metric, base in (("impressions", 4200), ("visits", 520)):
                total = 0
                for src in MK_SOURCES:
                    weight = {
                        "Steam Store Home": 0.34, "Discovery Queue": 0.22,
                        "Search Results": 0.16, "External Website": 0.14,
                        "Wishlists": 0.09, "Bot Traffic": 0.05,
                    }[src]
                    val = max(0, int(RNG.gauss(base * weight, base * weight * 0.25) * curve))
                    total += val
                    marketing.append({
                        "app_id": appid, "date": day, "metric": metric,
                        "source": src, "value": val, "collected_at": NOW,
                    })
                marketing.append({
                    "app_id": appid, "date": day, "metric": metric,
                    "source": "Total", "value": total, "collected_at": NOW,
                })

            # ---- traffic daily (sampled features) ----
            for cat, feat in TRAFFIC_FEATURES:
                imp = max(0, int(RNG.gauss(700, 220) * curve))
                traffic.append({
                    "app_id": appid, "date": day, "category": cat, "feature": feat,
                    "impressions": imp, "visits": int(imp * RNG.uniform(0.08, 0.2)),
                    "owner_impressions": int(imp * RNG.uniform(0.1, 0.3)),
                    "owner_visits": int(imp * RNG.uniform(0.02, 0.08)),
                    "collected_at": NOW,
                })

        # ---- monthly sales per country/platform ----
        month = launch.replace(day=1)
        while month <= TODAY:
            days_after = (month - launch).days
            base_units = max(0, RNG.gauss(2600, 500) * _launch_curve(max(days_after, 0)) * scale)
            price = RNG.choice([9.99, 14.99, 19.99, 24.99])
            for country, cw in COUNTRIES:
                for plat, pw in PLATFORMS:
                    units = int(base_units * cw * pw * RNG.uniform(0.8, 1.2))
                    if units <= 0:
                        continue
                    sales.append({
                        "month": month, "country": country,
                        "sku": f"{name} (Steam)", "package_id": appid,
                        "product_name": name, "platform": plat,
                        "net_units": units,
                        "net_sales_usd": round(units * price * RNG.uniform(0.62, 0.72), 2),
                        "collected_at": NOW,
                    })
            # advance one month
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)

        # ---- reviews ----
        for i in range(int(40 * scale) + 10):
            text, up, lang = RNG.choice(REVIEW_SNIPPETS)
            created = NOW - timedelta(days=RNG.randint(0, age), hours=RNG.randint(0, 23))
            reviews.append({
                "recommendation_id": f"{appid}{i:05d}",
                "app_id": appid, "language": lang,
                "voted_up": up, "votes_up": RNG.randint(0, 120),
                "votes_funny": RNG.randint(0, 30),
                "playtime_at_review_min": RNG.randint(20, 6000),
                "created_at": created, "review_text": text, "collected_at": NOW,
            })

        # ---- playtime distribution snapshot ----
        avg = RNG.randint(180, 900)
        playtime.append({
            "app_id": appid, "snapshot_date": TODAY,
            "lifetime_users": int(40000 * scale),
            "avg_minutes": avg, "median_minutes": int(avg * RNG.uniform(0.5, 0.8)),
            "distribution": {
                "0": 100, "10": RNG.randint(70, 85), "30": RNG.randint(50, 65),
                "60": RNG.randint(35, 50), "120": RNG.randint(20, 32),
                "300": RNG.randint(8, 18), "600": RNG.randint(3, 9),
            },
            "collected_at": NOW,
        })

        # ---- marketing ownership + top countries snapshots ----
        owner_pct = round(RNG.uniform(28, 52), 2)
        owners.append({
            "app_id": appid, "snapshot_date": TODAY,
            "owners_pct": owner_pct, "non_owners_pct": round(100 - owner_pct, 2),
            "collected_at": NOW,
        })
        for country, cw in COUNTRIES + [("Unknown", 0.06)]:
            visits = int(RNG.gauss(9000, 2500) * cw * scale + 200)
            countries.append({
                "app_id": appid, "snapshot_date": TODAY, "country": country,
                "visits": visits, "pct": round(cw * 100, 2), "collected_at": NOW,
            })

        # ---- a few public snapshots over time ----
        revs_tot = int(50 * scale) + 10
        for k in range(3):
            when = NOW - timedelta(days=30 * k)
            snapshots.append({
                "app_id": appid, "name": name,
                "current_players": int(RNG.gauss(400, 120) * scale),
                "reviews_total": revs_tot - k * 4,
                "reviews_positive": int((revs_tot - k * 4) * RNG.uniform(0.78, 0.93)),
                "review_score_desc": "Very Positive",
                "price": f"${RNG.choice([9.99, 14.99, 19.99, 24.99])}",
                "collected_at": when,
            })

    batches = [
        (WishlistDaily, wishlist), (PlayersDaily, players),
        (MarketingDaily, marketing), (TrafficDaily, traffic),
        (SalesByCountry, sales), (Review, reviews),
        (MarketingOwners, owners), (MarketingCountry, countries),
        (PlaytimeSnapshot, playtime), (GameSnapshot, snapshots),
    ]
    with engine.begin() as conn:
        for model, rows in batches:
            if rows:
                conn.execute(model.__table__.insert(), rows)

    total = sum(len(rows) for _, rows in batches)
    print(f"Demo DB written: {DEMO_DB}  ({total:,} rows across {len(batches)} tables)")
    print(f"Demo catalog:    {DEMO_GAMES}  ({len(GAMES)} games)")
    print("\nRun the dashboard against the demo (leaves your real data untouched):")
    print("  macOS/Linux:")
    print("    DATABASE_URL=sqlite:///data/demo.db STEAM_GAMES_PATH=config/games.demo.yaml \\")
    print('      STUDIO_NAME="Pixel Forge Studio (demo)" \\')
    print("      uv run streamlit run dashboard/app.py")
    print("  Windows (PowerShell):")
    print('    $env:DATABASE_URL="sqlite:///data/demo.db"; '
          '$env:STEAM_GAMES_PATH="config/games.demo.yaml"; '
          '$env:STUDIO_NAME="Pixel Forge Studio (demo)"; '
          "uv run streamlit run dashboard/app.py")


if __name__ == "__main__":
    build()
