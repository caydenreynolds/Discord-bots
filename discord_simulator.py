import asyncio
import os
import subprocess
import traceback
from time import time
from io import BytesIO
from random import choices, randint, seed
from shutil import which

import discord
from discord.ext import commands, tasks
from sqlalchemy import (BigInteger, Column, ForeignKey, Integer, String,
                        create_engine)
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import relationship, sessionmaker

from bot_utils import BaseMixin, MemberMixin, get_user_from_name, ignore_bots, get_user_from_id, get_role_from_id

Base = declarative_base()
engine = create_engine(os.getenv('SIMULATOR_DB'))
Session = sessionmaker(bind=engine)

MESSAGE_START = """MESSAGE_START_{i$5pJ|^ov8gmoC`96SRMs{%EC3({16v&R`po^O)bU%Vw]'sbx"""
MESSAGE_END = """MESSAGE_END_r>CX4XuxV1D\;Zron,yl@Qx;,9CMy[``t.H(@#pvz.I_kNREq#"""

SIM_LENGTH_MIN = 20
SIM_LENGTH_MAX = 50
SIM_TIME_MIN = 5
SIM_TIME_MAX = 9

SCHEDULE_FREQUENCY = 60 * 60 * 6 #six hours

seed()

class ProbabilityTuple(BaseMixin, Base):
    parent_node_id = Column(Integer, ForeignKey('markovnode.id'))
    node_id = Column(Integer)
    count = Column(Integer)

class MarkovNode(MemberMixin, BaseMixin, Base):
    word = Column(String)
    count = Column(BigInteger)
    probabilities = relationship('ProbabilityTuple', backref="parent_node", cascade="delete, delete-orphan")
    sim_member_id = Column(Integer, ForeignKey('simulatedmember.id'))
    sim_member = relationship('SimulatedMember', uselist=False)

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

class Channel(BaseMixin, Base):
    channel_id = Column(Integer)

Base.metadata.create_all(engine)

bot = commands.Bot(command_prefix='-sim-', description="I am a horrible, twisted version of your guild. FEAR ME.\nFor suggestions and bug reports, create an issue on my github: https://github.com/caydenreynolds/Discord-bots")

class ScheduledSimsCog(commands.Cog):
    def __init__(self):
        self.schedule_sim.start()

    @tasks.loop(seconds=SCHEDULE_FREQUENCY)
    async def schedule_sim(self):
        try:
            await bot.wait_until_ready()
            session = Session()
            channels=[]
            for channel in session.query(Channel).all():
                c = bot.get_channel(channel.channel_id)
                if c:
                    channels.append(c)
                else:
                    session.delete(channel)
            for channel in channels:
                await simulate(channel, session)
        except Exception as e:
            traceback.print_exc()
            session.rollback()
        else:
            session.commit()
        finally:
            session.close()


def increment_words(member, message):
    session = Session()
    sim_member = SimulatedMember.get_or_create(member, session, create_args={'session': session})
    message_words = f'{MESSAGE_START} {message} {MESSAGE_END}'.split()
    for i in range(len(message_words)-1):
        node = MarkovNode.get(message_words[i], sim_member, session)
        node.increase_word_count(message_words[i+1], session)
    session.commit()
    session.close()

def get_sim_members(guild, session):
    simulated_member_ids = [sim_member.member_id for sim_member in SimulatedMember.get_guild_members(guild, session)]
    result = [member for member in guild.members if member.id in simulated_member_ids]
    return result

def get_start_nodes(members, session):
    start_nodes = []
    for member in members:
        sim_member = SimulatedMember.get(member, session)
        start_nodes.append(MarkovNode.get(MESSAGE_START, sim_member, session))
    return start_nodes

def prevent_pings(word, guild, session):
    if word[0] == '<' and word[-1] == '>' and word[1] == '@':
        if word[2] == '!':
            member = get_user_from_id(int(word[3:-1]), guild)
            if member:
                name = member.nick or member.name
                return f'@{name}'
            else:
                return '@REMOVED_USER' + word
        elif word[2] =='&':
            role = get_role_from_id(int(word[3:-1]), guild)
            if role:
                return f'@{role.name}'
            else:
                return '@REMOVED_ROLE' + word
    elif word == '@everyone' or word == '@here':
        return f"{word[0]}'{word[1:]}"
    else:
        return word

def create_message(member, guild, session):
    words = [SimulatedMember.get(member, session).get_start_node(session)]
    while words[-1].word != MESSAGE_END:
        words.append(words[-1].choose_next_word(session))

    message = ' '.join([prevent_pings(word.word, guild, session) for word in words[1:-1]])
    message = f'{member.nick or member.name}:\n    {message}'
    return message

async def simulate(channel, session):
    available_members = get_sim_members(channel.guild, session)
    start_nodes = get_start_nodes(available_members, session)
    for chosen_member in choices(available_members, weights=[node.count for node in start_nodes], k=randint(SIM_LENGTH_MIN, SIM_LENGTH_MAX)):
        async with channel.typing():
            start_time = time()
            message = create_message(chosen_member, channel.guild, session)
            try:
                await asyncio.sleep(-(time() - start_time - randint(SIM_TIME_MIN, SIM_TIME_MAX)))
            except Exception:
                pass
            
            await channel.send(message)

@bot.event
@ignore_bots
async def on_message(message):
    content = message.content.lower()
    increment_words(message.author, message.content)
    await bot.process_commands(message)

@bot.command(name='start', help="Begin a simulated conversation")
async def start(ctx):
    session = Session()
    await simulate(ctx.channel, session)
    session.commit()
    session.close()

@bot.command(name='schedule', help="Schedule a simulation to occur periodically in this channel. Use '-sim-schedule stop' to stop simulations in this channel")
async def schedule(ctx, *args):
    session = Session()
    if len(args) == 0:
        if session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none():
            await ctx.channel.send("Simulations are already scheduled")
        else:
            await ctx.channel.send("Scheduling simulations in this channel!")
            session.add(Channel(channel_id=ctx.channel.id))
    elif args[0] == 'stop' and session.query(Channel).filter_by(channel_id=ctx.channel.id).one_or_none():
        session.query(Channel).filter_by(channel_id=ctx.channel.id).delete()
        await ctx.channel.send("Stopping simulations in this channel!")
    else:
        await ctx.channel.send("I don't quite understand you. Did you mean '-sim-schedule stop'?")

    session.commit()
    session.close()

@bot.event
async def on_command_error(ctx, exception):
    await ctx.channel.send("I'm sorry, I don't understand that command")
    raise exception

bot.add_cog(ScheduledSimsCog())
TOKEN = os.getenv('SIMULATOR_TOKEN')
print("Starting up...")
bot.run(TOKEN)
