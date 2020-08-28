"""I'd like to be notified when my device's ip address changes, because the network here doesn't allow me to connect via hostname"""
import os
import socket
import traceback

import discord
from discord.ext import commands
from sqlalchemy import Column, Integer, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from bot_utils import BaseMixin

POLL_FREQUENCY = 60
bot = commands.Bot(command_prefix='-ip-', description="I only exist to notify you when my ip address changes\nFor suggestions and bug reports, create an issue on my github: https://github.com/caydenreynolds/Discord-bots")

Base = declarative_base()
engine = create_engine(os.getenv('IP_DB'))
Session = sessionmaker(bind=engine)

class Channel(BaseMixin, Base):
    channel_id = Column(Integer)

Base.metadata.create_all(engine)

ip_addr = ""

class PollIPCog(commands.Cog):
    def __init__(self):
        self.poll_ip.start()

    @tasks.loop(seconds=POLL_FREQUENCY)
    async def poll_ip(self):
        try:
            await bot.wait_until_ready()
            session = Session()
            hostname = socket.gethostname()
            if socket.gethostbyname(hostname) != ip_addr:
                ip_addr = socket.gethostbyname(hostname)
                channels = []
                for channel in session.query(Channel).all():
                    c = bot.get_channel(channel.channel_id)
                    if c:
                        channels.append(c)
                    else:
                        session.delete(channel)
                message = f"My new IP addr is {ip_addr}" 
                for channel in channels:
                    await channel.send(message)
        except Exception:
            traceback.print_exc()
            session.rollback()
        else:
            session.commit()
        finally:
            session.close()

@bot.command(name='notify', help="Begin notifications in this channel")
async def schedule(ctx, *args):
    session = Session()
    if len(args) == 0:
        if session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none():
            await ctx.channel.send("Notifications are already scheduled")
        else:
            await ctx.channel.send("Scheduling notifications in this channel!")
            session.add(Channel(channel_id=ctx.channel.id))
    elif args[0] == 'stop' and session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none():
        session.query(Channel).filter_by(channel_id=ctx.channel.id).delete()
        await ctx.channel.send("Stopping notifications in this channel!")
    else:
        await ctx.channel.send("I don't quite understand you. Did you mean '-ip-notify stop'?")

    session.commit()
    session.close()

bot.add_cog(PollIPCog())
TOKEN = os.getenv('IP_TOKEN')
bot.run(TOKEN)
