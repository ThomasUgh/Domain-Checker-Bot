# 🔍 Discord Domain Checker Bot

<div align="center">
  
  ![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
  ![Discord.py](https://img.shields.io/badge/discord.py-2.3.0+-blue.svg)
  ![License](https://img.shields.io/badge/license-MIT-green.svg)
  ![Status](https://img.shields.io/badge/status-active-success.svg)
  
  Ein leistungsstarker Discord Bot zur Überwachung von Domain-Verfügbarkeiten mit automatischen Benachrichtigungen
  
</div>

---

## 🚀 Features

### Kern-Funktionen
- **🔍 Domain-Verfügbarkeitsprüfung** - Prüft Domains mit 18+ verschiedenen TLDs
- **📊 Live Status Dashboard** - Echtzeit-Überwachung im Discord Channel
- **🔔 Automatische Alerts** - Sofort-Benachrichtigung bei Priority-Domains
- **📅 Wochenberichte** - Detaillierte Zusammenfassung jeden Sonntag

### Erweiterte Features
- ** Expiry Tracking** - Überwacht Ablaufdaten von Domains
- **Priority System** - Markiere wichtige Domains für sofortige Alerts
- **Multi-TLD Check** - Prüft automatisch alternative Domain-Endungen
- **Watchlist Management** - Verwalte überwachte Domains per Befehl
- **JSON Datenspeicherung** - Persistente Speicherung aller Einstellungen
- **Rolle-Ping System** - Benachrichtige Teams bei wichtigen Änderungen

## 📋 Voraussetzungen

- Python 3.8 oder höher
- Discord Bot Token
- Discord Server mit Admin-Rechten

## 📝 Befehle

### Domain-Prüfung
| Befehl | Beschreibung | Beispiel |
|--------|--------------|----------|
| `!domaincheck <domain>` | Prüft eine Domain und Alternativen | `!domaincheck google` |
| `!dc <domain>` | Kurzform von domaincheck | `!dc example.com` |

### Watchlist-Verwaltung
| Befehl | Beschreibung | Beispiel |
|--------|--------------|----------|
| `!watchlist` | Zeigt alle überwachten Domains | `!watchlist` |
| `!watchlist add <domain> [priority]` | Fügt Domain zur Überwachung hinzu | `!watchlist add example.de true` |
| `!watchlist remove <domain>` | Entfernt Domain aus Überwachung | `!watchlist remove test.com` |

### Berichte & Admin
| Befehl | Beschreibung | Berechtigung |
|--------|--------------|--------------|
| `!report` | Erzwingt Wochenbericht | Administrator |
| `!help` | Zeigt alle Befehle | Alle |

## 🎨 Embed-Farben

- 🟢 Grün (`0x00ff00`) - Domain verfügbar
- 🔴 Rot (`0xff0000`) - Domain besetzt
- 🟡 Gelb (`0xffff00`) - Warnung
- 🔵 Blau (`0x3498db`) - Information
