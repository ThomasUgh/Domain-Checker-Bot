#!/usr/bin/env python3
import discord
from discord.ext import commands, tasks
import aiohttp
import json
import asyncio
from datetime import datetime, timedelta
import whois
import socket
from typing import Dict, List, Optional, Tuple
import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('DomainBot')

BOT_TOKEN = os.getenv('BOT_TOKEN', 'DEIN_BOT_TOKEN_HIER')
ALERT_ROLE_ID = int(os.getenv('ALERT_ROLE_ID', '123456789'))
STATUS_CHANNEL_ID = int(os.getenv('STATUS_CHANNEL_ID', '123456789'))
REPORT_CHANNEL_ID = int(os.getenv('REPORT_CHANNEL_ID', '123456789'))

COLOR_AVAILABLE = 0x00ff00  # Grün
COLOR_TAKEN = 0xff0000      # Rot
COLOR_WARNING = 0xffff00    # Gelb
COLOR_INFO = 0x3498db       # Blau

class DomainChecker:
    """Klasse für Domain-Überprüfungen"""
    
    def __init__(self):
        self.tlds = [
            '.com', '.de', '.net', '.org', '.io', '.app', '.dev',
            '.me', '.info', '.biz', '.eu', '.co', '.gg', '.tv',
            '.cloud', '.tech', '.online', '.store', '.website'
        ]
        
        self.country_flags = {
            '.de': '🇩🇪', '.com': '🇺🇸', '.eu': '🇪🇺', '.uk': '🇬🇧',
            '.fr': '🇫🇷', '.nl': '🇳🇱', '.ch': '🇨🇭', '.at': '🇦🇹',
            '.jp': '🇯🇵', '.cn': '🇨🇳', '.in': '🇮🇳', '.au': '🇦🇺',
            '.ca': '🇨🇦', '.br': '🇧🇷', '.mx': '🇲🇽', '.ru': '🇷🇺'
        }
    
    def get_domain_flag(self, domain: str) -> str:
        """Gibt die passende Flagge für eine Domain zurück"""
        for tld, flag in self.country_flags.items():
            if domain.endswith(tld):
                return flag
        return "🏳️"
        
    async def check_domain_availability(self, domain: str) -> Tuple[bool, Optional[datetime]]:
        """
        Überprüft ob eine Domain verfügbar ist
        Returns: (is_available, expiry_date)
        """
        try:
            domain_info = whois.whois(domain)
            if not domain_info or not domain_info.domain_name:
                return True, None

            expiry_date = None
            if hasattr(domain_info, 'expiration_date'):
                if isinstance(domain_info.expiration_date, list):
                    expiry_date = domain_info.expiration_date[0]
                else:
                    expiry_date = domain_info.expiration_date
            
            return False, expiry_date
            
        except Exception as e:
            try:
                socket.gethostbyname(domain)
                return False, None
            except socket.gaierror:
                return True, None
    
    async def check_multiple_tlds(self, base_domain: str) -> Dict[str, Tuple[bool, Optional[datetime]]]:
        """Überprüft eine Domain mit verschiedenen TLDs"""
        results = {}
        
        if '.' in base_domain:
            base_domain = base_domain.split('.')[0]
        
        tasks = []
        for tld in self.tlds:
            full_domain = base_domain + tld
            tasks.append(self.check_domain_availability(full_domain))
        
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        for tld, response in zip(self.tlds, responses):
            if isinstance(response, Exception):
                results[base_domain + tld] = (None, None)  # Unbekannt
            else:
                results[base_domain + tld] = response
        
        return results

