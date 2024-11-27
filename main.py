import discord
from discord.ext import commands
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="?", intents=intents)

# SQLite Database setup
conn = sqlite3.connect('helpers.db')
c = conn.cursor()

# Create tables for games and helpers if they don't exist
c.execute('''CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT UNIQUE,
                description TEXT
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS helpers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                game_id INTEGER,
                status TEXT DEFAULT 'green',
                FOREIGN KEY (game_id) REFERENCES games(id)
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                command TEXT NOT NULL,
                game_name TEXT
            )''')

conn.commit()

# Bot ready event
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}!")

# Add a game
@bot.command(name="addgame")
async def add_game(ctx, game_name: str, *, description: str = None):
    try:
        c.execute("INSERT INTO games (game_name, description) VALUES (?, ?)", (game_name, description))
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(ctx.author), "addgame", game_name))
        conn.commit()
        await ctx.send(f"Game '{game_name}' has been added.")
    except sqlite3.IntegrityError:
        await ctx.send(f"Game '{game_name}' is already in the list.")

# Update game description
@bot.command(name="updatedescription")
async def update_description(ctx, game_name: str, *, description: str):
    c.execute("UPDATE games SET description = ? WHERE game_name = ?", (description, game_name))
    if c.rowcount > 0:
        conn.commit()
        await ctx.send(f"Description for '{game_name}' has been updated.")
    else:
        await ctx.send(f"Game '{game_name}' not found.")

# Remove a game
@bot.command(name="removegame")
async def remove_game(ctx, game_name: str):
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("DELETE FROM games WHERE id = ?", (game_id,))
        c.execute("DELETE FROM helpers WHERE game_id = ?", (game_id,))
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(ctx.author), "removegame", game_name))
        conn.commit()
        await ctx.send(f"Game '{game_name}' has been removed.")
    else:
        await ctx.send(f"Game '{game_name}' not found.")

# Rename a game
@bot.command(name="renamegame")
async def rename_game(ctx, old_name: str, new_name: str):
    c.execute("UPDATE games SET game_name = ? WHERE game_name = ?", (new_name, old_name))
    if c.rowcount > 0:
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(ctx.author), "renamegame", f"{old_name} -> {new_name}"))
        conn.commit()
        await ctx.send(f"Game '{old_name}' has been renamed to '{new_name}'.")
    else:
        await ctx.send(f"Game '{old_name}' not found.")

# Add user as helper for a game
@bot.command(name="addme")
async def add_me(ctx, game_name: str):
    user_id = str(ctx.author.id)
    user_name = str(ctx.author)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("SELECT * FROM helpers WHERE user_id = ? AND game_id = ?", (user_id, game_id))
        if not c.fetchone():
            c.execute("INSERT INTO helpers (user_id, user_name, game_id) VALUES (?, ?, ?)", (user_id, user_name, game_id))
            conn.commit()
            await ctx.send(f"{ctx.author.mention}, you have been added as a helper for '{game_name}'.")
        else:
            await ctx.send(f"{ctx.author.mention}, you are already a helper for '{game_name}'.")
    else:
        await ctx.send(f"Game '{game_name}' not found.")

# Remove user as helper for a game
@bot.command(name="removeme")
async def remove_me(ctx, game_name: str):
    user_id = str(ctx.author.id)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("DELETE FROM helpers WHERE user_id = ? AND game_id = ?", (user_id, game_id))
        conn.commit()
        await ctx.send(f"{ctx.author.mention}, you have been removed as a helper for '{game_name}'.")
    else:
        await ctx.send(f"Game '{game_name}' not found.")

# Set helper status
@bot.command(name="setstatus")
async def set_status(ctx, status: str):
    user_id = str(ctx.author.id)
    if status.lower() in ["green", "amber", "red"]:
        c.execute("UPDATE helpers SET status = ? WHERE user_id = ?", (status.lower(), user_id))
        conn.commit()
        await ctx.send(f"{ctx.author.mention}, your status has been set to '{status}'.")
    else:
        await ctx.send("Invalid status. Please use 'green', 'amber', or 'red'.")

# Show games user helps with
@bot.command(name="showme")
async def show_me(ctx):
    user_id = str(ctx.author.id)
    c.execute('''SELECT g.game_name, g.description, h.status 
                 FROM games g 
                 JOIN helpers h ON g.id = h.game_id 
                 WHERE h.user_id = ?''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} ({game[2]}) - {game[1] if game[1] else 'No description'}" for game in games])
        await ctx.send(f"Games you help with:\n{game_list}")
    else:
        await ctx.send("You are not helping with any games.")

# Show games a user helps with
@bot.command(name="showuser")
async def show_user(ctx, user: discord.User):
    user_id = str(user.id)
    c.execute('''SELECT g.game_name, g.description, h.status 
                 FROM games g 
                 JOIN helpers h ON g.id = h.game_id 
                 WHERE h.user_id = ?''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} ({game[2]}) - {game[1] if game[1] else 'No description'}" for game in games])
        await ctx.send(f"Games {user.name} helps with:\n{game_list}")
    else:
        await ctx.send(f"{user.mention} is not helping with any games.")

# Show games with no helpers
@bot.command(name="nothelped")
async def not_helped(ctx):
    c.execute('''SELECT game_name, description 
                 FROM games 
                 WHERE id NOT IN (SELECT DISTINCT game_id FROM helpers)''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} - {game[1] if game[1] else 'No description'}" for game in games])
        await ctx.send(f"Games with no helpers:\n{game_list}")
    else:
        await ctx.send("All games have helpers.")

# Show top helpers
@bot.command(name="tophelper")
async def top_helper(ctx):
    c.execute('''
        SELECT h.user_name, COUNT(h.game_id) as game_count
        FROM helpers h
        GROUP BY h.user_id
        ORDER BY game_count DESC
        LIMIT 10
    ''')
    helpers = c.fetchall()
    if helpers:
        leaderboard = "\n".join([f"{idx + 1}. {helper[0]} - {helper[1]} games" for idx, helper in enumerate(helpers)])
        await ctx.send(f"Top Helpers:\n{leaderboard}")
    else:
        await ctx.send("No helpers registered yet.")

# Show the helpers for a specific game
@bot.command(name="showgame")
async def show_game(ctx, *, game_name: str):
    c.execute("SELECT id, description FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id, description = game
        c.execute("SELECT user_name, status FROM helpers WHERE game_id = ?", (game_id,))
        helpers = c.fetchall()

        helper_list = "\n".join([
            f"{helper[0]} {'🟢' if helper[1] == 'green' else '🟠' if helper[1] == 'amber' else '🔴'}"
            for helper in helpers
        ]) if helpers else "No helpers yet."

        await ctx.send(
            f"**Game Name:** {game_name}\n"
            f"**Description:** {description if description else 'No description'}\n"
            f"**Helpers:**\n{helper_list}"
        )
    else:
        await ctx.send(f"Game '{game_name}' not found.")

# Command: Show all games with helpers in alphabetical order
@bot.command(name="gameswithhelp")
async def games_with_help(ctx):
    c.execute('''SELECT DISTINCT g.game_name
                 FROM games g
                 JOIN helpers h ON g.id = h.game_id
                 ORDER BY g.game_name ASC''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await ctx.send(f"Games with help currently offered (alphabetical order):\n{game_list}")
    else:
        await ctx.send("No games currently have help offered.")

