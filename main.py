import discord
from discord.ext import commands
from discord import ButtonStyle
from discord.ui import Button, View
import sqlite3
import os
from dotenv import load_dotenv
import time
from datetime import datetime, timedelta
import calendar

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

# Add a game
@bot.tree.command(name="addgame", description="Adds a new game with optional description and guide URL.")
async def add_game(interaction: discord.Interaction, game_name: str, description: str = None, guide_url: str = None):
    try:
        c.execute("INSERT INTO games (game_name, description, guide_url) VALUES (?, ?, ?)", (game_name, description, guide_url))
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


# Show the helpers for a specific game
@bot.tree.command(name="showgame", description="Shows detailed information about a specific game, including guide and helpers.")
async def show_game(interaction: discord.Interaction, game_name: str):
    # Fetch game info
    c.execute("SELECT id, description, guide_url FROM games WHERE game_name = ?", (game_name,))
    game = c.fetchone()

    if not game:
        await interaction.response.send_message(f"Game '{game_name}' not found.")
        return

    game_id, description, guide_url = game

    # Fetch helpers
    c.execute("SELECT user_name, status FROM helpers WHERE game_id = ?", (game_id,))
    helpers = c.fetchall()

    # Format helper list
    if helpers:
        helper_list = "\n".join([
            f"{user} {'🟢' if status == 'green' else '🟠' if status == 'amber' else '🔴'}"
            for user, status in helpers
        ])
    else:
        helper_list = "No helpers yet."

    # Format guide display
    guide_display = f"[Guide]({guide_url})" if guide_url else "No guide available."

    # Build and send the response
    await interaction.response.send_message(
        f"**Game Name:** {game_name}\n"
        f"**Description:** {description if description else 'No description'}\n"
        f"**Guide:** {guide_display}\n"
        f"**Helpers:**\n{helper_list}"
    )


# Command: Show all games with helpers in alphabetical order
@bot.tree.command(name="gameswithhelp", description="Displays all games with help or guides.")
async def games_with_help(interaction: discord.Interaction):
    c.execute('''
        SELECT DISTINCT g.game_name, g.guide_url
        FROM games g
        LEFT JOIN helpers h ON g.id = h.game_id
        WHERE h.game_id IS NOT NULL OR g.guide_url IS NOT NULL
        ORDER BY g.game_name ASC
    ''')
    games = c.fetchall()
    if games:
        game_list = "\n".join([
            f"{game[0]} {'📘' if game[1] else ''}" for game in games
        ])
        await interaction.response.send_message(f"Games with help or guides:\n{game_list}")
    else:
        await interaction.response.send_message("No games currently have help or guides.")



# Command: Show bot version and information
@bot.tree.command(name="botversion", description="Displays the bot's version and additional information.")
async def bot_version(interaction: discord.Interaction):
    version_info = """
    **Bot Version:** 1.1
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

    
@bot.tree.command(name="givethanks", description="Give thanks to another user for their help.")
async def give_thanks(interaction: discord.Interaction, 
                      user: discord.Member, 
                      game: str = None, 
                      message: str = None):
    thanking_user_id = str(interaction.user.id)
    thanking_user_name = str(interaction.user)
    thanked_user_id = str(user.id)
    thanked_user_name = str(user)

    # Prevent self-thanks
    if thanking_user_id == thanked_user_id:
        await interaction.response.send_message("You can't thank yourself!", ephemeral=True)
        return

    # Insert into database
    c.execute('''INSERT INTO thanks (thanked_user_id, thanked_user_name, thanking_user_id, thanking_user_name, game, message)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (thanked_user_id, thanked_user_name, thanking_user_id, thanking_user_name, game, message))
    conn.commit()

    response_message = f"{interaction.user.mention} thanked {user.mention}!"
    if game:
        response_message += f"\n**Game:** {game}"
    if message:
        response_message += f"\n**Message:** {message}"
    
    await interaction.response.send_message(response_message)
    
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
                 LIMIT 5'''
    
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


token = os.getenv('DISCORD_TOKEN')
bot.run(token)