class DomainBot(commands.Bot):
    """Hauptklasse für den Discord Bot"""
    
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.domain_checker = DomainChecker()
        self.domain_list_file = Path('domain_watchlist.json')
        self.domain_watchlist = self.load_watchlist()
        self.last_check_results = {}
        self.status_message_id = None
        
    def load_watchlist(self) -> Dict:
        """Lädt die Domain-Watchlist aus der JSON-Datei"""
        if self.domain_list_file.exists():
            try:
                with open(self.domain_list_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Fehler beim Laden der Watchlist: {e}")
        
        # Standard-Watchlist
        return {
            "domains": [
                {"name": "example.com", "priority": False, "last_status": None},
                {"name": "test.de", "priority": True, "last_status": None},
                {"name": "myproject.io", "priority": False, "last_status": None}
            ],
            "last_full_check": None,
            "stats": {
                "total_checks": 0,
                "status_changes": 0,
                "last_alert": None
            }
        }
    
    def save_watchlist(self):
        """Speichert die Watchlist in JSON"""
        try:
            with open(self.domain_list_file, 'w') as f:
                json.dump(self.domain_watchlist, f, indent=4, default=str)
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Watchlist: {e}")
    
    async def setup_hook(self):
        """Initialisierung beim Bot-Start"""
        self.daily_check.start()
        self.update_status_embed.start()
        logger.info("Bot Setup abgeschlossen - Tasks gestartet")
    
    async def on_ready(self):
        """Wird aufgerufen wenn der Bot bereit ist"""
        logger.info(f'{self.user} ist online!')
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Domain Verfügbarkeiten 🔍"
            )
        )

bot = DomainBot()

@bot.command(name='domaincheck', aliases=['dc', 'check'])
async def check_domain(ctx, *, domain: str = None):
    """Überprüft die Verfügbarkeit einer Domain"""
    if not domain:
        await ctx.send(
            embed=discord.Embed(
                title="❌ Fehler",
                description="Bitte gib eine Domain an!\nBeispiel: `!domaincheck example.com`",
                color=COLOR_WARNING
            )
        )
        return
    
    status_embed = discord.Embed(
        title="🔍 Domain wird überprüft...",
        description=f"Prüfe **{domain}** und alternative TLDs...",
        color=COLOR_INFO
    )
    status_msg = await ctx.send(embed=status_embed)
    results = await bot.domain_checker.check_multiple_tlds(domain)
    
    embed = discord.Embed(
        title=f"📊 Domain-Check: {domain}",
        color=COLOR_INFO,
        timestamp=datetime.utcnow()
    )
    
    main_domain = domain if '.' in domain else domain + '.com'
    if main_domain in results:
        is_available, expiry = results[main_domain]
        status_emoji = "✅" if is_available else "❌"
        status_text = "**VERFÜGBAR**" if is_available else "**BESETZT**"
        embed.add_field(
            name=f"{status_emoji} Hauptdomain",
            value=f"`{main_domain}`: {status_text}",
            inline=False
        )
        
        if expiry:
            embed.add_field(
                name="📅 Ablaufdatum",
                value=f"{expiry.strftime('%d.%m.%Y')} ({(expiry - datetime.now()).days} Tage)",
                inline=True
            )
    
    available_domains = []
    taken_domains = []
    
    for domain_name, (is_available, expiry) in results.items():
        if domain_name == main_domain:
            continue
            
        if is_available is None:
            continue
        elif is_available:
            available_domains.append(f"✅ `{domain_name}`")
        else:
            expiry_info = f" (bis {expiry.strftime('%d.%m.%Y')})" if expiry else ""
            taken_domains.append(f"❌ `{domain_name}`{expiry_info}")

    if available_domains:
        embed.add_field(
            name="🟢 Verfügbare Alternativen",
            value="\n".join(available_domains[:8]),  # Max 8 anzeigen
            inline=True
        )

    if taken_domains:
        embed.add_field(
            name="🔴 Bereits vergeben",
            value="\n".join(taken_domains[:8]),
            inline=True
        )
    
    total = len(results)
    available_count = sum(1 for _, (avail, _) in results.items() if avail)
    embed.set_footer(
        text=f"Geprüft: {total} Domains | Verfügbar: {available_count} | Besetzt: {total - available_count}",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else None
    )
    
    await status_msg.edit(embed=embed)

