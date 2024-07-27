import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Button, View
import json
from datetime import datetime, timedelta
import pickle
import re

# Load the configuration from the JSON file
with open('config.json') as config_file:
    config = json.load(config_file)

# Load message counts and votes from files
try:
    with open('message_counts.json') as message_counts_file:
        message_counts = json.load(message_counts_file)
except FileNotFoundError:
    message_counts = {}

try:
    with open('votes.pkl', 'rb') as votes_file:
        user_votes = pickle.load(votes_file)
except FileNotFoundError:
    user_votes = {}

intents = discord.Intents.default()
intents.message_content = True
intents.guild_messages = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

muted_users = {}

# Save message counts to a JSON file
def save_message_counts():
    with open('message_counts.json', 'w') as message_counts_file:
        json.dump(message_counts, message_counts_file, indent=4)

def save_votes():
    with open('votes.pkl', 'wb') as votes_file:
        pickle.dump(user_votes, votes_file)


# Slash Command: stats
@bot.tree.command(name="stats", description="Show various stats for a user")
@app_commands.describe(user="The user to get stats for")
async def stats_slash(interaction: discord.Interaction, user: discord.User):
    user_id = str(user.id)
    user_data = message_counts.get(user_id, {'total': 0})

    # Fetch user joined date
    member = interaction.guild.get_member(user.id)
    if member and member.joined_at:
        joined_at = member.joined_at.strftime('%m/%d/%Y')
    else:
        joined_at = 'N/A'
        
    formatted_username = user.name.capitalize()

    embed = discord.Embed(
        title="User Stats",
        color=discord.Color.blue()
    )
    embed.add_field(name="Username", value=formatted_username, inline=True)
    embed.add_field(name="Total Messages Sent", value=str(user_data.get('total', 0)), inline=True)
    embed.add_field(name="Joined Server On", value=joined_at, inline=True)

    embed.set_footer(text="Stats Bot")

    await interaction.response.send_message(embed=embed)

# Slash Command: suggest
@bot.tree.command(name="suggest", description="Submit a suggestion")
@app_commands.describe(title="The title of the suggestion", description="The description of the suggestion")
async def suggest_slash(interaction: discord.Interaction, title: str, description: str):
    # Validate title and description
    if len(title) < 5 or len(title) > 50:
        await interaction.response.send_message("The title must be between 5 and 50 characters long.", ephemeral=True)
        return
    
    if len(description) < 10 or len(description) > 500:
        await interaction.response.send_message("The description must be between 10 and 500 characters long.", ephemeral=True)
        return

    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.orange()
    )
    embed.add_field(name="👍 Up Votes", value="0 (0.00%)", inline=False)
    embed.add_field(name="👎 Down Votes", value="0 (0.00%)", inline=False)
    embed.add_field(name="Vote Distribution", value="No votes yet.", inline=False)

    view = SuggestionView()
    await interaction.response.send_message(embed=embed, view=view)

# Suggestion Button View
class SuggestionView(View):
    def __init__(self):
        super().__init__()
        self.user_votes = user_votes  # Track user votes per message

    def generate_bar(self, up_votes, down_votes):
        total_votes = up_votes + down_votes
        if total_votes == 0:
            up_vote_percentage = 0.00
            down_vote_percentage = 0.00
        else:
            up_vote_percentage = (up_votes / total_votes) * 100
            down_vote_percentage = (down_votes / total_votes) * 100
        
        bar_length = 20
        bar_filled_length = int((up_vote_percentage / 100) * bar_length)
        bar_empty_length = bar_length - bar_filled_length
        bar = f"{'█' * bar_filled_length}{'░' * bar_empty_length}"
        return bar, f"👍 {up_vote_percentage:.2f}% | 👎 {down_vote_percentage:.2f}%"

    async def update_embed(self, message, up_vote_count, down_vote_count):
        try:
            vote_bar, vote_distribution = self.generate_bar(up_vote_count, down_vote_count)
            
            embed = message.embeds[0]
            embed.set_field_at(0, name="👍 Up Votes", value=f"{up_vote_count} ({vote_distribution.split('|')[0].split()[1]})", inline=False)
            embed.set_field_at(1, name="👎 Down Votes", value=f"{down_vote_count} ({vote_distribution.split('|')[1].split()[1]})", inline=False)
            embed.set_field_at(2, name="Vote Distribution", value=vote_bar, inline=False)
            
            await message.edit(embed=embed)
        except Exception as e:
            print(f"An error occurred while updating embed: {e}")
            await message.channel.send("An error occurred while updating the suggestion.")
        
    @discord.ui.button(label="👍", style=discord.ButtonStyle.green, custom_id="thumbs_up")
    async def thumbs_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        message = interaction.message
        message_id = str(message.id)
        
        # Retrieve current vote status
        user_vote = self.user_votes.get(message_id, {}).get(user_id)
        embed = message.embeds[0]
        thumbs_up_count = int(embed.fields[0].value.split(" ")[0])
        thumbs_down_count = int(embed.fields[1].value.split(" ")[0])

        # Update counts based on previous vote
        if user_vote == 'thumbs_down':
            thumbs_down_count -= 1
        elif user_vote == 'thumbs_up':
            await interaction.response.send_message("You have already voted thumbs up.", ephemeral=True)
            return

        thumbs_up_count += 1

        # Update vote record
        if message_id not in self.user_votes:
            self.user_votes[message_id] = {}
        self.user_votes[message_id][user_id] = 'thumbs_up'

        await self.update_embed(message, thumbs_up_count, thumbs_down_count)
        save_votes()  # Save votes to file
        await interaction.response.send_message("You voted thumbs up!", ephemeral=True)

    @discord.ui.button(label="👎", style=discord.ButtonStyle.red, custom_id="thumbs_down")
    async def thumbs_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        message = interaction.message
        message_id = str(message.id)

        # Retrieve current vote status
        user_vote = self.user_votes.get(message_id, {}).get(user_id)
        embed = message.embeds[0]
        thumbs_up_count = int(embed.fields[0].value.split(" ")[0])
        thumbs_down_count = int(embed.fields[1].value.split(" ")[0])

        # Update counts based on previous vote
        if user_vote == 'thumbs_up':
            thumbs_up_count -= 1
        elif user_vote == 'thumbs_down':
            await interaction.response.send_message("You have already voted thumbs down.", ephemeral=True)
            return

        thumbs_down_count += 1

        # Update vote record
        if message_id not in self.user_votes:
            self.user_votes[message_id] = {}
        self.user_votes[message_id][user_id] = 'thumbs_down'

        await self.update_embed(message, thumbs_up_count, thumbs_down_count)
        save_votes()  # Save votes to file
        await interaction.response.send_message("You voted thumbs down!", ephemeral=True)

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')
    await bot.tree.sync()

bot.run(config['token'])