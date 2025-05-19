from http.client import responses

import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import random
import time
from datetime import timedelta
import webserver



load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
secret_role = "Niner"
random_integer = random.randint(1,6)
user_messages = {}
timeout_counts = {}
last_timeout = {}

bot = commands.Bot(command_prefix='!', intents=intents)

#This should only be used for security purposes. Anything too big will slow the bot's response time down
@bot.event
async def on_message(message):
    # Spam Detection
    now = time.time()
    user_id = message.author.id
    if user_id not in user_messages:
        user_messages[user_id] = []

    user_messages[user_id].append(now)
    user_messages[user_id] = [t for t in user_messages[user_id] if now - t < 5]

    if len(user_messages[user_id]) > 3:
        await message.channel.send(f"{message.author.mention}, you're sending messages too quickly! Slow down.")
        try:
            if user_id not in timeout_counts:
                timeout_counts[user_id] = 0
            if user_id in last_timeout and (now - last_timeout[user_id]) > 3600:
                timeout_counts[user_id] = 0

            timeout_counts[user_id] += 1
            timeout_duration = timeout_counts[user_id]
            last_timeout[user_id] = now
            await message.author.timeout(discord.utils.utcnow() + timedelta(minutes=timeout_duration),
                                      reason="Spamming")
            #bans user if they exceed 2 timeouts in 1 hour
            if timeout_counts[user_id] > 2:
                await message.author.send(F"{message.author.mention} - has been banned for spamming")
                await message.author.ban(reason="Spamming")
        except Exception as e:
            print(f"Failed to timeout {message.author}: {e}")

    if message.author == bot.user or message.author.bot:
        return

    # Handle bad word
    with open("No_No_Words.txt", "r") as f:
        no_no_words = [line.strip().lower() for line in f if line.strip()]
        message_content = message.content.lower()

    for word in no_no_words:
        if word in message_content:
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention} - that's not a fun niner word!")
            except discord.errors.Forbidden:
                await message.channel.send("I don't have permission to delete messages!")
    await bot.process_commands(message)

@bot.command()
async def hello(ctx):
    #sends hello to whoever triggered the command
    await ctx.send(f'Wassup! {ctx.author.mention}!')

#assign role to user
@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name="Niner")
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} you are a {secret_role}")

#remove role from user
@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} role removed")
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def meeting(ctx):
    await ctx.send("Meeting Tonight in Friday 140 at 5:30pm!")

@bot.command()
async def roulette(ctx):
    # Simulate pulling the trigger
    roll = random.randint(1, 6)
    guess = random.randint(1, 6)
    await ctx.send(f"{ctx.author.mention} - pulls the trigger...")
    await ctx.send(f"{ctx.author.mention} - the revolver landed on **{roll}**")
    if roll == guess:
        timeout_duration = 1  # Timeout for 1 minute
        try:
            await ctx.author.timeout(discord.utils.utcnow() + timedelta(minutes=timeout_duration),
                                     reason="Lost at Russian Roulette")
            await ctx.send(
                f"{ctx.author.mention} - did not survive. Timed out for {timeout_duration} minute(s). RIP.")
        except Exception as e:
            await ctx.send(f"Couldn't timeout {ctx.author.mention}. Maybe I don't have permission?")
            print(f"Failed to timeout: {e}")
    else:
        await ctx.send(f"{ctx.author.mention} - lives to see another day.")

@bot.command()
async def ping(ctx):
    await ctx.send(f'Pong! {round(bot.latency * 1000)}ms')

@bot.command()
async def eightball(ctx, question=None):
    try:
        with open("8ball_responses.txt", "r") as f:
            response = [line.strip() for line in f if line.strip()]
        if not response:
            await ctx.send("No responses available.")
            return 
        response = random.choice(response)
        if question:
            await ctx.send(f"{ctx.author.mention} - {response}")
        else:
            await ctx.send(f"{ctx.author.mention} - {response}")
    except FileNotFoundError:
        await ctx.send("Sorry, I can't access my magic 8 ball responses right now.")
    except Exception as e:
        await ctx.send("An error occurred while processing your request.")
        print(f"Error in eightball command: {e}")


webserver.keep_alive()
bot.run(token, log_handler=handler, log_level=logging.DEBUG)
