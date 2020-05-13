import string
from functools import wraps
from sqlalchemy import Column, Integer
from sqlalchemy.ext.declarative import declared_attr

"""Ensure we ignore our own messages"""
def ignore_self(bot):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if args[0].author == bot.user:
                return
            else:
                await func(*args, **kwargs)
        return wrapper
    return decorator

"""Ensure we ignore bot messages"""
def ignore_bots(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if args[0].author.bot:
            return
        else:
            await func(*args, **kwargs)
    return wrapper

def remove_punctuation(punctuated_string):
    return punctuated_string.translate(str.maketrans('', '', string.punctuation))

class BaseMixin:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()
    id = Column(Integer, primary_key=True)

class MemberMixin:
    member_id = Column(Integer)
    guild_id = Column(Integer)

    def __init__(self, member=None):
        self.member_id = member.id
        self.guild_id = member.guild.id

    @classmethod
    def get_or_create(cls, member, session, create_args={}):
        result = session.query(cls).filter_by(member_id=member.id, guild_id=member.guild.id).one_or_none() or\
                 cls(member=member, **create_args)
        session.add(result)
        return result

    @classmethod
    def get(cls, member, session):
        return session.query(cls).filter_by(member_id=member.id, guild_id=member.guild.id).one()

    @classmethod
    def get_guild_members(cls, guild, session):
        return session.query(cls).filter_by(guild_id=guild.id).all()

    def __eq__(self, other):
        return type(self) == type(other) and self.member_id == other.member_id and self.guild_id == other.guild_id

    def __neq__(self, other):
        return not self == other
