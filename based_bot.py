import os
import discord
import random
from bot_utils import ignore_bots

TOKEN = os.getenv('BASED_TOKEN')
client = discord.Client()

response = "Based"

@client.event
@ignore_bots
async def on_message(message):
    if random.randint(0, 1000) == 0:
        await message.channel.send(response)

client.run(TOKEN)

