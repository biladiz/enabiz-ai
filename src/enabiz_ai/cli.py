"""Command-line interface for e-Nabız AI automation.

Usage:
    enabiz-ai setup           # First-time credential + bot configuration
    enabiz-ai sync labs       # Download & parse lab results
    enabiz-ai sync rx         # Download prescriptions
    enabiz-ai sync all        # Full sync
    enabiz-ai parse FILE      # Parse a local PDF
    enabiz-ai query labs      # Query stored lab results
    enabiz-ai export csv      # Export data to CSV
    enabiz-ai status          # Show system status
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from enabiz_ai import __version__
from enabiz_ai.config import AppConfig

console = Console()
app = typer.Typer(
    name="enabiz-ai",
    help="🏥 e-Nabız AI Automation System — Download and analyze your health data locally.",
    no_args_is_help=True,
)

# ── Helpers ────────────────────────────────────────────────────────


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_passphrase() -> str:
    """Prompt for master passphrase."""
    import getpass
    return getpass.getpass("🔑 Master passphrase: ")


def _run_async(coro):
    """Run an async function in the event loop."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(coro)


# ── Commands ───────────────────────────────────────────────────────


@app.command()
def setup():
    """🔧 First-time setup — configure credentials and Telegram bot."""
    config = AppConfig()
    _setup_logging(config.log_level)

    console.print(Panel(
        "[bold green]e-Nabız AI Kurulum Sihirbazı[/bold green]\n"
        f"Versiyon: {__version__}",
        title="🏥 Setup",
        border_style="green",
    ))

    # Step 1: Master passphrase
    console.print("\n[bold]1. Master Şifre[/bold]")
    console.print("Kimlik bilgilerinizi şifrelemek için bir master şifre belirleyin.")
    import getpass
    passphrase = getpass.getpass("  Yeni master şifre: ")
    passphrase_confirm = getpass.getpass("  Şifreyi tekrar girin: ")
    if passphrase != passphrase_confirm:
        console.print("[red]✗ Şifreler eşleşmiyor![/red]")
        raise typer.Exit(1)

    # Step 2: e-Devlet credentials
    console.print("\n[bold]2. e-Devlet Kimlik Bilgileri[/bold]")
    tc_no = typer.prompt("  TC Kimlik No (11 hane)")
    password = getpass.getpass("  e-Devlet Şifre: ")

    # Save credentials
    from enabiz_ai.credentials.manager import CredentialManager
    cred_manager = CredentialManager(config.data_dir)
    try:
        cred_manager.save(tc_no, password, passphrase)
        console.print("[green]  ✓ Kimlik bilgileri şifrelenerek kaydedildi.[/green]")
    except Exception as e:
        console.print(f"[red]  ✗ Kayıt başarısız: {e}[/red]")
        raise typer.Exit(1)

    # Step 3: Telegram bot (optional)
    console.print("\n[bold]3. Telegram Bot (İsteğe bağlı)[/bold]")
    console.print("  2FA kodlarını telefonda almak için bir Telegram botu gerekir.")
    console.print("  @BotFather'dan bot oluşturup token'ı buraya girin.")
    console.print("  (Atlamak için boş bırakın)")

    bot_token = typer.prompt("  Bot Token", default="", show_default=False)
    if bot_token:
        console.print(
            "  [dim]Bot'unuza /start mesajı gönderin, "
            "Chat ID'nizi öğrenin ve aşağıya girin.[/dim]"
        )
        chat_id = typer.prompt("  Chat ID")

        # Save to .env file
        env_path = Path(".env")
        env_lines = []
        if env_path.exists():
            env_lines = env_path.read_text().splitlines()

        # Update or add entries
        env_dict = {}
        for line in env_lines:
            if "=" in line and not line.strip().startswith("#"):
                key, _, val = line.partition("=")
                env_dict[key.strip()] = val.strip()

        env_dict["TELEGRAM_BOT_TOKEN"] = bot_token
        env_dict["TELEGRAM_CHAT_ID"] = chat_id

        with open(env_path, "w", encoding="utf-8") as f:
            for key, val in env_dict.items():
                f.write(f"{key}={val}\n")

        console.print("[green]  ✓ Telegram bot yapılandırıldı.[/green]")
    else:
        console.print("  [dim]Telegram atlandı — konsol 2FA kullanılacak.[/dim]")

    # Summary
    console.print(Panel(
        "[green]✓ Kurulum tamamlandı![/green]\n\n"
        "Şimdi şunları yapabilirsiniz:\n"
        "  [bold]enabiz-ai sync labs[/bold]    — Tahlil sonuçlarını indir\n"
        "  [bold]enabiz-ai sync all[/bold]     — Tüm verileri senkronize et\n"
        "  [bold]enabiz-ai status[/bold]       — Sistem durumunu kontrol et",
        title="🎉 Kurulum Başarılı",
        border_style="green",
    ))


