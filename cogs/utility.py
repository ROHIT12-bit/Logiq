"""
Utility Cog for Logiq
General utility commands
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from typing import Optional
import logging
import asyncio
import random

from utils.embeds import EmbedFactory, EmbedColor, sc
from utils.converters import TimeConverter
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)


class PollView(discord.ui.View):
    """Interactive poll view"""

    def __init__(self, question: str, options: list, duration: int):
        super().__init__(timeout=duration)
        self.question = question
        self.options = options
        self.votes = {i: [] for i in range(len(options))}

    def get_results_embed(self) -> discord.Embed:
        """Generate results embed"""
        total_votes = sum(len(voters) for voters in self.votes.values())
        description = f"**{self.question}**\n\n"

        for i, option in enumerate(self.options):
            vote_count = len(self.votes[i])
            percentage = (vote_count / total_votes * 100) if total_votes > 0 else 0
            bar_length = int(percentage / 10)
            bar = "█" * bar_length + "░" * (10 - bar_length)
            description += f"{i + 1}. {option}\n{bar} {vote_count} votes ({percentage:.1f}%)\n\n"

        embed = EmbedFactory.create(
            title="📊 Poll Results",
            description=description,
            color=EmbedColor.INFO
        )
        embed.set_footer(text=f"Total votes: {total_votes}")
        return embed

    @discord.ui.button(label="1", style=discord.ButtonStyle.primary, custom_id="poll_1")
    async def option_1(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.primary, custom_id="poll_2")
    async def option_2(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.primary, custom_id="poll_3")
    async def option_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.primary, custom_id="poll_4")
    async def option_4(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, 3)

    async def _vote(self, interaction: discord.Interaction, option_index: int):
        """Handle vote"""
        if option_index >= len(self.options):
            await interaction.response.send_message("Invalid option", ephemeral=True)
            return

        user_id = interaction.user.id

        # Remove previous vote
        for voters in self.votes.values():
            if user_id in voters:
                voters.remove(user_id)

        # Add new vote
        self.votes[option_index].append(user_id)

        # Update message
        await interaction.response.edit_message(embed=self.get_results_embed())


class Utility(commands.Cog):
    """Utility commands cog"""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot = bot
        self.db = db
        self.config = config
        self.reminders_task = self.bot.loop.create_task(self.check_reminders())

    def cog_unload(self):
        """Cleanup on cog unload"""
        self.reminders_task.cancel()

    async def check_reminders(self):
        """Background task to check for due reminders"""
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                current_time = datetime.utcnow().timestamp()
                due_reminders = await self.db.get_due_reminders(current_time)

                for reminder in due_reminders:
                    try:
                        channel = self.bot.get_channel(reminder['channel_id'])
                        if channel:
                            user = await self.bot.fetch_user(reminder['user_id'])
                            embed = EmbedFactory.info(
                                "⏰ Reminder",
                                f"{user.mention} {reminder['message']}"
                            )
                            await channel.send(embed=embed)

                        await self.db.complete_reminder(str(reminder['_id']))
                    except Exception as e:
                        logger.error(f"Error sending reminder: {e}", exc_info=True)

                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                logger.error(f"Error in reminder checker: {e}", exc_info=True)
                await asyncio.sleep(60)

    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Show bot latency"""
        latency = round(self.bot.latency * 1000)
        embed = EmbedFactory.create(
            title=f"◈ {sc('Ping')}",
            description=f"**{sc('websocket')}** {latency} ms",
            color=EmbedColor.SUCCESS if latency < 100 else EmbedColor.WARNING if latency < 200 else EmbedColor.ERROR
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="Browse all available commands")
    async def help(self, interaction: discord.Interaction):
        """List all commands"""
        embed = EmbedFactory.create(
            title=f"◈ {sc('Commands')}",
            color=EmbedColor.PRIMARY,
            fields=[
                {"name": sc("general"),    "value": "`/ping` `/help` `/avatar` `/userinfo` `/serverinfo` `/8ball` `/roll` `/choose`", "inline": False},
                {"name": sc("leveling"),   "value": "`/rank` `/leaderboard`", "inline": False},
                {"name": sc("economy"),    "value": "`/balance` `/daily` `/weekly` `/work` `/transfer` `/rob` `/shop` `/coinflip-bet`", "inline": False},
                {"name": sc("games"),      "value": "`/setup-game-panel`", "inline": False},
                {"name": sc("moderation"), "value": "`/warn` `/warnings` `/timeout` `/kick` `/ban` `/unban` `/purge` `/lock` `/unlock` `/slowmode` `/nickname`", "inline": False},
                {"name": sc("tickets"),    "value": "`/ticket-panel` `/ticket-setup` `/tickets` `/close-ticket`", "inline": False},
                {"name": sc("giveaways"),  "value": "`/giveaway` `/gend` `/greroll`", "inline": False},
                {"name": sc("music"),      "value": "`/play` `/pause` `/resume` `/skip` `/queue` `/nowplaying` `/volume` `/leave`", "inline": False},
                {"name": sc("utility"),    "value": "`/poll` `/remind` `/summarize` `/ask`", "inline": False},
                {"name": sc("admin"),      "value": "`/setlevel` `/setlevelchannel` `/setlogchannel` `/config` `/modules` `/sync`", "inline": False},
            ]
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="View server information")
    async def serverinfo(self, interaction: discord.Interaction):
        """Show server info"""
        guild = interaction.guild
        embed = EmbedFactory.create(
            title=f"◈ {sc(guild.name)}",
            color=EmbedColor.INFO,
            thumbnail=guild.icon.url if guild.icon else None,
            fields=[
                {"name": sc("owner"),          "value": guild.owner.mention if guild.owner else "Unknown",    "inline": True},
                {"name": sc("members"),         "value": f"**{guild.member_count:,}**",                       "inline": True},
                {"name": sc("channels"),        "value": f"**{len(guild.text_channels)}** text  **{len(guild.voice_channels)}** voice", "inline": True},
                {"name": sc("roles"),           "value": f"**{len(guild.roles)}**",                           "inline": True},
                {"name": sc("boost level"),     "value": f"**{guild.premium_tier}** ({guild.premium_subscription_count} boosts)", "inline": True},
                {"name": sc("created"),         "value": f"<t:{int(guild.created_at.timestamp())}:D>",         "inline": True},
                {"name": sc("server id"),       "value": f"`{guild.id}`",                                     "inline": False},
            ]
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    @app_commands.describe(question="Your yes/no question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        """Magic 8-ball"""
        responses = [
            ("It is certain.", EmbedColor.SUCCESS),
            ("It is decidedly so.", EmbedColor.SUCCESS),
            ("Without a doubt.", EmbedColor.SUCCESS),
            ("Yes, definitely.", EmbedColor.SUCCESS),
            ("You may rely on it.", EmbedColor.SUCCESS),
            ("As I see it, yes.", EmbedColor.SUCCESS),
            ("Most likely.", EmbedColor.SUCCESS),
            ("Outlook good.", EmbedColor.SUCCESS),
            ("Yes.", EmbedColor.SUCCESS),
            ("Signs point to yes.", EmbedColor.SUCCESS),
            ("Reply hazy, try again.", EmbedColor.WARNING),
            ("Ask again later.", EmbedColor.WARNING),
            ("Better not tell you now.", EmbedColor.WARNING),
            ("Cannot predict now.", EmbedColor.WARNING),
            ("Concentrate and ask again.", EmbedColor.WARNING),
            ("Don't count on it.", EmbedColor.ERROR),
            ("My reply is no.", EmbedColor.ERROR),
            ("My sources say no.", EmbedColor.ERROR),
            ("Outlook not so good.", EmbedColor.ERROR),
            ("Very doubtful.", EmbedColor.ERROR),
        ]
        answer, color = random.choice(responses)
        embed = EmbedFactory.create(
            title=f"🎱 {sc('8ball')}",
            description=f"**{sc('question')}** {question}\n**{sc('answer')}** {answer}",
            color=color
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="roll", description="Roll a dice")
    @app_commands.describe(sides="Number of sides (default: 6)", count="Number of dice (default: 1)")
    async def roll(self, interaction: discord.Interaction, sides: int = 6, count: int = 1):
        """Roll dice"""
        if sides < 2 or sides > 1000:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Dice", "Sides must be between 2 and 1000"), ephemeral=True)
            return
        if count < 1 or count > 20:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Count", "Count must be between 1 and 20"), ephemeral=True)
            return
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        rolls_str = "  ".join(f"`{r}`" for r in rolls)
        desc = f"{rolls_str}"
        if count > 1:
            desc += f"\n**{sc('total')}** {total}"
        embed = EmbedFactory.create(
            title=f"🎲 {sc('Roll')} {count}d{sides}",
            description=desc,
            color=EmbedColor.PRIMARY
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="choose", description="Pick randomly from your options")
    @app_commands.describe(options="Options separated by commas (e.g. pizza, sushi, tacos)")
    async def choose(self, interaction: discord.Interaction, options: str):
        """Choose between options"""
        choices = [o.strip() for o in options.split(",") if o.strip()]
        if len(choices) < 2:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Too Few Options", "Provide at least 2 options separated by commas"), ephemeral=True)
            return
        chosen = random.choice(choices)
        embed = EmbedFactory.create(
            title=f"◈ {sc('Choose')}",
            description=f"**{sc('options')}** {', '.join(choices)}\n**{sc('chosen')}** {chosen}",
            color=EmbedColor.PRIMARY
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="poll", description="Create a poll (Admin)")
    @app_commands.describe(
        question="Poll question",
        option1="Option 1",
        option2="Option 2",
        option3="Option 3 (optional)",
        option4="Option 4 (optional)",
        duration="Duration in minutes (default: 60)"
    )
    @is_admin()
    async def poll(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        duration: int = 60
    ):
        """Create a poll"""
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)

        if duration < 1 or duration > 10080:  # Max 1 week
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Duration", "Duration must be between 1 minute and 1 week"),
                ephemeral=True
            )
            return

        view = PollView(question, options, duration * 60)

        # Only show buttons for available options
        for i in range(4):
            if i >= len(options):
                view.children[i].disabled = True

        embed = view.get_results_embed()
        embed.set_footer(text=f"Poll ends in {duration} minutes | Total votes: 0")

        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"{interaction.user} created poll in {interaction.guild}")

    @app_commands.command(name="remind", description="Set a reminder (Admin)")
    @app_commands.describe(
        duration="When to remind (e.g., 1h, 30m, 1d)",
        message="Reminder message"
    )
    @is_admin()
    async def remind(self, interaction: discord.Interaction, duration: str, message: str):
        """Set a reminder"""
        seconds = TimeConverter.parse(duration)
        if not seconds:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Duration", "Please provide a valid duration (e.g., 1h, 30m, 2d)"),
                ephemeral=True
            )
            return

        if seconds > 31536000:  # Max 1 year
            await interaction.response.send_message(
                embed=EmbedFactory.error("Duration Too Long", "Maximum reminder duration is 1 year"),
                ephemeral=True
            )
            return

        remind_at = datetime.utcnow().timestamp() + seconds

        reminder_data = {
            "user_id": interaction.user.id,
            "guild_id": interaction.guild.id,
            "channel_id": interaction.channel.id,
            "message": message,
            "remind_at": remind_at,
            "completed": False
        }

        await self.db.create_reminder(reminder_data)

        embed = EmbedFactory.success(
            "Reminder Set",
            f"I'll remind you in **{TimeConverter.format_seconds(seconds)}**\n\n"
            f"Message: {message}"
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f"{interaction.user} set reminder in {interaction.guild}")

    @app_commands.command(name="serverstats", description="View server statistics (Admin)")
    @is_admin()
    async def serverstats(self, interaction: discord.Interaction):
        """View server stats"""
        guild = interaction.guild

        # Count various stats
        total_members = guild.member_count
        bots = sum(1 for member in guild.members if member.bot)
        humans = total_members - bots
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = len(guild.roles)

        embed = EmbedFactory.create(
            title=f"📊 Server Statistics - {guild.name}",
            color=EmbedColor.INFO,
            thumbnail=guild.icon.url if guild.icon else None,
            fields=[
                {"name": "👥 Total Members", "value": str(total_members), "inline": True},
                {"name": "🙋 Humans", "value": str(humans), "inline": True},
                {"name": "🤖 Bots", "value": str(bots), "inline": True},
                {"name": "💬 Text Channels", "value": str(text_channels), "inline": True},
                {"name": "🔊 Voice Channels", "value": str(voice_channels), "inline": True},
                {"name": "🎭 Roles", "value": str(roles), "inline": True},
                {"name": "👑 Owner", "value": guild.owner.mention if guild.owner else "Unknown", "inline": True},
                {"name": "📅 Created", "value": guild.created_at.strftime("%Y-%m-%d"), "inline": True},
                {"name": "🚀 Boost Level", "value": f"Level {guild.premium_tier}", "inline": True}
            ]
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Get information about a user")
    @app_commands.describe(user="User to get info about")
    async def userinfo(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Get user information"""
        target = user or interaction.user

        roles = [role.mention for role in target.roles[1:]]  # Exclude @everyone
        roles_str = ", ".join(roles[:10]) if roles else "None"
        if len(roles) > 10:
            roles_str += f" (+{len(roles) - 10} more)"

        embed = EmbedFactory.create(
            title=f"User Information - {target.display_name}",
            color=target.color if target.color.value != 0 else EmbedColor.INFO,
            thumbnail=target.display_avatar.url,
            fields=[
                {"name": "Username", "value": str(target), "inline": True},
                {"name": "ID", "value": str(target.id), "inline": True},
                {"name": "Nickname", "value": target.nick or "None", "inline": True},
                {"name": "Account Created", "value": target.created_at.strftime("%Y-%m-%d"), "inline": True},
                {"name": "Joined Server", "value": target.joined_at.strftime("%Y-%m-%d") if target.joined_at else "Unknown", "inline": True},
                {"name": "Top Role", "value": target.top_role.mention, "inline": True},
                {"name": f"Roles ({len(roles)})", "value": roles_str, "inline": False}
            ]
        )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Get user's avatar")
    @app_commands.describe(user="User to get avatar from")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        """Get user avatar"""
        target = user or interaction.user

        embed = EmbedFactory.create(
            title=f"Avatar - {target.display_name}",
            color=EmbedColor.INFO,
            image=target.display_avatar.url
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    """Setup function for cog loading"""
    await bot.add_cog(Utility(bot, bot.db, bot.config))