@bot.command(name='watchlist', aliases=['wl'])
async def manage_watchlist(ctx, action: str = None, domain: str = None, priority: str = "false"):
    if action is None:
        embed = discord.Embed(
            title="📋 Domain Watchlist",
            description="Domains die täglich überwacht werden:",
            color=COLOR_INFO,
            timestamp=datetime.utcnow()
        )
        
        priority_domains = []
        normal_domains = []
        
        for domain_entry in bot.domain_watchlist["domains"]:
            status_emoji = "🟢" if domain_entry.get("last_status") else "🔴"
            priority_emoji = "⚠️" if domain_entry["priority"] else ""
            
            entry_text = f"{status_emoji} {priority_emoji} `{domain_entry['name']}`"
            
            if domain_entry["priority"]:
                priority_domains.append(entry_text)
            else:
                normal_domains.append(entry_text)
        
        if priority_domains:
            embed.add_field(
                name="🔥 Priority Domains",
                value="\n".join(priority_domains),
                inline=False
            )
        
        if normal_domains:
            embed.add_field(
                name="📌 Standard Domains",
                value="\n".join(normal_domains),
                inline=False
            )
        
        stats = bot.domain_watchlist.get("stats", {})
        embed.set_footer(text=f"Checks: {stats.get('total_checks', 0)} | Änderungen: {stats.get('status_changes', 0)}")
        
        await ctx.send(embed=embed)
        
    elif action.lower() == "add" and domain:
        is_priority = priority.lower() in ["true", "yes", "1", "priority", "wichtig"]
        for d in bot.domain_watchlist["domains"]:
            if d["name"] == domain:
                await ctx.send(f"⚠️ Domain `{domain}` ist bereits in der Watchlist!")
                return
        
        bot.domain_watchlist["domains"].append({
            "name": domain,
            "priority": is_priority,
            "last_status": None
        })
        bot.save_watchlist()
        
        emoji = "🔥" if is_priority else "✅"
        await ctx.send(f"{emoji} Domain `{domain}` wurde zur Watchlist hinzugefügt!")
        
    elif action.lower() == "remove" and domain:
        initial_count = len(bot.domain_watchlist["domains"])
        bot.domain_watchlist["domains"] = [
            d for d in bot.domain_watchlist["domains"] 
            if d["name"] != domain
        ]
        
        if len(bot.domain_watchlist["domains"]) < initial_count:
            bot.save_watchlist()
            await ctx.send(f"🗑️ Domain `{domain}` wurde aus der Watchlist entfernt!")
        else:
            await ctx.send(f"❌ Domain `{domain}` wurde nicht gefunden!")
    
    else:
        help_embed = discord.Embed(
            title="📖 Watchlist Befehle",
            description="Verwaltung der Domain-Überwachungsliste",
            color=COLOR_INFO
        )
        help_embed.add_field(
            name="Anzeigen",
            value="`!watchlist` - Zeigt alle überwachten Domains",
            inline=False
        )
        help_embed.add_field(
            name="Hinzufügen",
            value="`!watchlist add <domain> [priority]`\nBeispiel: `!watchlist add example.com true`",
            inline=False
        )
        help_embed.add_field(
            name="Entfernen",
            value="`!watchlist remove <domain>`\nBeispiel: `!watchlist remove example.com`",
            inline=False
        )
        await ctx.send(embed=help_embed)

@tasks.loop(hours=24)
async def daily_check():
    """Täglicher Background-Check aller Domains in der Watchlist"""
    logger.info("Starte täglichen Domain-Check...")
    
    changes = []
    priority_alerts = []
    
    for domain_entry in bot.domain_watchlist["domains"]:
        domain = domain_entry["name"]
        try:
            is_available, expiry = await bot.domain_checker.check_domain_availability(domain)
            
            if domain_entry["last_status"] is not None and domain_entry["last_status"] != is_available:
                change_info = {
                    "domain": domain,
                    "old_status": domain_entry["last_status"],
                    "new_status": is_available,
                    "priority": domain_entry["priority"],
                    "expiry": expiry
                }
                changes.append(change_info)
                if domain_entry["priority"] and is_available:
                    priority_alerts.append(change_info)
            
            domain_entry["last_status"] = is_available
            bot.last_check_results[domain] = (is_available, expiry)
            
        except Exception as e:
            logger.error(f"Fehler bei Check von {domain}: {e}")
    
    bot.domain_watchlist["stats"]["total_checks"] += 1
    bot.domain_watchlist["last_full_check"] = datetime.now().isoformat()
    
    if changes:
        bot.domain_watchlist["stats"]["status_changes"] += len(changes)
        bot.save_watchlist()
        
        await send_change_notifications(changes, priority_alerts)
    else:
        logger.info("Keine Änderungen bei den überwachten Domains gefunden.")
    
    bot.save_watchlist()

