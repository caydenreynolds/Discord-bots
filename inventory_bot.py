import time
import os
from prettytable import PrettyTable
from discord.ext import commands
from discord.utils import find
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, Boolean

from bot_utils import ignore_self, remove_punctuation, BaseMixin, typing

Base = declarative_base()
engine = create_engine(os.getenv('INVENTORY_DB'))
Session = sessionmaker(bind=engine)

DELETE_AFTER_SECONDS = 60

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()

platinum_pieces = "PP"
gold_pieces = "GP"
silver_pieces = "SP"
copper_pieces = "CP"

class GuildChannel(BaseMixin, Base):
    guild_id = Column(BigInteger)
    channel_id = Column(BigInteger)
    gold_message_id = Column(BigInteger)
    items_message_id = Column(BigInteger)

    def __init__(self, ctx):
        self.guild_id = ctx.guild.id
        self.channel_id = ctx.channel.id

    async def set_message_ids(self, ctx):
        gold_message = await ctx.channel.send("gold")
        self.gold_message_id = gold_message.id
        items_message = await ctx.channel.send("items")
        self.items_message_id = items_message.id
        return

class Item(BaseMixin, Base):
    guild_id = Column(BigInteger)
    count = Column(Integer)
    name = Column(String)
    is_gold = Column(Boolean)

    def __init__(self, ctx, name, count=1, is_gold=False):
        self.guild_id = ctx.guild.id
        self.name = name
        self.count = count
        self.is_gold = is_gold

Base.metadata.create_all(engine)

def add_initial_money(ctx, session):
    pp = Item(ctx, platinum_pieces, 0, True)
    gp = Item(ctx, gold_pieces, 0, True)
    sp = Item(ctx, silver_pieces, 0, True)
    cp = Item(ctx, copper_pieces, 0, True)

    session.add_all([pp, gp, sp, cp])

def add_platinum(session, ctx, amount):
    pp = platinum_query(session, ctx)
    pp.count += amount

def add_gold(session, ctx, amount):
    gp = gold_query(session, ctx)
    gp.count += amount
    if gp.count >= 100:
        gp_count = gp.count
        gp.count = gp_count % 100
        add_platinum(session, ctx, (int)(gp_count/100))

def add_silver(session, ctx, amount):
    sp = silver_query(session, ctx)
    sp.count += amount
    if sp.count >= 100:
        sp_count = sp.count
        sp.count = sp_count % 100
        add_gold(session, ctx, (int)(sp_count/100))

def add_copper(session, ctx, amount):
    cp = copper_query(session, ctx)
    cp.count += amount
    if cp.count >= 100:
        cp_count = cp.count
        cp.count = cp_count % 100
        add_silver(session, ctx, (int)(cp_count/100))

def subtract_platinum(session, ctx, amount):
    pp = platinum_query(session, ctx)
    if pp.count < amount:
        raise ValueError("You don't have enough money!")
    pp.count -= amount

def subtract_gold(session, ctx, amount):
    gp = gold_query(session, ctx)
    gp.count -= amount
    times_added = 0
    while gp.count < 0:
        times_added += 1
        gp.count += 100
    subtract_platinum(session, ctx, times_added)

def subtract_silver(session, ctx, amount):
    sp = silver_query(session, ctx)
    sp.count -= amount
    times_added = 0
    while sp.count < 0:
        times_added += 1
        sp.count += 100
    subtract_gold(session, ctx, times_added)

def subtract_copper(session, ctx, amount):
    cp = copper_query(session, ctx)
    cp.count -= amount
    times_added = 0
    while cp.count < 0:
        times_added += 1
        cp.count += 100
    subtract_silver(session, ctx, times_added)

def platinum_query(session, ctx):
    return money_item_query(session, platinum_pieces, ctx)
def gold_query(session, ctx):
    return money_item_query(session, gold_pieces, ctx)
def silver_query(session, ctx):
    return money_item_query(session, silver_pieces, ctx)
def copper_query(session, ctx):
    return money_item_query(session, copper_pieces, ctx)

def money_item_query(session, name, ctx):
    return session.query(Item).filter_by(name=name, guild_id=ctx.guild.id, is_gold=True).one()


def add_item(session, ctx, name, amount=1):
    item = item_query(session, name, ctx)
    if item == None:
        item = Item(ctx, name, amount)
        session.add(item)
    else:
        item.count += amount

def subtract_item(session, ctx, name, amount=1):
    item = item_query(session, name, ctx)
    if item == None:
        raise ValueError("Cannot find the requested item!")
    elif item.count < amount:
        raise ValueError("You do not have enough of this item!")
    elif item.count == amount:
        session.delete(item)
    else:
        item.count -= amount


