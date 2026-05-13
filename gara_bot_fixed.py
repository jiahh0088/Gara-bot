"""
═══════════════════════════════════════════════════════════════════════════════
  G A R A   D I S C O R D   B O T  (FIXED)
  All-in-One Economy, Casino, Clan & Fame System
  Theme: Black/Dark | Brand: GARA
  Prefix: Per-guild configurable (default: .)
  Currency: Gara Coins (GC)
  Single-file deployment for Replit
═══════════════════════════════════════════════════════════════════════════════
"""

import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import asyncio
import sqlite3
import json
import random
import os
import datetime
from datetime import timedelta
from typing import Optional, Dict, List
import aiosqlite
from flask import Flask
from threading import Thread

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION PRESETS (Defaults — never mutated at runtime)
# ═══════════════════════════════════════════════════════════════════════════════

class GaraConfig:
    """Immutable defaults. Per-guild overrides live in DB + bot.guild_settings."""

    # ── Bot Identity ──
    BOT_NAME = "GARA"
    BOT_AVATAR_URL = ""
    EMBED_COLOR = 0x000000
    EMBED_COLOR_ACCENT = 0x1a1a1a
    EMBED_COLOR_SUCCESS = 0x00ff88
    EMBED_COLOR_FAIL = 0xff0044
    EMBED_COLOR_WARN = 0xffaa00

    # ── Command Settings ──
    PREFIX = "."
    CURRENCY_NAME = "Gara Coins"
    CURRENCY_ABBREV = "GC"
    CURRENCY_SYMBOL = "💎"

    # ── Economy Settings ──
    STARTING_BALANCE = 1000
    STARTING_VAULT = 0
    DAILY_REWARD_MIN = 100
    DAILY_REWARD_MAX = 500
    WORK_COOLDOWN_HOURS = 4
    WORK_REWARD_MIN = 50
    WORK_REWARD_MAX = 200
    ROB_CHANCE = 0.4
    ROB_COOLDOWN_HOURS = 2

    # ── Casino Settings ──
    MINES_GRID_SIZE = 9
    MINES_BOMB_COUNT = 3
    SLOTS_EMOJIS = ["💎", "🔥", "👑", "💰", "🎯", "🎲"]
    SLOTS_JACKPOT_MULTIPLIER = 10
    SLOTS_MATCH_MULTIPLIER = 3

    # ── Fame System ──
    FAME_AURA_START = 0
    FAME_IMPACT_START = 1
    BOOST_COOLDOWN_HOURS = 1
    NEG_COOLDOWN_HOURS = 1

    # ── VC Activity Roles ──
    VC_TIER_1_HOURS = 1
    VC_TIER_2_HOURS = 5
    VC_PROTECTED_HOURS = 25
    VC_TIER_X_HOURS = 35
    VC_VIP_HOURS = 55

    VC_TIER_1_REWARD = 10000
    VC_TIER_2_REWARD = 50000
    VC_PROTECTED_REWARD = 0
    VC_TIER_X_REWARD = 1000000
    VC_VIP_REWARD = 5000000

    # ── Clan System ──
    CLAN_INACTIVITY_DAYS = 7
    CLAN_DAILY_PENALTY_PERCENT = 10
    CLAN_GOLD_POOL_DAILY = 100000

    # ── Shop Items ──
    SHOP_ITEMS = {
        "mute": {"name": "🔇 Mute", "price": 1000000, "desc": "Timeout someone for 5 minutes"},
        "pin": {"name": "📌 Pin", "price": 10000, "desc": "Pin one message in the pin channel"},
        "vs1": {"name": "💍 VS1 Ring", "price": 30000, "desc": "Marriage proposal ring - VS1 quality"},
        "vvs": {"name": "💍 VVS Ring", "price": 100000, "desc": "Marriage proposal ring - VVS quality"},
        "flawless": {"name": "💍 Flawless Ring", "price": 500000, "desc": "Marriage proposal ring - Flawless quality"},
    }

    # ── Admin IDs ──
    ADMIN_IDS = []

# ═══════════════════════════════════════════════════════════════════════════════
# DATABASE SETUP
# ═══════════════════════════════════════════════════════════════════════════════

