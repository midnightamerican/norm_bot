import discord 
import aiohttp
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

import os
import json
import re
import random
import logging
import time

from datetime import timedelta
from urllib.parse import urlparse

# =====================================================
# CONFIGURATION
# =====================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN: 
    raise ValueError("DISCORD_TOKEN not found")


try:
    MOD_LOG_CHANNEL = int(os.getenv("MOD_LOG_CHANNEL", "0"))
except ValueError:
    MOD_LOG_CHANNEL = 0

SECRET_ROLE = "Niner"

WARNING_FILE = os.path.join(BASE_DIR, "warnings.json")
BAD_WORDS_FILE = os.path.join(BASE_DIR, "No_No_Words.txt")
EIGHTBALL_RESPONSES_FILE = os.path.join(BASE_DIR, "8ball_responses")

ALLOWED_DOMAINS = [
    "x.com",
    "youtube.com",
    "youtu.be",
    "ncaa.com",
    "espn.com"
]

SPAM_WINDOW = 5
SPAM_LIMIT = 3

PERMISSION_NAMES = {
    "moderate_members": "Moderate Members",
    "ban_members": "Ban Members",
    "kick_members": "Kick Members",
    "manage_messages": "Manage Messages"
}

SCOREBOARD_LEAGUES = {
    "nfl": ("football", "nfl", "NFL"),
    "nba": ("basketball", "nba", "NBA"),
    "mlb": ("baseball", "mlb", "MLB"),
    "nhl": ("hockey", "nhl", "NHL"),
    "wnba": ("basketball", "wnba", "WNBA"),
    "ncaaf": ("football", "college-football", "College Football"),
    "ncaamb": (
        "basketball",
        "mens-college-basketball",
        "Men's College Basketball"
    )
}

# =====================================================
# LOGGING
# =====================================================

handler = logging.FileHandler(
    filename=os.path.join(BASE_DIR, "discord.log"),
    encoding="utf-8",
    mode="w"
)

# =====================================================
# INTENTS
# =====================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =====================================================
# GLOBAL DATA
# =====================================================

user_messages = {}
timeout_counts = {}
last_timeout = {}

URL_PATTERN = re.compile(
    r'https?://[^\s]+|www\.[^\s]+',
    re.IGNORECASE
)

def is_allowed_url(url):

    if url.lower().startswith("www."):
        url = f"https://{url}"

    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]

    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in ALLOWED_DOMAINS
    )

def contains_bad_word(content):

    normalized = content.lower()

    return next(
        (
            word for word in BAD_WORDS
            if re.search(
                rf"\b{re.escape(word)}\b",
                normalized
            )
        ),
        None
    )

async def send_interaction_message(
    interaction,
    content,
    *,
    ephemeral=False
):

    if interaction.response.is_done():
        await interaction.followup.send(
            content,
            ephemeral=ephemeral
        )
    else:
        await interaction.response.send_message(
            content,
            ephemeral=ephemeral
        )

async def send_channel_message(channel, content):

    try:
        await channel.send(content)
    except discord.Forbidden:
        print(
            "Missing permission to send messages "
            f"in channel {channel}."
        )

def bot_can_moderate(member, permission):

    guild = member.guild
    bot_member = guild.me or guild.get_member(bot.user.id)

    if bot_member is None:
        return False, "I could not find my bot member record."

    if member.id == guild.owner_id:
        return False, "I cannot moderate the server owner."

    if not getattr(
        bot_member.guild_permissions,
        permission,
        False
    ):
        permission_name = PERMISSION_NAMES.get(
            permission,
            permission
        )

        return False, f"I need the {permission_name} permission."

    if bot_member.top_role <= member.top_role:
        return (
            False,
            "My highest role must be above that member's highest role."
        )

    return True, None

def format_scoreboard_event(event):

    competition = event.get("competitions", [{}])[0]
    status = competition.get("status", {}).get("type", {})
    competitors = competition.get("competitors", [])

    teams = {
        competitor.get("homeAway"): competitor
        for competitor in competitors
    }

    home = teams.get("home")
    away = teams.get("away")

    if not home or not away:
        return None

    home_team = home.get("team", {})
    away_team = away.get("team", {})

    home_name = (
        home_team.get("shortDisplayName")
        or home_team.get("displayName")
        or "Home"
    )
    away_name = (
        away_team.get("shortDisplayName")
        or away_team.get("displayName")
        or "Away"
    )

    state = status.get("state")
    detail = (
        status.get("shortDetail")
        or status.get("detail")
        or "Scheduled"
    )

    if state == "pre":
        return f"**{away_name} at {home_name}**\n{detail}"

    away_score = away.get("score", "0")
    home_score = home.get("score", "0")

    return (
        f"**{away_name} {away_score} - "
        f"{home_name} {home_score}**\n{detail}"
    )

