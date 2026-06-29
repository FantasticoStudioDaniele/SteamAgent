"""SteamAgent CLI (typer)."""
from __future__ import annotations

import asyncio
import logging

import typer
import yaml
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table
from sqlalchemy import select

from steam_agent.collectors.public_api import PublicApiCollector
from steam_agent.settings import settings
from steam_agent.storage.db import SessionLocal, init_db
from steam_agent.storage.models import GameSnapshot
from steam_agent.storage.raw import build_snapshot, save_raw, save_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
console = Console()
app = typer.Typer(add_completion=False, help="SteamAgent — Steam developer data collection.")


@app.command("init-db")
def init_db_cmd() -> None:
    """Create or migrate the database schema to the latest Alembic revision."""
    init_db()
    console.print(f"[green]Schema up to date[/] (Alembic head): {settings.database_url}")


@app.command("collect-public")
def collect_public(
    appid: int = typer.Option(None, help="AppID; default = SMOKE_TEST_APPID"),
) -> None:
    """Collect the public data for an appid and save raw + snapshot."""
    app_id = appid or settings.smoke_test_appid
    console.print(f"Collecting public data for appid [bold]{app_id}[/]...")
    records = PublicApiCollector(app_id).collect()
    n = save_raw(records)
    snap = build_snapshot(app_id, records)
    save_snapshot(snap)
    console.print(f"[green]OK[/] — {n} raw payloads saved.")

    table = Table(title=f"Snapshot appid {app_id}")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Name", str(snap.name))
    table.add_row("Players now", str(snap.current_players))
    table.add_row("Total reviews", str(snap.reviews_total))
    table.add_row("Positive reviews", str(snap.reviews_positive))
    table.add_row("Rating", str(snap.review_score_desc))
    table.add_row("Price", str(snap.price))
    console.print(table)


@app.command()
def login(
    headed: bool = typer.Option(False, help="Show the browser (recommended on first login)."),
) -> None:
    """Establish/refresh the authenticated Steam session (TOTP)."""
    from steam_agent.auth.session import ensure_session

    asyncio.run(ensure_session(headless=not headed))
    console.print("[green]Session ready.[/]")


@app.command("collect-games")
def collect_games() -> None:
    """Fetch the games list from the partner portal and save it to config/games.yaml."""
    from steam_agent.collectors.partner_games import fetch_games

    games = asyncio.run(fetch_games())
    out = settings.games_catalog_path
    out.write_text(yaml.safe_dump({"games": games}, allow_unicode=True), encoding="utf-8")
    console.print(f"[green]Saved {len(games)} games to[/] {out}")


