import os
import discord
from discord.ext import commands
from services.llm_service import generate_huohuo_result

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Huohuo online: {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if bot.user and bot.user.mentioned_in(message):
        text = message.content.replace(f"<@{bot.user.id}>", "").strip()

        result = await generate_huohuo_result(
            text,
            user_id=f"discord:{message.author.id}",
        )

        await message.channel.send(result.response_text)

    await bot.process_commands(message)


bot.run(os.environ["DISCORD_BOT_TOKEN"])