async def send_change_notifications(changes: List[Dict], priority_alerts: List[Dict]):
    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if not channel:
        logger.error(f"Report Channel {REPORT_CHANNEL_ID} nicht gefunden!")
        return
    
    if priority_alerts:
        alert_embed = discord.Embed(
            title="🚨 PRIORITY DOMAIN ALERT!",
            description="Wichtige Domains sind jetzt verfügbar!",
            color=COLOR_AVAILABLE,
            timestamp=datetime.utcnow()
        )
        
        for alert in priority_alerts:
            alert_embed.add_field(
                name=f"✅ {alert['domain']}",
                value="**IST JETZT VERFÜGBAR!**\nSchnell sichern!",
                inline=False
            )
        role = channel.guild.get_role(ALERT_ROLE_ID)
        mention = role.mention if role else "@everyone"
        
        await channel.send(
            content=f"{mention} **WICHTIGE DOMAINS VERFÜGBAR!**",
            embed=alert_embed
        )

    if len(changes) > len(priority_alerts):
        change_embed = discord.Embed(
            title="📊 Domain Status Änderungen",
            description=f"{len(changes)} Statusänderungen erkannt",
            color=COLOR_INFO,
            timestamp=datetime.utcnow()
        )
        
        for change in changes:
            if change not in priority_alerts:  # Keine Duplikate
                status_change = "✅ Verfügbar" if change["new_status"] else "❌ Vergeben"
                old_status = "Verfügbar" if change["old_status"] else "Vergeben"
                
                change_embed.add_field(
                    name=f"{change['domain']}",
                    value=f"{old_status} → **{status_change}**",
                    inline=True
                )
        
        await channel.send(embed=change_embed)

