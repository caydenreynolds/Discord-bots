import os 
from discord.ext import commands
from discord.utils import find

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, String

from bot_utils import ignore_bots

Base = declarative_base()
engine = create_engine(os.getenv('SIMULATOR_DB'))
Session = sessionmaker(bind=engine)

def ProbabilityTupleFactory(member):
    class ProbabilityTuple(Base):
        __tablename__ = f'probabilities_{member.id}_{member.guild.id}'
        id = Column(Integer, primary_key=True)
        parent_id=Column(Integer, ForeignKey(f'nodes_{member.id}_{member.guild.id}.id'))
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
        probabilities = relationship(f'probabilities_{member.id}_{member.guild.id}')

        def __init__(self, word='', count=0, probabilities=[], session=0, ProbabilityTuple=None, MarkovNode=None):
            if probabilities == []:
                probabilities.append(ProbabilityTuple(node_id=MarkovNode.get_end_node(session).id, count=0))
            elif probabilities is None:
                probabilities = []
            self.probabilities.extend(probabilities)
            
            self.count = count
            self.word = word

        def increase_word_count(self, word, session, MarkovNode, ProbabilityTuple):
            self.count += 1

            node = MarkovNode.get_node(word, session, ProbabilityTuple)
            node_ids = [pt.node_id for pt in self.probabilities]
            if node.id in node_ids:
                i = node_ids.index(node.id)
                self.probabilities[i].probability += 1

        def increase_end_node_count(self):
                self.count += 1
                self.probabilities[0].probability += 1

        def is_start_node(self):
            return self.id == 1

        def is_end_node(self):
            return self.id == 2

        @classmethod
        def get_node(cls, word, session, ProbabilityTuple):
            return session.query(session.query(cls).filter_by(word=word).one_or_none() or\
                session.add(cls(word=word, count=0, session=session, ProbabilityTuple=ProbabilityTuple, MarkovNode=cls)))
        @classmethod
        def get_start_node(cls, session):
            return session.query(cls).filter_by(id=1).one()

        @classmethod
        def get_end_node(cls, session):
            return session.query(cls).filter_by(id=2).one()

    Base.metadata.create_all()
    session = Session()
    #Nodes id 1 and 2 are the start and end nodes, respectively
    session.query(MarkovNode).filter_by(id=1).one_or_none() or\
        session.add(MarkovNode(count=0, probabilities=None))
    session.query(MarkovNode).filter_by(id=2).one_or_none() or\
        session.add(MarkovNode(count=0, probabilities=None))
    return MarkovNode

class PresentMembers(Base):
    __tablename__ = 'present_member'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    guild = Column(Integer)

Base.metadata.create_all(engine)

def increment_words(member, message):
    session = Session()
    MarkovNode = MarkovNodeFactory(member)
    ProbabilityTuple = ProbabilityTupleFactory(member)

    message_words = message.split()
    MarkovNode.get_start_node(session).increase_word_count(message_words[0], session, MarkovNode, ProbabilityTuple)
    for i in range(len(message_words)-1):
        if i == 0:
            continue
        node = MarkovNode.get_node(message_words[i], session, ProbabilityTuple)
        node.increase_word_count(message_words[i+1], session, MarkovNode, ProbabilityTuple)
        
    MarkovNode.get_node(message_words[-1], session, ProbabilityTuple).increase_end_node_count()
    session.commit()
    session.close()

TOKEN = os.getenv('SIMULATOR_TOKEN')
bot = commands.Bot(command_prefix='-sim-', description="I am a horrible, twisted version of your guild. FEAR ME.\nFor suggestions and bug reports, create an issue on my github: https://github.com/caydenreynolds/Discord-bots")

@bot.event
@ignore_bots
async def on_message(message):
    content = message.content.lower()
    increment_words(message.member, message)

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