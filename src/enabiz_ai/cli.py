"""Command-line interface for e-Nabız AI multi-profile automation.

Usage:
    enabiz-ai profile list             # List family member profiles
    enabiz-ai profile add anne         # Add a family member with e-Devlet credentials
    enabiz-ai profile login anne       # Launch visible browser to authenticate a member
    enabiz-ai weekly --profile all     # Run weekly sync & report for all family members
    enabiz-ai schedule add anne -d Sunday -t 20:30 # Register weekly task in Task Scheduler
    enabiz-ai status                   # Show system & all profiles status
"""

from __future__ import annotations

import asyncio
import getpass
import json
import logging
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from enabiz_ai import __version__
from enabiz_ai.analysis.rag_engine import RAGEngine
from enabiz_ai.browser.authenticator import authenticate_profile
from enabiz_ai.config import AppConfig
from enabiz_ai.extraction.harvester import ENabizHarvester
from enabiz_ai.extraction.llm_extractor import LLMExtractor
from enabiz_ai.profiles.manager import ProfileManager, InvalidProfileIdError
from enabiz_ai.profiles.models import ProfileInfo
from enabiz_ai.services.pipeline import SyncService
from enabiz_ai.services.scheduler import SchedulerService
from enabiz_ai.storage.database import HealthDatabase

console = Console(force_terminal=True, legacy_windows=False)
app = typer.Typer(
    name="enabiz-ai",
    help="🏥 e-Nabız AI Automation System — Multi-Person Health Records & AI Analysis.",
    no_args_is_help=True,
)

profile_app = typer.Typer(name="profile", help="👥 Manage family profiles (Mom, Dad, Self, etc.)")
schedule_app = typer.Typer(name="schedule", help="⏰ Manage weekly Windows Task Scheduler jobs per person")

app.add_typer(profile_app)
app.add_typer(schedule_app)


# ── Helpers ────────────────────────────────────────────────────────


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def _get_passphrase(prompt_text: str = "🔑 Master passphrase: ") -> str:
    """Prompt for master passphrase."""
    return getpass.getpass(prompt_text)


def _run_async(coro):
    """Run an async function in the event loop."""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(coro)


# ── Profile Commands ───────────────────────────────────────────────


@profile_app.command("list")
def profile_list():
    """📋 List all registered family member profiles."""
    config = AppConfig()
    pm = ProfileManager(config.data_dir)
    profiles = pm.list_profiles()

    if not profiles:
        console.print("[dim]Kayıtlı profil bulunamadı.[/dim]")
        return

    table = Table(title="👥 Kayıtlı Aile Profilleri")
    table.add_column("Profil ID", style="cyan")
    table.add_column("Kişi Adı", style="bold white")
    table.add_column("Yakınlık", style="yellow")
    table.add_column("Kimlik", style="green")
    table.add_column("Oturum (2FA)", style="magenta")
    table.add_column("Tahlil / Ziyaret", style="blue")

    sync_svc = SyncService(config)
    stats_map = _run_async(sync_svc.get_all_profiles_stats(profiles))

    for p in profiles:
        cred_mgr = pm.get_credential_manager(p.id)
        has_cred = "✅ Şifrelendi" if cred_mgr.exists() else "❌ Yok"
        session_file = pm.get_session_path(p.id)
        has_session = "✅ Aktif" if session_file.exists() else "⚠️ Giriş Gerekli"

        s = stats_map.get(p.id, {})
        if s:
            stats_str = f"{s.get('lab_reports', 0)} tahlil, {s.get('visits', 0)} ziyaret"
        else:
            stats_str = "-"

        table.add_row(p.id, p.display_name, p.relation, has_cred, has_session, stats_str)

    console.print(table)


