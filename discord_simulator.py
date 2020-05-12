import os 
from functools import wraps
from discord.ext import commands
from discord.utils import find

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ARRAY

Base = declarative_base()
engine = create_engine(os.getenv('SIMULATOR_DB'))
Session = sessionmaker(bind=engine)

class MarkovNode(Base):
    __tablename__ = 'nodes'
    id = Column(Integer, primary_key=True)
    word = Column(String)
    count = Column(BigInteger)
    next = ARRAY(Integer)
    next_count = ARRAY(Integer)

Base.metadata.create_all(engine)

def increment_snipes(member):
    session = Session()
    db_member = session.query(BeeSting).filter_by(user_id=member.id, guild=member.guild.id).one_or_none() or\
                BeeSting(user_id=member.id, sting_count=0, guild=member.guild.id)
    try:
        session.add(db_member)
    except Exception:
        pass
    db_member.sting_count += 1
    session.commit()
    session.close()

def get_stings(member):
    if not member:
        return f"I can't find that user"
    session = Session()
    try:
        db_member = session.query(BeeSting).filter_by(user_id=member.id, guild=member.guild.id).one()
    except Exception:
        return f"{member.nick or member.name} has not been stung yet"
    else:
        member_stings = db_member.sting_count
        leaderboard = get_leaderboard(session, member.guild)
        total = len(leaderboard)
        place = [user.user_id for user in leaderboard].index(member.id)
        return f'{member.nick or member.name} has been stung {member_stings} times. They are ranked {place+1} out of {total}'
    finally:
        session.commit()
        session.close()

def get_leaderboard(session, guild):
    return session.query(BeeSting).filter_by(guild=guild.id).order_by(BeeSting.sting_count.asc()).all()

"""Ensure we never reply to our own messages"""
def check_user(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if args[0].author == bot.user:
            return
        else:
            await func(*args, **kwargs)
    return wrapper

TOKEN = os.getenv('BEE_TOKEN')

bot = commands.Bot(command_prefix='-bee-')

@bot.event
@check_user
async def on_message(message):
    content = message.content.lower()
    message_words = content.split()
    message_triplets = []
    for index in range(len(message_words)-2):
        message_triplets.append(' '.join(message_words[index:index+3]).strip())
    for line in lines:
        for triplet in message_triplets:
            if triplet in line:
                increment_snipes(message.author)
                await message.channel.send(line)
                return
    await bot.process_commands(message)

@bot.command(name='stings', help="See how many times you've been stung. Give me user's name to inspect them instead")
async def snipes(ctx, *args):
    if len(args) == 0:
        await ctx.channel.send(get_stings(ctx.author))
    else:
        await ctx.channel.send(get_stings(find(lambda m: m.nick == args[0] if m.nick else m.name == args[0], ctx.guild.members)))

@bot.command(name="ranking", help="See the sting rankings")
async def leaderboard(ctx):
    session = Session()
    leaderboard = get_leaderboard(session, ctx.guild)
    t = PrettyTable(['Ranking', 'Name', 'Stings'])
    for i in range(len(leaderboard)):
        member = find(lambda m: m.id == leaderboard[i].user_id, ctx.guild.members)
        t.add_row([i+1, member.nick or member.name, leaderboard[i].sting_count])
    await ctx.channel.send(t)

@bot.event
async def on_command_error(ctx, exception):
    await ctx.channel.send("I'm sorry, I don't understand that command")
    raise exception

print("Starting up...")
bot.run(TOKEN)