"""CLI di SteamAgent (typer)."""
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
from steam_agent.settings import CONFIG_DIR, settings
from steam_agent.storage.db import SessionLocal, init_db
from steam_agent.storage.models import GameSnapshot
from steam_agent.storage.raw import build_snapshot, save_raw, save_snapshot

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
)
console = Console()
app = typer.Typer(add_completion=False, help="SteamAgent — raccolta dati Steam developer.")


@app.command("init-db")
def init_db_cmd() -> None:
    """Crea le tabelle del database."""
    init_db()
    console.print(f"[green]DB pronto:[/] {settings.database_url}")


@app.command("collect-public")
def collect_public(
    appid: int = typer.Option(None, help="AppID; default = SMOKE_TEST_APPID"),
) -> None:
    """Raccoglie i dati pubblici per un appid e salva raw + snapshot."""
    app_id = appid or settings.smoke_test_appid
    console.print(f"Raccolta dati pubblici per appid [bold]{app_id}[/]...")
    records = PublicApiCollector(app_id).collect()
    n = save_raw(records)
    snap = build_snapshot(app_id, records)
    save_snapshot(snap)
    console.print(f"[green]OK[/] — {n} payload grezzi salvati.")

    table = Table(title=f"Snapshot appid {app_id}")
    table.add_column("Campo")
    table.add_column("Valore")
    table.add_row("Nome", str(snap.name))
    table.add_row("Giocatori ora", str(snap.current_players))
    table.add_row("Recensioni totali", str(snap.reviews_total))
    table.add_row("Recensioni positive", str(snap.reviews_positive))
    table.add_row("Giudizio", str(snap.review_score_desc))
    table.add_row("Prezzo", str(snap.price))
    console.print(table)


@app.command()
def login(
    headed: bool = typer.Option(False, help="Mostra il browser (consigliato al primo login)."),
) -> None:
    """Effettua/aggiorna la sessione autenticata Steam (TOTP)."""
    from steam_agent.auth.session import ensure_session

    asyncio.run(ensure_session(headless=not headed))
    console.print("[green]Sessione pronta.[/]")


@app.command("collect-games")
def collect_games() -> None:
    """Recupera la lista giochi dal portale partner e la salva in config/games.yaml."""
    from steam_agent.collectors.partner_games import fetch_games

    games = asyncio.run(fetch_games())
    out = CONFIG_DIR / "games.yaml"
    out.write_text(yaml.safe_dump({"games": games}, allow_unicode=True), encoding="utf-8")
    console.print(f"[green]Salvati {len(games)} giochi in[/] {out}")


@app.command()
def show(limit: int = typer.Option(20, help="Numero di snapshot da mostrare.")) -> None:
    """Mostra gli ultimi snapshot salvati."""
    init_db()
    with SessionLocal() as session:
        rows = session.execute(
            select(GameSnapshot).order_by(GameSnapshot.collected_at.desc()).limit(limit)
        ).scalars().all()

    table = Table(title="Ultimi snapshot")
    for col in ("appid", "nome", "giocatori", "rec. tot", "positive", "quando"):
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
    day: str = typer.Option(None, "--day", help="Giorno YYYY-MM-DD (default: ieri UTC)"),
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
) -> None:
    """Scarica il traffico pagina store (per sorgente) di un giorno e lo salva."""
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
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    console.print(f"Raccolta traffico per {len(appids)} app, giorno [bold]{target}[/]...")
    data = asyncio.run(fetch_traffic(appids, target))
    total = sum(save_traffic(aid, target, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} righe traffico da {with_data}/{len(appids)} app per {target}."
    )


@app.command("collect-wishlist")
def collect_wishlist(
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
) -> None:
    """Scarica lo storico wishlist (azioni giornaliere) dal portale partner."""
    from steam_agent.collectors.wishlist import fetch_wishlist
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_wishlist

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    console.print(f"Raccolta wishlist (storico completo) per {len(appids)} app...")
    data = asyncio.run(fetch_wishlist(appids))
    total = sum(save_wishlist(aid, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} giorni-wishlist da {with_data}/{len(appids)} app."
    )


@app.command("collect-sales")
def collect_sales(
    since: str = typer.Option("2018-01", help="Mese iniziale YYYY-MM (default 2018-01)"),
    until: str = typer.Option(None, help="Mese finale YYYY-MM (default: mese corrente)"),
    month: str = typer.Option(None, help="Solo questo mese YYYY-MM"),
    months_opt: str = typer.Option(None, "--months", help="Lista YYYY-MM separati da virgola (gap-fill)"),
) -> None:
    """Scarica le vendite mensili (unita' + ricavi netti, per paese) dal portale."""
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

    console.print(f"Raccolta vendite per {len(months)} mesi...")
    counter = {"rows": 0, "months": 0}

    def _on(m, rows) -> None:
        counter["rows"] += save_sales(m, rows)
        if rows:
            counter["months"] += 1

    asyncio.run(fetch_sales(months, on_result=_on))
    console.print(
        f"[green]OK[/] — {counter['rows']} righe vendite da {counter['months']}/{len(months)} mesi."
    )