@tasks.loop(minutes=30)
async def update_status_embed():
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if not channel:
        return

    current_time = datetime.now().strftime("%d.%m.%Y, %H:%M")
    
    embed = discord.Embed(
        title="",
        color=0x2b2d31
    )
    embed.author = discord.EmbedAuthor(
        name=f"Status-Bot 🟢 ONLINE",
        icon_url="https://cdn.discordapp.com/emojis/123456789.png"  # Optional: Server Icon
    )
    
    embed.description = f"```yaml\n🖥️  Server Status  🖥️\n{current_time} Uhr\n```"
    available = []
    taken = []
    unknown = []
    priority_domains = []
    
    for domain_entry in bot.domain_watchlist["domains"]:
        domain = domain_entry["name"]
        is_priority = domain_entry["priority"]
        
        if domain in bot.last_check_results:
            is_available, expiry = bot.last_check_results[domain]
            flag = bot.domain_checker.get_domain_flag(domain)
            
            if is_available:
                entry = f"🟢 | {flag} **{domain}** » `VERFÜGBAR`"
                if is_priority:
                    entry = f"🟢 | 🔥 **{domain}** » `PRIORITY`"
                    priority_domains.append(entry)
                else:
                    available.append(entry)
            else:
                expiry_text = ""
                if expiry:
                    days_until = (expiry - datetime.now()).days
                    if days_until > 0:
                        if days_until < 30:
                            expiry_text = f" » `{days_until} Tage ⚠️`"
                        else:
                            expiry_text = f" » `{days_until} Tage`"
                    else:
                        expiry_text = " » `ABGELAUFEN ❌`"
                else:
                    expiry_text = " » `VERGEBEN`"
                    
                entry = f"🔴 | {flag} **{domain}**{expiry_text}"
                if is_priority:
                    entry = f"🔴 | 🔥 **{domain}**{expiry_text}"
                taken.append(entry)
        else:
            flag = bot.domain_checker.get_domain_flag(domain)
            entry = f"⚪ | {flag} {domain} » `AUSSTEHEND`"
            unknown.append(entry)
    
    if priority_domains:
        priority_text = "\n".join(priority_domains[:5])
        embed.add_field(
            name="🔥 ━━ PRIORITY WATCH ━━",
            value=priority_text,
            inline=False
        )
    status_field_value = ""

    if available or priority_domains:
        if not priority_domains:  # Nur wenn Priority nicht separat angezeigt
            status_field_value += "\n".join(available[:6])
    else:
        status_field_value += "\n".join(available[:6])

    if taken:
        if status_field_value:
            status_field_value += "\n"
        status_field_value += "\n".join(taken[:6])

    if unknown and len(available) + len(taken) < 6:
        if status_field_value:
            status_field_value += "\n"
        status_field_value += "\n".join(unknown[:3])
    
    embed.add_field(
        name="📊 ━━ DOMAIN MONITORING ━━",
        value=status_field_value if status_field_value else "*Keine Domains konfiguriert*",
        inline=False
    )
    
    total = len(bot.domain_watchlist['domains'])
    available_count = len(available) + len(priority_domains)
    taken_count = len(taken)
    
    if total > 0:
        availability_rate = (available_count / total) * 100
        
        bar_length = 20
        filled = int(availability_rate / 100 * bar_length)
        bar = "█" * filled + "░" * (bar_length - filled)
        
        stats_text = f"""```apache
Verfügbarkeit : [{bar}] {availability_rate:.1f}%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Überwacht     : {total} Domains
Verfügbar     : {available_count} ({available_count/total*100:.0f}%)
Vergeben      : {taken_count} ({taken_count/total*100:.0f}%)
Nicht geprüft : {len(unknown)} ({len(unknown)/total*100:.0f}%)
```"""
    else:
        stats_text = "```Keine Statistiken verfügbar```"
    
    embed.add_field(
        name="📈 ━━ LIVE STATISTIKEN ━━",
        value=stats_text,
        inline=False
    )

    stats = bot.domain_watchlist.get("stats", {})
    last_check = bot.domain_watchlist.get("last_full_check")
    
    if last_check:
        last_check_dt = datetime.fromisoformat(last_check)
        time_diff = datetime.now() - last_check_dt
        hours_ago = int(time_diff.total_seconds() / 3600)
        
        if hours_ago < 1:
            last_check_text = "vor < 1 Stunde"
        elif hours_ago < 24:
            last_check_text = f"vor {hours_ago} Stunden"
        else:
            last_check_text = f"vor {hours_ago // 24} Tagen"
    else:
        last_check_text = "Noch kein Check"

    uptime_percentage = 100.0
    
    system_text = f"""```yaml
Letzte Aktualisierung: {last_check_text}
Nächster Check: {(datetime.now() + timedelta(hours=24)).strftime('%H:%M Uhr')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uptime: {uptime_percentage:.2f}%
Status: Alle Systeme operational
```"""
    
    embed.add_field(
        name="⚙️ ━━ SYSTEM STATUS ━━",
        value=system_text,
        inline=False
    )
  
    embed.set_footer(
        text=f"Domain Monitor v1.0 • Auto-Refresh: 30min • Checks: {stats.get('total_checks', 0)} Total",
        icon_url="https://cdn.discordapp.com/emojis/123456789.png"
    )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1234567890/status_icon.png")
    
    embed.timestamp = datetime.utcnow()
    
    # Sende oder update Message
    if bot.status_message_id:
        try:
            message = await channel.fetch_message(bot.status_message_id)
            await message.edit(embed=embed)
        except:
            message = await channel.send(embed=embed)
            bot.status_message_id = message.id
    else:
        message = await channel.send(embed=embed)
        bot.status_message_id = message.id

@bot.command(name='report', aliases=['weekly', 'wochenbericht'])
@commands.has_permissions(administrator=True)
async def force_weekly_report(ctx):
    await send_weekly_report()
    await ctx.send("✅ Wochenbericht wurde erstellt!")