@app.command()
def show(limit: int = typer.Option(20, help="Number of snapshots to show.")) -> None:
    """Show the latest saved snapshots."""
    init_db()
    with SessionLocal() as session:
        rows = session.execute(
            select(GameSnapshot).order_by(GameSnapshot.collected_at.desc()).limit(limit)
        ).scalars().all()

    table = Table(title="Latest snapshots")
    for col in ("appid", "name", "players", "rev. tot", "positive", "when"):
        table.add_column(col)
    for r in rows:
        table.add_row(
            str(r.app_id), str(r.name), str(r.current_players),
            str(r.reviews_total), str(r.reviews_positive),
            r.collected_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@app.command("collect-traffic")
def collect_traffic(
    day: str = typer.Option(None, "--day", help="Day YYYY-MM-DD (default: yesterday UTC)"),
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
) -> None:
    """Download the store page traffic (per source) for a day and save it."""
    from datetime import date as date_cls
    from datetime import datetime, timedelta, timezone

    from steam_agent.collectors.traffic import fetch_traffic
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_traffic

    target = (
        date_cls.fromisoformat(day)
        if day
        else datetime.now(timezone.utc).date() - timedelta(days=1)
    )
    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    console.print(f"Collecting traffic for {len(appids)} apps, day [bold]{target}[/]...")
    data = asyncio.run(fetch_traffic(appids, target))
    total = sum(save_traffic(aid, target, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} traffic rows from {with_data}/{len(appids)} apps for {target}."
    )


@app.command("collect-wishlist")
def collect_wishlist(
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
) -> None:
    """Download the wishlist history (daily actions) from the partner portal."""
    from steam_agent.collectors.wishlist import fetch_wishlist
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_wishlist

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    console.print(f"Collecting wishlist (full history) for {len(appids)} apps...")
    data = asyncio.run(fetch_wishlist(appids))
    total = sum(save_wishlist(aid, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} wishlist-days from {with_data}/{len(appids)} apps."
    )


@app.command("collect-sales")
def collect_sales(
    since: str = typer.Option("2018-01", help="Start month YYYY-MM (default 2018-01)"),
    until: str = typer.Option(None, help="End month YYYY-MM (default: current month)"),
    month: str = typer.Option(None, help="Only this month YYYY-MM"),
    months_opt: str = typer.Option(None, "--months", help="Comma-separated list of YYYY-MM (gap-fill)"),
) -> None:
    """Download monthly sales (units + net revenue, per country) from the portal."""
    from datetime import date as date_cls
    from datetime import datetime, timezone

    from steam_agent.collectors.sales import fetch_sales, months_range
    from steam_agent.storage.raw import save_sales

    def _parse(ym: str) -> date_cls:
        y, m = ym.split("-")
        return date_cls(int(y), int(m), 1)

    if months_opt:
        months = [_parse(x.strip()) for x in months_opt.split(",") if x.strip()]
    elif month:
        months = [_parse(month)]
    else:
        start = _parse(since)
        end = _parse(until) if until else datetime.now(timezone.utc).date().replace(day=1)
        months = months_range(start, end)

    console.print(f"Collecting sales for {len(months)} months...")
    counter = {"rows": 0, "months": 0}

    def _on(m, rows) -> None:
        counter["rows"] += save_sales(m, rows)
        if rows:
            counter["months"] += 1

    asyncio.run(fetch_sales(months, on_result=_on))
    console.print(
        f"[green]OK[/] — {counter['rows']} sales rows from {counter['months']}/{len(months)} months."
    )


@app.command("collect-reviews")
def collect_reviews(
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
    max_reviews: int = typer.Option(2000, "--max", help="Max reviews per game"),
) -> None:
    """Download reviews (text + vote) from the public API, basis for sentiment."""
    from steam_agent.collectors.reviews import fetch_reviews
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_reviews

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    total = 0
    with_data = 0
    for aid in appids:
        rows = fetch_reviews(aid, max_reviews)
        n = save_reviews(rows)
        total += n
        if n:
            with_data += 1
    console.print(f"[green]OK[/] — {total} reviews from {with_data}/{len(appids)} apps.")


@app.command("collect-players")
def collect_players(
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
) -> None:
    """Download the players history (DAU + peak concurrent, daily) from the portal."""
    from steam_agent.collectors.players import fetch_players
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_players

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    console.print(f"Collecting players (history) for {len(appids)} apps...")
    data = asyncio.run(fetch_players(appids))
    total = sum(save_players(aid, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} player-days from {with_data}/{len(appids)} apps."
    )


@app.command("collect-playtime")
def collect_playtime(
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
) -> None:
    """Download the lifetime playtime snapshot (average/median + distribution)."""
    from steam_agent.collectors.playtime import fetch_playtime
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_playtime

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    console.print(f"Collecting playtime for {len(appids)} apps...")
    data = asyncio.run(fetch_playtime(appids))
    n = sum(save_playtime(s) for s in data.values())
    console.print(f"[green]OK[/] — playtime snapshot for {n}/{len(appids)} apps.")


@app.command("collect-marketing")
def collect_marketing(
    appid: int = typer.Option(None, help="Only this appid (default: all games)"),
    preset: str = typer.Option(
        "lifetime", help="Range: lifetime|1year|6months|3months|1month|1week"
    ),
) -> None:
    """Download Visits/Impressions Over Time series + ownership + top countries (Marketing page)."""
    from steam_agent.collectors.marketing import fetch_marketing
    from steam_agent.games import load_games
    from steam_agent.storage.raw import (
        save_marketing,
        save_marketing_country,
        save_marketing_owners,
    )

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]No appid: run `collect-games` first.[/]")
        raise typer.Exit(1)

    console.print(f"Collecting marketing ({preset}) for {len(appids)} apps...")
    data = asyncio.run(fetch_marketing(appids, preset))
    series = owners_n = country_n = 0
    for aid, res in data.items():
        series += save_marketing(aid, res["daily"])
        owners_n += save_marketing_owners(aid, res["owners"])
        country_n += save_marketing_country(aid, res["countries"])
    with_data = sum(1 for res in data.values() if res["daily"])
    console.print(
        f"[green]OK[/] — {series} series rows · owners for {owners_n} apps · "
        f"{country_n} country rows · from {with_data}/{len(appids)} apps."
    )