@app.command("collect-reviews")
def collect_reviews(
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
    max_reviews: int = typer.Option(2000, "--max", help="Max recensioni per gioco"),
) -> None:
    """Scarica le recensioni (testo + voto) dalla API pubblica, base per il sentiment."""
    from steam_agent.collectors.reviews import fetch_reviews
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_reviews

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    total = 0
    with_data = 0
    for aid in appids:
        rows = fetch_reviews(aid, max_reviews)
        n = save_reviews(rows)
        total += n
        if n:
            with_data += 1
    console.print(f"[green]OK[/] — {total} recensioni da {with_data}/{len(appids)} app.")


@app.command("collect-players")
def collect_players(
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
) -> None:
    """Scarica lo storico players (DAU + picco concorrenti, giornaliero) dal portale."""
    from steam_agent.collectors.players import fetch_players
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_players

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    console.print(f"Raccolta players (storico) per {len(appids)} app...")
    data = asyncio.run(fetch_players(appids))
    total = sum(save_players(aid, rows) for aid, rows in data.items())
    with_data = sum(1 for rows in data.values() if rows)
    console.print(
        f"[green]OK[/] — {total} giorni-players da {with_data}/{len(appids)} app."
    )


@app.command("collect-playtime")
def collect_playtime(
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
) -> None:
    """Scarica lo snapshot lifetime di tempo di gioco (medio/mediano + distribuzione)."""
    from steam_agent.collectors.playtime import fetch_playtime
    from steam_agent.games import load_games
    from steam_agent.storage.raw import save_playtime

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    console.print(f"Raccolta playtime per {len(appids)} app...")
    data = asyncio.run(fetch_playtime(appids))
    n = sum(save_playtime(s) for s in data.values())
    console.print(f"[green]OK[/] — snapshot playtime per {n}/{len(appids)} app.")