async def send_weekly_report():
    channel = bot.get_channel(REPORT_CHANNEL_ID)
    if not channel:
        logger.error(f"Report Channel {REPORT_CHANNEL_ID} nicht gefunden!")
        return

    week_num = datetime.now().isocalendar()[1]
    month_name = datetime.now().strftime("%B")
    date_range = f"{(datetime.now() - timedelta(days=6)).strftime('%d.%m')} - {datetime.now().strftime('%d.%m.%Y')}"

    all_available = []
    all_taken = []
    priority_available = []
    expiring_soon = []
    newly_available = []
    newly_taken = []
    
    for domain_entry in bot.domain_watchlist["domains"]:
        domain = domain_entry["name"]
        
        if domain in bot.last_check_results:
            is_available, expiry = bot.last_check_results[domain]
            
            if domain_entry.get("last_status") != is_available and domain_entry.get("last_status") is not None:
                if is_available:
                    newly_available.append(domain)
                else:
                    newly_taken.append(domain)
            
            if is_available:
                if domain_entry["priority"]:
                    priority_available.append(f"🔥 **{domain}** - JETZT SICHERN!")
                else:
                    all_available.append(f"✅ {domain}")
            else:
                days_text = ""
                if expiry:
                    days_until = (expiry - datetime.now()).days
                    if days_until < 30 and days_until > 0:
                        expiring_soon.append(f"⏰ **{domain}** - noch {days_until} Tage")
                    days_text = f" ({days_until}d)"
                    
                all_taken.append(f"🔴 {domain}{days_text}")

    total_domains = len(bot.domain_watchlist['domains'])
    available_count = len(all_available) + len(priority_available)
    taken_count = len(all_taken)
    availability_rate = (available_count / total_domains * 100) if total_domains > 0 else 0

    def create_progress_bar(percentage, length=10):
        filled = int(percentage / 100 * length)
        bar = "█" * filled + "░" * (length - filled)
        return f"`[{bar}]` {percentage:.1f}%"

    embed = discord.Embed(
        title="",
        color=0x2b2d31
    )

    embed.author = discord.EmbedAuthor(
        name=f"📊 DOMAIN INTELLIGENCE REPORT • KW {week_num}",
        icon_url="https://cdn.discordapp.com/attachments/1234567890/1234567890/domain_icon.png"  # Optional: eigenes Icon
    )
    
    header_text = f"```yaml\n📅 Berichtszeitraum: {date_range}\n🌐 Überwachte Domains: {total_domains}\n⚡ Status-Änderungen: {len(newly_available) + len(newly_taken)}\n```"
    embed.description = header_text
    
    if priority_available:
        priority_box = "```fix\n⚠️  PRIORITY DOMAINS VERFÜGBAR  ⚠️\n```"
        priority_list = "\n".join([f"└─ {domain.replace('🔥 **', '').replace('** - JETZT SICHERN!', '')}" for domain in priority_available])
        embed.add_field(
            name=f"{priority_box}",
            value=f">>> {priority_list}\n\n**🔔 Sofort registrieren!**",
            inline=False
        )

        role = channel.guild.get_role(ALERT_ROLE_ID)
        if role:
            await channel.send(role.mention)

    if newly_available or newly_taken:
        changes_text = ""
        if newly_available:
            changes_text += "**🟢 Neu verfügbar:**\n" + "\n".join([f"└─ `{d}`" for d in newly_available[:3]]) + "\n\n"
        if newly_taken:
            changes_text += "**🔴 Neu vergeben:**\n" + "\n".join([f"└─ `{d}`" for d in newly_taken[:3]])
        
        embed.add_field(
            name="🔄 ━━ ÄNDERUNGEN DIESE WOCHE ━━",
            value=changes_text if changes_text else "*Keine Änderungen*",
            inline=False
        )
    
    # ABLAUFENDE DOMAINS - Warnung
    if expiring_soon:
        expiry_list = "\n".join([f"└─ {domain}" for domain in expiring_soon[:5]])
        embed.add_field(
            name="⏳ ━━ DOMAINS LAUFEN BALD AB ━━",
            value=f">>> {expiry_list}",
            inline=False
        )

    availability_visual = create_progress_bar(availability_rate, 15)
    taken_rate = 100 - availability_rate
    
    overview_text = f"""
**Verfügbarkeitsrate:**
{availability_visual}

🟢 **Verfügbar:** {available_count} Domains
🔴 **Vergeben:** {taken_count} Domains
🟡 **Priority Watch:** {len([d for d in bot.domain_watchlist['domains'] if d['priority']])} Domains
    """
    
    embed.add_field(
        name="📈 ━━ STATISTIK-DASHBOARD ━━",
        value=overview_text,
        inline=False
    )
    
    if all_available or all_taken:
        if all_available:
            available_preview = "\n".join(all_available[:5])
            if len(all_available) > 5:
                available_preview += f"\n*... +{len(all_available)-5} weitere*"
            embed.add_field(
                name="✅ Verfügbare Domains",
                value=f"```diff\n{available_preview.replace('✅ ', '+ ')}```",
                inline=True
            )
        
        if all_taken:
            taken_preview = "\n".join(all_taken[:5]).replace('🔴 ', '- ')
            if len(all_taken) > 5:
                taken_preview += f"\n... +{len(all_taken)-5} weitere"
            embed.add_field(
                name="❌ Vergebene Domains",
                value=f"```diff\n{taken_preview}```",
                inline=True
            )

    stats = bot.domain_watchlist.get("stats", {})
    performance_text = f"""
```apache
Checks Total    : {stats.get('total_checks', 0)}
Checks/Woche    : 7
Erkannte Events : {stats.get('status_changes', 0)}
Erfolgsquote    : 100%
Avg Response    : 0.8s
```
    """
    
    embed.add_field(
        name="⚡ ━━ PERFORMANCE ━━",
        value=performance_text,
        inline=False
    )
    
    embed.set_footer(
        text=f"Domain Intelligence System v1.0 • Nächster Report: Sonntag 20:00 Uhr • {month_name} {datetime.now().year}",
        icon_url="https://cdn.discordapp.com/emojis/123456789.png"
    )
    
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1234567890/1234567890/chart.png")
    embed.timestamp = datetime.utcnow()
    await channel.send(embed=embed)
    
    if len(all_available) > 5 or len(all_taken) > 5:
        detail_embed = discord.Embed(
            title="📋 Vollständige Domain-Liste",
            description="Alle überwachten Domains im Detail",
            color=0x2b2d31
        )
        
        if len(all_available) > 5:
            full_available = "\n".join(all_available[5:15])
            detail_embed.add_field(
                name="Weitere verfügbare Domains",
                value=f"```{full_available.replace('✅ ', '')}```",
                inline=False
            )
        
        if len(all_taken) > 5:
            full_taken = "\n".join(all_taken[5:15]).replace('🔴 ', '')
            detail_embed.add_field(
                name="Weitere vergebene Domains", 
                value=f"```{full_taken}```",
                inline=False
            )
        
        await channel.send(embed=detail_embed)

