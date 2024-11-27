import discord
from discord.ext import commands
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
intents.members = True          # Required for accessing member data
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

# Sync slash commands with Discord
@bot.event
async def on_ready():
    # Register the bot's slash commands globally (across all servers) or for specific guilds
    await bot.tree.sync()  # Global sync
    print(f"Logged in as {bot.user}!")


# Add a game
@bot.tree.command(name="addgame", description="Adds a new game to the list with an optional description.")
async def add_game(interaction: discord.Interaction, game_name: str, description: str = None):
    try:
        c.execute("INSERT INTO games (game_name, description) VALUES (?, ?)", (game_name, description))
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(interaction.user), "addgame", game_name))
        conn.commit()
        await interaction.response.send_message(f"Game '{game_name}' has been added.")
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"Game '{game_name}' is already in the list.")


# Update game description
@bot.tree.command(name="updatedescription", description="Updates the description for an existing game.")
async def update_description(interaction: discord.Interaction, game_name: str, description: str):
    c.execute("UPDATE games SET description = ? WHERE game_name = ?", (description, game_name))
    if c.rowcount > 0:
        conn.commit()
        await interaction.response.send_message(f"Description for '{game_name}' has been updated.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")


# Remove a game
@bot.tree.command(name="removegame", description="Removes a game from the list.")
async def remove_game(interaction: discord.Interaction, game_name: str):
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("DELETE FROM games WHERE id = ?", (game_id,))
        c.execute("DELETE FROM helpers WHERE game_id = ?", (game_id,))
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(interaction.user), "removegame", game_name))
        conn.commit()
        await interaction.response.send_message(f"Game '{game_name}' has been removed.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")


# Rename a game
@bot.tree.command(name="renamegame", description="Renames a game if there's an error or update needed.")
async def rename_game(interaction: discord.Interaction, old_name: str, new_name: str):
    c.execute("UPDATE games SET game_name = ? WHERE game_name = ?", (new_name, old_name))
    if c.rowcount > 0:
        conn.commit()
        c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", (str(interaction.user), "renamegame", f"{old_name} -> {new_name}"))
        conn.commit()
        await interaction.response.send_message(f"Game '{old_name}' has been renamed to '{new_name}'.")
    else:
        await interaction.response.send_message(f"Game '{old_name}' not found.")

# Add user as helper for a game
@bot.tree.command(name="addme", description="Registers yourself as a helper for a specific game.")
async def add_me(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)
    user_name = str(interaction.user)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("SELECT * FROM helpers WHERE user_id = ? AND game_id = ?", (user_id, game_id))
        if not c.fetchone():
            c.execute("INSERT INTO helpers (user_id, user_name, game_id) VALUES (?, ?, ?)", (user_id, user_name, game_id))
            conn.commit()
            await interaction.response.send_message(f"{interaction.user.mention}, you have been added as a helper for '{game_name}'.")
        else:
            await interaction.response.send_message(f"{interaction.user.mention}, you are already a helper for '{game_name}'.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")


# Remove user as helper for a game
@bot.tree.command(name="removeme", description="Removes yourself as a helper for a specific game.")
async def remove_me(interaction: discord.Interaction, game_name: str):
    user_id = str(interaction.user.id)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("DELETE FROM helpers WHERE user_id = ? AND game_id = ?", (user_id, game_id))
        conn.commit()
        await interaction.response.send_message(f"{interaction.user.mention}, you have been removed as a helper for '{game_name}'.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")

# Set helper status
@bot.tree.command(name="setstatus", description="Sets your availability status (Green/Amber/Red).")
async def set_status(interaction: discord.Interaction, status: str):
    user_id = str(interaction.user.id)
    if status.lower() in ["green", "amber", "red"]:
        c.execute("UPDATE helpers SET status = ? WHERE user_id = ?", (status.lower(), user_id))
        conn.commit()
        await interaction.response.send_message(f"{interaction.user.mention}, your status has been set to '{status}'.")
    else:
        await interaction.response.send_message("Invalid status. Please use 'green', 'amber', or 'red'.")