class Database:
    def __init__(self, db_path="gara.db"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER, guild_id INTEGER,
                    balance INTEGER DEFAULT 0, vault INTEGER DEFAULT 0,
                    aura INTEGER DEFAULT 0, impact INTEGER DEFAULT 1,
                    last_work TEXT, last_rob TEXT, last_daily TEXT,
                    last_boost TEXT, last_neg TEXT,
                    vc_hours REAL DEFAULT 0, vc_join_time TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clans (
                    clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE, role_id INTEGER, guild_id INTEGER,
                    gold INTEGER DEFAULT 0, total_messages INTEGER DEFAULT 0,
                    last_active TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS clan_members (
                    user_id INTEGER, clan_id INTEGER,
                    personal_gold INTEGER DEFAULT 0,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, clan_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS daily_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    clan_id INTEGER, date TEXT,
                    message_count INTEGER DEFAULT 0,
                    percentage REAL DEFAULT 0,
                    UNIQUE(clan_id, date)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    user_id INTEGER, item_id TEXT, quantity INTEGER DEFAULT 1,
                    PRIMARY KEY (user_id, item_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS mines_games (
                    user_id INTEGER PRIMARY KEY, bet INTEGER,
                    grid TEXT, revealed TEXT,
                    multiplier REAL DEFAULT 1.0, active INTEGER DEFAULT 1
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    guild_id INTEGER PRIMARY KEY,
                    prefix TEXT DEFAULT '.',
                    currency_name TEXT DEFAULT 'Gara Coins',
                    currency_abbrev TEXT DEFAULT 'GC',
                    log_channel INTEGER DEFAULT 0
                )
            """)
            # Performance indexes
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_guild ON users(guild_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_clan_members_user ON clan_members(user_id)")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_daily_activity_clan_date ON daily_activity(clan_id, date)")
            await db.commit()

    async def get_user(self, user_id: int, guild_id: int = 0):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    await db.execute(
                        "INSERT INTO users (user_id, guild_id, balance, vault) VALUES (?, ?, ?, ?)",
                        (user_id, guild_id, GaraConfig.STARTING_BALANCE, GaraConfig.STARTING_VAULT)
                    )
                    await db.commit()
                    return {
                        "user_id": user_id, "guild_id": guild_id,
                        "balance": GaraConfig.STARTING_BALANCE, "vault": GaraConfig.STARTING_VAULT,
                        "aura": 0, "impact": 1, "vc_hours": 0
                    }
                cols = [desc[0] for desc in cursor.description]
                return dict(zip(cols, row))

    async def update_user(self, user_id: int, guild_id: int, **kwargs):
        async with aiosqlite.connect(self.db_path) as db:
            sets = ", ".join([f"{k} = ?" for k in kwargs])
            vals = list(kwargs.values()) + [user_id, guild_id]
            await db.execute(f"UPDATE users SET {sets} WHERE user_id = ? AND guild_id = ?", vals)
            await db.commit()

    # ── Atomic Economy Operations ──
    async def add_balance(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?",
                (amount, user_id, guild_id)
            )
            await db.commit()

    async def sub_balance(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                (amount, user_id, guild_id, amount)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def move_to_vault(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET balance = balance - ?, vault = vault + ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                (amount, amount, user_id, guild_id, amount)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def move_from_vault(self, user_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE users SET balance = balance + ?, vault = vault - ? WHERE user_id = ? AND guild_id = ? AND vault >= ?",
                (amount, amount, user_id, guild_id, amount)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def transfer_balance(self, from_id: int, to_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                (amount, from_id, guild_id, amount)
            )
            if cursor.rowcount == 0:
                await db.execute("ROLLBACK")
                return False
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?",
                (amount, to_id, guild_id)
            )
            await db.execute("COMMIT")
            return True

    async def battle_transfer(self, winner_id: int, loser_id: int, guild_id: int, amount: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                "UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?",
                (amount, winner_id, guild_id)
            )
            await db.execute(
                "UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id = ? AND guild_id = ?",
                (amount, loser_id, guild_id)
            )
            await db.execute("COMMIT")

    async def rob_balance(self, robber_id: int, target_id: int, guild_id: int, stolen: int, fine: int, success: bool):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            now = datetime.datetime.now().isoformat()
            if success:
                cursor = await db.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ? AND guild_id = ? AND balance >= ?",
                    (stolen, target_id, guild_id, stolen)
                )
                if cursor.rowcount == 0:
                    await db.execute("ROLLBACK")
                    return False
                await db.execute(
                    "UPDATE users SET balance = balance + ?, last_rob = ? WHERE user_id = ? AND guild_id = ?",
                    (stolen, now, robber_id, guild_id)
                )
            else:
                await db.execute(
                    "UPDATE users SET balance = MAX(0, balance - ?), last_rob = ? WHERE user_id = ? AND guild_id = ?",
                    (fine, now, robber_id, guild_id)
                )
            await db.execute("COMMIT")
            return True

    async def boost_user(self, booster_id: int, target_id: int, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.datetime.now().isoformat()
            await db.execute("UPDATE users SET aura = aura + 1 WHERE user_id = ? AND guild_id = ?", (target_id, guild_id))
            await db.execute("UPDATE users SET last_boost = ? WHERE user_id = ? AND guild_id = ?", (now, booster_id, guild_id))
            await db.commit()

    async def neg_user(self, negger_id: int, target_id: int, guild_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            now = datetime.datetime.now().isoformat()
            await db.execute(
                "UPDATE users SET aura = MAX(0, aura - 1) WHERE user_id = ? AND guild_id = ?",
                (target_id, guild_id)
            )
            await db.execute("UPDATE users SET last_neg = ? WHERE user_id = ? AND guild_id = ?", (now, negger_id, guild_id))
            await db.commit()

    async def get_clan(self, clan_id: int = None, name: str = None):
        async with aiosqlite.connect(self.db_path) as db:
            if clan_id:
                async with db.execute("SELECT * FROM clans WHERE clan_id = ?", (clan_id,)) as c:
                    row = await c.fetchone()
            elif name:
                async with db.execute("SELECT * FROM clans WHERE name = ?", (name,)) as c:
                    row = await c.fetchone()
            else:
                return None
            if row:
                cols = [desc[0] for desc in c.description]
                return dict(zip(cols, row))
            return None

    async def get_user_clan(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT c.* FROM clans c
                JOIN clan_members cm ON c.clan_id = cm.clan_id
                WHERE cm.user_id = ?
            """, (user_id,)) as c:
                row = await c.fetchone()
                if row:
                    cols = [desc[0] for desc in c.description]
                    return dict(zip(cols, row))
                return None

    async def get_leaderboard(self, guild_id: int, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT user_id, balance + vault as total FROM users
                WHERE guild_id = ? ORDER BY total DESC LIMIT ?
            """, (guild_id, limit)) as c:
                rows = await c.fetchall()
                return rows

    async def get_fame_leaderboard(self, guild_id: int, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT user_id, aura, impact FROM users
                WHERE guild_id = ? ORDER BY aura DESC, impact DESC LIMIT ?
            """, (guild_id, limit)) as c:
                rows = await c.fetchall()
                return rows

    async def get_clan_leaderboard(self, guild_id: int, limit: int = 10):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT * FROM clans WHERE guild_id = ? ORDER BY gold DESC LIMIT ?
            """, (guild_id, limit)) as c:
                rows = await c.fetchall()
                cols = [desc[0] for desc in c.description]
                return [dict(zip(cols, row)) for row in rows]

# ═══════════════════════════════════════════════════════════════════════════════
# BOT SETUP
# ═══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

async def prefix_callable(bot_obj, message):
    if not message.guild:
        return GaraConfig.PREFIX
    settings = bot_obj.guild_settings.get(message.guild.id)
    return settings.get("prefix", GaraConfig.PREFIX) if settings else GaraConfig.PREFIX

bot = commands.Bot(command_prefix=prefix_callable, intents=intents, help_command=None)
bot.guild_settings = {}
bot._command_cooldowns = {}
bot.leaderboard_messages = {}
bot.lockcycles = {}
db = Database()

def get_currency_name(guild_id):
    settings = bot.guild_settings.get(guild_id)
    return settings.get("currency_name", GaraConfig.CURRENCY_NAME) if settings else GaraConfig.CURRENCY_NAME

def get_currency_abbrev(guild_id):
    settings = bot.guild_settings.get(guild_id)
    return settings.get("currency_abbrev", GaraConfig.CURRENCY_ABBREV) if settings else GaraConfig.CURRENCY_ABBREV

# ═══════════════════════════════════════════════════════════════════════════════
# EMBED BUILDER (Black Theme)
# ═══════════════════════════════════════════════════════════════════════════════

def gara_embed(title: str = None, description: str = None, color: int = None, 
               thumbnail: str = None, footer: str = None, guild_id: int = None):
    embed = discord.Embed(
        title=f"**{title}**" if title else None,
        description=description,
        color=color or GaraConfig.EMBED_COLOR
    )
    embed.set_author(name=GaraConfig.BOT_NAME, icon_url=GaraConfig.BOT_AVATAR_URL or None)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)
    c_name = get_currency_name(guild_id) if guild_id else GaraConfig.CURRENCY_NAME
    c_abbrev = get_currency_abbrev(guild_id) if guild_id else GaraConfig.CURRENCY_ABBREV
    if footer:
        embed.set_footer(text=footer, icon_url=GaraConfig.BOT_AVATAR_URL or None)
    else:
        embed.set_footer(text=f"{GaraConfig.BOT_NAME} • {c_name} ({c_abbrev})", 
                        icon_url=GaraConfig.BOT_AVATAR_URL or None)
    return embed

# ═══════════════════════════════════════════════════════════════════════════════
# EVENTS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    await db.init()
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute("SELECT guild_id, prefix, currency_name, currency_abbrev, log_channel FROM server_settings") as c:
            rows = await c.fetchall()
            for row in rows:
                bot.guild_settings[row[0]] = {
                    "prefix": row[1],
                    "currency_name": row[2],
                    "currency_abbrev": row[3],
                    "log_channel": row[4]
                }
    print(f"═══════════════════════════════════════")
    print(f"  {GaraConfig.BOT_NAME} is online!")
    print(f"  Logged in as: {bot.user}")
    print(f"  Prefix: {GaraConfig.PREFIX}")
    print(f"  Currency: {GaraConfig.CURRENCY_NAME} ({GaraConfig.CURRENCY_ABBREV})")
    print(f"  Loaded {len(bot.guild_settings)} guild settings")
    print(f"═══════════════════════════════════════")
    daily_reset.start()
    vc_payout.start()
    update_leaderboards.start()
    lockcycle_task.start()


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild:
        clan = await db.get_user_clan(message.author.id)
        if clan:
            async with aiosqlite.connect(db.db_path) as conn:
                today = datetime.date.today().isoformat()
                await conn.execute("""
                    INSERT INTO daily_activity (clan_id, date, message_count)
                    VALUES (?, ?, 1)
                    ON CONFLICT(clan_id, date) DO UPDATE SET message_count = message_count + 1
                """, (clan["clan_id"], today))
                await conn.commit()
    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    user = await db.get_user(member.id, member.guild.id)
    if before.channel is None and after.channel is not None:
        await db.update_user(member.id, member.guild.id, 
                           vc_join_time=datetime.datetime.now().isoformat())
    elif before.channel is not None and after.channel is None:
        join_time = user.get("vc_join_time")
        if join_time:
            try:
                joined = datetime.datetime.fromisoformat(join_time)
                duration = (datetime.datetime.now() - joined).total_seconds() / 3600
                new_hours = user.get("vc_hours", 0) + duration
                await db.update_user(member.id, member.guild.id, vc_hours=new_hours, vc_join_time=None)
                await check_vc_roles(member, new_hours)
            except:
                pass


async def check_vc_roles(member, hours):
    guild = member.guild
    roles_config = [
        (GaraConfig.VC_TIER_1_HOURS, "Tier 1", GaraConfig.VC_TIER_1_REWARD),
        (GaraConfig.VC_TIER_2_HOURS, "Tier 2", GaraConfig.VC_TIER_2_REWARD),
        (GaraConfig.VC_PROTECTED_HOURS, "Protected", GaraConfig.VC_PROTECTED_REWARD),
        (GaraConfig.VC_TIER_X_HOURS, "Tier X", GaraConfig.VC_TIER_X_REWARD),
        (GaraConfig.VC_VIP_HOURS, "VIP", GaraConfig.VC_VIP_REWARD),
    ]
    for req_hours, role_name, reward in roles_config:
        if hours >= req_hours:
            role = discord.utils.get(guild.roles, name=role_name)
            if role and role not in member.roles:
                await member.add_roles(role)
                if reward > 0:
                    await db.add_balance(member.id, guild.id, reward)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏰ Slow down! Try again in {error.retry_after:.1f}s.", delete_after=5)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"❌ Missing argument: `{error.param.name}`", delete_after=10)
    elif isinstance(error, commands.BadArgument):
        await ctx.reply("❌ Invalid argument provided.", delete_after=10)
    elif isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ You don't have permission to use this command.", delete_after=10)
    else:
        print(f"Unhandled error: {error}")
        await ctx.reply("❌ An unexpected error occurred.", delete_after=10)


# ═══════════════════════════════════════════════════════════════════════════════
# GLOBAL RATE LIMIT (1 second per user)
# ═══════════════════════════════════════════════════════════════════════════════

@bot.check
async def global_rate_limit(ctx):
    now = datetime.datetime.now().timestamp()
    key = ctx.author.id
    last = bot._command_cooldowns.get(key, 0)
    if now - last < 1.0:
        raise commands.CommandOnCooldown(commands.Cooldown(1, 1.0), 1.0 - (now - last), commands.BucketType.user)
    bot._command_cooldowns[key] = now
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# LOOPS
# ═══════════════════════════════════════════════════════════════════════════════

@tasks.loop(hours=24)
async def daily_reset():
    await asyncio.sleep(5)
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute("""
            SELECT c.clan_id, c.guild_id, COALESCE(SUM(da.message_count), 0) as msgs
            FROM clans c
            LEFT JOIN daily_activity da ON c.clan_id = da.clan_id AND da.date = ?
            GROUP BY c.clan_id
        """, (today,)) as c:
            clan_data = await c.fetchall()
        total_msgs = sum(d[2] for d in clan_data)
        if total_msgs == 0:
            return
        for clan_id, guild_id, msgs in clan_data:
            pct = (msgs / total_msgs) * 100
            gold_earned = int(GaraConfig.CLAN_GOLD_POOL_DAILY * (pct / 100))
            await conn.execute(
                "UPDATE clans SET gold = gold + ?, last_active = ? WHERE clan_id = ?",
                (gold_earned, today, clan_id)
            )
            await conn.execute(
                "UPDATE daily_activity SET percentage = ? WHERE clan_id = ? AND date = ?",
                (pct, clan_id, today)
            )
        async with conn.execute("""
            SELECT clan_id FROM daily_activity
            WHERE date = ? ORDER BY percentage ASC, message_count ASC LIMIT 1
        """, (today,)) as c:
            lowest = await c.fetchone()
            if lowest:
                penalty = int(GaraConfig.CLAN_GOLD_POOL_DAILY * (GaraConfig.CLAN_DAILY_PENALTY_PERCENT / 100))
                await conn.execute(
                    "UPDATE clans SET gold = MAX(0, gold - ?) WHERE clan_id = ?",
                    (penalty, lowest[0])
                )
        await conn.commit()


@tasks.loop(minutes=1)
async def vc_payout():
    for guild in bot.guilds:
        for member in guild.members:
            if (member.voice and member.voice.channel and 
                not member.voice.afk and not member.voice.deaf and not member.voice.self_deaf):
                await db.add_balance(member.id, guild.id, 10)


@tasks.loop(minutes=1)
async def update_leaderboards():
    for channel_id, view in list(bot.leaderboard_messages.items()):
        if not view.message:
            continue
        try:
            embed = await view.get_embed()
            await view.message.edit(embed=embed, view=view)
        except discord.NotFound:
            bot.leaderboard_messages.pop(channel_id, None)
        except Exception as e:
            print(f"Leaderboard update error: {e}")


@tasks.loop(minutes=1)
async def lockcycle_task():
    now = datetime.datetime.now()
    for channel_id, config in list(bot.lockcycles.items()):
        guild = bot.get_guild(config["guild_id"])
        if not guild:
            continue
        channel = guild.get_channel(channel_id)
        if not channel:
            continue
        open_h, open_m = config["open"]
        close_h, close_m = config["close"]
        today_str = now.strftime("%Y-%m-%d")
        # Lock
        if now.hour == close_h and now.minute == close_m:
            if config.get("last_lock_date") != today_str:
                try:
                    await channel.set_permissions(guild.default_role, send_messages=False)
                    config["last_lock_date"] = today_str
                    config.pop("last_unlock_date", None)
                except discord.Forbidden:
                    pass
        # Unlock
        if now.hour == open_h and now.minute == open_m:
            if config.get("last_unlock_date") != today_str:
                try:
                    await channel.set_permissions(guild.default_role, send_messages=True)
                    config["last_unlock_date"] = today_str
                    config.pop("last_lock_date", None)
                except discord.Forbidden:
                    pass


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def is_admin(ctx):
    return (ctx.author.id in GaraConfig.ADMIN_IDS or 
            ctx.author.guild_permissions.manage_guild or
            ctx.author.guild_permissions.administrator)


# ═══════════════════════════════════════════════════════════════════════════════
# UI VIEWS
# ═══════════════════════════════════════════════════════════════════════════════

class HelpView(View):
    def __init__(self, ctx):
        super().__init__(timeout=120)
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("❌ This isn't your help menu!", ephemeral=True)
            return False
        return True

    def main_embed(self):
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(
            title=f"Welcome to {GaraConfig.BOT_NAME}!",
            description="Select a category below to view commands.",
            color=GaraConfig.EMBED_COLOR_ACCENT,
            guild_id=self.ctx.guild.id if self.ctx.guild else None
        )
        embed.add_field(name="🎮 Player", value="Earn coins & fame", inline=True)
        embed.add_field(name="💰 Economy", value="Manage your balance", inline=True)
        embed.add_field(name="🎰 Casino", value="Try your luck", inline=True)
        embed.add_field(name="⚔️ Clans", value="Compete with groups", inline=True)
        embed.set_footer(text=f"Use {prefix}help with buttons below • {GaraConfig.BOT_NAME}")
        return embed

    @discord.ui.button(label="Player", emoji="🎮", style=discord.ButtonStyle.blurple, row=0)
    async def player_btn(self, interaction: discord.Interaction, button: Button):
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(title="🎮 Player Commands", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=self.ctx.guild.id if self.ctx.guild else None)
        embed.add_field(name="Commands", value=(
            f"• `{prefix}work` — Work to gain coins (4h cooldown)\n"
            f"• `{prefix}daily` — Claim daily reward\n"
            f"• `{prefix}shop` — Buy perks & items\n"
            f"• `{prefix}fame <user>` — Check someone's Fame\n"
            f"• `{prefix}famous` — Most famous people\n"
            f"• `{prefix}boost <user>` — Boost a friend's aura\n"
            f"• `{prefix}neg <user>` — Neg an enemy's aura"
        ), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Economy", emoji="💰", style=discord.ButtonStyle.green, row=0)
    async def economy_btn(self, interaction: discord.Interaction, button: Button):
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(title="💰 Economy Commands", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=self.ctx.guild.id if self.ctx.guild else None)
        embed.add_field(name="Commands", value=(
            f"• `{prefix}balance` — View your total balance\n"
            f"• `{prefix}deposit <amount>` — Deposit coins into vault\n"
            f"• `{prefix}withdraw <amount>` — Withdraw coins from vault\n"
            f"• `{prefix}give <user> <amount>` — Give coins to another user\n"
            f"• `{prefix}leaderboard` — Live-updating rich list\n"
            f"• `{prefix}rob <user>` — Rob another user (risky!)\n"
            f"• `{prefix}battle <user>` — Duel against friends"
        ), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Casino", emoji="🎰", style=discord.ButtonStyle.red, row=0)
    async def casino_btn(self, interaction: discord.Interaction, button: Button):
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(title="🎰 Casino Commands", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=self.ctx.guild.id if self.ctx.guild else None)
        embed.add_field(name="Commands", value=(
            f"• `{prefix}slots <bet>` — Spin the slots\n"
            f"• `{prefix}mines start <bet>` — Start a mines game\n"
            f"• `{prefix}mines pick <1-9>` — Pick a tile\n"
            f"• `{prefix}mines cashout` — Cash out your winnings\n"
            f"• `{prefix}mines all` — Auto-reveal all (risky!)"
        ), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Clans", emoji="⚔️", style=discord.ButtonStyle.gray, row=0)
    async def clans_btn(self, interaction: discord.Interaction, button: Button):
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(title="⚔️ Clan Commands", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=self.ctx.guild.id if self.ctx.guild else None)
        embed.add_field(name="Commands", value=(
            f"• `{prefix}clans` — View clan leaderboard\n"
            f"• `{prefix}clanstats` — Today's activity per clan\n"
            f"• `{prefix}mygold` — Your personal and clan gold\n"
            f"• `{prefix}joinclan <name>` — Join a clan\n"
            f"• `{prefix}leaveclan` — Leave your clan"
        ), inline=False)
        embed.add_field(name="Admin", value=(
            f"• `{prefix}createclan <name> <@role>` — Create clan\n"
            f"• `{prefix}givemoney <user> <amount>` — Give GC"
        ), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Admin", emoji="🔧", style=discord.ButtonStyle.danger, row=0)
    async def admin_btn(self, interaction: discord.Interaction, button: Button):
        if not is_admin(self.ctx):
            return await interaction.response.send_message("❌ Admin only!", ephemeral=True)
        prefix = get_prefix_for_guild(self.ctx.guild.id) if self.ctx.guild else GaraConfig.PREFIX
        embed = gara_embed(title="🔧 Admin Commands", color=GaraConfig.EMBED_COLOR_WARN, guild_id=self.ctx.guild.id if self.ctx.guild else None)
        embed.add_field(name="Commands", value=(
            f"• `{prefix}givemoney <user> <amount>` — Give GC to user\n"
            f"• `{prefix}takemoney <user> <amount>` — Remove GC from user\n"
            f"• `{prefix}setprefix <new>` — Change command prefix\n"
            f"• `{prefix}setcurrency <name> <abbrev>` — Change currency\n"
            f"• `{prefix}createclan <name> <@role>` — Create a clan\n"
            f"• `{prefix}lockcycle <open> <close> [channel]` — Auto lock/unlock"
        ), inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Back", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back_btn(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(embed=self.main_embed(), view=self)


class LeaderboardView(View):
    def __init__(self, ctx, mode="users"):
        super().__init__(timeout=None)
        self.ctx = ctx
        self.mode = mode
        self.message = None

    async def get_embed(self):
        gid = self.ctx.guild.id
        abbrev = get_currency_abbrev(gid)
        if self.mode == "users":
            rows = await db.get_leaderboard(gid, 10)
            embed = gara_embed(title="🏆 Richest Users", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=gid)
            desc = ""
            medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for i, (uid, total) in enumerate(rows):
                user = self.ctx.guild.get_member(uid)
                name = user.display_name if user else f"User {uid}"
                desc += f"{medals[i]} **{name}** — {total:,} {abbrev}\n"
            embed.description = desc or "No users found yet!"
        else:
            clans = await db.get_clan_leaderboard(gid, 10)
            embed = gara_embed(title="⚔️ Clan Leaderboard", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=gid)
            desc = ""
            for i, clan in enumerate(clans):
                desc += f"**{i+1}. {clan['name']}** — {clan['gold']:,} {abbrev}\n"
            embed.description = desc or "No clans yet!"
        return embed

    @discord.ui.button(label="Users", style=discord.ButtonStyle.blurple)
    async def users_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "users"
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Clans", style=discord.ButtonStyle.green)
    async def clans_btn(self, interaction: discord.Interaction, button: Button):
        self.mode = "clans"
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)


def get_prefix_for_guild(guild_id):
    settings = bot.guild_settings.get(guild_id)
    return settings.get("prefix", GaraConfig.PREFIX) if settings else GaraConfig.PREFIX


# ═══════════════════════════════════════════════════════════════════════════════
# ECONOMY COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="balance", aliases=["bal", "money", "gc"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def balance_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    user = await db.get_user(target.id, ctx.guild.id)
    embed = gara_embed(
        title=f"{target.display_name}'s Balance",
        color=GaraConfig.EMBED_COLOR_ACCENT,
        guild_id=ctx.guild.id
    )
    abbrev = get_currency_abbrev(ctx.guild.id)
    embed.add_field(name=f"{GaraConfig.CURRENCY_SYMBOL} {get_currency_name(ctx.guild.id)}", 
                   value=f"**{user['balance']:,}**", inline=True)
    embed.add_field(name="🏦 Vault", value=f"**{user['vault']:,}**", inline=True)
    embed.add_field(name="💰 Total", value=f"**{user['balance'] + user['vault']:,}**", inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.reply(embed=embed)


@bot.command(name="deposit", aliases=["dep"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def deposit_cmd(ctx, amount: str):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    if amount.lower() == "all":
        amt = user["balance"]
    else:
        try:
            amt = int(amount.replace(",", ""))
        except:
            return await ctx.reply("❌ Invalid amount!")
    if amt <= 0:
        return await ctx.reply("❌ Amount must be positive!")
    success = await db.move_to_vault(ctx.author.id, ctx.guild.id, amt)
    if not success:
        return await ctx.reply("❌ You don't have enough coins!")
    embed = gara_embed(
        title="Deposited",
        description=f"Deposited **{amt:,}** {get_currency_abbrev(ctx.guild.id)}.",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="withdraw", aliases=["with"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def withdraw_cmd(ctx, amount: str):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    if amount.lower() == "all":
        amt = user["vault"]
    else:
        try:
            amt = int(amount.replace(",", ""))
        except:
            return await ctx.reply("❌ Invalid amount!")
    if amt <= 0:
        return await ctx.reply("❌ Amount must be positive!")
    success = await db.move_from_vault(ctx.author.id, ctx.guild.id, amt)
    if not success:
        return await ctx.reply("❌ You don't have enough in your vault!")
    embed = gara_embed(
        title="Withdrew",
        description=f"Withdrew **{amt:,}** {get_currency_abbrev(ctx.guild.id)}.",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="give", aliases=["pay", "send"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def give_cmd(ctx, member: discord.Member, amount: int):
    if member.bot or member.id == ctx.author.id:
        return await ctx.reply("❌ You can't give coins to that user!")
    if amount <= 0:
        return await ctx.reply("❌ Amount must be positive!")
    success = await db.transfer_balance(ctx.author.id, member.id, ctx.guild.id, amount)
    if not success:
        return await ctx.reply("❌ You don't have enough coins!")
    embed = gara_embed(
        title="Transfer Complete",
        description=f"You gave **{amount:,}** {get_currency_abbrev(ctx.guild.id)} to {member.mention}!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="leaderboard", aliases=["lb", "rich", "top"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def leaderboard_cmd(ctx):
    view = LeaderboardView(ctx, mode="users")
    embed = await view.get_embed()

    existing = bot.leaderboard_messages.get(ctx.channel.id)
    if existing:
        try:
            await existing.message.edit(embed=embed, view=view)
            view.message = existing.message
            bot.leaderboard_messages[ctx.channel.id] = view
            return
        except discord.NotFound:
            pass

    msg = await ctx.send(embed=embed, view=view)
    view.message = msg
    bot.leaderboard_messages[ctx.channel.id] = view


@bot.command(name="rob")
@commands.cooldown(1, 1, commands.BucketType.user)
async def rob_cmd(ctx, member: discord.Member):
    if member.bot or member.id == ctx.author.id:
        return await ctx.reply("❌ Can't rob that user!")
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    target = await db.get_user(member.id, ctx.guild.id)
    last_rob = user.get("last_rob")
    if last_rob:
        last = datetime.datetime.fromisoformat(last_rob)
        if datetime.datetime.now() - last < timedelta(hours=GaraConfig.ROB_COOLDOWN_HOURS):
            remaining = timedelta(hours=GaraConfig.ROB_COOLDOWN_HOURS) - (datetime.datetime.now() - last)
            return await ctx.reply(f"⏰ Wait {remaining.seconds // 60} more minutes!")
    if target["balance"] < 100:
        return await ctx.reply("❌ They're too broke to rob!")
    success = random.random() < GaraConfig.ROB_CHANCE
    if success:
        stolen = random.randint(int(target["balance"] * 0.1), int(target["balance"] * 0.3))
        ok = await db.rob_balance(ctx.author.id, member.id, ctx.guild.id, stolen, 0, True)
        if not ok:
            return await ctx.reply("❌ Their balance changed! Try again.")
        embed = gara_embed(
            title="🦹 Robbery Successful!",
            description=f"You stole **{stolen:,}** {get_currency_abbrev(ctx.guild.id)} from {member.mention}!",
            color=GaraConfig.EMBED_COLOR_SUCCESS,
            guild_id=ctx.guild.id
        )
    else:
        fine = random.randint(50, min(500, user["balance"]))
        await db.rob_balance(ctx.author.id, member.id, ctx.guild.id, 0, fine, False)
        embed = gara_embed(
            title="🚔 Caught!",
            description=f"You got caught and paid a **{fine:,}** {get_currency_abbrev(ctx.guild.id)} fine!",
            color=GaraConfig.EMBED_COLOR_FAIL,
            guild_id=ctx.guild.id
        )
    await ctx.reply(embed=embed)


@bot.command(name="work")
@commands.cooldown(1, 1, commands.BucketType.user)
async def work_cmd(ctx):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    last_work = user.get("last_work")
    if last_work:
        last = datetime.datetime.fromisoformat(last_work)
        if datetime.datetime.now() - last < timedelta(hours=GaraConfig.WORK_COOLDOWN_HOURS):
            remaining = timedelta(hours=GaraConfig.WORK_COOLDOWN_HOURS) - (datetime.datetime.now() - last)
            return await ctx.reply(f"⏰ You can work again in {remaining.seconds // 60} minutes!")
    jobs = [
        "delivered packages", "mined crypto", "traded stocks", "streamed games",
        "fixed bugs", "designed logos", "wrote code", "hacked the mainframe"
    ]
    earned = random.randint(GaraConfig.WORK_REWARD_MIN, GaraConfig.WORK_REWARD_MAX)
    await db.add_balance(ctx.author.id, ctx.guild.id, earned)
    await db.update_user(ctx.author.id, ctx.guild.id, last_work=datetime.datetime.now().isoformat())
    embed = gara_embed(
        title="💼 Work Complete",
        description=f"You {random.choice(jobs)} and earned **{earned:,}** {get_currency_abbrev(ctx.guild.id)}!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="daily")
@commands.cooldown(1, 1, commands.BucketType.user)
async def daily_cmd(ctx):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    last_daily = user.get("last_daily")
    if last_daily:
        last = datetime.datetime.fromisoformat(last_daily)
        if datetime.datetime.now() - last < timedelta(days=1):
            remaining = timedelta(days=1) - (datetime.datetime.now() - last)
            return await ctx.reply(f"⏰ Come back in {remaining.seconds // 3600} hours!")
    reward = random.randint(GaraConfig.DAILY_REWARD_MIN, GaraConfig.DAILY_REWARD_MAX)
    await db.add_balance(ctx.author.id, ctx.guild.id, reward)
    await db.update_user(ctx.author.id, ctx.guild.id, last_daily=datetime.datetime.now().isoformat())
    embed = gara_embed(
        title="🎁 Daily Reward",
        description=f"You claimed **{reward:,}** {get_currency_abbrev(ctx.guild.id)}!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="givemoney", aliases=["addmoney", "givegc"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def givemoney_cmd(ctx, member: discord.Member, amount: int):
    if not is_admin(ctx):
        return await ctx.reply("❌ You don't have permission!")
    if amount <= 0:
        return await ctx.reply("❌ Amount must be positive!")
    await db.add_balance(member.id, ctx.guild.id, amount)
    embed = gara_embed(
        title="💰 Admin Transfer",
        description=f"Gave **{amount:,}** {get_currency_abbrev(ctx.guild.id)} to {member.mention}!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="takemoney", aliases=["removemoney", "rmgc"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def takemoney_cmd(ctx, member: discord.Member, amount: int):
    if not is_admin(ctx):
        return await ctx.reply("❌ You don't have permission!")
    await db.sub_balance(member.id, ctx.guild.id, amount)
    embed = gara_embed(
        title="💸 Admin Deduction",
        description=f"Took **{amount:,}** {get_currency_abbrev(ctx.guild.id)} from {member.mention}!",
        color=GaraConfig.EMBED_COLOR_WARN,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="setprefix")
@commands.cooldown(1, 1, commands.BucketType.user)
async def setprefix_cmd(ctx, new_prefix: str):
    if not is_admin(ctx):
        return await ctx.reply("❌ You don't have permission!")
    if len(new_prefix) > 5:
        return await ctx.reply("❌ Prefix too long! Max 5 characters.")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            """INSERT INTO server_settings (guild_id, prefix) VALUES (?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET prefix = ?""",
            (ctx.guild.id, new_prefix, new_prefix)
        )
        await conn.commit()
    bot.guild_settings.setdefault(ctx.guild.id, {})
    bot.guild_settings[ctx.guild.id]["prefix"] = new_prefix
    embed = gara_embed(
        title="⚙️ Prefix Updated",
        description=f"New prefix: `{new_prefix}`",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="setcurrency")
@commands.cooldown(1, 1, commands.BucketType.user)
async def setcurrency_cmd(ctx, name: str, abbrev: str):
    if not is_admin(ctx):
        return await ctx.reply("❌ You don't have permission!")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            """INSERT INTO server_settings (guild_id, currency_name, currency_abbrev)
               VALUES (?, ?, ?)
               ON CONFLICT(guild_id) DO UPDATE SET currency_name = ?, currency_abbrev = ?""",
            (ctx.guild.id, name, abbrev, name, abbrev)
        )
        await conn.commit()
    bot.guild_settings.setdefault(ctx.guild.id, {})
    bot.guild_settings[ctx.guild.id]["currency_name"] = name
    bot.guild_settings[ctx.guild.id]["currency_abbrev"] = abbrev
    embed = gara_embed(
        title="⚙️ Currency Updated",
        description=f"Currency: **{name}** ({abbrev})",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# CASINO COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="slots")
@commands.cooldown(1, 1, commands.BucketType.user)
async def slots_cmd(ctx, bet: int):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    if bet <= 0 or bet > user["balance"]:
        return await ctx.reply("❌ Invalid bet or not enough coins!")
    emojis = GaraConfig.SLOTS_EMOJIS
    result = [random.choice(emojis) for _ in range(3)]
    winnings = 0
    if result[0] == result[1] == result[2]:
        winnings = bet * GaraConfig.SLOTS_JACKPOT_MULTIPLIER
        title = "🎰 JACKPOT!"
        color = GaraConfig.EMBED_COLOR_SUCCESS
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        winnings = bet * GaraConfig.SLOTS_MATCH_MULTIPLIER
        title = "🎰 Winner!"
        color = GaraConfig.EMBED_COLOR_SUCCESS
    else:
        winnings = -bet
        title = "🎰 No luck..."
        color = GaraConfig.EMBED_COLOR_FAIL
    await db.add_balance(ctx.author.id, ctx.guild.id, winnings)
    new_bal = user["balance"] + winnings
    embed = gara_embed(
        title=title,
        description=f"**{' | '.join(result)}**\n\n",
        color=color,
        guild_id=ctx.guild.id
    )
    abbrev = get_currency_abbrev(ctx.guild.id)
    embed.add_field(name="Bet", value=f"{bet:,}", inline=True)
    embed.add_field(name="Result", value=f"{winnings:+,} {abbrev}", inline=True)
    embed.add_field(name="Balance", value=f"{new_bal:,}", inline=True)
    await ctx.reply(embed=embed)


@bot.command(name="mines")
@commands.cooldown(1, 1, commands.BucketType.user)
async def mines_cmd(ctx, action: str = "start", *args):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    if action.lower() == "start":
        if not args:
            return await ctx.reply("Usage: `.mines start <bet>`")
        try:
            bet = int(args[0].replace(",", ""))
        except:
            return await ctx.reply("❌ Invalid bet!")
        if bet <= 0 or bet > user["balance"]:
            return await ctx.reply("❌ Invalid bet!")
        grid = ["💎"] * 6 + ["💣"] * 3
        random.shuffle(grid)
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO mines_games (user_id, bet, grid, revealed, multiplier, active)
                 VALUES (?, ?, ?, ?, ?, ?)",
                (ctx.author.id, bet, json.dumps(grid), json.dumps([]), 1.0, 1)
            )
            await conn.commit()
        await db.sub_balance(ctx.author.id, ctx.guild.id, bet)
        embed = gara_embed(
            title="💣 Mines — Game Started",
            description=f"Bet: **{bet:,}** {get_currency_abbrev(ctx.guild.id)}\nPick a tile: `.mines pick <1-9>`",
            color=GaraConfig.EMBED_COLOR_ACCENT,
            guild_id=ctx.guild.id
        )
        grid_display = ""
        for i in range(9):
            if i % 3 == 0 and i > 0:
                grid_display += "\n"
            grid_display += f"`[{i+1}]` "
        embed.add_field(name="Grid", value=grid_display, inline=False)
        await ctx.reply(embed=embed)

    elif action.lower() == "pick":
        if not args:
            return await ctx.reply("Usage: `.mines pick <1-9>`")
        try:
            pick = int(args[0]) - 1
        except:
            return await ctx.reply("❌ Pick a number 1-9!")
        if pick < 0 or pick > 8:
            return await ctx.reply("❌ Pick 1-9!")
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT * FROM mines_games WHERE user_id = ? AND active = 1", (ctx.author.id,)
            ) as c:
                game = await c.fetchone()
            if not game:
                return await ctx.reply("❌ No active game! Start with `.mines start <bet>`")
            grid = json.loads(game[2])
            revealed = json.loads(game[3])
            bet = game[1]
            multiplier = game[4]
            if pick in revealed:
                return await ctx.reply("❌ Already picked!")
            revealed.append(pick)
            if grid[pick] == "💣":
                await conn.execute("DELETE FROM mines_games WHERE user_id = ?", (ctx.author.id,))
                await conn.commit()
                embed = gara_embed(
                    title="💣 Mines — Bomb Hit",
                    description=f"You hit a bomb and lost **{bet:,}** {get_currency_abbrev(ctx.guild.id)}.",
                    color=GaraConfig.EMBED_COLOR_FAIL,
                    guild_id=ctx.guild.id
                )
                grid_display = ""
                for i in range(9):
                    if i % 3 == 0 and i > 0:
                        grid_display += "\n"
                    grid_display += f"{grid[i]} "
                embed.add_field(name="Grid", value=grid_display, inline=False)
                await ctx.reply(embed=embed)
            else:
                new_mult = multiplier * 1.2
                await conn.execute(
                    "UPDATE mines_games SET revealed = ?, multiplier = ? WHERE user_id = ?",
                    (json.dumps(revealed), new_mult, ctx.author.id)
                )
                await conn.commit()
                potential = int(bet * new_mult)
                embed = gara_embed(
                    title="💎 Safe!",
                    description=f"Multiplier: **{new_mult:.2f}x**\nPotential win: **{potential:,}** {get_currency_abbrev(ctx.guild.id)}",
                    color=GaraConfig.EMBED_COLOR_SUCCESS,
                    guild_id=ctx.guild.id
                )
                grid_display = ""
                for i in range(9):
                    if i % 3 == 0 and i > 0:
                        grid_display += "\n"
                    if i in revealed:
                        grid_display += f"💎 "
                    else:
                        grid_display += f"`[{i+1}]` "
                embed.add_field(name="Grid", value=grid_display, inline=False)
                embed.add_field(name="Options", value="`.mines pick <#>` or `.mines cashout`", inline=False)
                await ctx.reply(embed=embed)

    elif action.lower() == "cashout":
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT * FROM mines_games WHERE user_id = ? AND active = 1", (ctx.author.id,)
            ) as c:
                game = await c.fetchone()
            if not game:
                return await ctx.reply("❌ No active game!")
            bet = game[1]
            multiplier = game[4]
            winnings = int(bet * multiplier)
            await conn.execute("DELETE FROM mines_games WHERE user_id = ?", (ctx.author.id,))
            await conn.commit()
        await db.add_balance(ctx.author.id, ctx.guild.id, winnings)
        embed = gara_embed(
            title="💰 Cashed Out!",
            description=f"Bet: **{bet:,}** | Multiplier: **{multiplier:.2f}x**\nPaid: **{winnings:,}** {get_currency_abbrev(ctx.guild.id)}!",
            color=GaraConfig.EMBED_COLOR_SUCCESS,
            guild_id=ctx.guild.id
        )
        await ctx.reply(embed=embed)

    elif action.lower() == "all":
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT * FROM mines_games WHERE user_id = ? AND active = 1", (ctx.author.id,)
            ) as c:
                game = await c.fetchone()
            if not game:
                return await ctx.reply("❌ No active game!")
            grid = json.loads(game[2])
            bet = game[1]
            if grid[0] == "💣":
                await conn.execute("DELETE FROM mines_games WHERE user_id = ?", (ctx.author.id,))
                await conn.commit()
                embed = gara_embed(
                    title="💣 Mines — Bomb Hit",
                    description=f"You hit a bomb and lost **{bet:,}** {get_currency_abbrev(ctx.guild.id)}.",
                    color=GaraConfig.EMBED_COLOR_FAIL,
                    guild_id=ctx.guild.id
                )
                grid_display = ""
                for i in range(9):
                    if i % 3 == 0 and i > 0:
                        grid_display += "\n"
                    grid_display += f"{grid[i]} "
                embed.add_field(name="Grid", value=grid_display, inline=False)
                await ctx.reply(embed=embed)
            else:
                safe_tiles = [i for i, x in enumerate(grid) if x == "💎"]
                mult = 1.0
                for _ in safe_tiles:
                    mult *= 1.2
                winnings = int(bet * mult)
                await conn.execute("DELETE FROM mines_games WHERE user_id = ?", (ctx.author.id,))
                await conn.commit()
                await db.add_balance(ctx.author.id, ctx.guild.id, winnings)
                embed = gara_embed(
                    title="💎 Mines — Washed Out",
                    description=f"Bet: **{bet:,}** | Multiplier: **{mult:.2f}x**\nPaid: **{winnings:,}** {get_currency_abbrev(ctx.guild.id)}!",
                    color=GaraConfig.EMBED_COLOR_SUCCESS,
                    guild_id=ctx.guild.id
                )
                grid_display = ""
                for i in range(9):
                    if i % 3 == 0 and i > 0:
                        grid_display += "\n"
                    grid_display += f"{grid[i]} "
                embed.add_field(name="Grid", value=grid_display, inline=False)
                await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# FAME SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="fame")
@commands.cooldown(1, 1, commands.BucketType.user)
async def fame_cmd(ctx, member: discord.Member = None):
    target = member or ctx.author
    user = await db.get_user(target.id, ctx.guild.id)
    embed = gara_embed(
        title=f"{target.display_name}'s Profile",
        color=GaraConfig.EMBED_COLOR_ACCENT,
        guild_id=ctx.guild.id
    )
    embed.add_field(name="❄️ Aura", value=f"**{user['aura']}**", inline=True)
    embed.add_field(name="⚡ Impact", value=f"**{user['impact']}**", inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    msg = await ctx.reply(embed=embed)
    await msg.add_reaction("⬆️")
    await msg.add_reaction("⬇️")


@bot.command(name="boost")
@commands.cooldown(1, 1, commands.BucketType.user)
async def boost_cmd(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        return await ctx.reply("❌ You can't boost yourself!")
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    last_boost = user.get("last_boost")
    if last_boost:
        last = datetime.datetime.fromisoformat(last_boost)
        if datetime.datetime.now() - last < timedelta(hours=GaraConfig.BOOST_COOLDOWN_HOURS):
            remaining = timedelta(hours=GaraConfig.BOOST_COOLDOWN_HOURS) - (datetime.datetime.now() - last)
            return await ctx.reply(f"⏰ Wait {remaining.seconds // 60} more minutes!")
    target = await db.get_user(member.id, ctx.guild.id)
    await db.boost_user(ctx.author.id, member.id, ctx.guild.id)
    embed = gara_embed(
        title="⬆️ Boosted!",
        description=f"You boosted {member.mention}'s aura! They now have **{target['aura'] + 1}** aura.",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="neg")
@commands.cooldown(1, 1, commands.BucketType.user)
async def neg_cmd(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        return await ctx.reply("❌ You can't neg yourself!")
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    last_neg = user.get("last_neg")
    if last_neg:
        last = datetime.datetime.fromisoformat(last_neg)
        if datetime.datetime.now() - last < timedelta(hours=GaraConfig.NEG_COOLDOWN_HOURS):
            remaining = timedelta(hours=GaraConfig.NEG_COOLDOWN_HOURS) - (datetime.datetime.now() - last)
            return await ctx.reply(f"⏰ Wait {remaining.seconds // 60} more minutes!")
    target = await db.get_user(member.id, ctx.guild.id)
    new_aura = max(0, target["aura"] - 1)
    await db.neg_user(ctx.author.id, member.id, ctx.guild.id)
    embed = gara_embed(
        title="⬇️ Negged!",
        description=f"You negged {member.mention}! Their aura is now **{new_aura}**.",
        color=GaraConfig.EMBED_COLOR_FAIL,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="famous")
@commands.cooldown(1, 1, commands.BucketType.user)
async def famous_cmd(ctx):
    rows = await db.get_fame_leaderboard(ctx.guild.id, 10)
    embed = gara_embed(title="🌟 Most Famous", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=ctx.guild.id)
    desc = ""
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, (uid, aura, impact) in enumerate(rows):
        user = ctx.guild.get_member(uid)
        name = user.display_name if user else f"User {uid}"
        desc += f"{medals[i]} **{name}** — ❄️ {aura} | ⚡ {impact}\n"
    embed.description = desc or "No famous people yet!"
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# SHOP COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="shop", aliases=["store"])
@commands.cooldown(1, 1, commands.BucketType.user)
async def shop_cmd(ctx):
    prefix = get_prefix_for_guild(ctx.guild.id)
    embed = gara_embed(
        title="🛒 Shop",
        description=f"Spend your {get_currency_name(ctx.guild.id)} on fun perks below.\nUse `{prefix}buy <item>` to purchase.",
        color=GaraConfig.EMBED_COLOR_ACCENT,
        guild_id=ctx.guild.id
    )
    for item_id, item in GaraConfig.SHOP_ITEMS.items():
        embed.add_field(
            name=f"{item['name']}",
            value=f"{item['desc']}\n**{item['price']:,}** {get_currency_abbrev(ctx.guild.id)} • `{prefix}buy {item_id}`",
            inline=False
        )
    embed.set_footer(text=f"Earn coins by spending time in VC or gambling. • {GaraConfig.BOT_NAME}")
    await ctx.reply(embed=embed)


@bot.command(name="buy")
@commands.cooldown(1, 1, commands.BucketType.user)
async def buy_cmd(ctx, item_id: str, target: discord.Member = None):
    item = GaraConfig.SHOP_ITEMS.get(item_id.lower())
    if not item:
        return await ctx.reply(f"❌ Item not found! Check `{get_prefix_for_guild(ctx.guild.id)}shop`")
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    price = item["price"]
    if item_id.lower() == "mute":
        total = user["balance"] + user["vault"]
        if total > price:
            price = int(total * 0.1)
    success = await db.sub_balance(ctx.author.id, ctx.guild.id, price)
    if not success:
        return await ctx.reply("❌ You don't have enough coins!")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            """INSERT INTO inventory (user_id, item_id, quantity)
               VALUES (?, ?, 1)
               ON CONFLICT(user_id, item_id) DO UPDATE SET quantity = quantity + 1""",
            (ctx.author.id, item_id.lower())
        )
        await conn.commit()
    if item_id.lower() == "mute" and target:
        try:
            await target.timeout(timedelta(minutes=5), reason=f"Bought by {ctx.author.display_name}")
            effect = f"{target.mention} has been muted for 5 minutes!"
        except:
            effect = "Couldn't mute user (missing permissions). Item saved."
    else:
        effect = f"You bought **{item['name']}**!"
    embed = gara_embed(
        title="🛒 Purchase Complete",
        description=f"{effect}\nCost: **{price:,}** {get_currency_abbrev(ctx.guild.id)}",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# CLAN SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="clans")
@commands.cooldown(1, 1, commands.BucketType.user)
async def clans_cmd(ctx):
    clans = await db.get_clan_leaderboard(ctx.guild.id, 10)
    embed = gara_embed(title="⚔️ Clan Leaderboard", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=ctx.guild.id)
    if not clans:
        embed.description = "No clans yet! Admins can create them."
    else:
        desc = ""
        for i, clan in enumerate(clans):
            desc += f"**{i+1}. {clan['name']}** — {clan['gold']:,} {get_currency_abbrev(ctx.guild.id)}\n"
        embed.description = desc
    await ctx.reply(embed=embed)


@bot.command(name="clanstats")
@commands.cooldown(1, 1, commands.BucketType.user)
async def clanstats_cmd(ctx):
    today = datetime.date.today().isoformat()
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute("""
            SELECT c.name, COALESCE(da.message_count, 0) as msgs, COALESCE(da.percentage, 0) as pct
            FROM clans c
            LEFT JOIN daily_activity da ON c.clan_id = da.clan_id AND da.date = ?
            WHERE c.guild_id = ?
            ORDER BY msgs DESC
        """, (today, ctx.guild.id)) as c:
            rows = await c.fetchall()
    embed = gara_embed(title="📊 Today's Clan Activity", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=ctx.guild.id)
    desc = ""
    for name, msgs, pct in rows:
        desc += f"**{name}** — {msgs} msgs ({pct:.1f}%)\n"
    embed.description = desc or "No activity today!"
    await ctx.reply(embed=embed)


@bot.command(name="mygold")
@commands.cooldown(1, 1, commands.BucketType.user)
async def mygold_cmd(ctx):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    clan = await db.get_user_clan(ctx.author.id)
    embed = gara_embed(title="💰 Your Gold", color=GaraConfig.EMBED_COLOR_ACCENT, guild_id=ctx.guild.id)
    embed.add_field(name="Personal", value=f"**{user['balance']:,}** {get_currency_abbrev(ctx.guild.id)}", inline=True)
    if clan:
        async with aiosqlite.connect(db.db_path) as conn:
            async with conn.execute(
                "SELECT personal_gold FROM clan_members WHERE user_id = ? AND clan_id = ?",
                (ctx.author.id, clan["clan_id"])
            ) as c:
                row = await c.fetchone()
                personal_clan_gold = row[0] if row else 0
        embed.add_field(name=f"Clan: {clan['name']}", value=f"**{clan['gold']:,}** {get_currency_abbrev(ctx.guild.id)}", inline=True)
        embed.add_field(name="Your Clan Share", value=f"**{personal_clan_gold:,}**", inline=True)
    else:
        embed.add_field(name="Clan", value="Not in a clan!", inline=True)
    await ctx.reply(embed=embed)


@bot.command(name="createclan")
@commands.cooldown(1, 1, commands.BucketType.user)
async def createclan_cmd(ctx, name: str, role: discord.Role):
    if not is_admin(ctx):
        return await ctx.reply("❌ Admin only!")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO clans (name, role_id, guild_id, last_active) VALUES (?, ?, ?, ?)",
            (name, role.id, ctx.guild.id, datetime.date.today().isoformat())
        )
        await conn.commit()
    embed = gara_embed(
        title="⚔️ Clan Created",
        description=f"Clan **{name}** has been created!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="joinclan")
@commands.cooldown(1, 1, commands.BucketType.user)
async def joinclan_cmd(ctx, clan_name: str):
    clan = await db.get_clan(name=clan_name)
    if not clan:
        return await ctx.reply("❌ Clan not found!")
    existing = await db.get_user_clan(ctx.author.id)
    if existing:
        return await ctx.reply(f"❌ Leave your current clan first! ({existing['name']})")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "INSERT INTO clan_members (user_id, clan_id, personal_gold) VALUES (?, ?, 0)",
            (ctx.author.id, clan["clan_id"])
        )
        await conn.commit()
    role = ctx.guild.get_role(clan["role_id"])
    if role:
        await ctx.author.add_roles(role)
    embed = gara_embed(
        title="⚔️ Clan Joined",
        description=f"You joined **{clan_name}**!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


@bot.command(name="leaveclan")
@commands.cooldown(1, 1, commands.BucketType.user)
async def leaveclan_cmd(ctx):
    clan = await db.get_user_clan(ctx.author.id)
    if not clan:
        return await ctx.reply("❌ You're not in a clan!")
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "DELETE FROM clan_members WHERE user_id = ? AND clan_id = ?",
            (ctx.author.id, clan["clan_id"])
        )
        await conn.commit()
    role = ctx.guild.get_role(clan["role_id"])
    if role:
        await ctx.author.remove_roles(role)
    embed = gara_embed(
        title="⚔️ Clan Left",
        description=f"You left **{clan['name']}**.",
        color=GaraConfig.EMBED_COLOR_WARN,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# HELP SYSTEM (with sub-pages)
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="help")
@commands.cooldown(1, 1, commands.BucketType.user)
async def help_cmd(ctx):
    view = HelpView(ctx)
    embed = view.main_embed()
    await ctx.reply(embed=embed, view=view)


# ═══════════════════════════════════════════════════════════════════════════════
# BATTLE COMMAND
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="battle")
@commands.cooldown(1, 1, commands.BucketType.user)
async def battle_cmd(ctx, opponent: discord.Member):
    if opponent.bot or opponent.id == ctx.author.id:
        return await ctx.reply("❌ Can't battle that user!")
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    opp = await db.get_user(opponent.id, ctx.guild.id)
    user_power = user["balance"] + user["aura"] * 1000 + random.randint(1, 1000)
    opp_power = opp["balance"] + opp["aura"] * 1000 + random.randint(1, 1000)
    bet = min(user["balance"] // 10, opp["balance"] // 10, 10000)
    if user_power > opp_power:
        winner = ctx.author
        loser = opponent
        await db.battle_transfer(ctx.author.id, opponent.id, ctx.guild.id, bet)
        color = GaraConfig.EMBED_COLOR_SUCCESS
    elif opp_power > user_power:
        winner = opponent
        loser = ctx.author
        await db.battle_transfer(opponent.id, ctx.author.id, ctx.guild.id, bet)
        color = GaraConfig.EMBED_COLOR_FAIL
    else:
        winner = None
        color = GaraConfig.EMBED_COLOR_WARN
        bet = 0
    embed = gara_embed(
        title="⚔️ Battle Result",
        color=color,
        guild_id=ctx.guild.id
    )
    if winner:
        embed.description = f"**{winner.mention}** defeated {loser.mention}!\n**{bet:,}** {get_currency_abbrev(ctx.guild.id)} transferred!"
    else:
        embed.description = "It's a **draw**! No coins lost."
    embed.add_field(name=ctx.author.display_name, value=f"Power: {user_power:,}", inline=True)
    embed.add_field(name=opponent.display_name, value=f"Power: {opp_power:,}", inline=True)
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# VC STATS COMMAND
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="stats")
@commands.cooldown(1, 1, commands.BucketType.user)
async def stats_cmd(ctx):
    user = await db.get_user(ctx.author.id, ctx.guild.id)
    hours = user.get("vc_hours", 0)
    embed = gara_embed(
        title="📊 Your Activity Stats",
        color=GaraConfig.EMBED_COLOR_ACCENT,
        guild_id=ctx.guild.id
    )
    embed.add_field(name="VC Hours", value=f"**{hours:.1f}h**", inline=True)
    tiers = [
        (GaraConfig.VC_TIER_1_HOURS, "Tier 1"),
        (GaraConfig.VC_TIER_2_HOURS, "Tier 2"),
        (GaraConfig.VC_PROTECTED_HOURS, "Protected"),
        (GaraConfig.VC_TIER_X_HOURS, "Tier X"),
        (GaraConfig.VC_VIP_HOURS, "VIP"),
    ]
    next_tier = None
    for req, name in tiers:
        if hours < req:
            next_tier = (req, name)
            break
    if next_tier:
        embed.add_field(name="Next Tier", value=f"**{next_tier[1]}** in {next_tier[0] - hours:.1f}h", inline=True)
    else:
        embed.add_field(name="Status", value="**MAX TIER REACHED** 🏆", inline=True)
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# SPIN COMMAND (Monthly Nitro Prize)
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="spin")
@commands.cooldown(1, 1, commands.BucketType.user)
async def spin_cmd(ctx):
    if not is_admin(ctx):
        return await ctx.reply("❌ Admin only!")
    clans = await db.get_clan_leaderboard(ctx.guild.id, 1)
    if not clans:
        return await ctx.reply("❌ No clans active yet!")
    winning_clan = clans[0]
    async with aiosqlite.connect(db.db_path) as conn:
        async with conn.execute(
            "SELECT user_id FROM clan_members WHERE clan_id = ? ORDER BY RANDOM() LIMIT 1",
            (winning_clan["clan_id"],)
        ) as c:
            row = await c.fetchone()
    if not row:
        return await ctx.reply("❌ No members in winning clan!")
    winner_id = row[0]
    winner = ctx.guild.get_member(winner_id)
    winner_name = winner.mention if winner else f"<@{winner_id}>"
    embed = gara_embed(
        title="🎉 Nitro Spin Result!",
        description=f"Winning Clan: **{winning_clan['name']}**\n"
                    f"Lucky Winner: {winner_name}\n\n"
                    f"🎁 **Discord Nitro Classic** prize!",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    embed.set_footer(text="Monthly reset complete. New month begins!")
    await ctx.reply(embed=embed)
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute("UPDATE clans SET gold = 0 WHERE guild_id = ?", (ctx.guild.id,))
        await conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# LOCKCYCLE COMMAND (Channel Lock/Unlock Schedule)
# ═══════════════════════════════════════════════════════════════════════════════

@bot.command(name="lockcycle")
@commands.cooldown(1, 1, commands.BucketType.user)
async def lockcycle_cmd(ctx, open_time: str, close_time: str, channel: discord.TextChannel = None):
    if not is_admin(ctx):
        return await ctx.reply("❌ Admin only!")
    target = channel or ctx.channel
    try:
        open_h, open_m = map(int, open_time.split(":"))
        close_h, close_m = map(int, close_time.split(":"))
    except:
        return await ctx.reply("❌ Use format: HH:MM (e.g., 18:30)")
    bot.lockcycles[target.id] = {
        "open": (open_h, open_m),
        "close": (close_h, close_m),
        "guild_id": ctx.guild.id
    }
    embed = gara_embed(
        title="🔒 Lock Cycle Set",
        description=f"Channel: {target.mention}\n"
                    f"🔓 Opens at: **{open_time}**\n"
                    f"🔒 Locks at: **{close_time}**",
        color=GaraConfig.EMBED_COLOR_SUCCESS,
        guild_id=ctx.guild.id
    )
    await ctx.reply(embed=embed)


# ═══════════════════════════════════════════════════════════════════════════════
# REPLIT KEEP-ALIVE (Web Server)
# ═══════════════════════════════════════════════════════════════════════════════

app = Flask('')

@app.route('/')
def home():
    return f"""
    <html>
    <head><title>{GaraConfig.BOT_NAME}</title>
    <style>
        body {{ background: #000; color: #fff; font-family: monospace; text-align: center; padding: 50px; }}
        h1 {{ color: #00ff88; }}
        .status {{ color: #00ff88; font-size: 24px; }}
    </style>
    </head>
    <body>
        <h1>⚡ {GaraConfig.BOT_NAME} BOT</h1>
        <p class="status">● ONLINE</p>
        <p>Currency: {GaraConfig.CURRENCY_NAME} ({GaraConfig.CURRENCY_ABBREV})</p>
        <p>Prefix: {GaraConfig.PREFIX}</p>
    </body>
    </html>
    """

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()


# ═══════════════════════════════════════════════════════════════════════════════
# RUN THE BOT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    keep_alive()
    TOKEN = os.environ.get("DISCORD_TOKEN")
    if not TOKEN:
        print("❌ ERROR: Set DISCORD_TOKEN environment variable!")
        print("   In Replit: Secrets (lock icon) → Add DISCORD_TOKEN")
    else:
        bot.run(TOKEN)