async def fetch_scoreboard(league_key):

    sport, league, display_name = SCOREBOARD_LEAGUES[league_key]
    url = (
        "https://site.api.espn.com/apis/site/v2/sports/"
        f"{sport}/{league}/scoreboard"
    )

    timeout = aiohttp.ClientTimeout(total=10)

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            data = await response.json()

    events = data.get("events", [])
    lines = [
        formatted
        for event in events[:10]
        if (formatted := format_scoreboard_event(event))
    ]

    embed = discord.Embed(
        title=f"{display_name} Scores",
        color=discord.Color.green()
    )

    if lines:
        embed.description = "\n\n".join(lines)
    else:
        embed.description = "No games found right now."

    embed.set_footer(text="Score data from ESPN")

    return embed

# =====================================================
# JSON UTILITIES
# =====================================================

def load_warnings():

    if not os.path.exists(WARNING_FILE):
        with open(WARNING_FILE, "w") as f:
            json.dump({}, f)

    try:
        with open(WARNING_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}

def save_warnings(data):

    with open(WARNING_FILE, "w") as f:
        json.dump(data, f, indent=4)

warnings_data = load_warnings()

# =====================================================
# BAD WORDS
# =====================================================

try:
    with open(BAD_WORDS_FILE, "r", encoding="utf-8") as f:
        BAD_WORDS = {
            line.strip().lower()
            for line in f
            if line.strip()
        }
except FileNotFoundError:
    BAD_WORDS = set()

try:
    with open(EIGHTBALL_RESPONSES_FILE, "r", encoding="utf-8") as f:
        EIGHTBALL_RESPONSES = [
            line.strip()
            for line in f
            if line.strip()
        ]
except FileNotFoundError:
    EIGHTBALL_RESPONSES = []

if not EIGHTBALL_RESPONSES:
    EIGHTBALL_RESPONSES = [
        "Yes",
        "No",
        "Maybe",
        "Absolutely",
        "Ask again later",
        "Definitely not",
        "Without a doubt",
        "Very likely"
    ]

# =====================================================
# MOD LOGGING
# =====================================================

async def log_action(guild, message):

    if MOD_LOG_CHANNEL == 0:
        return

    channel = guild.get_channel(MOD_LOG_CHANNEL)

    if channel:
        try:
            await channel.send(message)
        except Exception:
            pass

# =====================================================
# WARNING SYSTEM
# =====================================================

async def add_warning(member, reason="No reason provided"):

    user_id = str(member.id)

    if user_id not in warnings_data:
        warnings_data[user_id] = []

    warnings_data[user_id].append(reason)

    save_warnings(warnings_data)

    warning_count = len(warnings_data[user_id])

    try:

        if warning_count >= 7:
            await member.ban(
                reason="Exceeded warning limit"
            )

        elif warning_count >= 5:
            await member.kick(
                reason="Exceeded warning limit"
            )

        elif warning_count >= 3:
            await member.timeout(
                discord.utils.utcnow()
                + timedelta(minutes=10),
                reason="Exceeded warning limit"
            )

    except Exception as e:
        print(e)

    return warning_count

# =====================================================
# READY EVENT
# =====================================================

@bot.event
async def on_ready():

    try:
        synced = await bot.tree.sync()

        print(
            f"Synced {len(synced)} slash commands."
        )

    except Exception as e:
        print(e)

    print(
        f"Logged in as {bot.user}"
    )