@profile_app.command("add")
def profile_add(
    profile_id: str = typer.Argument(..., help="Profil ID (örn: 'anne', 'baba')"),
    display_name: str = typer.Option(None, "--name", "-n", help="Görünen isim (örn: 'Annem (Ayşe)')"),
    relation: str = typer.Option(None, "--relation", "-r", help="Yakınlık (örn: 'Anne', 'Baba')"),
):
    """➕ Add a new family member profile with their e-Devlet credentials."""
    config = AppConfig()
    pm = ProfileManager(config.data_dir)

    console.print(Panel(
        f"[bold cyan]Yeni Profil Ekleme: {profile_id}[/bold cyan]",
        title="👥 Profil Sihirbazı",
        border_style="cyan",
    ))

    if not display_name:
        display_name = typer.prompt("  Kişi Görünen Adı (örn: Annem)", default=profile_id.capitalize())
    if not relation:
        relation = typer.prompt("  Yakınlık Derecesi (örn: Anne, Baba, Eş)", default="Aile")

    tc_no = typer.prompt("  TC Kimlik No (11 hane)")
    edevlet_pass = getpass.getpass("  e-Devlet Şifresi: ")

    passphrase = _get_passphrase("  Master Şifre (bu bilgileri şifrelemek için): ")

    # Validate and normalize profile ID
    try:
        validated_id = ProfileManager.validate_profile_id(profile_id)
    except InvalidProfileIdError as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)

    # Save profile metadata
    prof = ProfileInfo(
        id=validated_id,
        display_name=display_name,
        relation=relation,
        created_at=datetime.now(),
    )
    pm.save_profile(prof)

    # Save encrypted credentials
    cred_mgr = pm.get_credential_manager(prof.id)
    cred_mgr.save(tc_no, edevlet_pass, passphrase)

    console.print(Panel(
        f"[green]✓ {display_name} ({relation}) profili başarıyla oluşturuldu ve kimlik bilgileri şifrelendi![/green]\n\n"
        f"Şimdi ilk oturum açma ve 2FA onayını gerçekleştirmek için:\n"
        f"  [bold]enabiz-ai profile login {prof.id}[/bold]",
        title="🎉 Başarılı",
        border_style="green",
    ))


@profile_app.command("login")
def profile_login(
    profile_id: str = typer.Argument("default", help="Oturum açılacak profil (örn: 'anne', 'baba')"),
):
    """🔑 Launch browser login & 2FA approval for a family member."""
    config = AppConfig()
    _setup_logging(config.log_level)
    pm = ProfileManager(config.data_dir)
    profile = pm.get_profile(profile_id)
    if not profile:
        console.print(f"[red]✗ Profil bulunamadı: {profile_id}[/red]")
        raise typer.Exit(1)

    passphrase = _get_passphrase()

    console.print(f"[cyan]🚀 {profile.display_name} için e-Devlet giriş penceresi açılıyor...[/cyan]")
    try:
        ok = _run_async(authenticate_profile(
            profile_id=profile_id,
            config=config,
            master_passphrase=passphrase,
            headless=False,
        ))
        if ok:
            console.print(f"[bold green]✓ {profile.display_name} için e-Nabız oturumu başarıyla kaydedildi![/bold green]")
        else:
            console.print(f"[red]✗ Giriş tamamlanamadı.[/red]")
    except Exception as e:
        console.print(f"[red]✗ Hata: {e}[/red]")


@profile_app.command("delete")
def profile_delete(
    profile_id: str = typer.Argument(..., help="Silinecek profil ID"),
    delete_data: bool = typer.Option(False, "--delete-data", help="Tüm veritabanı ve oturum dosyalarını da sil"),
):
    """🗑️ Delete a family member profile."""
    config = AppConfig()
    pm = ProfileManager(config.data_dir)
    try:
        if pm.delete_profile(profile_id, delete_data=delete_data):
            console.print(f"[green]✓ {profile_id} profili silindi.[/green]")
        else:
            console.print(f"[red]✗ Profil bulunamadı: {profile_id}[/red]")
    except Exception as e:
        console.print(f"[red]✗ {e}[/red]")


# ── Schedule Commands ──────────────────────────────────────────────


_VALID_DAYS = {"sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"}
_TIME_PATTERN = re.compile(r'^\d{1,2}:\d{2}$')