@app.command("collect-marketing")
def collect_marketing(
    appid: int = typer.Option(None, help="Solo questo appid (default: tutti i giochi)"),
    preset: str = typer.Option(
        "lifetime", help="Intervallo: lifetime|1year|6months|3months|1month|1week"
    ),
) -> None:
    """Scarica serie Visits/Impressions Over Time + ownership + top-paesi (pagina Marketing)."""
    from steam_agent.collectors.marketing import fetch_marketing
    from steam_agent.games import load_games
    from steam_agent.storage.raw import (
        save_marketing,
        save_marketing_country,
        save_marketing_owners,
    )

    appids = [appid] if appid else [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Nessun appid: esegui prima `collect-games`.[/]")
        raise typer.Exit(1)

    console.print(f"Raccolta marketing ({preset}) per {len(appids)} app...")
    data = asyncio.run(fetch_marketing(appids, preset))
    series = owners_n = country_n = 0
    for aid, res in data.items():
        series += save_marketing(aid, res["daily"])
        owners_n += save_marketing_owners(aid, res["owners"])
        country_n += save_marketing_country(aid, res["countries"])
    with_data = sum(1 for res in data.values() if res["daily"])
    console.print(
        f"[green]OK[/] — {series} righe serie · owners per {owners_n} app · "
        f"{country_n} righe paesi · da {with_data}/{len(appids)} app."
    )


@app.command()
def doctor() -> None:
    """Verifica i prerequisiti (Python, browser, .env, credenziali, sessione, DB, catalogo)."""
    import sys
    from pathlib import Path as _Path

    from steam_agent.games import load_games
    from steam_agent.settings import PROJECT_ROOT

    checks: list[tuple[str, str, str]] = []  # (stato OK|FAIL|WARN, voce, dettaglio)

    py_ok = sys.version_info >= (3, 11)
    checks.append(("OK" if py_ok else "FAIL", "Python >= 3.11",
                   f"{sys.version_info.major}.{sys.version_info.minor}"))

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            exe = p.chromium.executable_path
        ok = bool(exe) and _Path(exe).exists()
        checks.append(("OK" if ok else "FAIL", "Browser Playwright (chromium)",
                       "installato" if ok else "manca -> uv run playwright install chromium"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("FAIL", "Browser Playwright (chromium)", f"errore: {exc}"))

    env_ok = (PROJECT_ROOT / ".env").exists()
    checks.append(("OK" if env_ok else "FAIL", "File .env",
                   "presente" if env_ok else "manca -> copia .env.example o usa `setup`"))

    creds_ok = bool(settings.steam_username and settings.steam_password)
    checks.append(("OK" if creds_ok else "FAIL", "Credenziali bot",
                   "ok" if creds_ok else "STEAM_USERNAME/PASSWORD mancanti"))

    secret = bool(settings.steam_shared_secret.strip())
    checks.append(("OK" if secret else "WARN", "shared_secret (login automatico)",
                   "ok (TOTP)" if secret else "assente -> `login --headed` (manuale)"))

    pid = settings.steam_partner_id
    checks.append(("OK" if pid else "WARN", "STEAM_PARTNER_ID (vendite)",
                   str(pid) if pid else "non impostato -> `setup` lo rileva"))

    sess_ok = settings.storage_state_path.exists()
    checks.append(("OK" if sess_ok else "WARN", "Sessione salvata",
                   "presente" if sess_ok else "assente -> `login` / `setup`"))

    try:
        init_db()
        checks.append(("OK", "Database", settings.database_url))
        n = len(load_games())
        checks.append(("OK" if n else "WARN", "Catalogo giochi",
                       f"{n} giochi" if n else "vuoto -> `collect-games`"))
    except Exception as exc:  # noqa: BLE001
        checks.append(("FAIL", "Database", f"errore: {exc}"))

    colors = {"OK": "green", "FAIL": "red", "WARN": "yellow"}
    table = Table(title="SteamAgent — doctor")
    table.add_column("Stato")
    table.add_column("Voce")
    table.add_column("Dettaglio")
    for stato, voce, det in checks:
        table.add_row(f"[{colors[stato]}]{stato}[/]", voce, det)
    console.print(table)

    fails = [v for s, v, _ in checks if s == "FAIL"]
    if fails:
        console.print(f"[red]Da sistemare:[/] {', '.join(fails)}")
        raise typer.Exit(1)
    console.print("[green]Prerequisiti a posto.[/] Procedi con `setup` (primo avvio) o `collect-all`.")


@app.command()
def setup() -> None:
    """Wizard di primo avvio: .env, login, rilevamento partner, catalogo giochi, DB."""
    from steam_agent.auth.session import ensure_session, fetch_publishers
    from steam_agent.collectors.partner_games import fetch_games
    from steam_agent.envtools import update_env
    from steam_agent.settings import PROJECT_ROOT

    console.print("[bold]SteamAgent — setup[/]\n")
    console.print(
        "Serve un ACCOUNT STEAM DEDICATO al bot (non il tuo personale), invitato nel\n"
        "vostro Steamworks con permesso di sola lettura dei report. Dettagli nel README.\n"
    )

    # 1) credenziali -> .env
    reconfigure = True
    if (PROJECT_ROOT / ".env").exists() and settings.steam_username:
        reconfigure = typer.confirm(
            f"Credenziali già presenti ({settings.steam_username}). Riconfigurare?", default=False
        )
    if reconfigure:
        username = typer.prompt("STEAM_USERNAME (account bot)",
                                default=settings.steam_username or None)
        password = typer.prompt("STEAM_PASSWORD", hide_input=True)
        console.print(
            "\n[dim]shared_secret (base64) = login automatico non presidiato (TOTP).\n"
            "Lascia VUOTO per inserire il codice a mano a ogni login (più semplice per iniziare).[/]"
        )
        secret = typer.prompt("STEAM_SHARED_SECRET (invio per saltare)",
                              default="", hide_input=True, show_default=False)
        anthropic = typer.prompt("ANTHROPIC_API_KEY (opzionale, invio per saltare)",
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
        console.print("[green].env aggiornato.[/]\n")

    # 2) login (headed: gestisce conferma email e codice 2FA manuale)
    console.print("Apro il browser per il login (completa eventuali conferme email/2FA)...\n")
    try:
        asyncio.run(ensure_session(headless=False))
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Login fallito:[/] {exc}")
        raise typer.Exit(1)
    console.print("[green]Login completato.[/]\n")

    # 3) rileva partner_id + nome studio dal portale
    try:
        pubs = asyncio.run(fetch_publishers(headless=True))
    except Exception:  # noqa: BLE001
        pubs = {}
    if not pubs:
        console.print(
            "[yellow]Nessun publisher rilevato.[/] Imposta STEAM_PARTNER_ID a mano "
            "se ti serve per le vendite.\n"
        )
    else:
        if len(pubs) == 1:
            pid_s, name = next(iter(pubs.items()))
        else:
            items = list(pubs.items())
            console.print("Publisher disponibili:")
            for i, (pid_, name_) in enumerate(items, 1):
                console.print(f"  {i}. {name_} (id {pid_})")
            idx = typer.prompt("Scegli il numero", type=int, default=1)
            pid_s, name = items[min(max(idx, 1), len(items)) - 1]
        update_env({"STEAM_PARTNER_ID": str(pid_s), "STUDIO_NAME": name})
        settings.steam_partner_id = int(pid_s)
        settings.studio_name = name
        console.print(f"[green]Partner rilevato:[/] {name} (id {pid_s}).\n")

    # 4) catalogo giochi
    console.print("Scarico la lista giochi dal portale...")
    try:
        games = asyncio.run(fetch_games())
        (CONFIG_DIR / "games.yaml").write_text(
            yaml.safe_dump({"games": games}, allow_unicode=True), encoding="utf-8"
        )
        console.print(f"[green]{len(games)} giochi[/] salvati in config/games.yaml.\n")
    except Exception as exc:  # noqa: BLE001
        console.print(f"[yellow]Lista giochi non scaricata:[/] {exc} (riprova con `collect-games`).\n")

    # 5) DB
    init_db()
    console.print("[bold green]Setup completato![/]\n")
    console.print("Prossimi passi:")
    console.print("  uv run steam-agent collect-all          # scarica tutti i dati")
    console.print("  uv run streamlit run dashboard/app.py   # apri la dashboard")


@app.command("collect-all")
def collect_all(
    sales_since: str = typer.Option(
        None, help="Mese iniziale vendite YYYY-MM (default: ultimi 2 mesi)"
    ),
) -> None:
    """Aggiorna TUTTI i dataset in sequenza (marketing, wishlist, players, recensioni, playtime, vendite, traffico)."""
    from datetime import date as _date
    from datetime import datetime as _dt
    from datetime import timedelta as _td
    from datetime import timezone as _tz

    from steam_agent.games import load_games

    appids = [g["appid"] for g in load_games()]
    if not appids:
        console.print("[yellow]Catalogo vuoto: esegui prima `setup` o `collect-games`.[/]")
        raise typer.Exit(1)

    results: list[tuple[str, str]] = []

    def step(label: str, fn) -> None:
        console.print(f"[bold]→ {label}[/]")
        try:
            results.append((label, fn()))
        except Exception as exc:  # noqa: BLE001
            results.append((label, f"[red]errore: {exc}[/]"))

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
        return f"{s} righe serie · owners {o} · paesi {c}"

    def _wishlist() -> str:
        from steam_agent.collectors.wishlist import fetch_wishlist
        from steam_agent.storage.raw import save_wishlist

        data = asyncio.run(fetch_wishlist(appids))
        return f"{sum(save_wishlist(a, r) for a, r in data.items())} giorni-wishlist"

    def _players() -> str:
        from steam_agent.collectors.players import fetch_players
        from steam_agent.storage.raw import save_players

        data = asyncio.run(fetch_players(appids))
        return f"{sum(save_players(a, r) for a, r in data.items())} giorni-players"

    def _reviews() -> str:
        from steam_agent.collectors.reviews import fetch_reviews
        from steam_agent.storage.raw import save_reviews

        return f"{sum(save_reviews(fetch_reviews(a, 2000)) for a in appids)} recensioni"

    def _playtime() -> str:
        from steam_agent.collectors.playtime import fetch_playtime
        from steam_agent.storage.raw import save_playtime

        data = asyncio.run(fetch_playtime(appids))
        return f"snapshot per {sum(save_playtime(s) for s in data.values())} app"

    def _sales() -> str:
        from steam_agent.collectors.sales import fetch_sales, months_range
        from steam_agent.storage.raw import save_sales

        if not settings.steam_partner_id:
            return "saltato (STEAM_PARTNER_ID non impostato)"
        today = _dt.now(_tz.utc).date().replace(day=1)
        if sales_since:
            y, m = sales_since.split("-")
            start = _date(int(y), int(m), 1)
        else:
            start = (today - _td(days=1)).replace(day=1)  # mese scorso
        months = months_range(start, today)
        counter = {"rows": 0}

        def _on(_m, rows) -> None:
            counter["rows"] += save_sales(_m, rows)

        asyncio.run(fetch_sales(months, on_result=_on))
        return f"{counter['rows']} righe vendite ({len(months)} mesi)"

    def _traffic() -> str:
        from steam_agent.collectors.traffic import fetch_traffic
        from steam_agent.storage.raw import save_traffic

        day = _dt.now(_tz.utc).date() - _td(days=1)
        data = asyncio.run(fetch_traffic(appids, day))
        return f"{sum(save_traffic(a, day, r) for a, r in data.items())} righe traffico ({day})"

    step("Marketing", _marketing)
    step("Wishlist", _wishlist)
    step("Players", _players)
    step("Recensioni", _reviews)
    step("Playtime", _playtime)
    step("Vendite", _sales)
    step("Traffico", _traffic)

    table = Table(title="collect-all — riepilogo")
    table.add_column("Dataset")
    table.add_column("Esito")
    for label, res in results:
        table.add_row(label, str(res))
    console.print(table)


if __name__ == "__main__":
    app()