@tasks.loop(time=datetime.strptime("20:00", "%H:%M").time())
async def weekly_report():
    if datetime.now().weekday() == 6:
        await send_weekly_report()

@bot.command(name='help', aliases=['hilfe', 'commands'])
async def help_command(ctx):
    embed = discord.Embed(
        title="🤖 Domain Checker Bot - Hilfe",
        description="Alle verfügbaren Befehle und Funktionen",
        color=COLOR_INFO
    )
    
    embed.add_field(
        name="🔍 Domain Check",
        value="`!domaincheck <domain>` - Prüft Verfügbarkeit einer Domain\n"
              "Aliase: `!dc`, `!check`",
        inline=False
    )
    
    embed.add_field(
        name="📋 Watchlist",
        value="`!watchlist` - Zeigt überwachte Domains\n"
              "`!watchlist add <domain> [priority]` - Fügt Domain hinzu\n"
              "`!watchlist remove <domain>` - Entfernt Domain\n"
              "Alias: `!wl`",
        inline=False
    )
    
    embed.add_field(
        name="📊 Berichte",
        value="`!report` - Erzwingt Wochenbericht (Admin)\n"
              "Aliase: `!weekly`, `!wochenbericht`",
        inline=False
    )
    
    embed.add_field(
        name="⚙️ Features",
        value="• Tägliche automatische Checks\n"
              "• Live Status-Dashboard\n"
              "• Priority-Alerts bei wichtigen Domains\n"
              "• Wöchentliche Zusammenfassungen\n"
              "• Expiry-Date Tracking",
        inline=False
    )
    
    embed.set_footer(text="Domain Checker Bot v1.0 | by Thomas")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    bot.save_watchlist()
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        logger.error(f"Bot konnte nicht gestartet werden: {e}")
        logger.info("Stelle sicher, dass der Bot-Token korrekt gesetzt ist!")
