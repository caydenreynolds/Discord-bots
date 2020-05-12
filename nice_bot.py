import os 
import discord
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('NICE_TOKEN')
client = discord.Client()

@client.event
async def on_message(message):
    if '69' in message.content:
        await message.channel.send('Nice')

client.run(TOKEN)