# =====================================================
# AUTOMOD
# =====================================================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    if message.guild is None:
        await bot.process_commands(message)
        return

    now = time.time()
    user_id = message.author.id

    # ---------------------------------------------
    # SPAM DETECTION
    # ---------------------------------------------

    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id].append(now)

    user_messages[user_id] = [
        t for t in user_messages[user_id]
        if now - t < SPAM_WINDOW
    ]

    if len(user_messages[user_id]) > SPAM_LIMIT:

        try:

            if user_id not in timeout_counts:
                timeout_counts[user_id] = 0

            if (
                user_id in last_timeout and
                now - last_timeout[user_id] > 3600
            ):
                timeout_counts[user_id] = 0

            timeout_counts[user_id] += 1

            timeout_minutes = timeout_counts[user_id]

            last_timeout[user_id] = now

            can_timeout, reason = bot_can_moderate(
                message.author,
                "moderate_members"
            )

            if not can_timeout:
                user_messages[user_id] = []

                await send_channel_message(
                    message.channel,
                    "I detected spam, but I couldn't timeout "
                    f"{message.author.mention}. {reason}"
                )

                return

            await message.author.timeout(
                discord.utils.utcnow()
                + timedelta(minutes=timeout_minutes),
                reason="Spam Detection"
            )

            await send_channel_message(
                message.channel,
                f"{message.author.mention} "
                f"timed out for spamming."
            )

            user_messages[user_id] = []

            if timeout_counts[user_id] > 2:

                can_ban, reason = bot_can_moderate(
                    message.author,
                    "ban_members"
                )

                if not can_ban:
                    await send_channel_message(
                        message.channel,
                        "I would ban this member for repeated spam, "
                        f"but I can't. {reason}"
                    )

                    return

                await message.author.ban(
                    reason="Repeated spam"
                )

                await send_channel_message(
                    message.channel,
                    f"{message.author.mention} "
                    f"has been banned for repeated spam."
                )

            return

        except discord.Forbidden as e:
            user_messages[user_id] = []
            print(f"Discord denied a spam moderation action: {e}")

            await send_channel_message(
                message.channel,
                "I detected spam, but Discord denied the moderation "
                "action. Check my role position and moderation "
                "permissions."
            )

            return

        except Exception as e:
            print(e)

    # ---------------------------------------------
    # LINK FILTER
    # ---------------------------------------------

    urls = URL_PATTERN.findall(message.content)

    if urls:

        allowed = all(
            is_allowed_url(url)
            for url in urls
        )

        if not allowed:

            try:

                await message.delete()

                await message.channel.send(
                    f"{message.author.mention} "
                    f"links are not allowed."
                )

                await add_warning(
                    message.author,
                    "Unauthorized link"
                )

                return

            except discord.Forbidden as e:
                print(f"Discord denied link moderation: {e}")

                await send_channel_message(
                    message.channel,
                    "I found a blocked link, but I need Manage Messages "
                    "and a high enough role to delete it."
                )

                return

            except Exception as e:
                print(e)

    # ---------------------------------------------
    # BAD WORD FILTER
    # ---------------------------------------------

    bad_word = contains_bad_word(
        message.content
    )

    if bad_word:

        try:

            await message.delete()

            await message.channel.send(
                f"{message.author.mention} "
                f"watch your language."
            )

            await add_warning(
                message.author,
                f"Bad word: {bad_word}"
            )

            return

        except discord.Forbidden as e:
            print(f"Discord denied bad-word moderation: {e}")

            await send_channel_message(
                message.channel,
                "I found blocked language, but I need Manage Messages "
                "and a high enough role to delete it."
            )

            return

        except Exception as e:
            print(e)

    await bot.process_commands(message)

# =====================================================
# FUN COMMANDS
# =====================================================

@bot.tree.command(
    name="hello",
    description="Say hello"
)
async def hello(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Wassup {interaction.user.mention}!"
    )

@bot.tree.command(
    name="ping",
    description="Latency"
)
async def ping(interaction: discord.Interaction):

    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)}ms"
    )

@bot.tree.command(
    name="scores",
    description="Show live or recent game scores"
)
@app_commands.describe(
    league="League to show scores for"
)
@app_commands.choices(
    league=[
        app_commands.Choice(name="NFL", value="nfl"),
        app_commands.Choice(name="NBA", value="nba"),
        app_commands.Choice(name="MLB", value="mlb"),
        app_commands.Choice(name="NHL", value="nhl"),
        app_commands.Choice(name="WNBA", value="wnba"),
        app_commands.Choice(
            name="College Football",
            value="ncaaf"
        ),
        app_commands.Choice(
            name="Men's College Basketball",
            value="ncaamb"
        )
    ]
)
async def scores(
    interaction: discord.Interaction,
    league: app_commands.Choice[str]
):

    await interaction.response.defer()

    try:
        embed = await fetch_scoreboard(league.value)

        await interaction.followup.send(embed=embed)

    except aiohttp.ClientResponseError as e:
        print(f"Scoreboard API returned an error: {e}")

        await interaction.followup.send(
            "I couldn't get scores for that league right now."
        )

    except aiohttp.ClientError as e:
        print(f"Scoreboard request failed: {e}")

        await interaction.followup.send(
            "I couldn't reach the scoreboard service right now."
        )