# Show games user helps with
@bot.tree.command(name="showme", description="Displays all the games you're helping with.")
async def show_me(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    c.execute('''SELECT g.game_name, g.description, h.status 
                 FROM games g 
                 JOIN helpers h ON g.id = h.game_id 
                 WHERE h.user_id = ?''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} ({game[2]}) - {game[1] if game[1] else 'No description'}" for game in games])
        await interaction.response.send_message(f"Games you help with:\n{game_list}")
    else:
        await interaction.response.send_message("You are not helping with any games.")


# Show games a user helps with
@bot.tree.command(name="showuser", description="Displays what games a specific user is helping with.")
async def show_user(interaction: discord.Interaction, user: discord.Member):
    user_id = str(user.id)
    c.execute('''SELECT g.game_name, g.description, h.status 
                 FROM games g 
                 JOIN helpers h ON g.id = h.game_id 
                 WHERE h.user_id = ?''', (user_id,))
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} ({game[2]}) - {game[1] if game[1] else 'No description'}" for game in games])
        await interaction.response.send_message(f"Games {user.name} helps with:\n{game_list}")
    else:
        await interaction.response.send_message(f"{user.mention} is not helping with any games.")


# Show games with no helpers
@bot.tree.command(name="nothelped", description="Displays games that currently lack helpers.")
async def not_helped(interaction: discord.Interaction):
    c.execute('''SELECT game_name, description 
                 FROM games 
                 WHERE id NOT IN (SELECT DISTINCT game_id FROM helpers)''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} - {game[1] if game[1] else 'No description'}" for game in games])
        await interaction.response.send_message(f"Games with no helpers:\n{game_list}")
    else:
        await interaction.response.send_message("All games have helpers.")

# Show top helpers
@bot.tree.command(name="tophelper", description="Shows a leaderboard of users helping with the most games.")
async def top_helper(interaction: discord.Interaction):
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
        await interaction.response.send_message(f"Top Helpers:\n{leaderboard}")
    else:
        await interaction.response.send_message("No helpers registered yet.")


# Show the helpers for a specific game
@bot.tree.command(name="showgame", description="Shows detailed information about a specific game.")
async def show_game(interaction: discord.Interaction, game_name: str):
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

        await interaction.response.send_message(
            f"**Game Name:** {game_name}\n"
            f"**Description:** {description if description else 'No description'}\n"
            f"**Helpers:**\n{helper_list}"
        )
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")


# Command: Show all games with helpers in alphabetical order
@bot.tree.command(name="gameswithhelp", description="Displays all games that currently have help offered.")
async def games_with_help(interaction: discord.Interaction):
    c.execute('''SELECT DISTINCT g.game_name
                 FROM games g
                 JOIN helpers h ON g.id = h.game_id
                 ORDER BY g.game_name ASC''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([game[0] for game in games])
        await interaction.response.send_message(f"Games with help currently offered (alphabetical order):\n{game_list}")
    else:
        await interaction.response.send_message("No games currently have help offered.")


# Command: Show bot version and information
@bot.tree.command(name="botversion", description="Displays the bot's version and additional information.")
async def bot_version(interaction: discord.Interaction):
    version_info = """
    **Bot Version:** 1.0
    **Created by:** Tide44
    **GitHub:** [HavensHelper](https://github.com/Tide44-cmd/HavensHelper)
    """
    await interaction.response.send_message(version_info)

    
@bot.tree.command(name="help", description="Displays a list of all available commands.")
async def help_command(interaction: discord.Interaction):
    help_text = """
**Haven's Helper Commands:**

- `/addgame "game name" [description]` - Adds a new game to the list with an optional description.
- `/updatedescription "game name" "description"` - Updates the description for an existing game.
- `/removegame "game name"` - Removes a game from the list.
- `/renamegame "old game name" "new game name"` - Renames a game if there's an error or update needed.
- `/addme "game name"` - Registers yourself as a helper for a specific game.
- `/removeme "game name"` - Removes yourself as a helper for a game.
- `/setstatus "status"` - Sets your availability status:
  - 🟢 Green: Available
  - 🟠 Amber: Limited Availability
  - 🔴 Red: Unavailable
- `/showme` - Displays all the games you're helping with.
- `/showuser "@user"` - Displays what games a specific user is helping with.
- `/nothelped` - Displays games that currently lack helpers.
- `/tophelper` - Shows a leaderboard of users helping with the most games.
- `/showgame "game name"` - Shows detailed information about a specific game, including its description and helpers.
- `/gameswithhelp` - Displays all games that currently have help offered, sorted alphabetically.
- `/botversion` - Displays the bot's version and additional information.

Need more assistance? Feel free to ask!
"""
    await interaction.response.send_message(help_text)


token = os.getenv('DISCORD_TOKEN')
bot.run(token)