@schedule_app.command("add")
def schedule_add(
    profile: str = typer.Option("all", "--profile", "-p", help="Hangi profil için ('all', 'default', 'anne', vb.)"),
    day: str = typer.Option("Sunday", "--day", "-d", help="Haftanın günü (örn: Sunday, Monday)"),
    time_str: str = typer.Option("20:00", "--time", "-t", help="Çalışma saati (örn: 20:00, 20:30)"),
):
    """⏰ Register weekly Windows Task Scheduler job for a person or all members."""
    try:
        success, task_name, msg = SchedulerService.add_schedule(profile, day, time_str)
        if success:
            console.print(Panel(
                f"[bold green]✓ Görev Zamanlayıcıya Başarıyla Kaydedildi![/bold green]\n\n"
                f"Görev Adı: [cyan]{task_name}[/cyan]\n"
                f"Profil: [yellow]{profile}[/yellow]\n"
                f"Zaman: Her [white]{day} saat {time_str}[/white] (Bilgisayar kapalıysa açıldığında çalışır)",
                title="⏰ Haftalık Zamanlama",
                border_style="green",
            ))
        else:
            console.print(f"[red]✗ Görev oluşturulamadı: {msg}[/red]")
            raise typer.Exit(1)
    except (ValueError, InvalidProfileIdError) as e:
        console.print(f"[red]✗ {e}[/red]")
        raise typer.Exit(1)


@schedule_app.command("list")
def schedule_list():
    """📋 List active e-Nabız scheduled tasks in Windows."""
    tasks = SchedulerService.list_schedules()
    if not tasks:
        console.print("[dim]Aktif e-Nabız AI zamanlanmış görevi bulunamadı.[/dim]")
        return

    table = Table(title="⏰ Windows Görev Zamanlayıcı (e-Nabız AI)")
    table.add_column("Görev Adı", style="cyan")
    table.add_column("Durum", style="green")

    for t in tasks:
        table.add_row(t.get("TaskName", ""), t.get("StateText", ""))
    console.print(table)


@schedule_app.command("remove")
def schedule_remove(
    profile: str = typer.Argument(..., help="Kaldırılacak görev profili veya adı (örn: 'anne', 'all', 'ENabizAI_WeeklySync')"),
):
    """🗑️ Remove a scheduled task from Windows Task Scheduler."""
    success, res = SchedulerService.remove_schedule(profile)
    if success:
        console.print(f"[green]✓ Görev kaldırıldı: {res}[/green]")
    else:
        console.print(f"[red]✗ Hata: {res}[/red]")


# ── Core Operations (Multi-Profile Aware) ──────────────────────────


@app.command()
def weekly(
    profile: str = typer.Option("all", "--profile", "-p", help="Hangi profil için ('all', 'default', 'anne', vb.)"),
):
    """📅 Run weekly sync and deliver clinical report to Telegram for family member(s)."""
    config = AppConfig()
    _setup_logging(config.log_level)
    pm = ProfileManager(config.data_dir)
    sync_svc = SyncService(config)

    async def _runner():
        targets = pm.list_profiles() if profile.lower() == "all" else [pm.get_profile(profile)]
        for p in targets:
            if not p:
                console.print(f"[red]✗ Profil bulunamadı: {profile}[/red]")
                raise typer.Exit(1)

            console.print(Panel(
                f"[bold cyan]Kişi: {p.display_name} ({p.relation})[/bold cyan]\n"
                f"Profil ID: {p.id}",
                title="👤 Haftalık İşlem Yapılıyor",
                border_style="cyan",
            ))

            res, report = await sync_svc.run_weekly_pipeline(p)
            console.print(f"[green]✓ Veriler güncellendi: {res}[/green]")
            console.print(Panel(report, title=f"📋 Klinik Rapor: {p.display_name}", border_style="green"))
            console.print(f"[green]✓ [{p.display_name}] haftalık değerlendirmesi tamamlandı![/green]\n")

    _run_async(_runner())