@bot.tree.command(
    name="eightball",
    description="Ask the magic 8-ball"
)
@app_commands.describe(
    question="Your question"
)
async def eightball(
    interaction: discord.Interaction,
    question: str
):

    await interaction.response.send_message(
        random.choice(EIGHTBALL_RESPONSES)
    )

@bot.tree.command(
    name="roulette",
    description="Russian roulette"
)
async def roulette(
    interaction: discord.Interaction
):

    roll = random.randint(1, 6)
    guess = random.randint(1, 6)

    if roll == guess:

        try:

            await interaction.user.timeout(
                discord.utils.utcnow()
                + timedelta(minutes=1),
                reason="Lost roulette"
            )

            await interaction.response.send_message(
                f"{interaction.user.mention} "
                f"lost and was timed out."
            )

        except Exception:

            await interaction.response.send_message(
                "Unable to timeout user."
            )

    else:

        await interaction.response.send_message(
            f"{interaction.user.mention} survived."
        )

# =====================================================
# MODERATION COMMANDS
# =====================================================

@bot.tree.command(
    name="warn",
    description="Warn a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def warn(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str
):

    count = await add_warning(
        member,
        reason
    )

    await interaction.response.send_message(
        f"{member.mention} warned.\n"
        f"Warnings: {count}"
    )

@bot.tree.command(
    name="kick",
    description="Kick a member"
)
@app_commands.checks.has_permissions(
    kick_members=True
)
async def kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    await member.kick(reason=reason)

    await interaction.response.send_message(
        f"{member.mention} kicked."
    )

@bot.tree.command(
    name="ban",
    description="Ban a member"
)
@app_commands.checks.has_permissions(
    ban_members=True
)
async def ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str = "No reason provided"
):

    await member.ban(reason=reason)

    await interaction.response.send_message(
        f"{member.mention} banned."
    )

@bot.tree.command(
    name="timeout",
    description="Timeout a member"
)
@app_commands.checks.has_permissions(
    moderate_members=True
)
async def timeout(
    interaction: discord.Interaction,
    member: discord.Member,
    minutes: int,
    reason: str = "No reason provided"
):

    await member.timeout(
        discord.utils.utcnow()
        + timedelta(minutes=minutes),
        reason=reason
    )

    await interaction.response.send_message(
        f"{member.mention} timed out "
        f"for {minutes} minutes."
    )

@bot.tree.command(
    name="purge",
    description="Delete messages"
)
@app_commands.checks.has_permissions(
    manage_messages=True
)
async def purge(
    interaction: discord.Interaction,
    amount: int
):

    if amount < 1 or amount > 100:
        await interaction.response.send_message(
            "Amount must be between 1 and 100.",
            ephemeral=True
        )
        return

    if not hasattr(
        interaction.channel,
        "purge"
    ):
        await interaction.response.send_message(
            "This command can only be used in a text channel.",
            ephemeral=True
        )
        return

    await interaction.response.defer(
        ephemeral=True
    )

    deleted = await interaction.channel.purge(
        limit=amount
    )

    await interaction.followup.send(
        f"Deleted {len(deleted)} messages.",
        ephemeral=True
    )

# =====================================================
# ROLE COMMANDS
# =====================================================

@bot.tree.command(
    name="assign",
    description="Assign role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def assign(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role
):

    await member.add_roles(role)

    await interaction.response.send_message(
        f"Added {role.name} "
        f"to {member.mention}"
    )

@bot.tree.command(
    name="remove",
    description="Remove role"
)
@app_commands.checks.has_permissions(
    manage_roles=True
)
async def remove(
    interaction: discord.Interaction,
    member: discord.Member,
    role: discord.Role
):

    await member.remove_roles(role)

    await interaction.response.send_message(
        f"Removed {role.name} "
        f"from {member.mention}"
    )

# =====================================================
# ERROR HANDLER
# =====================================================

@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction,
    error
):

    if isinstance(
        error,
        app_commands.MissingPermissions
    ):

        await send_interaction_message(
            interaction,
            "You don't have permission "
            "to use this command.",
            ephemeral=True
        )

    else:

        print(error)

        await send_interaction_message(
            interaction,
            "I couldn't complete that command.",
            ephemeral=True
        )

# =====================================================
# RUN
# =====================================================

bot.run(
    TOKEN,
    log_handler=handler,
    log_level=logging.INFO
)