@app.command()
def sync(
    target: str = typer.Argument(
        "all",
        help="What to sync: labs, rx (prescriptions), all",
    ),
):
    """🔄 Sync health data from e-Nabız."""
    config = AppConfig()
    _setup_logging(config.log_level)
    passphrase = _get_passphrase()

    from enabiz_ai.orchestrator import Orchestrator
    orch = Orchestrator(config, master_passphrase=passphrase)

    async def _sync():
        if target == "labs":
            count = await orch.sync_lab_results()
            console.print(f"[green]✓ {count} yeni tahlil raporu kaydedildi.[/green]")
        elif target in ("rx", "prescriptions"):
            count = await orch.sync_prescriptions()
            console.print(f"[green]✓ {count} yeni reçete kaydedildi.[/green]")
        elif target == "all":
            results = await orch.sync_all()
            table = Table(title="Senkronizasyon Sonuçları")
            table.add_column("Kategori", style="cyan")
            table.add_column("Yeni Kayıt", style="green")
            for category, count in results.items():
                status = str(count) if count >= 0 else "❌ Hata"
                table.add_row(category, status)
            console.print(table)
        else:
            console.print(f"[red]Bilinmeyen hedef: {target}[/red]")
            console.print("Geçerli hedefler: labs, rx, all")

    _run_async(_sync())


@app.command()
def parse(
    file: Path = typer.Argument(..., help="Path to a lab result PDF to parse"),
):
    """📄 Parse a local lab result PDF and save to database."""
    config = AppConfig()
    _setup_logging(config.log_level)

    if not file.exists():
        console.print(f"[red]✗ Dosya bulunamadı: {file}[/red]")
        raise typer.Exit(1)

    passphrase = _get_passphrase()
    from enabiz_ai.orchestrator import Orchestrator
    orch = Orchestrator(config, master_passphrase=passphrase)

    async def _parse():
        await orch.parse_local_pdf(file)
        console.print(f"[green]✓ {file.name} başarıyla ayrıştırıldı ve kaydedildi.[/green]")

    _run_async(_parse())


@app.command()
def query(
    data_type: str = typer.Argument("labs", help="Data type: labs, prescriptions"),
    since: str = typer.Option(None, help="Filter from date (YYYY-MM-DD)"),
    search: str = typer.Option(None, "--search", "-s", help="Search term"),
    output_format: str = typer.Option("table", "--format", "-f", help="Output: table, json"),
):
    """🔍 Query stored health data."""
    config = AppConfig()
    _setup_logging(config.log_level)
    passphrase = _get_passphrase()

    from enabiz_ai.orchestrator import Orchestrator
    orch = Orchestrator(config, master_passphrase=passphrase)

    async def _query():
        results = await orch.query_data(
            data_type=data_type,
            since=since,
            search=search,
        )

        if output_format == "json":
            console.print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
        else:
            if not results:
                console.print("[dim]Sonuç bulunamadı.[/dim]")
                return

            table = Table(title=f"📋 {data_type.capitalize()} Sonuçları")

            if data_type == "labs" and results:
                table.add_column("Tarih", style="cyan")
                table.add_column("Rapor ID", style="dim")
                table.add_column("Test Sayısı", style="green")
                table.add_column("Hastane", style="yellow")
                for r in results:
                    date = r.get("date", "")[:10]
                    table.add_row(
                        date,
                        r.get("report_id", ""),
                        str(len(r.get("tests", []))),
                        r.get("hospital", "-"),
                    )
            elif search:
                table.add_column("Kaynak", style="cyan")
                table.add_column("Detay", style="white")
                table.add_column("Tarih", style="dim")
                for r in results:
                    detail = r.get("test_name") or r.get("medication") or ""
                    table.add_row(r.get("source", ""), detail, r.get("date", ""))

            console.print(table)

    _run_async(_query())