@app.command()
def analyze(
    profile: str = typer.Option("default", "--profile", "-p", help="Profil ID ('default', 'anne', 'all')"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Telegram'a gönder"),
):
    """🧠 Generate RAG clinical evaluation using DGX Spark LLM."""
    config = AppConfig()
    _setup_logging(config.log_level)
    pm = ProfileManager(config.data_dir)
    sync_svc = SyncService(config)

    async def _analyze():
        targets = pm.list_profiles() if profile.lower() == "all" else [pm.get_profile(profile)]
        for p in targets:
            if not p:
                continue
            db_path = pm.get_db_path(p.id)
            if not db_path.exists():
                console.print(f"[yellow]⚠️ {p.display_name} için veritabanı bulunamadı.[/yellow]")
                continue

            console.print(f"[bold cyan]🧠 [{p.display_name}] RAG Klinik Analiz Başlatılıyor...[/bold cyan]")
            report = await sync_svc.run_clinical_analysis(p, notify=notify)
            console.print(Panel(report, title=f"📋 Klinik Rapor: {p.display_name}", border_style="green"))

    _run_async(_analyze())


@app.command()
def sync(
    target: str = typer.Argument("all", help="labs, rx, all"),
    profile: str = typer.Option("default", "--profile", "-p", help="Profil ID ('default', 'anne', vb.)"),
):
    """🔄 Sync health data from e-Nabız for a profile."""
    config = AppConfig()
    _setup_logging(config.log_level)
    pm = ProfileManager(config.data_dir)
    p = pm.get_profile(profile)
    if not p:
        console.print(f"[red]✗ Profil bulunamadı: {profile}[/red]")
        raise typer.Exit(1)

    sync_svc = SyncService(config)

    async def _sync():
        try:
            res = await sync_svc.harvest_profile(p, target=target)
            table = Table(title=f"Senkronizasyon Sonuçları: {p.display_name}")
            table.add_column("Kategori", style="cyan")
            table.add_column("Yeni Kayıt", style="green")
            for cat, cnt in res.items():
                table.add_row(cat, str(cnt))
            console.print(table)
        except Exception as e:
            console.print(f"[yellow]⚠️ Senkronizasyon uyarısı: {e}[/yellow]")

    _run_async(_sync())


@app.command()
def status():
    """📊 Show system status and all registered family profiles."""
    config = AppConfig()
    _setup_logging(config.log_level)

    console.print(Panel(
        f"[bold]e-Nabız AI Multi-Profile Health Automation[/bold]\n"
        f"Versiyon: {__version__}",
        title="🏥 Sistem Durumu",
        border_style="blue",
    ))

    # Config table
    config_table = Table(title="⚙️ Yapılandırma")
    config_table.add_column("Ayar", style="cyan")
    config_table.add_column("Değer", style="white")
    config_table.add_row("Veri Dizini", str(config.data_dir))
    config_table.add_row("Ollama URL", config.ollama_base_url)
    config_table.add_row("Ollama Model", config.ollama_model)
    config_table.add_row("Telegram", "✅ Yapılandırıldı" if config.telegram_bot_token else "❌ Yok")
    console.print(config_table)

    # Profiles table
    pm = ProfileManager(config.data_dir)
    profile_list()

    # Ollama connectivity
    console.print("\n[bold]🤖 Ollama Bağlantısı[/bold]")
    from enabiz_ai.extraction.llm_extractor import LLMExtractor
    extractor = LLMExtractor(
        ollama_base_url=config.ollama_base_url,
        model=config.ollama_model,
    )
    try:
        if _run_async(extractor.is_available()):
            console.print(f"  [green]✅ Ollama erişilebilir ({config.ollama_base_url})[/green]")
        else:
            console.print(f"  [yellow]⚠️ Ollama yanıt vermiyor ({config.ollama_base_url})[/yellow]")
    except Exception:
        console.print(f"  [red]❌ Ollama bağlantı hatası[/red]")


@app.command()
def version():
    """Show version information."""
    console.print(f"enabiz-ai v{__version__}", highlight=False)


if __name__ == "__main__":
    app()
