# Discord Bots
A collection of ... not-so-useful discord bots

![Bee bot go bzzzz](bzzzz.jpg?raw=true)

# Setup
So, you want to use my shitty robots for yourself, huh? Here's what you need to know:
Once you've setup your bot on discord, you'll need to set an environment variable with your bot token.
Use the environment variable name appropriate for your bot:
1. BEE_TOKEN
2. NICE_TOKEN
3. SIMULATOR_TOKEN

Some bots require a database to store information. You're going to need to set an environment variable to the database URL.
1. BEE_DB
2. SIMULATOR_DB

You'll need a few packages:
```pip install discord, sqlalchemy, prettytable```

Once you've completed these steps, simply run the python script for your bot, add the bot to your guild, and profit
