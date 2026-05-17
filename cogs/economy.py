"""
Economy Cog for Logiq
Virtual currency system with shop and gambling
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional
import logging
import random

from utils.embeds import EmbedFactory, EmbedColor, sc
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class Economy(commands.Cog):
    """Economy system cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.module_config = config.get('modules', {}).get('economy', {})
        self.currency_symbol = self.module_config.get('currency_symbol', '💎')
        self.currency_name = self.module_config.get('currency_name', 'ProgrammiCoin')

    # NOTE: /balance command has been moved to games.py as PUBLIC command

    @app_commands.command(name="daily", description="Claim your daily reward")
    async def daily(self, interaction: discord.Interaction):
        """Claim daily reward"""
        user_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        last_daily = user_data.get('last_daily', 0)
        current_time = datetime.utcnow().timestamp()
        cooldown = self.module_config.get('daily_cooldown', 86400)

        if current_time - last_daily < cooldown:
            time_left = cooldown - (current_time - last_daily)
            hours = int(time_left // 3600)
            minutes = int((time_left % 3600) // 60)

            await interaction.response.send_message(
                embed=EmbedFactory.warning(
                    "Cooldown Active",
                    f"You can claim your daily reward in **{hours}h {minutes}m**"
                ),
                ephemeral=True
            )
            return

        daily_amount = self.module_config.get('daily_reward', 100)
        await self.db.add_balance(interaction.user.id, interaction.guild.id, daily_amount)
        await self.db.update_user(interaction.user.id, interaction.guild.id, {'last_daily': current_time})

        new_balance = user_data.get('balance', 0) + daily_amount

        embed = EmbedFactory.success(
            "Daily Reward Claimed!",
            f"You received **{self.currency_symbol} {daily_amount:,}**!\n\n"
            f"New balance: **{self.currency_symbol} {new_balance:,}**"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} claimed daily reward in {interaction.guild}")

    @app_commands.command(name="give", description="Give currency to another user (Admin)")
    @app_commands.describe(
        user="User to give to",
        amount="Amount to give"
    )
    @is_admin()
    async def give(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Give currency to user"""
        if amount <= 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Amount", "Amount must be positive"),
                ephemeral=True
            )
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't give currency to yourself"),
                ephemeral=True
            )
            return

        if user.bot:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't give currency to bots"),
                ephemeral=True
            )
            return

        # Check if sender has enough balance
        sender_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not sender_data:
            sender_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        if sender_data.get('balance', 0) < amount:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Insufficient Funds", "You don't have enough currency"),
                ephemeral=True
            )
            return

        # Transfer currency
        await self.db.remove_balance(interaction.user.id, interaction.guild.id, amount)
        await self.db.add_balance(user.id, interaction.guild.id, amount)

        embed = EmbedFactory.success(
            "Transfer Complete",
            f"{interaction.user.mention} gave **{self.currency_symbol} {amount:,}** to {user.mention}"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} gave {amount} to {user}")

    @app_commands.command(name="coinflip-bet", description="Flip a coin and bet currency (Admin)")
    @app_commands.describe(
        amount="Amount to bet",
        choice="Heads or Tails"
    )
    @is_admin()
    async def coinflip(self, interaction: discord.Interaction, amount: int, choice: str):
        """Coinflip gambling"""
        if amount <= 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Amount", "Amount must be positive"),
                ephemeral=True
            )
            return

        choice = choice.lower()
        if choice not in ['heads', 'tails', 'h', 't']:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Choice", "Choose 'heads' or 'tails'"),
                ephemeral=True
            )
            return

        # Normalize choice
        choice = 'heads' if choice in ['heads', 'h'] else 'tails'

        # Check balance
        user_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        if user_data.get('balance', 0) < amount:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Insufficient Funds", "You don't have enough currency"),
                ephemeral=True
            )
            return

        # Flip coin
        result = random.choice(['heads', 'tails'])
        won = result == choice

        if won:
            await self.db.add_balance(interaction.user.id, interaction.guild.id, amount)
            new_balance = user_data.get('balance', 0) + amount
            embed = EmbedFactory.success(
                "🎉 You Won!",
                f"The coin landed on **{result}**!\n\n"
                f"You won **{self.currency_symbol} {amount:,}**!\n"
                f"New balance: **{self.currency_symbol} {new_balance:,}**"
            )
        else:
            await self.db.remove_balance(interaction.user.id, interaction.guild.id, amount)
            new_balance = user_data.get('balance', 0) - amount
            embed = EmbedFactory.error(
                "You Lost!",
                f"The coin landed on **{result}**!\n\n"
                f"You lost **{self.currency_symbol} {amount:,}**!\n"
                f"New balance: **{self.currency_symbol} {new_balance:,}**"
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="shop", description="View the server shop")
    async def shop(self, interaction: discord.Interaction):
        """View shop"""
        items = await self.db.get_shop_items(interaction.guild.id)

        if not items:
            await interaction.response.send_message(
                embed=EmbedFactory.info("Empty Shop", "The shop is currently empty"),
                ephemeral=True
            )
            return

        description = ""
        for item in items[:25]:
            description += f"**{item['name']}** - {self.currency_symbol} {item['price']:,}\n"
            description += f"  *{item['description']}*\n\n"

        embed = EmbedFactory.create(
            title="🏪 Server Shop",
            description=description,
            color=EmbedColor.ECONOMY
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="weekly", description="Claim your weekly reward")
    async def weekly(self, interaction: discord.Interaction):
        """Claim weekly reward"""
        user_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        last_weekly = user_data.get('last_weekly', 0)
        current_time = datetime.utcnow().timestamp()
        cooldown = 604800  # 7 days

        if current_time - last_weekly < cooldown:
            time_left = cooldown - (current_time - last_weekly)
            days = int(time_left // 86400)
            hours = int((time_left % 86400) // 3600)
            await interaction.response.send_message(
                embed=EmbedFactory.warning(
                    "Cooldown Active",
                    f"Come back in **{days}d {hours}h** for your weekly reward"
                ),
                ephemeral=True
            )
            return

        weekly_amount = self.module_config.get('daily_reward', 100) * 5
        await self.db.add_balance(interaction.user.id, interaction.guild.id, weekly_amount)
        await self.db.update_user(interaction.user.id, interaction.guild.id, {'last_weekly': current_time})
        new_balance = user_data.get('balance', 0) + weekly_amount

        embed = EmbedFactory.success(
            "Weekly Reward Claimed!",
            f"You received **{self.currency_symbol} {weekly_amount:,}**!\n\n"
            f"**{sc('new balance')}** {self.currency_symbol} {new_balance:,}"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="work", description="Work to earn some currency")
    async def work(self, interaction: discord.Interaction):
        """Work for currency"""
        user_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not user_data:
            user_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        last_work = user_data.get('last_work', 0)
        current_time = datetime.utcnow().timestamp()
        cooldown = 3600  # 1 hour

        if current_time - last_work < cooldown:
            time_left = cooldown - (current_time - last_work)
            minutes = int(time_left // 60)
            seconds = int(time_left % 60)
            await interaction.response.send_message(
                embed=EmbedFactory.warning(
                    "Still Working",
                    f"You need to rest for **{minutes}m {seconds}s** before working again"
                ),
                ephemeral=True
            )
            return

        jobs = [
            ("delivered packages", "📦"), ("wrote code", "💻"), ("sold lemonade", "🍋"),
            ("fixed computers", "🖥️"), ("walked dogs", "🐕"), ("cooked meals", "🍳"),
            ("taught lessons", "📚"), ("drove a taxi", "🚕"), ("mined crypto", "⛏️"),
            ("streamed online", "🎮"),
        ]
        job, emoji = random.choice(jobs)
        earned = random.randint(
            self.module_config.get('daily_reward', 100) // 4,
            self.module_config.get('daily_reward', 100) // 2
        )

        await self.db.add_balance(interaction.user.id, interaction.guild.id, earned)
        await self.db.update_user(interaction.user.id, interaction.guild.id, {'last_work': current_time})
        new_balance = user_data.get('balance', 0) + earned

        embed = EmbedFactory.success(
            f"{emoji} Work Complete",
            f"You {job} and earned **{self.currency_symbol} {earned:,}**!\n\n"
            f"**{sc('new balance')}** {self.currency_symbol} {new_balance:,}"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="transfer", description="Transfer currency to another user")
    @app_commands.describe(user="User to transfer to", amount="Amount to transfer")
    async def transfer(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Transfer currency between users"""
        if amount <= 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Amount", "Amount must be positive"), ephemeral=True)
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't transfer to yourself"), ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't transfer to bots"), ephemeral=True)
            return

        sender_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not sender_data:
            sender_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        if sender_data.get('balance', 0) < amount:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Insufficient Funds", "You don't have enough currency"), ephemeral=True)
            return

        await self.db.remove_balance(interaction.user.id, interaction.guild.id, amount)
        await self.db.add_balance(user.id, interaction.guild.id, amount)

        embed = EmbedFactory.success(
            "Transfer Complete",
            f"{interaction.user.mention} → {user.mention}\n\n"
            f"**{sc('amount')}** {self.currency_symbol} {amount:,}"
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rob", description="Attempt to rob another user")
    @app_commands.describe(user="User to rob")
    async def rob(self, interaction: discord.Interaction, user: discord.Member):
        """Rob another user"""
        if user.id == interaction.user.id:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't rob yourself"), ephemeral=True)
            return
        if user.bot:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Target", "You can't rob bots"), ephemeral=True)
            return

        robber_data = await self.db.get_user(interaction.user.id, interaction.guild.id)
        if not robber_data:
            robber_data = await self.db.create_user(interaction.user.id, interaction.guild.id)

        last_rob = robber_data.get('last_rob', 0)
        current_time = datetime.utcnow().timestamp()
        rob_cooldown = 7200  # 2 hours

        if current_time - last_rob < rob_cooldown:
            time_left = rob_cooldown - (current_time - last_rob)
            minutes = int(time_left // 60)
            await interaction.response.send_message(
                embed=EmbedFactory.warning("Laying Low", f"You need to wait **{minutes}m** before robbing again"),
                ephemeral=True
            )
            return

        victim_data = await self.db.get_user(user.id, interaction.guild.id)
        if not victim_data:
            victim_data = await self.db.create_user(user.id, interaction.guild.id)

        victim_balance = victim_data.get('balance', 0)
        if victim_balance < 50:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Broke Target", f"{user.mention} doesn't have enough to steal from"),
                ephemeral=True
            )
            return

        await self.db.update_user(interaction.user.id, interaction.guild.id, {'last_rob': current_time})

        success_chance = 0.45
        if random.random() < success_chance:
            stolen = random.randint(int(victim_balance * 0.10), int(victim_balance * 0.35))
            stolen = max(10, stolen)
            await self.db.remove_balance(user.id, interaction.guild.id, stolen)
            await self.db.add_balance(interaction.user.id, interaction.guild.id, stolen)
            embed = EmbedFactory.success(
                "🦹 Successful Robbery",
                f"You robbed **{self.currency_symbol} {stolen:,}** from {user.mention}!\n\n"
                f"**{sc('your balance')}** {self.currency_symbol} {robber_data.get('balance', 0) + stolen:,}"
            )
        else:
            fine = random.randint(50, max(50, int(robber_data.get('balance', 0) * 0.15)))
            fine = min(fine, robber_data.get('balance', 0))
            if fine > 0:
                await self.db.remove_balance(interaction.user.id, interaction.guild.id, fine)
            embed = EmbedFactory.error(
                "🚔 Caught!",
                f"You were caught trying to rob {user.mention}!\n\n"
                f"**{sc('fine')}** {self.currency_symbol} {fine:,}"
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="addbalance", description="Add balance to user (Admin)")
    @app_commands.describe(
        user="User to add balance to",
        amount="Amount to add"
    )
    @is_admin()
    async def add_balance_admin(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        amount: int
    ):
        """Add balance to user (ADMIN ONLY)"""
        await self.db.add_balance(user.id, interaction.guild.id, amount)

        embed = EmbedFactory.success(
            "Balance Added",
            f"Added **{self.currency_symbol} {amount:,}** to {user.mention}"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} added {amount} to {user}")


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Economy(bot, bot.db, bot.config))