@app.command()
def export(
    target: str = typer.Argument("csv", help="Export format: csv"),
    table_name: str = typer.Option("lab_tests", "--table", "-t", help="Table to export"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file path"),
):
    """📤 Export health data to CSV."""
    config = AppConfig()
    _setup_logging(config.log_level)

    if output is None:
        output = Path(f"enabiz_{table_name}_{datetime.now():%Y%m%d}.csv")

    from enabiz_ai.storage.database import HealthDatabase
    db_path = config.data_dir / "health.db"

    async def _export():
        async with HealthDatabase(db_path) as db:
            count = await db.export_csv(table_name, output)
            console.print(f"[green]✓ {count} satır {output} dosyasına aktarıldı.[/green]")

    _run_async(_export())


@app.command()
def status():
    """📊 Show system status and statistics."""
    config = AppConfig()
    _setup_logging(config.log_level)

    console.print(Panel(
        f"[bold]e-Nabız AI Automation System[/bold]\n"
        f"Versiyon: {__version__}",
        title="🏥 Sistem Durumu",
        border_style="blue",
    ))

    # Config status
    config_table = Table(title="⚙️ Yapılandırma")
    config_table.add_column("Ayar", style="cyan")
    config_table.add_column("Değer", style="white")
    config_table.add_row("Veri Dizini", str(config.data_dir))
    config_table.add_row("Ollama URL", config.ollama_base_url)
    config_table.add_row("Ollama Model", config.ollama_model)
    config_table.add_row("Chrome CDP", config.chrome_cdp_url)
    config_table.add_row("Headless", str(config.headless))
    config_table.add_row(
        "Telegram",
        "✅ Yapılandırıldı" if config.telegram_bot_token else "❌ Yapılandırılmadı",
    )

    # Credential status
    from enabiz_ai.credentials.manager import CredentialManager
    cred_mgr = CredentialManager(config.data_dir)
    config_table.add_row(
        "Kimlik Bilgileri",
        "✅ Kayıtlı" if cred_mgr.exists() else "❌ Kayıtlı değil",
    )

    console.print(config_table)

    # Database stats
    db_path = config.data_dir / "health.db"
    if db_path.exists():
        from enabiz_ai.storage.database import HealthDatabase

        async def _get_stats():
            async with HealthDatabase(db_path) as db:
                return await db.get_stats()

        stats = _run_async(_get_stats())

        db_table = Table(title="📊 Veritabanı İstatistikleri")
        db_table.add_column("Tablo", style="cyan")
        db_table.add_column("Kayıt Sayısı", style="green")
        for table, count in stats.items():
            db_table.add_row(table, str(count))
        console.print(db_table)
    else:
        console.print("[dim]Henüz veritabanı oluşturulmadı.[/dim]")

    # File store stats
    from enabiz_ai.storage.file_store import FileStore
    file_store = FileStore(config.data_dir / "data")
    file_stats = file_store.get_stats()

    file_table = Table(title="📁 Dosya Deposu")
    file_table.add_column("Kategori", style="cyan")
    file_table.add_column("Dosya Sayısı", style="green")
    file_table.add_column("Boyut (MB)", style="yellow")
    for category, info in file_stats.items():
        file_table.add_row(category, str(info["count"]), str(info["total_size_mb"]))
    console.print(file_table)

    # Ollama connectivity
    console.print("\n[bold]🤖 Ollama Bağlantısı[/bold]")
    from enabiz_ai.extraction.llm_extractor import LLMExtractor
    extractor = LLMExtractor(
        ollama_base_url=config.ollama_base_url,
        model=config.ollama_model,
    )

    async def _check_ollama():
        return await extractor.is_available()

    try:
        ollama_ok = _run_async(_check_ollama())
        if ollama_ok:
            console.print(f"  [green]✅ Ollama erişilebilir ({config.ollama_base_url})[/green]")
        else:
            console.print(f"  [yellow]⚠️ Ollama erişilemiyor ({config.ollama_base_url})[/yellow]")
    except Exception:
        console.print(f"  [red]❌ Ollama bağlantı hatası ({config.ollama_base_url})[/red]")


@app.command()
def version():
    """Show version information."""
    console.print(f"enabiz-ai v{__version__}")


if __name__ == "__main__":
    app()
