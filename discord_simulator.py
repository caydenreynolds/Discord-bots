import os 
from functools import wraps
from discord.ext import commands
from discord.utils import find

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ARRAY, String

Base = declarative_base()
engine = create_engine(os.getenv('SIMULATOR_DB'))
Session = sessionmaker(bind=engine)

def ProbabilityTupleFactory(member):
    class ProbabilityTuple(Base):
        __tablename__ = f'probabilities_{member.id}_{member.guild.id}'
        id = Column(Integer, primary_key=True)
        node_id = Column(Integer)
        probability = Column(Integer)

    Base.metadata.create_all()
    session = Session()
    session.query(PresentMembers).filter_by(user_id=member.id, guild=member.guild.id).one_or_none() or\
        session.add(PresentMembers(user_id=member.id, guild=member.guild.id))
    session.commit()
    session.close()
    return ProbabilityTuple

def MarkovNodeFactory(member):
    class MarkovNode(Base):
        __tablename__ = f'nodes_{member.id}_{member.guild.id}'
        id = Column(Integer, primary_key=True)
        word = Column(String)
        count = Column(BigInteger)
        probabilities = ARRAY(ProbabilityTupleFactory(member))
    return MarkovNode

    Base.metadata.create_all()

class PresentMembers(Base):
    __tablename__ = 'present_member'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    guild = Column(Integer)

#Initialize database
#node id 1 is a special node that signifies the end of the message
def init_db():
    Base.metadata.create_all(engine)
    session = Session()
    try:
        if not session.query(MarkovNode).filter_by(id=1).one_or_none():
            session.add(MarkovNode())
    finally:
        session.commit()
        session.close()

def increment_words(member, message):
    session = Session()
    sim_member = session.query(SimulatedMember).filter_by(user_id=member.id, guild=member.guild.id).one_or_none() or\
                SimulatedMember(member.id, member.guild)
    
    for i in range(len(message)-1):
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

"""Ensure we never record bot messages"""
def check_user(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if args[0].author.bot:
            return
        else:
            await func(*args, **kwargs)
    return wrapper

TOKEN = os.getenv('SIMULATOR_TOKEN')
bot = commands.Bot(command_prefix='-sim-')

# @bot.event
# @check_user
# async def on_message(message):
#     content = message.content.lower()
#     message_words = content.split()
#     message_triplets = []
#     for index in range(len(message_words)-2):
#         message_triplets.append(' '.join(message_words[index:index+3]).strip())
#     for line in lines:
#         for triplet in message_triplets:
#             if triplet in line:
#                 increment_snipes(message.author)
#                 await message.channel.send(line)
#                 return
#     await bot.process_commands(message)

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

init_db()
print("Starting up...")
bot.run(TOKEN)