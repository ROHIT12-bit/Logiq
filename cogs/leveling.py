"""
Leveling Cog for Logiq
XP and leveling system with rank cards
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
import logging
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

from utils.embeds import EmbedFactory, EmbedColor
from utils.constants import calculate_level_xp
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class Leveling(commands.Cog):
    """Leveling system cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('leveling', {})
        self.xp_cooldown = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Award XP for messages"""
        if not self.module_config.get('enabled', True):
            return

        if message.author.bot or not message.guild:
            return

        # Check cooldown
        user_key = f"{message.guild.id}_{message.author.id}"
        current_time = datetime.utcnow().timestamp()

        if user_key in self.xp_cooldown:
            if current_time - self.xp_cooldown[user_key] < self.module_config.get('xp_cooldown', 60):
                return

        self.xp_cooldown[user_key] = current_time

        # Get or create user
        user_data = await self.db.get_user(message.author.id, message.guild.id)
        if not user_data:
            user_data = await self.db.create_user(message.author.id, message.guild.id)

        # Calculate XP
        xp_gain = self.module_config.get('xp_per_message', 10)
        new_xp = user_data.get('xp', 0) + xp_gain
        current_level = user_data.get('level', 0)

        # Check for level up
        next_level_xp = calculate_level_xp(current_level + 1)

        if new_xp >= next_level_xp:
            new_level = current_level + 1
            await self.db.update_user(message.author.id, message.guild.id, {
                'xp': new_xp,
                'level': new_level
            })

            # Send level up notification to configured channel, or fall back to message channel
            embed = EmbedFactory.level_up(message.author, new_level, new_xp)
            notify_channel = message.channel
            guild_config = await self.db.get_guild(message.guild.id)
            if guild_config:
                level_channel_id = guild_config.get('level_channel')
                if level_channel_id:
                    ch = message.guild.get_channel(level_channel_id)
                    if ch:
                        notify_channel = ch
            await notify_channel.send(embed=embed)
            logger.info(f"{message.author} leveled up to {new_level} in {message.guild}")
        else:
            await self.db.update_user(message.author.id, message.guild.id, {'xp': new_xp})

    # NOTE: /rank and /leaderboard commands have been moved to games.py as PUBLIC commands

    @app_commands.command(name="setlevelchannel", description="Set the channel for level-up notifications (Admin)")
    @app_commands.describe(channel="Channel to send level-up notifications in")
    @is_admin()
    async def set_level_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        """Set the level-up notification channel"""
        guild_config = await self.db.get_guild(interaction.guild.id)
        if not guild_config:
            await self.db.create_guild(interaction.guild.id)

        await self.db.update_guild(interaction.guild.id, {'level_channel': channel.id})

        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "Level Channel Set",
                f"Level-up notifications will now be sent to {channel.mention}"
            ),
            ephemeral=True
        )
        logger.info(f"{interaction.user} set level channel to {channel} in {interaction.guild}")

    @app_commands.command(name="removelevelchannel", description="Remove the level-up notification channel (Admin)")
    @is_admin()
    async def remove_level_channel(self, interaction: discord.Interaction):
        """Remove the level-up notification channel (falls back to message channel)"""
        guild_config = await self.db.get_guild(interaction.guild.id)
        if not guild_config or not guild_config.get('level_channel'):
            await interaction.response.send_message(
                embed=EmbedFactory.warning(
                    "Not Set",
                    "No level-up notification channel is currently configured."
                ),
                ephemeral=True
            )
            return

        await self.db.update_guild(interaction.guild.id, {'level_channel': None})

        await interaction.response.send_message(
            embed=EmbedFactory.success(
                "Level Channel Removed",
                "Level-up notifications will now appear in the same channel as the message."
            ),
            ephemeral=True
        )

    @app_commands.command(name="setlevel", description="Set user's level (Admin)")
    @app_commands.describe(
        user="User to modify",
        level="New level"
    )
    @is_admin()
    async def set_level(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        level: int
    ):
        """Set user level"""
        if level < 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Level", "Level must be 0 or greater"),
                ephemeral=True
            )
            return

        xp = sum(calculate_level_xp(i) for i in range(1, level + 1))

        await self.db.update_user(user.id, interaction.guild.id, {
            'level': level,
            'xp': xp
        })

        embed = EmbedFactory.success(
            "Level Set",
            f"Set {user.mention}'s level to **{level}**"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} set {user}'s level to {level}")

    @app_commands.command(name="resetlevels", description="Reset all levels (Admin)")
    @is_admin()
    async def reset_levels(self, interaction: discord.Interaction):
        """Reset all levels in guild"""
        # This would require a bulk update - implementing basic version
        await interaction.response.send_message(
            embed=EmbedFactory.warning(
                "Reset Levels",
                "This feature will reset all user levels. This is a destructive action.\n\n"
                "To implement: Use database bulk operations to reset all users in this guild."
            ),
            ephemeral=True
        )


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Leveling(bot, bot.db, bot.config))
