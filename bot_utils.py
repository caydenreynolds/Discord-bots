import string
from functools import wraps

"""Ensure we ignore our own messages"""
def ignore_self(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if args[0].author == bot.user:
            return
        else:
            await func(*args, **kwargs)
    return wrapper

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