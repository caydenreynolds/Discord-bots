import os
import time
from random import seed, randint, choice
from discord.ext import commands
from discord.utils import find

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, ForeignKey, String

from bot_utils import ignore_bots, BaseMixin, MemberMixin

Base = declarative_base()
engine = create_engine(os.getenv('SIMULATOR_DB'))
Session = sessionmaker(bind=engine)

MESSAGE_START = """MESSAGE_START_{i$5pJ|^ov8gmoC`96SRMs{%EC3({16v&R`po^O)bU%Vw]'sbx"""
MESSAGE_END = """MESSAGE_END_r>CX4XuxV1D\;Zron,yl@Qx;,9CMy[``t.H(@#pvz.I_kNREq#"""

SIM_LENGTH_MIN = 20
SIM_LENGTH_MAX = 50
SIM_TIME_MIN = 2
SIM_TIME_MAX = 5

seed()

class ProbabilityTuple(BaseMixin, Base):
    parent_node_id = Column(Integer, ForeignKey('markovnode.id'))
    node_id = Column(Integer)
    count = Column(Integer)

class MarkovNode(MemberMixin, BaseMixin, Base):
    word = Column(String)
    count = Column(BigInteger)
    probabilities = relationship('ProbabilityTuple', lazy='subquery')
    sim_member_id = Column(Integer, ForeignKey('simulatedmember.id'))
    sim_member = relationship('SimulatedMember', uselist=False, lazy='subquery')

    def __init__(self, sim_member=None, word='', count=0):
        self.count = count
        self.word = word
        self.sim_member = sim_member

    def increase_word_count(self, word, session):
        self.count += 1

        node = MarkovNode.get_or_create(word, self.sim_member, session)
        session.flush()
        node_ids = [pt.node_id for pt in self.probabilities]
        if node.id in node_ids:
            i = node_ids.index(node.id)
            self.probabilities[i].count += 1
        else:
            pt = ProbabilityTuple(node_id=node.id, count=1)
            session.add(pt)
            self.probabilities.append(pt)

    def choose_next_word(self, session):
        number = randint(0, self.count-1)
        i = 0
        while number > 0:
            number -= self.probabilities[i].count
            i += 1
        return session.query(MarkovNode).filter_by(id=self.probabilities[i-1].node_id).one()

    @classmethod
    def get_or_create(cls, word, sim_member, session):
        result = session.query(cls).filter_by(word=word, sim_member=sim_member).one_or_none() or\
                 cls(word=word, sim_member=sim_member)
        session.add(result)
        return result

    @classmethod
    def get(cls, word, sim_member, session):
        return session.query(cls).filter_by(word=word, sim_member=sim_member).one()

class SimulatedMember(MemberMixin, BaseMixin, Base):
    def __init__(self, member=None, session=None):
        super().__init__(member=member)
        session.add(MarkovNode(self, MESSAGE_START))

    def get_start_node(self, session):
        return MarkovNode.get(MESSAGE_START, self, session)

Base.metadata.create_all(engine)

def increment_words(member, message):
    session = Session()
    sim_member = SimulatedMember.get_or_create(member, session, create_args={'session': session})
    message_words = f'{MESSAGE_START} {message} {MESSAGE_END}'.split()
    for i in range(len(message_words)-1):
        node = MarkovNode.get(message_words[i], sim_member, session)
        node.increase_word_count(message_words[i+1], session)
    session.commit()
    session.close()

def get_sim_members(guild):
    session = Session()
    simulated_member_ids = [sim_member.member_id for sim_member in SimulatedMember.get_guild_members(guild, session)]
    result = [member for member in guild.members if member.id in simulated_member_ids]
    session.commit()
    session.close()
    return result

def create_message(member):
    session = Session()
    words = [SimulatedMember.get(member, session).get_start_node(session)]
    while words[-1].word != MESSAGE_END:
        words.append(words[-1].choose_next_word(session))
    message = ' '.join([word.word for word in words[1:-1]])
    message = f'{member.nick or member.name}:\n    {message}'
    session.commit()
    session.close()
    return message

TOKEN = os.getenv('SIMULATOR_TOKEN')
bot = commands.Bot(command_prefix='-sim-', description="I am a horrible, twisted version of your guild. FEAR ME.\nFor suggestions and bug reports, create an issue on my github: https://github.com/caydenreynolds/Discord-bots")

@bot.event
@ignore_bots
async def on_message(message):
    content = message.content.lower()
    increment_words(message.author, message.content)
    await bot.process_commands(message)

@bot.command(name='start', help="Begin a simulated conversation")
async def start(ctx):
    available_members = get_sim_members(ctx.guild)
    for i in range(randint(SIM_LENGTH_MIN, SIM_LENGTH_MAX)):
        with ctx.channel.typing():
            chosen_member = choice(available_members)
            message = create_message(chosen_member)
            time.sleep(randint(SIM_TIME_MIN, SIM_TIME_MAX))
            await ctx.channel.send(message)

@bot.command(name='get', help="Begin a simulated conversation")
async def get(ctx):
    session = Session()
    node = MarkovNode.get('is', SimulatedMember.get(ctx.author, session), session)
    print(len(node.probabilities))
    session.commit()
    session.close()

@bot.event
async def on_command_error(ctx, exception):
    await ctx.channel.send("I'm sorry, I don't understand that command")
    raise exception

print("Starting up...")
bot.run(TOKEN)