def item_query(session, name, ctx):
    return session.query(Item).filter_by(name=name, guild_id=ctx.guild.id, is_gold=False).one_or_none()
def items_query(session, ctx):
    return session.query(Item).filter_by(guild_id=ctx.guild.id, is_gold=False).all()

def guild_channel_query(session, ctx):
    return session.query(GuildChannel).filter_by(guild_id=ctx.guild.id).one()

async def get_gold_msg(session, ctx):
    msg_id = guild_channel_query(session, ctx).gold_message_id
    return await get_msg(ctx, msg_id)
async def get_items_msg(session, ctx):
    msg_id = guild_channel_query(session, ctx).items_message_id
    return await get_msg(ctx, msg_id)

async def get_msg(ctx, msg_id):
    return await ctx.fetch_message(msg_id)

async def redraw_money_table(session, ctx):
    pp = platinum_query(session, ctx)
    gp = gold_query(session, ctx)
    sp = silver_query(session, ctx)
    cp = copper_query(session, ctx)

    table = PrettyTable(['Name', 'Amount'])
    table.add_row([pp.name, pp.count])
    table.add_row([gp.name, gp.count])
    table.add_row([sp.name, sp.count])
    table.add_row([cp.name, cp.count])
    gold_message = await get_gold_msg(session, ctx)
    await gold_message.edit(content=f'```\n{table}\n```')

async def redraw_items_table(session, ctx):
    items = items_query(session, ctx)
    table = PrettyTable(['Name', 'Amount'])
    for item in items:
        table.add_row([item.name, item.count])
    items_message = await get_items_msg(session, ctx)
    await items_message.edit(content=f'```\n{table}\n```')

async def remove_msg(ctx):
    await ctx.message.delete()

async def error_message(ctx, content):
    await ctx.channel.send(content=content, delete_after=DELETE_AFTER_SECONDS)

TOKEN = os.getenv('INVENTORY_TOKEN')

bot = commands.Bot(command_prefix='i!', description="Manage your party's inventory")

def print_commands():
    helptext = "```In order to use a command, type the following: i![command] [args]\nCommands:\n"
    bot_commands = [command for command in bot.commands]
    bot_commands.sort(key=lambda x: str(x))

    for command in bot_commands:
        helptext+=f"{command}    {command.help}\n"
    helptext+="\nType i!help command for more info on a command.\n```"
    return helptext

@typing
@bot.command(name='init', help='Begin running the inventory_bot in this channel', usage='i!init')
async def initialize_bot(ctx):
    with session_scope() as session:
        await ctx.channel.send(content=print_commands())
        gc = GuildChannel(ctx)
        await gc.set_message_ids(ctx)
        session.add(gc)
        add_initial_money(ctx, session)
        await redraw_money_table(session, ctx)
        await redraw_items_table(session, ctx)

    await remove_msg(ctx)

@typing
@bot.command(name='redraw', help='Redraw the item tables')
async def redraw(ctx):
    with session_scope() as session:
        await ctx.channel.send(content=print_commands())
        gc = guild_channel_query(session, ctx)
        await gc.set_message_ids(ctx)
        await redraw_money_table(session, ctx)
        await redraw_items_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='addpp', help='Add platinum pieces to the party inventory', aliases=['addplatinum', 'platinum'])
async def add_platinum_to_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of platinum added must be > 0")
        return

    with session_scope() as session:
        add_platinum(session, ctx, amount)
        await redraw_money_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='addgp', help='Add gold pieces to the party inventory', aliases=['addgold', 'earn', 'gold'])
async def add_gold_to_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of gold added must be > 0")
        return

    with session_scope() as session:
        add_gold(session, ctx, amount)
        await redraw_money_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='addsp', help='Add silver pieces to the party inventory', aliases=['addsilver', 'silver'])
async def add_silver_to_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of silver added must be > 0")
        return

    with session_scope() as session:
        add_silver(session, ctx, amount)
        await redraw_money_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='addcp', help='Add copper pieces to the party inventory', aliases=['addcopper', 'copper'])
async def add_copper_to_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of copper added must be > 0")
        return

    with session_scope() as session:
        add_copper(session, ctx, amount)
        await redraw_money_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='spendpp', help='Remove platinum pieces from the party inventory', aliases=['spendplatinum'])
async def remove_platinum_from_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of platinum removed must be > 0")
        return

    try:
        with session_scope() as session:
            subtract_platinum(session, ctx, amount)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='spendgp', help='Remove gold pieces from the party inventory', aliases=['spendgold'])
