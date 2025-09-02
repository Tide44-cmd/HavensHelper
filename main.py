import discord
from discord.ext import commands
from discord import ButtonStyle
from discord.ui import Button, View
from discord import AllowedMentions
from discord import app_commands
import sqlite3
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta, timezone
import calendar

import io, asyncio, aiohttp, math
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

# Track the bot's start time
start_time = time.time()

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


# Add 'guide_url' column if it doesn't already exist
c.execute("PRAGMA table_info(games)")
columns = [col[1] for col in c.fetchall()]
if 'guide_url' not in columns:
    c.execute("ALTER TABLE games ADD COLUMN guide_url TEXT")

c.execute('''CREATE TABLE IF NOT EXISTS helpers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                user_name TEXT,
                game_id INTEGER,
                platform TEXT,
                status TEXT DEFAULT 'green' CHECK(status IN ('green', 'amber', 'red')),
                FOREIGN KEY (game_id) REFERENCES games(id)
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user TEXT NOT NULL,
                command TEXT NOT NULL,
                game_name TEXT,
                executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
c.execute('''CREATE TABLE IF NOT EXISTS thanks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thanked_user_id TEXT NOT NULL,
                thanked_user_name TEXT NOT NULL,
                thanking_user_id TEXT NOT NULL,
                thanking_user_name TEXT NOT NULL,
                game TEXT DEFAULT NULL,
                message TEXT DEFAULT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
# Create indexes for faster queries
c.execute('CREATE INDEX IF NOT EXISTS idx_game_name ON games(game_name)')
c.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON helpers(user_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_game_id ON helpers(game_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_thanked_user_id ON thanks(thanked_user_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_thanking_user_id ON thanks(thanking_user_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON thanks(timestamp)')

conn.commit()

# Sync slash commands with Discord
@bot.event
async def on_ready():
    # Register the bot's slash commands globally (across all servers) or for specific guilds
    await bot.tree.sync()  # Global sync
    print(f"Logged in as {bot.user}!")

async def _game_autocomplete(interaction: discord.Interaction, current: str):
    # Case-insensitive partial match; return up to 25
    rows = conn.execute(
        "SELECT game_name FROM games WHERE game_name LIKE ? ORDER BY game_name COLLATE NOCASE LIMIT 25",
        (f"%{current}%",)
    ).fetchall()
    return [app_commands.Choice(name=r[0], value=r[0]) for r in rows]

# Add a game
@bot.tree.command(name="addgame", description="Adds a new game with optional description and guide URL.")
async def add_game(interaction: discord.Interaction, game_name: str, description: str = None, guide_url: str = None):
    try:
        # 1) Insert game
        c.execute(
            "INSERT INTO games (game_name, description, guide_url) VALUES (?, ?, ?)",
            (game_name, description, guide_url)
        )
        game_id = c.lastrowid            # <-- Get it right here
        conn.commit()

        # 2) Auto-add creator as helper (uses the correct game_id)
        user_id = str(interaction.user.id)
        user_name = str(interaction.user)
        c.execute(
            "INSERT INTO helpers (user_id, user_name, game_id) VALUES (?, ?, ?)",
            (user_id, user_name, game_id)
        )
        conn.commit()

        # 3) Log last (so lastrowid changes don’t matter)
        c.execute(
            "INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)",
            (str(interaction.user), "addgame", game_name)
        )
        conn.commit()

        await interaction.response.send_message(
            f"Game '{game_name}' has been added.\n"
            f"{interaction.user.mention} is now registered as a helper for this game."
        )
    except sqlite3.IntegrityError:
        await interaction.response.send_message(f"Game '{game_name}' is already in the list.")



# Update game description
class DescriptionChoiceView(View):
    def __init__(self, game_name, new_description, existing_description):
        super().__init__()
        self.game_name = game_name
        self.new_description = new_description
        self.existing_description = existing_description

    @discord.ui.button(label="Replace", style=ButtonStyle.primary)
    async def replace(self, interaction: discord.Interaction, button: Button):
        c.execute("UPDATE games SET description = ? WHERE game_name = ?", (self.new_description, self.game_name))
        conn.commit()
        await interaction.response.edit_message(content=f"✅ Description for '{self.game_name}' replaced.", view=None)

    @discord.ui.button(label="Append", style=ButtonStyle.success)
    async def append(self, interaction: discord.Interaction, button: Button):
        combined = f"{self.existing_description}; {interaction.user.name}: {self.new_description}"
        c.execute("UPDATE games SET description = ? WHERE game_name = ?", (combined, self.game_name))
        conn.commit()
        await interaction.response.edit_message(content=f"✅ Description for '{self.game_name}' appended.", view=None)

    @discord.ui.button(label="Cancel", style=ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="❌ Update cancelled.", view=None)


@bot.tree.command(name="updatedescription", description="Updates the description for an existing game.")
async def update_description(interaction: discord.Interaction, game_name: str, description: str):
    c.execute("SELECT description FROM games WHERE game_name = ?", (game_name,))
    result = c.fetchone()
    if not result:
        await interaction.response.send_message(f"Game '{game_name}' not found.")
        return

    existing_description = result[0]
    if existing_description:
        view = DescriptionChoiceView(game_name, description, existing_description)
        await interaction.response.send_message(
            f"This game already has the description:\n**{existing_description}**\nWhat do you want to do?",
            view=view
        )
    else:
        c.execute("UPDATE games SET description = ? WHERE game_name = ?", (description, game_name))
        conn.commit()
        await interaction.response.send_message(f"Description for '{game_name}' has been updated.")


# Update game URL
@bot.tree.command(name="updateurl", description="Updates or adds a guide URL for a game.")
async def update_url(interaction: discord.Interaction, game_name: str, guide_url: str):
    c.execute("UPDATE games SET guide_url = ? WHERE game_name = ?", (guide_url, game_name))
    if c.rowcount > 0:
        conn.commit()
        await interaction.response.send_message(f"Guide URL for '{game_name}' updated.")
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
@bot.tree.command(name="addme", description="Register yourself as a helper for a specific game.")
@app_commands.autocomplete(game_name=_game_autocomplete)
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
            await interaction.response.send_message(f"{interaction.user.mention}, you are now a helper for '{game_name}'.")
        else:
            await interaction.response.send_message(f"{interaction.user.mention}, you're already listed as a helper for '{game_name}'.")
    else:
        await interaction.response.send_message(f"Game '{game_name}' not found.")
    
# Define the custom platform view with button callbacks
class PlatformView(View):
    def __init__(self, game_name):
        super().__init__()
        self.game_name = game_name

    @discord.ui.button(label="Xbox", style=ButtonStyle.primary, custom_id="platform_xbox")
    async def xbox_button(self, interaction: discord.Interaction, button: Button):
        await process_platform(interaction, self.game_name, "Xbox")

    @discord.ui.button(label="PC", style=ButtonStyle.primary, custom_id="platform_pc")
    async def pc_button(self, interaction: discord.Interaction, button: Button):
        await process_platform(interaction, self.game_name, "PC")

    @discord.ui.button(label="PlayStation", style=ButtonStyle.primary, custom_id="platform_ps")
    async def ps_button(self, interaction: discord.Interaction, button: Button):
        await process_platform(interaction, self.game_name, "PlayStation")

# Process the platform selection
async def process_platform(interaction: discord.Interaction, game_name: str, platform: str):
    user_id = str(interaction.user.id)  # Correctly accesses the user from interaction
    user_name = str(interaction.user)
    c.execute("SELECT id FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()
    if game:
        game_id = game[0]
        c.execute("SELECT * FROM helpers WHERE user_id = ? AND game_id = ? AND platform = ?", (user_id, game_id, platform))
        if not c.fetchone():
            c.execute("INSERT INTO helpers (user_id, user_name, game_id, platform) VALUES (?, ?, ?, ?)", (user_id, user_name, game_id, platform))
            conn.commit()
            await interaction.response.send_message(f"{interaction.user.mention}, you have been added as a helper for `{game_name}` on `{platform}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"{interaction.user.mention}, you are already a helper for `{game_name}` on `{platform}`.", ephemeral=True)
    else:
        await interaction.response.send_message(f"Game `{game_name}` not found.", ephemeral=True)



# Remove user as helper for a game
@bot.tree.command(name="removeme", description="Removes yourself as a helper for a specific game.")
@app_commands.autocomplete(game_name=_game_autocomplete)
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
    c.execute('''
        SELECT g.game_name, g.description, h.status 
        FROM games g 
        JOIN helpers h ON g.id = h.game_id 
        WHERE h.user_id = ?
        ORDER BY g.game_name ASC
    ''', (user_id,))
    games = c.fetchall()
    
    if games:
        game_list = "\n".join([
            f"{game[0]} {'🟢' if game[2] == 'green' else '🟠' if game[2] == 'amber' else '🔴'} - {game[1] if game[1] else 'No description'}"
            for game in games
        ])
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
        game_list = "\n".join([
            f"{game[0]} {'🟢' if game[2] == 'green' else '🟠' if game[2] == 'amber' else '🔴'} - {game[1] if game[1] else 'No description'}"
            for game in games
        ])
        await interaction.response.send_message(f"Games {user.name} helps with:\n{game_list}")
    else:
        await interaction.response.send_message(f"{user.mention} is not helping with any games.")

# Show games with no helpers
@bot.tree.command(name="nothelped", description="Displays games that have no helpers and no guides.")
async def not_helped(interaction: discord.Interaction):
    c.execute('''
        SELECT game_name, description
        FROM games
        WHERE id NOT IN (SELECT DISTINCT game_id FROM helpers)
        AND (guide_url IS NULL OR guide_url = '')
    ''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([f"{game[0]} - {game[1] if game[1] else 'No description'}" for game in games])
        await interaction.response.send_message(f"Games with no helpers and no guide:\n{game_list}")
    else:
        await interaction.response.send_message("All games either have helpers or guides.")

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

# --- Small helper to safely send long lists -----------------------
async def _send_long(interaction: discord.Interaction, header: str, lines: list[str]):
    if not lines:
        await interaction.response.send_message(header)
        return
    message_limit = 1900
    current = header + "\n"
    first = True
    for line in lines:
        if len(current) + len(line) + 1 > message_limit:
            if first:
                await interaction.response.send_message(current.rstrip())
                first = False
            else:
                await interaction.followup.send(current.rstrip())
            current = ""
        current += line + "\n"
    if current:
        if first:
            await interaction.response.send_message(current.rstrip())
        else:
            await interaction.followup.send(current.rstrip())


# 1) gameswithhelp — only games that have ≥1 helper; add 📘 if they also have a guide
@bot.tree.command(name="gameswithhelp", description="Lists all games that currently have helpers (adds 📘 if a guide also exists).")
async def games_with_help(interaction: discord.Interaction):
    sql = """
    SELECT g.game_name, g.guide_url
    FROM games g
    WHERE EXISTS (SELECT 1 FROM helpers h WHERE h.game_id = g.id)
    ORDER BY g.game_name COLLATE NOCASE;
    """
    rows = conn.execute(sql).fetchall()

    if not rows:
        await interaction.response.send_message("No games currently have helpers.")
        return

    lines = [f"{name}{' 📘' if (guide_url and str(guide_url).strip()) else ''}"
             for (name, guide_url) in rows]
    await _send_long(interaction, "**Games with Helpers** (📘 = has guide)", lines)


# 2) gameswithguides — only games that have a guide; add 👥 if they also have a helper
@bot.tree.command(name="gameswithguides", description="Lists all games that have guides (adds 👥 if helpers also exist).")
async def games_with_guides(interaction: discord.Interaction):
    sql = """
    SELECT g.game_name,
           EXISTS(SELECT 1 FROM helpers h WHERE h.game_id = g.id) AS has_helper
    FROM games g
    WHERE g.guide_url IS NOT NULL AND TRIM(g.guide_url) <> ''
    ORDER BY g.game_name COLLATE NOCASE;
    """
    rows = conn.execute(sql).fetchall()

    if not rows:
        await interaction.response.send_message("No games currently have guides.")
        return

    lines = [f"{name}{' 👥' if has_helper else ''}" for (name, has_helper) in rows]
    await _send_long(interaction, "**Games with Guides** (👥 = has helpers)", lines)


# 3) showgame — case-insensitive, tidy sections (hide Guide if none; hide Helpers if none)
STATUS_EMOJI = {"green": "🟢", "amber": "🟡", "yellow": "🟡", "red": "🔴"}

@bot.tree.command(name="showgame", description="Show details for a game (case-insensitive).")
@app_commands.autocomplete(game_name=_game_autocomplete)
async def show_game(interaction: discord.Interaction, game_name: str):
    game = conn.execute(
        "SELECT id, game_name, description, guide_url FROM games WHERE game_name = ? COLLATE NOCASE",
        (game_name,)
    ).fetchone()
    if not game:
        await interaction.response.send_message(f"Couldn't find a game named **{game_name}**.", ephemeral=True)
        return

    game_id, proper_name, description, guide_url = game
    helpers = conn.execute(
        "SELECT user_name, status FROM helpers WHERE game_id = ? ORDER BY user_name COLLATE NOCASE",
        (game_id,)
    ).fetchall()

    parts = [f"**Game Name:** {proper_name}"]
    if description and str(description).strip():
        parts.append(f"**Description:** {description}")
    if guide_url and str(guide_url).strip():
        parts.append(f"**Guide:** [Guide]({guide_url})")
    if helpers:
        STATUS_EMOJI = {"green": "🟢", "amber": "🟡", "yellow": "🟡", "red": "🔴"}
        hl = [f"{u} {STATUS_EMOJI.get((s or '').lower(), '')}".strip() for (u, s) in helpers]
        parts.append("**Helpers:**\n" + "\n".join(hl))

    await interaction.response.send_message("\n".join(parts))


# Command: Show bot version and information
@bot.tree.command(name="botversion", description="Displays the bot's version and additional information.")
async def bot_version(interaction: discord.Interaction):
    version_info = """
    **Bot Version:** 1.3
    **Created by:** Tide44
    **GitHub:** [HavensHelper](https://github.com/Tide44-cmd/HavensHelper)
    """
    await interaction.response.send_message(version_info)

    
@bot.tree.command(name="help", description="Displays a list of all available commands.")
async def help_command(interaction: discord.Interaction):
    help_text = """
**Haven's Helper Commands:**

- **Game Management:**
  - `/addgame "game name" [description]` - Adds a new game to the list with an optional description.
  - `/updatedescription "game name" "description"` - Updates the description for an existing game.
  - `/updateurl "game name" "URL Link"` - Updates or adds a guide URL for a game.
  - `/removegame "game name"` - Removes a game from the list.
  - `/renamegame "old game name" "new game name"` - Renames a game if there's an error or update needed.

- **Helper Management:**
  - `/addme "game name"` - Register yourself as a helper for a specific game.
  - `/removeme "game name"` - Removes yourself as a helper for a game.
  - `/setstatus "status"` - Sets your availability status:
    - 🟢 Green: Available
    - 🟠 Amber: Limited Availability
    - 🔴 Red: Unavailable.

- **Insights and Discovery:**
  - `/showme` - Displays all the games you're helping with.
  - `/showuser "@user"` - Displays what games a specific user is helping with.
  - `/nothelped` - Displays games that currently lack helpers.
  - `/tophelper` - Shows a leaderboard of users helping with the most games.
  - `/showgame "game name"` - Shows detailed information about a specific game, including its description and helpers.
  - `/gameswithhelp` - Displays all games that currently have help offered, sorted alphabetically.

- **Thanks and Feedback:**
  - `/givethanks @user [Game] [Message]` - Give thanks to another user with optional game and message details. (Cannot thank yourself.)
  - `/mostthanked [Month] [Year]` - Shows the most thanked users, either all-time or for a specific month and year.
  - `/showfeedback @user` - Displays the last 10 feedback messages received by a specific user.

- **Bot Information:**
  - `/botversion` - Displays the bot's version and additional information.

Need more assistance? Feel free to ask!
"""
    await interaction.response.send_message(help_text)

# Shared logic stays here
async def _process_give_thanks(interaction: discord.Interaction, thanked_member: discord.Member, game: str | None, message: str | None):
    thanking_user_id = str(interaction.user.id)
    thanked_user_id  = str(thanked_member.id)

    if thanking_user_id == thanked_user_id:
        await interaction.response.send_message("You can't thank yourself!", ephemeral=True)
        return

    before_count = conn.execute(
        "SELECT COUNT(*) FROM thanks WHERE thanked_user_id = ?", (thanked_user_id,)
    ).fetchone()[0]

    conn.execute(
        '''INSERT INTO thanks (thanked_user_id, thanked_user_name, thanking_user_id, thanking_user_name, game, message)
           VALUES (?, ?, ?, ?, ?, ?)''',
        (thanked_user_id, str(thanked_member), thanking_user_id, str(interaction.user), game, message)
    )

    resp = f"{interaction.user.mention} thanked {thanked_member.mention}!"
    if game: resp += f"\n**Game:** {game}"
    if message: resp += f"\n**Message:** {message}"

    if interaction.response.is_done():
        await interaction.followup.send(resp)
    else:
        await interaction.response.send_message(resp)

    after_count = before_count + 1
    MILESTONES = {15: "The Pathfinder 🗺️", 50: "Haven's Guardian 🛡️", 100: "The Apex Hunter 🏹"}
    crossed = next((m for m in MILESTONES if before_count < m <= after_count), None)
    if crossed is not None:
        MOD_ROLE_ID = 1314735241360834640
        guild = interaction.guild
        mod_role = guild.get_role(MOD_ROLE_ID) if guild else None
        role_mention = mod_role.mention if mod_role else f"<@&{MOD_ROLE_ID}>"
        congrats = (
            f"🎉 {thanked_member.mention} just hit **{crossed} thanks** and earned **{MILESTONES[crossed]}**!\n"
            f"{role_mention} please award this role in recognition of their support."
        )
        await interaction.followup.send(
            congrats,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False)
        )

# Slash command (works on mobile & desktop)
@bot.tree.command(name="givethanks", description="Give thanks to another user for their help.")
async def give_thanks(interaction: discord.Interaction, user: discord.Member, game: str = None, message: str = None):
    await _process_give_thanks(interaction, user, game, message)

# Right-click context menu
class GiveThanksModal(discord.ui.Modal, title="Give Thanks"):
    game = discord.ui.TextInput(label="Game (optional)", required=False, max_length=100)
    note = discord.ui.TextInput(label="Message (optional)", required=False, style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, target_member: discord.Member):
        super().__init__()
        self.target_member = target_member

    async def on_submit(self, interaction: discord.Interaction):
        await _process_give_thanks(interaction, self.target_member, str(self.game).strip() or None, str(self.note).strip() or None)

@bot.tree.context_menu(name="Give Thanks")
async def give_thanks_context(interaction: discord.Interaction, user: discord.Member):
    await interaction.response.send_modal(GiveThanksModal(user))

    
@bot.tree.command(name="mostthanked", description="Shows the most thanked users.")
async def most_thanked(interaction: discord.Interaction, month: int = None, year: int = None):
    # Build the SQL query dynamically based on optional parameters
    query = '''SELECT thanked_user_name, COUNT(*) as thank_count
               FROM thanks'''
    params = []

    # Modify query if filtering by month and year
    if month and year:
        query += ''' WHERE strftime('%m', timestamp) = ? AND strftime('%Y', timestamp) = ?'''
        params.extend([f"{month:02d}", str(year)])

    query += ''' GROUP BY thanked_user_id, thanked_user_name
                 ORDER BY thank_count DESC
                 LIMIT 10'''
    
    c.execute(query, params)
    results = c.fetchall()

    # Determine title based on provided parameters
    if month and year:
        title = f"Most Thanked Users ({calendar.month_name[month]} {year}):"
    else:
        title = "Most Thanked Users (All-Time):"

    if results:
        # Format the results into a list
        thank_list = "\n".join([f"{row[0]} - {row[1]} thanks" for row in results])
        response = f"**{title}**\n{thank_list}"
    else:
        response = f"**{title}**\nNo thanks recorded for the specified period."

    await interaction.response.send_message(response)

@bot.tree.command(name="mostthankedfull", description="Shows the full all-time list of most thanked users.")
async def most_thanked_full(interaction: discord.Interaction):
    # Query without date filters or LIMIT
    query = '''SELECT thanked_user_name, COUNT(*) as thank_count
               FROM thanks
               GROUP BY thanked_user_id, thanked_user_name
               ORDER BY thank_count DESC'''
    
    c.execute(query)
    results = c.fetchall()

    title = "Most Thanked Users (All-Time Full List):"

    if results:
        thank_list = "\n".join([f"{row[0]} - {row[1]} thanks" for row in results])
        response = f"**{title}**\n{thank_list}"
    else:
        response = f"**{title}**\nNo thanks recorded."

    await interaction.response.send_message(response)


@bot.tree.command(name="showfeedback", description="Shows the last 10 feedback messages received by a user.")
async def show_feedback(interaction: discord.Interaction, user: discord.Member):
    user_id = str(user.id)
    c.execute('''SELECT thanking_user_name, game, message, timestamp
                 FROM thanks
                 WHERE thanked_user_id = ?
                 ORDER BY timestamp DESC
                 LIMIT 10''', (user_id,))
    feedback = c.fetchall()

    if feedback:
        feedback_list = "\n".join([
            f"**From:** {row[0]}\n**Game:** {row[1] if row[1] else 'N/A'}\n**Message:** {row[2] if row[2] else 'No message'}\n**Date:** {row[3]}"
            for row in feedback
        ])
        await interaction.response.send_message(f"**Feedback for {user.name}:**\n{feedback_list}")
    else:
        await interaction.response.send_message(f"No feedback found for {user.mention}.")

@bot.tree.command(name="deleteusermanual", description="Remove a user from all games using their username (Admin only)")
@commands.has_permissions(administrator=True)
async def remove_user_manual(interaction: discord.Interaction, username: str):
    c.execute("DELETE FROM helpers WHERE user_name = ?", (username,))
    conn.commit()
    c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", 
              (str(interaction.user), "removeusermanual", f"Removed {username} from all games"))
    conn.commit()
    await interaction.response.send_message(f"User '{username}' has been removed from all games.")

@bot.tree.command(name="deleteuser", description="Remove a user from all games (Admin only)")
@commands.has_permissions(administrator=True)
async def remove_user(interaction: discord.Interaction, user: discord.User):
    user_id = str(user.id)
    c.execute("DELETE FROM helpers WHERE user_id = ?", (user_id,))
    conn.commit()
    c.execute("INSERT INTO logs (user, command, game_name) VALUES (?, ?, ?)", 
              (str(interaction.user), "removeuser", f"Removed {user} from all games"))
    conn.commit()
    await interaction.response.send_message(f"User '{user}' has been removed from all games.")
    
@bot.tree.command(name="healthcheck", description="Checks the bot's status and health.")
async def health_check(interaction: discord.Interaction):
    try:
        # Check database connection
        c.execute("SELECT 1")
        db_status = "✅ Connected"
    except Exception as e:
        db_status = f"❌ Error: {str(e)}"
    
    # Calculate uptime
    uptime_seconds = int(time.time() - start_time)
    uptime = str(timedelta(seconds=uptime_seconds))

    # Get registered commands
    command_count = len(bot.tree.get_commands())

    # Construct the health report
    health_report = (
        "**Haven's Helper Health Check:**\n"
        f"- **Uptime:** {uptime}\n"
        f"- **Database:** {db_status}\n"
        f"- **Registered Commands:** {command_count}\n"
    )
    
    await interaction.response.send_message(health_report)

@bot.tree.command(name="syncname", description="Sync a member's display name across stored records.")
async def sync_name(interaction: discord.Interaction, user: discord.Member):
    uid = str(user.id)
    uname = str(user)  # e.g., "fatjay4lisa#1234" or display name depending on your needs
    # thanks table (both sides)
    c.execute("UPDATE thanks SET thanked_user_name = ? WHERE thanked_user_id = ?", (uname, uid))
    c.execute("UPDATE thanks SET thanking_user_name = ? WHERE thanking_user_id = ?", (uname, uid))
    # helpers table too (optional but handy)
    c.execute("UPDATE helpers SET user_name = ? WHERE user_id = ?", (uname, uid))
    conn.commit()
    await interaction.response.send_message(f"Synced names for {user.mention}.")



# ---------- MOST THANKED TABLE TEST ----------
# Build a human label like "All-time", "Last 30 days", or "Jul 2025"
def _range_label(scope: str, month: int | None, year: int | None) -> str:
    if scope == "last30":
        return "Last 30 days"
    if month and year:
        return f"{calendar.month_abbr[month]} {year}"
    return "All-time"

# Compute WHERE clause + params for the chosen scope
def _thanks_where(scope: str, month: int | None, year: int | None):
    where = []
    params = []
    if scope == "last30":
        # last 30 days rolling
        dt_to = datetime.now(timezone.utc)
        dt_from = dt_to - timedelta(days=30)
        where.append("timestamp >= ? AND timestamp < ?")
        params.extend([dt_from.strftime("%Y-%m-%d %H:%M:%S"), dt_to.strftime("%Y-%m-%d %H:%M:%S")])
    elif month and year:
        # calendar month
        start = datetime(year, month, 1, tzinfo=timezone.utc)
        # first day of next month
        if month == 12:
            end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
        where.append("timestamp >= ? AND timestamp < ?")
        params.extend([start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")])
    # else all-time → no filter
    return (" WHERE " + " AND ".join(where)) if where else "", params

def _query_top_thanked_paginated(limit: int, offset: int, scope: str, month: int | None, year: int | None):
    where_sql, params = _thanks_where(scope, month, year)
    sql = f"""
        SELECT thanked_user_id AS user_id,
               MAX(thanked_user_name) AS name,
               COUNT(*) AS thank_count
        FROM thanks
        {where_sql}
        GROUP BY thanked_user_id
        ORDER BY thank_count DESC
        LIMIT ? OFFSET ?
    """
    cur = conn.execute(sql, (*params, limit, offset))
    rows = cur.fetchall()
    return [{"user_id": r[0], "name": r[1], "thank_count": r[2]} for r in rows]

def _count_distinct_thanked(scope: str, month: int | None, year: int | None) -> int:
    where_sql, params = _thanks_where(scope, month, year)
    sql = f"SELECT COUNT(DISTINCT thanked_user_id) FROM thanks {where_sql}"
    return int(conn.execute(sql, params).fetchone()[0])

# ===== View (buttons + select), only in all-time mode =========================

class MostThankedView(discord.ui.View):
    def __init__(self, guild: discord.Guild, scope: str = "all", page: int = 0):
        super().__init__(timeout=300)
        self.guild = guild
        self.scope = scope            # "all" or "last30"
        self.page = page              # 0-based
        # Only show components in ALL-TIME mode
        if self.scope in ("all", "last30"):
            self._wire_components()

    def _wire_components(self):
        # Quick range select (only in all-time view)
        self.add_item(self.RangeSelect(self))
        # Prev/Next buttons (only useful in all-time/all-range modes)
        self.add_item(self.PrevButton(self))
        self.add_item(self.NextButton(self))

    def _sync_controls(self, total_users: int, limit: int, offset: int, rows_len: int):
        # Prev/Next enable/disable
        for item in self.children:
            if isinstance(item, MostThankedView.PrevButton):
                item.disabled = (self.page == 0)
            if isinstance(item, MostThankedView.NextButton):
                item.disabled = (offset + rows_len >= total_users)

        # Update select defaults + placeholder to match current scope
        for item in self.children:
            if isinstance(item, MostThankedView.RangeSelect):
                for opt in item.options:
                    opt.default = (opt.value == self.scope)
                item.placeholder = "Last 30 days" if self.scope == "last30" else "All-time"

    # -- Components ------------------------------------------------------------

    class RangeSelect(discord.ui.Select):
        def __init__(self, parent: "MostThankedView"):
            self.parent = parent
            options = [
                discord.SelectOption(label="All-time", value="all", default=(parent.scope == "all")),
                discord.SelectOption(label="Last 30 days", value="last30", default=(parent.scope == "last30")),
            ]
            super().__init__(placeholder="All-time", min_values=1, max_values=1, options=options)

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(thinking=True)
            self.parent.scope = self.values[0]
            self.parent.page = 0  # reset to first page
            await self.parent._rerender(interaction)

    class PrevButton(discord.ui.Button):
        def __init__(self, parent: "MostThankedView"):
            super().__init__(label="Prev", style=discord.ButtonStyle.secondary)
            self.parent = parent

        async def callback(self, interaction: discord.Interaction):
            if self.parent.page > 0:
                await interaction.response.defer(thinking=True)
                self.parent.page -= 1
                await self.parent._rerender(interaction)

    class NextButton(discord.ui.Button):
        def __init__(self, parent: "MostThankedView"):
            super().__init__(label="Next", style=discord.ButtonStyle.secondary)
            self.parent = parent

        async def callback(self, interaction: discord.Interaction):
            await interaction.response.defer(thinking=True)
            self.parent.page += 1
            await self.parent._rerender(interaction)

    # -- Rerender --------------------------------------------------------------

    async def _rerender(self, interaction: discord.Interaction):
        limit = 10
        offset = self.page * limit
        total_users = _count_distinct_thanked(scope=self.scope, month=None, year=None)
        rows = _query_top_thanked_paginated(limit, offset, scope=self.scope, month=None, year=None)

        self._sync_controls(total_users=total_users, limit=limit, offset=offset, rows_len=len(rows))

        # Disable buttons if needed
        start_index = offset + 1
        end_index = offset + len(rows)
        # Find our buttons in the view
        for item in self.children:
            if isinstance(item, MostThankedView.PrevButton):
                item.disabled = (self.page == 0)
            if isinstance(item, MostThankedView.NextButton):
                item.disabled = (end_index >= total_users)

        title = f"Most thanked — {_range_label(self.scope, None, None)}"
        offset = self.page * limit
        rows = _query_top_thanked_paginated(limit, offset, scope=self.scope, month=None, year=None)
        file = await render_most_thanked_table(self.guild, rows,title_text=title, start_rank=offset + 1)
        #file = await render_most_thanked_table(self.guild, rows, title_text=title)

        embed = discord.Embed(color=discord.Color.teal()).set_image(url="attachment://mostthanked.png")
        await interaction.edit_original_response(embed=embed, attachments=[file], view=self)


# ---------- tiny font helper (tries DejaVu, falls back to default) ----------
def _load_font(size=28, bold=False):
    try:
        path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# ---------- avatar fetch (async) ----------
async def _fetch_avatar_bytes(session: aiohttp.ClientSession, member: discord.Member) -> bytes:
    url = str(member.display_avatar.url)
    async with session.get(url) as resp:
        return await resp.read()

# ---------- renderer for the table image ----------
async def render_most_thanked_table(guild: discord.Guild, rows: list[dict], title_text: str, start_rank: int = 1) -> discord.File:
    # Layout constants
    rows_to_draw = min(10, len(rows))
    W = 900
    top_margin = 90
    bottom_margin = 48
    row_h = 76  # avatar 64 + spacing
    H = top_margin + rows_to_draw * row_h + bottom_margin

    bg = (22, 27, 34)
    fg = (230, 230, 230)
    accent = (0, 200, 180)
    sub = (170, 180, 190)

    im = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(im)

    title_font = _load_font(36, bold=True)
    name_font  = _load_font(28, bold=True)
    small_font = _load_font(22, bold=False)

    # Header
    draw.text((40, 24), title_text, font=title_font, fill=(210, 240, 240))

    # Scale for bars
    max_count = max((r["thank_count"] for r in rows[:rows_to_draw]), default=1)

    # Pre-fetch avatars (aligned 1:1 with the page rows)
    async with aiohttp.ClientSession() as session:
        avatar_bytes: list[bytes | None] = []
        for r in rows[:rows_to_draw]:
            member = guild.get_member(int(r["user_id"]))
            if member is None:
                try:
                    member = await guild.fetch_member(int(r["user_id"]))
                except Exception:
                    member = None
            if member:
                try:
                    async with session.get(str(member.display_avatar.url)) as resp:
                        avatar_bytes.append(await resp.read())
                except Exception:
                    avatar_bytes.append(None)
            else:
                avatar_bytes.append(None)

    # Draw each row
    y = top_margin
    bar_x = 420
    right_padding = 80
    bar_w = W - bar_x - right_padding
    bar_h = 10

    for j, r in enumerate(rows[:rows_to_draw]):   # j = 0..N-1
        display_rank = start_rank + j              # 1-based absolute rank
        user_id = int(r["user_id"])
        count = int(r["thank_count"])

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None
        display = member.display_name if member else (r.get("name") or f"User {user_id}")

        # Avatar
        if avatar_bytes[j]:
            try:
                pfp = Image.open(io.BytesIO(avatar_bytes[j])).convert("RGB").resize((64, 64))
                im.paste(pfp, (40, y - 8))
            except Exception:
                pass

        # Rank + text
        # Highlight only absolute #1 (first page top); others get neutral color
        rank_color = (255, 193, 7) if display_rank == 1 else (200, 200, 200)
        draw.text((120, y - 18), f"#{display_rank} • {display}", font=name_font, fill=rank_color)
        draw.text((120, y + 12), f"{count} thanks", font=small_font, fill=sub)

        # Progress bar
        max_bar_fraction = 0.85
        pct = 0 if max_count == 0 else min(1.0, count / max_count)
        pct *= max_bar_fraction
        by = y + 20
        draw.rectangle([bar_x, by, bar_x + bar_w, by + bar_h], fill=(60, 70, 80))
        draw.rectangle([bar_x, by, bar_x + int(bar_w * pct), by + bar_h], fill=accent)

        y += row_h

    # Return as attachment
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename="mostthanked.png")



# ---------- DB query helper ----------
def _query_top_thanked(limit: int = 10):
    sql = """
        SELECT thanked_user_id AS user_id,
               MAX(thanked_user_name) AS name,
               COUNT(*) AS thank_count
        FROM thanks
        GROUP BY thanked_user_id
        ORDER BY thank_count DESC
        LIMIT ?
    """
    cur = conn.execute(sql, (limit,))
    rows = cur.fetchall()
    return [{"user_id": r[0], "name": r[1], "thank_count": r[2]} for r in rows]

# ---------- Slash command ----------
@bot.tree.command(name="mostthankedtable", description="Shows a Most Thanked leaderboard as an image.")
@app_commands.describe(month="1-12 (optional)", year="e.g., 2025 (optional)")
async def most_thanked_table(interaction: discord.Interaction, month: int | None = None, year: int | None = None):
    await interaction.response.defer(thinking=True)

    # Validate month/year pairing
    if (month is None) ^ (year is None):
        await interaction.followup.send("Please provide **both** month and year, or neither.", ephemeral=True)
        return
    if month is not None and not (1 <= month <= 12):
        await interaction.followup.send("Month must be between 1 and 12.", ephemeral=True)
        return

    if month and year:
        # Specific month view (no components)
        scope = "month"
        rows = _query_top_thanked_paginated(limit=10, offset=0, scope=scope, month=month, year=year)
        if not rows:
            label = _range_label(scope, month, year)
            await interaction.followup.send(f"No thanks recorded for **{label}**.", ephemeral=True)
            return

        title = f"Most thanked — {_range_label(scope, month, year)}"
        file = await render_most_thanked_table(interaction.guild, rows, title_text=title, start_rank=1)
        embed = discord.Embed(color=discord.Color.teal()).set_image(url="attachment://mostthanked.png")
        await interaction.followup.send(embed=embed, file=file)

    else:
        # All-time view with components (dropdown + pagination)
        view = MostThankedView(interaction.guild, scope="all", page=0)
        # Prime the first render via the same code path used by callbacks
        # (so buttons are properly enabled/disabled)
        limit = 10
        rows = _query_top_thanked_paginated(limit=limit, offset=0, scope="all", month=None, year=None)
        if not rows:
            await interaction.followup.send("No thanks recorded yet.", ephemeral=True)
            return
        total = _count_distinct_thanked(scope="all", month=None, year=None)
        # Set initial disable state
        for item in view.children:
            if isinstance(item, MostThankedView.PrevButton):
                item.disabled = True
            if isinstance(item, MostThankedView.NextButton):
                item.disabled = (len(rows) >= total and len(rows) <= 10)

        title = f"Most thanked — {_range_label('all', None, None)}"
        file = await render_most_thanked_table(interaction.guild, rows, title_text=title)
        embed = discord.Embed(color=discord.Color.teal()).set_image(url="attachment://mostthanked.png")
        await interaction.followup.send(embed=embed, file=file, view=view)


# --- Delete to here

token = os.getenv('DISCORD_TOKEN')
bot.run(token)
