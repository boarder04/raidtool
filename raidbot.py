import discord
from discord.ext import commands
from discord.ui import Button, View
from collections import Counter
import asyncio
import sqlite3
import datetime
import random
import config

intents = discord.Intents.default()
intents.messages = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)

# Global variable to store the current raid ID and roll sessions
current_raid_id = None
roll_sessions = {}  


# Initialize the database and create tables if they don't exist
def initialize_db():
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS raids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time DATETIME,
            end_time DATETIME,
            status TEXT
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raid_id INTEGER,
            name TEXT,
            winner_user_id TEXT,
            winner_username TEXT,
            contested BOOLEAN DEFAULT 1,           
            FOREIGN KEY (raid_id) REFERENCES raids(id)
        )''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS rolls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            user_id INTEGER,
            roll_type TEXT,
            random_roll_value INTEGER,           
            FOREIGN KEY (item_id) REFERENCES items(id)
        )''')


def create_raid(start_time, status='active'):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO raids (start_time, status) VALUES (?, ?)", (start_time, status))
        return cursor.lastrowid

def start_new_raid():
    start_time = datetime.datetime.now().isoformat()
    global current_raid_id
    current_raid_id = create_raid(start_time)
    print(f"Raid automatically started with ID: {current_raid_id}")

def create_item(raid_id, name):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO items (raid_id, name) VALUES (?, ?)", (raid_id, name))
        item_id = cursor.lastrowid
        conn.commit()
        print(f"Created item with ID: {item_id}") 
        return item_id
    
class WinnerSelectView(discord.ui.View):
    def __init__(self, options, item_id, message):
        super().__init__()
        self.select = WinnerSelect(options=options, item_id=item_id, message=message) 
        self.add_item(self.select)


class WinnerSelect(discord.ui.Select):
    def __init__(self, options, item_id, message):
        super().__init__(placeholder="Choose a winner...", options=options)
        self.item_id = item_id
        self.message = message

    async def callback(self, interaction: discord.Interaction):
        user_id = self.values[0]
        user = await interaction.guild.fetch_member(int(user_id))
        username = user.display_name
        
        #Database update for selected winner
        update_winner_in_db(self.item_id, user_id, username, contested = 1)
        
        #Disable menu after use
        self.disabled = True

        item_name = fetch_item_name(self.item_id)
        
        # Fetch rolls and regenerate the roll results list with the correct user in bold
        rolls = fetch_rolls(self.item_id)
        rolls_with_wins = []
        for roll in rolls:
            roll_user_id, roll_type, random_roll_value = roll
            roll_user = await interaction.guild.fetch_member(roll_user_id)
            roll_username = roll_user.display_name
            win_count = count_wins(current_raid_id, roll_user_id, roll_type)
            is_winner = roll_user_id == int(user_id)
            rolls_with_wins.append({
                'user_id': roll_user_id,
                'name': f"**{roll_username}**" if is_winner else roll_username,
                'roll_type': roll_type,
                'random_roll_value': random_roll_value,
                'win_count': win_count-1 if is_winner else win_count
            })

        rolls_with_wins.sort(key=lambda x: (x['roll_type'] == 'Standard', x['win_count'], -x['random_roll_value']))
        roll_results = "\n".join([f"{roll['name']} - {roll['roll_type']} Roll: {roll['random_roll_value']} (Wins: {roll['win_count']})"
                                  for roll in rolls_with_wins])


        # Update the original message with the new winner highlighted
        await self.message.edit(content=f"Item: {item_name}\nItem ID: {self.item_id}\nRolls:\n{roll_results}\n\n{username} has been updated as the winner", view=None)
        await interaction.response.edit_message(content=f"{username} has been updated as the winner!", view=self.view)



        
class SelectWinnerButton(discord.ui.Button):
    def __init__(self, label, style, custom_id, session, message):
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.session = session
        self.message = message
        
    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.session.initiator.id:
            # Inform the user they're not authorized if they're not the session initiator
            await interaction.response.send_message("You're not authorized to select the winner.", ephemeral=True)
            return

        # Use the options stored in the session to create the WinnerSelect dropdown
        view = WinnerSelectView(options=self.session.options, item_id=self.session.item_id, message=self.message)


        # Respond with the dropdown in an ephemeral message
        await interaction.response.send_message("Please select the winner:", view=view, ephemeral=True)




def insert_roll(item_id, user_id, roll_type):
    random_roll_value = random.randint(1, 10000)
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rolls (item_id, user_id, roll_type, random_roll_value) VALUES (?, ?, ?, ?)
        """, (item_id, user_id, roll_type, random_roll_value))
        conn.commit()
        
def update_winner_in_db(item_id, winner_id, winner_name, contested=1):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE items 
            SET winner_user_id = ?, winner_username = ?, contested = ? 
            WHERE id = ?
        """, (winner_id, winner_name, contested, item_id))
        conn.commit()
        
def fetch_rolls(item_id):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT user_id, roll_type, random_roll_value
            FROM rolls
            WHERE item_id = ? AND roll_type != 'cancelled'
            ORDER BY roll_type DESC, random_roll_value DESC
        """, (item_id,))
        return cursor.fetchall()

def fetch_item_name(item_id):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM items WHERE id = ?", (item_id,))
        item_name = cursor.fetchone()
        if item_name:
            return item_name[0]
        else:
            return None

def count_wins(current_raid_id, user_id, roll_type):
    """Count the number of wins for the given user_id within the current raid based on roll_type."""
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT items.id)
            FROM items
            JOIN rolls ON items.id = rolls.item_id
            WHERE items.winner_user_id = ? 
            AND items.raid_id = ? 
            AND rolls.roll_type = ? 
            AND rolls.user_id = items.winner_user_id
            AND items.contested = 1
        """, (user_id, current_raid_id, roll_type))
        win_count = cursor.fetchone()[0]
        return win_count
    
def has_priority_win(current_raid_id, user_id):
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM items
            INNER JOIN rolls ON items.id = rolls.item_id
            WHERE items.raid_id = ? AND rolls.user_id = ? AND rolls.roll_type = 'priority_roll' AND items.winner_user_id = ?
        """, (current_raid_id, user_id, user_id))
        win_count = cursor.fetchone()[0]
        return win_count > 0

class RollSession:
    def __init__(self, item_name, classes, ctx, time, item_id, initiator):
        self.item_name = item_name
        self.classes = classes
        self.ctx = ctx
        self.time = time
        self.item_id = item_id
        self.priority_rolls = {}
        self.standard_rolls = {}
        self.message = None
        self.initiator = initiator
        self.combined_rolls = []
        self.selected_winner_id = None
        
        self.priority_roll_button = Button(label="Priority Roll", style=discord.ButtonStyle.green, custom_id="priority_roll")
        self.standard_roll_button = Button(label="Standard Roll", style=discord.ButtonStyle.blurple, custom_id="standard_roll")
        self.leave_button = Button(label="Leave", style=discord.ButtonStyle.red, custom_id="leave")

        self.priority_roll_button.callback = self.handle_roll
        self.standard_roll_button.callback = self.handle_roll
        self.leave_button.callback = self.handle_roll
        
    def get_roll_name(self, roll_type):
        """Convert a roll_type to a user-friendly name."""
        return {
            'priority_roll': 'Priority Roll',
            'standard_roll': 'Standard Roll'
        }.get(roll_type, roll_type)  # Fallback to the raw roll_type value

    async def handle_roll(self, interaction: discord.Interaction):
        roll_type = interaction.data['custom_id']
        user_id = interaction.user.id
        roll_name = self.get_roll_name(roll_type)
        
        if roll_type == "leave":
            # User chose to leave; delete their roll from the database
            with sqlite3.connect('raidbot.db') as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM rolls
                    WHERE item_id = ? AND user_id = ?
                """, (self.item_id, user_id))
                conn.commit()
            self.priority_rolls.pop(user_id, None)
            self.standard_rolls.pop(user_id, None)
            response = "You have left the roll."
        else:
            # Determine if the user is attempting a priority roll and has previously won with a priority roll
            if roll_type == 'priority_roll' and has_priority_win(current_raid_id, user_id):
                roll_type = 'standard_roll'  # Change their roll to a standard roll
                item_name = fetch_item_name(self.item_id)  
                response = f"You already won {item_name} with a Priority Roll, your roll has been updated to a Standard Roll."
            else:
                if not user_id in self.priority_rolls and not user_id in self.standard_rolls:
                    insert_roll(self.item_id, user_id, roll_type)
                    response = f"You successfully submitted a {roll_name}."
                    if roll_type == 'priority_roll':
                        self.priority_rolls[user_id] = interaction.user.display_name
                    elif roll_type == 'standard_roll':
                        self.standard_rolls[user_id] = interaction.user.display_name
                else:
                    response = "You have already submitted a roll."
                pass
            
        await interaction.response.send_message(response, ephemeral=True)

    async def start(self):
        view = View()
        view.add_item(self.priority_roll_button)
        view.add_item(self.standard_roll_button)
        view.add_item(self.leave_button)
        self.message = await self.ctx.respond(f"Now Rolling: {self.item_name}\nThe following may bid: {self.classes}", view=view)

        await asyncio.sleep(self.time)
        await self.end_roll()

    async def end_roll(self):
        # Fetch rolls from the database
        combined_rolls_list = fetch_rolls(self.item_id)
        
        # Determine if the item is contested
        is_contested = 0 if len(combined_rolls_list) == 1 else 1

        # Enrich rolls with usernames from Discord and win counts
        rolls_with_wins = [] 
        for user_id, roll_type, random_roll_value in combined_rolls_list:
            user = await self.ctx.bot.fetch_user(user_id)
            username = user.display_name
            win_count = count_wins(current_raid_id, user_id, roll_type)
            rolls_with_wins.append({
                'user_id': user_id,
                'name': username,
                'roll_type': roll_type,
                'random_roll_value': random_roll_value,
                'win_count': win_count
            })

        # Sort: by roll type (Priority first), then by wins (ascending), and then by random_roll_value (descending)
        rolls_with_wins.sort(key=lambda x: (x['roll_type'] == 'Standard', x['win_count'], -x['random_roll_value']))

        # Prepare options for WinnerSelectView with updated list
        options = [discord.SelectOption(label=f"{roll['name']}", value=str(roll['user_id'])) for roll in rolls_with_wins]
        self.options = [discord.SelectOption(label=f"{roll['name']}", value=str(roll['user_id'])) for roll in rolls_with_wins]

        # Generate display-friendly string for roll results
        roll_results = "\n".join([
            f"**{roll['name']}** - {self.get_roll_name(roll['roll_type'])} Roll: {roll['random_roll_value']} (Wins: {roll['win_count']})" 
            if idx == 0 
            else f"{roll['name']} - {self.get_roll_name(roll['roll_type'])} Roll: {roll['random_roll_value']} (Wins: {roll['win_count']})"
            for idx, roll in enumerate(rolls_with_wins)
        ])

        # Update the database with the default winner's information
        if rolls_with_wins:
            default_winner = rolls_with_wins[0]
            update_winner_in_db(self.item_id, default_winner['user_id'], default_winner['name'], is_contested)

        # Define and add the "Select Winner" button
        select_winner_button = SelectWinnerButton(label="Update Winner", style=discord.ButtonStyle.green, custom_id="select_winner", session=self, message=self.message)
        view = discord.ui.View()
        view.add_item(select_winner_button)
        
        # Update the message to show the button
        await self.message.edit(content=f"Now Rolling: {self.item_name}\nThe following may bid: {self.classes}\nRolls:\n{roll_results}", view=view)

@bot.event
async def on_ready():
    print(f'Bot logged in as {bot.user}')
    initialize_db()  # Ensure the database is initialized when the bot starts

@bot.slash_command(name="startraid", description="Start a new raid")
async def start_raid(ctx):
    global current_raid_id
    if current_raid_id is not None:
        await ctx.respond("There is already an active raid. Please end the current raid before starting a new one.")
        return
    
    start_new_raid()
    await ctx.respond(f"Raid started with ID: {current_raid_id}")

@bot.slash_command(name="roll", description="Start a roll for an item")
async def roll(ctx, item_name: str, classes: str, time: int):
    global current_raid_id
    if current_raid_id is None:
        start_new_raid()
    
    item_id = create_item(current_raid_id, item_name)
    initiator = ctx.author
    session = RollSession(item_name, classes, ctx, time, item_id, initiator)
    print(f"Roll session started for item ID: {item_id}") 
    roll_sessions[ctx.interaction.id] = session
    await session.start()
    
@bot.slash_command(name="endraid", description="End the current raid")
async def end_raid(ctx):
    global current_raid_id
    if current_raid_id is None:
        await ctx.respond("No active raid to end.")
        return
    
    # Update the raid's status in the database
    with sqlite3.connect('raidbot.db') as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE raids SET status = ?, end_time = datetime('now') WHERE id = ?", ('ended', current_raid_id))
        conn.commit()

    current_raid_id = None  # Reset current raid ID to indicate no active raid
    await ctx.respond("Raid ended successfully.")


bot.run(config.TOKEN)