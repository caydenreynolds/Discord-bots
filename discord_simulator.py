import asyncio
import os
import subprocess
import traceback
from io import BytesIO
from random import choice, randint, seed
from shutil import which

import discord
from discord.ext import commands, tasks
from PIL import Image
from sqlalchemy import (BigInteger, Column, ForeignKey, Integer, String,
                        create_engine)
from sqlalchemy.ext.declarative import declarative_base, declared_attr
from sqlalchemy.orm import relationship, sessionmaker

from bot_utils import BaseMixin, MemberMixin, get_user_from_name, ignore_bots

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
PRUNE_FREQUENCY = 60 * 60 * 24 * 7 * 4 #4 weeks

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
    sim_member = relationship('SimulatedMember', uselist=False, lazy='subquery', backref="parent_node", cascade="delete, delete-orphan")

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
        self.prune.start()

    @tasks.loop(seconds=SCHEDULE_FREQUENCY)
    async def schedule_sim(self):
        await bot.wait_until_ready()
        session = Session()
        try:
            channels=[]
            for channel in session.query(Channel).all():
                c = bot.get_channel(channel.channel_id)
                if c:
                    channels.append(c)
                else:
                    session.delete(channel)
            session.commit()
            session.close()
            for channel in channels:
                await simulate(channel)
        except Exception as e:
            pass
        finally:
            session.commit()
            session.close()

    @tasks.loop(seconds=PRUNE_FREQUENCY)
    async def prune(self):
        """Prune words only said one time from the database. Do this in order to reduce the database size and steps during message generation"""
        await bot.wait_until_ready()
        session = Session()
        scheduled_deletes = []
        try:
            print("starting prune")
            #Find nodes to baleet
            for member in session.query(SimulatedMember).all():
                for node in session.query(MarkovNode).filter_by(sim_member=member).all():
                    for i in range(len(node.probabilities)):
                        probability = node.probabilities[i]
                        if probability.count == 1:
                            destination_node = session.query(MarkovNode).filter_by(id=probability.node_id).one()
                            if destination_node.count == 1:
                                node.count -= probability.count
                                node.probabilities.pop(i)
                                destination_node.delete()

            #baleet the nodes
            for scheduled_delete in scheduled_deletes:delete(node)
                probability_node, destination_node = scheduled_delete
                for probability in probability_node.probabilities:
                    if probability.node_id == destination_node.id:
                        probability_to_remove = probability
                        break
                probability_node.count -= 1
                probability_node.probabilities.remove(probability_to_remove)
                session.delete(probability_to_remove)
                session.delete(destination_node)

                if probability_node.count == 0:
                    #ope, this node is invalid now. We have to baleet it
                    try:
                        self.remove_node(probability_node, session)
                    except self.AllNodesDeleted:
                        pass

        except Exception as e:
            traceback.print_exc()
        finally:
            session.commit()
            session.close()
            print('finished!')

    def remove_node(self, node, session):
        member = node.sim_member
        if node.word == MESSAGE_START:
            session.query(MarkovNode).filter_by(sim_member=member).delete()
            session.delete(member)
            raise self.AllNodesDeleted()
        else:
            nodes = session.query(MarkovNode).filter_by(sim_member=member).all()
            for parent_node in nodes:
                if len(parent_node.probabilities) == 1 and parent_node.probabilities[0].node_id == node.id:
                    self.remove_node(parent_node, session)
                else:
                    probability_to_remove = None
                    for probability in parent_node.probabilities:
                        if probability.node_id == node.id:
                            probability_to_remove = probability
                            breaktha
                    if probability_to_remove:
                        node.count -= probability_to_remove.count
                        node.probabilities.remove(probability_to_remove)
                        session.delete(probability_to_remove)
            session.delete(node)

    class AllNodesDeleted(Exception):
        pass


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

async def simulate(channel):
    available_members = get_sim_members(channel.guild)
    for i in range(randint(SIM_LENGTH_MIN, SIM_LENGTH_MAX)):
        async with channel.typing():
            await asyncio.sleep(randint(SIM_TIME_MIN, SIM_TIME_MAX))
            chosen_member = choice(available_members)
            message = create_message(chosen_member)
            await channel.send(message)

@bot.event
@ignore_bots
async def on_message(message):
    content = message.content.lower()
    increment_words(message.author, message.content)
    await bot.process_commands(message)

@bot.command(name='start', help="Begin a simulated conversation")
async def start(ctx):
    await simulate(ctx.channel)

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
