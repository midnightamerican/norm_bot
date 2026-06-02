import discord
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

# =====================================================
# CONFIGURATION
# =====================================================

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

MOD_LOG_CHANNEL = 000000000000000000  # Replace if desired

SECRET_ROLE = "Niner"

WARNING_FILE = "warnings.json"

ALLOWED_DOMAINS = [
    "x.com",
    "youtube.com",
    "youtu.be",
    "ncaa.com",
    "espn.com"
]

SPAM_WINDOW = 5
SPAM_LIMIT = 3

# =====================================================
# LOGGING
# =====================================================

handler = logging.FileHandler(
    filename="discord.log",
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

# =====================================================
# JSON UTILITIES
# =====================================================

def load_warnings():

    if not os.path.exists(WARNING_FILE):
        with open(WARNING_FILE, "w") as f:
            json.dump({}, f)

    with open(WARNING_FILE, "r") as f:
        return json.load(f)

def save_warnings(data):

    with open(WARNING_FILE, "w") as f:
        json.dump(data, f, indent=4)

warnings_data = load_warnings()

# =====================================================
# BAD WORDS
# =====================================================

try:
    with open("badwords.txt", "r", encoding="utf-8") as f:
        BAD_WORDS = {
            line.strip().lower()
            for line in f
            if line.strip()
        }
except FileNotFoundError:
    BAD_WORDS = set()

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

            await message.author.timeout(
                discord.utils.utcnow()
                + timedelta(minutes=timeout_minutes),
                reason="Spam Detection"
            )

            await message.channel.send(
                f"{message.author.mention} "
                f"timed out for spamming."
            )

            if timeout_counts[user_id] > 2:

                await message.author.ban(
                    reason="Repeated spam"
                )

                await message.channel.send(
                    f"{message.author.mention} "
                    f"has been banned for repeated spam."
                )

            return

        except Exception as e:
            print(e)

    # ---------------------------------------------
    # LINK FILTER
    # ---------------------------------------------

    urls = URL_PATTERN.findall(message.content)

    if urls:

        allowed = False

        for url in urls:

            for domain in ALLOWED_DOMAINS:

                if domain.lower() in url.lower():
                    allowed = True
                    break

            if allowed:
                break

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

            except Exception as e:
                print(e)

    # ---------------------------------------------
    # BAD WORD FILTER
    # ---------------------------------------------

    content = message.content.lower()

    for word in BAD_WORDS:

        if word in content:

            try:

                await message.delete()

                await message.channel.send(
                    f"{message.author.mention} "
                    f"watch your language."
                )

                await add_warning(
                    message.author,
                    f"Bad word: {word}"
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

    responses = [
        "Yes",
        "No",
        "Maybe",
        "Absolutely",
        "Ask again later",
        "Definitely not",
        "Without a doubt",
        "Very likely"
    ]

    await interaction.response.send_message(
        random.choice(responses)
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

        await interaction.response.send_message(
            "You don't have permission "
            "to use this command.",
            ephemeral=True
        )

    else:

        print(error)

# =====================================================
# RUN
# =====================================================

bot.run(
    TOKEN,
    log_handler=handler,
    log_level=logging.INFO
)