@app.command()
def doctor() -> None:
    """Check the prerequisites (Python, browser, .env, credentials, session, DB, catalog)."""
    import os
    import sys
    from pathlib import Path as _Path

    from steam_agent.games import load_games
    from steam_agent.secure import is_exposed
    from steam_agent.settings import PROJECT_ROOT

    checks: list[tuple[str, str, str]] = []  # (status OK|FAIL|WARN, item, detail)

    py_ok = sys.version_info >= (3, 11)
    checks.append(("OK" if py_ok else "FAIL", "Python >= 3.11",
                   f"{sys.version_info.major}.{sys.version_info.minor}"))

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
        ok = bool(exe) and _Path(exe).exists()
        checks.append(("OK" if ok else "FAIL", "Browser Playwright (chromium)",
                       "installed" if ok else "missing -> uv run playwright install chromium"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("FAIL", "Browser Playwright (chromium)", f"error: {exc}"))

    env_ok = (PROJECT_ROOT / ".env").exists()
    checks.append(("OK" if env_ok else "FAIL", ".env file",
                   "present" if env_ok else "missing -> copy .env.example or use `setup`"))

    creds_ok = bool(settings.steam_username and settings.steam_password)
    checks.append(("OK" if creds_ok else "FAIL", "Bot credentials",
                   "ok" if creds_ok else "STEAM_USERNAME/PASSWORD missing"))

    secret = bool(settings.steam_shared_secret.strip())
    checks.append(("OK" if secret else "WARN", "shared_secret (automatic login)",
                   "ok (TOTP)" if secret else "absent -> `login --headed` (manual)"))

    pid = settings.steam_partner_id
    checks.append(("OK" if pid else "WARN", "STEAM_PARTNER_ID (sales)",
                   str(pid) if pid else "not set -> `setup` detects it"))

    sess_ok = settings.storage_state_path.exists()
    checks.append(("OK" if sess_ok else "WARN", "Saved session",
                   "present" if sess_ok else "absent -> `login` / `setup`"))

    exposed = [
        name
        for name, p in (
            (".env", PROJECT_ROOT / ".env"),
            ("storage_state.json", settings.storage_state_path),
        )
        if is_exposed(p)
    ]
    if exposed:
        checks.append(("WARN", "Secret file permissions",
                       f"group/other-readable: {', '.join(exposed)} -> chmod 600"))
    else:
        checks.append(("OK", "Secret file permissions",
                       "restricted" if os.name == "posix" else "n/a (Windows ACLs)"))

    try:
        init_db()
        checks.append(("OK", "Database", settings.database_url))
        n = len(load_games())
        checks.append(("OK" if n else "WARN", "Games catalog",
                       f"{n} games" if n else "empty -> `collect-games`"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("FAIL", "Database", f"error: {exc}"))

    colors = {"OK": "green", "FAIL": "red", "WARN": "yellow"}
    table = Table(title="SteamAgent — doctor")
    table.add_column("Status")
    table.add_column("Item")
    table.add_column("Detail")
    for stato, voce, det in checks:
        table.add_row(f"[{colors[stato]}]{stato}[/]", voce, det)
    console.print(table)

    fails = [v for s, v, _ in checks if s == "FAIL"]
    if fails:
        console.print(f"[red]To fix:[/] {', '.join(fails)}")
        raise typer.Exit(1)
    console.print("[green]Prerequisites OK.[/] Proceed with `setup` (first run) or `collect-all`.")


@app.command()
def setup() -> None:
    """First-run wizard: .env, login, partner detection, games catalog, DB."""
    from steam_agent.auth.session import ensure_session, fetch_publishers
    from steam_agent.collectors.partner_games import fetch_games
    from steam_agent.envtools import update_env
    from steam_agent.settings import PROJECT_ROOT

    console.print("[bold]SteamAgent — setup[/]\n")
    console.print(
        "You need a STEAM ACCOUNT DEDICATED to the bot (not your personal one), invited to\n"
        "your Steamworks with read-only permission on the reports. Details in the README.\n"
    )

    # 1) credentials -> .env
    reconfigure = True
    if (PROJECT_ROOT / ".env").exists() and settings.steam_username:
        reconfigure = typer.confirm(
            f"Credentials already present ({settings.steam_username}). Reconfigure?", default=False
        )
    if reconfigure:
        username = typer.prompt("STEAM_USERNAME (bot account)",
                                default=settings.steam_username or None)
        password = typer.prompt("STEAM_PASSWORD", hide_input=True)
        console.print(
            "\n[dim]shared_secret (base64) = unattended automatic login (TOTP).\n"
            "Leave EMPTY to enter the code manually at every login (simpler to start with).[/]"
        )
        secret = typer.prompt("STEAM_SHARED_SECRET (enter to skip)",
                              default="", hide_input=True, show_default=False)
        anthropic = typer.prompt("ANTHROPIC_API_KEY (optional, enter to skip)",
                                 default="", hide_input=True, show_default=False)
        updates = {"STEAM_USERNAME": username, "STEAM_PASSWORD": password}
        if secret:
            updates["STEAM_SHARED_SECRET"] = secret
        if anthropic:
            updates["ANTHROPIC_API_KEY"] = anthropic
        update_env(updates)
        settings.steam_username = username
        settings.steam_password = password
        settings.steam_shared_secret = secret
        if anthropic:
            settings.anthropic_api_key = anthropic
        console.print("[green].env updated.[/]\n")

    # 2) login (headed: handles email confirmation and manual 2FA code)
    console.print("Opening the browser for login (complete any email/2FA confirmations)...\n")
    try:
        asyncio.run(ensure_session(headless=False))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Login failed:[/] {exc}")
        raise typer.Exit(1)
    console.print("[green]Login completed.[/]\n")

    # 3) detect partner_id + studio name from the portal
    try:
        pubs = asyncio.run(fetch_publishers(headless=True))
    except Exception:  # noqa: BLE001
        pubs = {}
    if not pubs:
        console.print(
            "[yellow]No publisher detected.[/] Set STEAM_PARTNER_ID manually "
            "if you need it for sales.\n"
        )
    else:
        if len(pubs) == 1:
            pid_s, name = next(iter(pubs.items()))
        else:
            items = list(pubs.items())
            console.print("Available publishers:")
            for i, (pid_, name_) in enumerate(items, 1):
                console.print(f"  {i}. {name_} (id {pid_})")
            idx = typer.prompt("Choose the number", type=int, default=1)
            pid_s, name = items[min(max(idx, 1), len(items)) - 1]
        update_env({"STEAM_PARTNER_ID": str(pid_s), "STUDIO_NAME": name})
        settings.steam_partner_id = int(pid_s)
        settings.studio_name = name
        console.print(f"[green]Partner detected:[/] {name} (id {pid_s}).\n")

    # 4) games catalog
    console.print("Downloading the games list from the portal...")
    try:
        games = asyncio.run(fetch_games())
        settings.games_catalog_path.write_text(
            yaml.safe_dump({"games": games}, allow_unicode=True), encoding="utf-8"
        )
        console.print(f"[green]{len(games)} games[/] saved to config/games.yaml.\n")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Games list not downloaded:[/] {exc} (retry with `collect-games`).\n")

    # 5) DB
    init_db()
    console.print("[bold green]Setup completed![/]\n")
    console.print("Next steps:")
    console.print("  uv run steam-agent collect-all          # download all the data")
    console.print("  uv run streamlit run dashboard/app.py   # open the dashboard")


@app.command("collect-all")
def collect_all(
    sales_since: str = typer.Option(
        None, help="Sales start month YYYY-MM (default: last 2 months)"
    ),
) -> None:
    """Update ALL datasets in sequence (marketing, wishlist, players, reviews, playtime, sales, traffic)."""
    from datetime import date as _date
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from datetime import timezone as _tz

    from steam_agent.games import load_games
    from steam_agent.scraping import report

    appids = [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Empty catalog: run `setup` or `collect-games` first.[/]")
        raise typer.Exit(1)

    report.reset()  # collect schema-drift events across all collectors this run
    results: list[tuple[str, str]] = []
    failures: list[str] = []

    def step(label: str, fn) -> None:
        console.print(f"[bold]→ {label}[/]")
        try:
            results.append((label, fn()))
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).exception("collect-all step failed: %s", label)
            results.append((label, f"[red]error: {exc}[/]"))
            failures.append(label)

    def _marketing() -> str:
        from steam_agent.collectors.marketing import fetch_marketing
        from steam_agent.storage.raw import (
            save_marketing,
            save_marketing_country,
            save_marketing_owners,
        )

        data = asyncio.run(fetch_marketing(appids))
        s = o = c = 0
        for aid, res in data.items():
            s += save_marketing(aid, res["daily"])
            o += save_marketing_owners(aid, res["owners"])
            c += save_marketing_country(aid, res["countries"])
        return f"{s} series rows · owners {o} · countries {c}"

    def _wishlist() -> str:
        from steam_agent.collectors.wishlist import fetch_wishlist
        from steam_agent.storage.raw import save_wishlist

        data = asyncio.run(fetch_wishlist(appids))
        return f"{sum(save_wishlist(a, r) for a, r in data.items())} wishlist-days"

    def _players() -> str:
        from steam_agent.collectors.players import fetch_players
        from steam_agent.storage.raw import save_players

        data = asyncio.run(fetch_players(appids))
        return f"{sum(save_players(a, r) for a, r in data.items())} player-days"

    def _reviews() -> str:
        from steam_agent.collectors.reviews import fetch_reviews
        from steam_agent.storage.raw import save_reviews

        return f"{sum(save_reviews(fetch_reviews(a, 2000)) for a in appids)} reviews"

    def _playtime() -> str:
        from steam_agent.collectors.playtime import fetch_playtime
        from steam_agent.storage.raw import save_playtime

        data = asyncio.run(fetch_playtime(appids))
        return f"snapshot for {sum(save_playtime(s) for s in data.values())} apps"

    def _sales() -> str:
        from steam_agent.collectors.sales import fetch_sales, months_range
        from steam_agent.storage.raw import save_sales

        if not settings.steam_partner_id:
            return "skipped (STEAM_PARTNER_ID not set)"
        today = _dt.now(_tz.utc).date().replace(day=1)
        if sales_since:
            y, m = sales_since.split("-")
            start = _date(int(y), int(m), 1)
        else:
            start = (today - _td(days=1)).replace(day=1)  # last month
        months = months_range(start, today)
        counter = {"rows": 0}

        def _on(_m, rows) -> None:
            counter["rows"] += save_sales(_m, rows)

        asyncio.run(fetch_sales(months, on_result=_on))
        return f"{counter['rows']} sales rows ({len(months)} months)"

    def _traffic() -> str:
        from steam_agent.collectors.traffic import fetch_traffic
        from steam_agent.storage.raw import save_traffic

        day = _dt.now(_tz.utc).date() - _td(days=1)
        data = asyncio.run(fetch_traffic(appids, day))
        return f"{sum(save_traffic(a, day, r) for a, r in data.items())} traffic rows ({day})"

    step("Marketing", _marketing)
    step("Wishlist", _wishlist)
    step("Players", _players)
    step("Reviews", _reviews)
    step("Playtime", _playtime)
    step("Sales", _sales)
    step("Traffic", _traffic)

    table = Table(title="collect-all — summary")
    table.add_column("Dataset")
    table.add_column("Result")
    for label, res in results:
        table.add_row(label, str(res))
    console.print(table)

    drift = report.drift_events()
    if drift:
        console.print(
            f"[red]SCHEMA DRIFT — {len(drift)} event(s)[/]: Steam may have changed a page "
            "layout. Inspect the artifacts under data/raw/_failures/ :"
        )
        for ev in drift:
            console.print(f"  • {ev}")

    if failures or drift:
        # Exit non-zero so an unattended scheduler (cron/systemd/Task Scheduler) can
        # detect and alert. Drift in particular needs a human — retrying won't help.
        if failures:
            console.print(
                f"[red]{len(failures)}/{len(results)} dataset(s) failed:[/] {', '.join(failures)}"
            )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