async def remove_gold_from_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of gold removed must be > 0")
        return

    try:
        with session_scope() as session:
            subtract_gold(session, ctx, amount)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='spendsp', help='Remove silver pieces from the party inventory', aliases=['spendsilver'])
async def remove_silver_from_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of silver removed must be > 0")
        return

    try:
        with session_scope() as session:
            subtract_silver(session, ctx, amount)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='spendcp', help='Remove copper pieces from the party inventory', aliases=['spendcopper'])
async def remove_copper_from_pool(ctx, amount: int):
    if amount <= 0:
        await error_message(ctx, "The amount of copper removed must be > 0")
        return

    try:
        with session_scope() as session:
            subtract_copper(session, ctx, amount)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='additem', help='Add a new item to the party inventory', aliases=['acquire', 'newitem', 'add', 'item'])
async def add_item_to_pool(ctx, *, name: str):
    name = name.lower()
    with session_scope() as session:
        add_item(session, ctx, name)
        await redraw_items_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='additems', help='Add new items to the party inventory', aliases=['newitems', 'items'])
async def add_items_to_pool(ctx, amount: int, *, name: str):
    name = name.lower()
    if amount <= 0:
        await error_message(ctx, "The number of items added must be > 0")
        return

    with session_scope() as session:
        add_item(session, ctx, name, amount)
        await redraw_items_table(session, ctx)
    await remove_msg(ctx)

@typing
@bot.command(name='removeitem', help='Removes an item from the party inventory', aliases=['useitem', 'remove', 'use', 'consume'])
async def remove_item_from_pool(ctx, *, name: str):
    name = name.lower()
    try:
        with session_scope() as session:
            subtract_item(session, ctx, name)
            await redraw_items_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='removeitems', help='Removes some items from the party inventory', aliases=['useitems'])
async def remove_items_from_pool(ctx, amount: int, *, name: str):
    name = name.lower()
    if amount <= 0:
        await error_message(ctx, "The number of items removed must be > 0")
        return
    try:
        with session_scope() as session:
            subtract_item(session, ctx, name, amount)
            await redraw_items_table(session, ctx)
    except ValueError as e:
        await error_message(e)
    await remove_msg(ctx)

@typing
@bot.command(name='buyitem', help='Purchase an item using the party gold', aliases=['purchase', 'buy'])
async def buy_item(ctx, price: int, *, name: str):
    name = name.lower()
    if price <= 0:
        await error_message(ctx, "The price of the item must be > 0")
        return
    try:
        with session_scope() as session:
            subtract_gold(session, ctx, price)
            add_item(session, ctx, name)
            await redraw_items_table(session, ctx)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(ctx, e)
    await remove_msg(ctx)

@typing
@bot.command(name='buyitems', help='Purchase several items using the party gold', aliases=['purchaseitems'])
async def buy_items(ctx, amount: int, price: int, *, name: str):
    name = name.lower()
    if price <= 0:
        await error_message(ctx, "The price of the item must be > 0")
        return
    if amount <= 0:
        await error_message(ctx, "The number of items purchased must be > 0")
        return
    try:
        with session_scope() as session:
            subtract_gold(session, ctx, price*amount)
            add_item(session, ctx, name, amount)
            await redraw_items_table(session, ctx)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(ctx, e)
    await remove_msg(ctx)

@typing
@bot.command(name='sellitem', help='Sell an item using the party gold', aliases=['sell'])
async def sell_item(ctx, price: int, *, name: str):
    name = name.lower()
    if price <= 0:
        await error_message(ctx, "The price of the item must be > 0")
        return
    try:
        with session_scope() as session:
            add_gold(session, ctx, price)
            subtract_item(session, ctx, name)
            await redraw_items_table(session, ctx)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(ctx, e)
    await remove_msg(ctx)

@typing
@bot.command(name='sellitems', help='Sell several items using the party gold')
async def sell_items(ctx, amount: int, price: int, *, name: str):
    name = name.lower()
    if price <= 0:
        await error_message(ctx, "The price of the item must be > 0")
        return
    if amount <= 0:
        await error_message(ctx, "The number of items sold must be > 0")
        return
    try:
        with session_scope() as session:
            add_gold(session, ctx, price*amount)
            subtract_item(session, ctx, name, amount)
            await redraw_items_table(session, ctx)
            await redraw_money_table(session, ctx)
    except ValueError as e:
        await error_message(ctx, e)
    await remove_msg(ctx)

@bot.event
async def on_command_error(ctx, exception):
    await error_message(ctx, "I'm sorry, I don't understand that command")
    await remove_msg(ctx)
    raise exception

print("Starting up...")
bot.run(TOKEN)
