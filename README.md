# Haven's Helper 
Haven's Helper is a Discord bot designed to connect gamers with helpers willing to share their expertise and guide others through various games. Whether you're looking to master challenging Easter eggs, tackle tough boss fights, or learn the ropes of a new game, Haven's Helper makes it easy to find and manage a network of gaming assistance.

Key Features:
- Game Management: Add, update, rename, or remove games with detailed descriptions.
- Helper Registration: Users can sign up as helpers for specific games and display their availability status (Green: Available, Amber: Limited, Red: Unavailable).
- Helper Discovery: Quickly find helpers for games and see what kind of assistance they offer.
- Status Tracking: Easily set and manage your availability as a helper.
- Thanks and Feedback: Users can express gratitude to helpers with optional game and message details, while helpers can view feedback and track their thanks count.
- Leaderboard & Insights: View top helpers and discover which games lack assistance.
- Transparency: Logs track all bot activities for accountability.

Example Use Case:

**Game Name:** Call of Duty: Black Ops 4  
**Help Offered:** All Easter Egg Runs  
**Helpers:** Tide 🟢

Whether you're a completionist or just need a helping hand, Haven's Helper is your go-to bot for fostering a supportive gaming community!

## Commands Overview:

### Game Management:
- /addgame `"game name"` [description] - Adds a new game to the list, with an optional description.
- /updatedescription `"game name"` `"description"` - Updates the description for an existing game.
- /removegame `"game name"` - Removes a game from the list.
- /renamegame `"old game name"` `"new game name"` - Renames a game if there’s an error or update needed.

### Helper Management:
- /addme `"game name"` - Registers yourself as a helper for a specific game.
- /removeme `"game name"` - Removes yourself as a helper for a game.
- /setstatus `"status"` - Sets your availability status:
- 🟢 Green: Available
- 🟠 Amber: Limited Availability
- 🔴 Red: Unavailable.

### Insights and Discovery:
- /showme - Displays all the games you’re helping with.
- /showuser `"@user"` - Displays what games a specific user is helping with.
- /nothelped - Displays games that currently lack helpers.
- /tophelper - Shows a leaderboard of users helping with the most games.
- /showgame `"game name"` - Shows detailed information about a specific game, including its description and helpers.
- /gameswithhelp - Displays all games that currently have help offered, sorted alphabetically.

### Thanks and Feedback:
- /givethanks `"@user"` [Game] [Message] - Give thanks to another user for their help, with optional game and message details. (Cannot thank yourself.)
- /mostthanked [Month] [Year] - Shows the most thanked users, either all-time or for a specific month and year.
- /showfeedback `"@user"` - Displays the last 10 feedback messages received by a specific user.

### Bot Information:
- /botversion - Displays the bot’s version and additional information.
- /help - Displays a list of all available commands.
- /healthcheck - Checks the bot’s status and health.
