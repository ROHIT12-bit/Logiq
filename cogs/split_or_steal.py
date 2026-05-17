"""
Split or Steal Cog for Logiq
A social deception game where two players secretly choose to split or steal a prize.
"""

import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
from typing import Optional
import logging

from utils.embeds import EmbedFactory, EmbedColor, sc
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

# ── Outcome constants ──────────────────────────────────────────────────────────
SPLIT  = "split"
STEAL  = "steal"

OUTCOME_SPLIT_SPLIT = "split_split"
OUTCOME_SPLIT_STEAL = "split_steal"
OUTCOME_STEAL_SPLIT = "steal_split"
OUTCOME_STEAL_STEAL = "steal_steal"


def _outcome(c1: str, c2: str) -> str:
    return f"{c1}_{c2}"


# ── Private choice view (sent via DM) ─────────────────────────────────────────
class ChoiceView(discord.ui.View):
    """SPLIT / STEAL buttons sent to each player in DMs."""

    def __init__(self, games: dict, guild_id: int, user_id: int):
        super().__init__(timeout=7200)   # 2-hour window
        self.games   = games
        self.guild_id = guild_id
        self.user_id  = user_id
        self.chosen   = False

    def _lock(self):
        self.chosen = True
        for child in self.children:
            child.disabled = True

    async def _record(self, interaction: discord.Interaction, choice: str):
        game = self.games.get(self.guild_id)
        if not game:
            await interaction.response.edit_message(
                embed=EmbedFactory.error("Game Over", "That game no longer exists."),
                view=None
            )
            return

        if self.chosen:
            await interaction.response.send_message(
                embed=EmbedFactory.warning("Already Chosen", "You have already locked in your choice."),
                ephemeral=True
            )
            return

        game["choices"][self.user_id] = choice
        self._lock()

        label = "🤝 Split" if choice == SPLIT else "🦹 Steal"
        colour = EmbedColor.SUCCESS if choice == SPLIT else EmbedColor.ERROR
        embed = EmbedFactory.create(
            title=f"◈ {sc('Choice Locked')}",
            description=(
                f"**{sc('your choice')}** {label}\n\n"
                f"Your selection is sealed. The admin will reveal results when both players have chosen."
            ),
            color=colour
        )
        embed.set_footer(text=sc("rioshin") + " • " + sc("rioshinbot"))
        await interaction.response.edit_message(embed=embed, view=self)
        logger.info(f"User {self.user_id} chose {choice} in guild {self.guild_id}")

    @discord.ui.button(label="SPLIT", style=discord.ButtonStyle.success, emoji="🤝", custom_id="sos_split")
    async def btn_split(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._record(interaction, SPLIT)

    @discord.ui.button(label="STEAL", style=discord.ButtonStyle.danger, emoji="🦹", custom_id="sos_steal")
    async def btn_steal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._record(interaction, STEAL)


# ── Cog ───────────────────────────────────────────────────────────────────────
class SplitOrSteal(commands.Cog):
    """Split or Steal social deception game."""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot    = bot
        self.db     = db
        self.config = config
        # {guild_id: game_state_dict}
        self.games: dict[int, dict] = {}

    # ── /splitorsteal ─────────────────────────────────────────────────────────
    @app_commands.command(
        name="splitorsteal",
        description="Start a Split or Steal game between two users (Admin)"
    )
    @app_commands.describe(
        player1="First player",
        player2="Second player",
        prize="Prize pool (currency)"
    )
    @is_admin()
    async def start_game(
        self,
        interaction: discord.Interaction,
        player1: discord.Member,
        player2: discord.Member,
        prize: int
    ):
        """Launch a Split or Steal game."""

        # ── Validation ────────────────────────────────────────────────────────
        if prize <= 0:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Prize", "The prize must be greater than zero."),
                ephemeral=True
            )
            return

        if player1.id == player2.id:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Players", "Both players must be different users."),
                ephemeral=True
            )
            return

        if player1.bot or player2.bot:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Invalid Players", "Bots cannot participate in this game."),
                ephemeral=True
            )
            return

        if interaction.guild.id in self.games:
            await interaction.response.send_message(
                embed=EmbedFactory.warning(
                    "Game in Progress",
                    "A game is already running in this server. Use `/reveal` to finish it first."
                ),
                ephemeral=True
            )
            return

        # ── Store game state ──────────────────────────────────────────────────
        self.games[interaction.guild.id] = {
            "player1":    player1.id,
            "player2":    player2.id,
            "prize":      prize,
            "channel_id": interaction.channel.id,
            "started_by": interaction.user.id,
            "started_at": datetime.utcnow().timestamp(),
            "choices":    {}
        }

        currency = self.config.get("modules", {}).get("economy", {}).get("currency_symbol", "💎")

        # ── Public announcement ───────────────────────────────────────────────
        announce = EmbedFactory.create(
            title=f"🎭 {sc('Split or Steal')}",
            description=(
                f"{player1.mention} vs {player2.mention}\n\n"
                f"**{sc('prize pool')}** {currency} {prize:,}\n\n"
                "Each player has been sent a **private DM** to make their secret choice.\n"
                "No one will know what was chosen until the admin runs `/reveal`."
            ),
            color=EmbedColor.PRIMARY,
            fields=[
                {
                    "name": sc("how it works"),
                    "value": (
                        "🤝 **Split + Split** — prize divided equally\n"
                        "🦹 **Split + Steal** — the stealer takes everything\n"
                        "💀 **Steal + Steal** — both players lose it all"
                    ),
                    "inline": False
                }
            ]
        )
        announce.set_footer(text=sc("rioshin") + " • " + sc("rioshinbot"))

        await interaction.response.send_message(embed=announce)

        # ── DM both players ───────────────────────────────────────────────────
        dm_embed_base = EmbedFactory.create(
            title=f"🎭 {sc('Split or Steal — Your Choice')}",
            description=(
                f"You've been invited to a **Split or Steal** game in **{interaction.guild.name}**.\n\n"
                f"**{sc('opponent')}** {player2.display_name if interaction.user.id != player1.id else player1.display_name}\n"
                f"**{sc('prize pool')}** {currency} {prize:,}\n\n"
                "Pick your strategy. Your opponent **cannot** see your choice until both have locked in."
            ),
            color=EmbedColor.WARNING,
            fields=[
                {
                    "name": "🤝 " + sc("split"),
                    "value": "If both split — you share the prize equally.",
                    "inline": True
                },
                {
                    "name": "🦹 " + sc("steal"),
                    "value": "If you steal and they split — you take everything.",
                    "inline": True
                }
            ]
        )
        dm_embed_base.set_footer(text=sc("rioshin") + " • " + sc("rioshinbot"))

        failed_dms = []
        for player in (player1, player2):
            view = ChoiceView(self.games, interaction.guild.id, player.id)
            try:
                dm_embed = dm_embed_base.copy()
                dm_embed.description = (
                    f"You've been challenged in a **Split or Steal** game in **{interaction.guild.name}**.\n\n"
                    f"**{sc('opponent')}** {(player2 if player.id == player1.id else player1).display_name}\n"
                    f"**{sc('prize pool')}** {currency} {prize:,}\n\n"
                    "Pick your strategy. Your opponent **cannot** see your choice until both have locked in."
                )
                await player.send(embed=dm_embed, view=view)
            except discord.Forbidden:
                failed_dms.append(player.mention)

        if failed_dms:
            await interaction.followup.send(
                embed=EmbedFactory.warning(
                    "DM Failed",
                    f"Could not DM {', '.join(failed_dms)}. They must enable DMs from server members.\n"
                    "The game has been cancelled."
                ),
                ephemeral=True
            )
            self.games.pop(interaction.guild.id, None)

        logger.info(f"{interaction.user} started Split or Steal: {player1} vs {player2} for {prize} in {interaction.guild}")

    # ── /reveal ───────────────────────────────────────────────────────────────
    @app_commands.command(
        name="reveal",
        description="Reveal the Split or Steal result (Admin)"
    )
    @is_admin()
    async def reveal(self, interaction: discord.Interaction):
        """Reveal the outcome of the active game."""

        game = self.games.get(interaction.guild.id)
        if not game:
            await interaction.response.send_message(
                embed=EmbedFactory.error("No Active Game", "There is no Split or Steal game running in this server."),
                ephemeral=True
            )
            return

        await interaction.response.defer()

        player1 = interaction.guild.get_member(game["player1"]) or await self.bot.fetch_user(game["player1"])
        player2 = interaction.guild.get_member(game["player2"]) or await self.bot.fetch_user(game["player2"])
        prize   = game["prize"]
        choices = game["choices"]
        currency = self.config.get("modules", {}).get("economy", {}).get("currency_symbol", "💎")

        c1 = choices.get(game["player1"])
        c2 = choices.get(game["player2"])

        # ── Warn if someone hasn't chosen ─────────────────────────────────────
        missing = []
        if not c1:
            missing.append(player1.mention)
        if not c2:
            missing.append(player2.mention)

        if missing:
            await interaction.followup.send(
                embed=EmbedFactory.warning(
                    "Waiting on Players",
                    f"{', '.join(missing)} {'have' if len(missing) > 1 else 'has'} not yet made a choice.\n"
                    "Force-reveal anyway? Their missing choice will count as **Steal**."
                ),
                view=ForceRevealView(self, interaction.guild.id),
                ephemeral=True
            )
            return

        await self._do_reveal(interaction.channel, game, player1, player2, currency, c1, c2, interaction.guild.id)
        self.games.pop(interaction.guild.id, None)

    async def _do_reveal(self, channel, game, player1, player2, currency, c1, c2, guild_id: int):
        """Calculate outcome and post the result embed."""
        prize   = game["prize"]
        outcome = _outcome(c1, c2)

        choice_icon = {SPLIT: "🤝 Split", STEAL: "🦹 Steal"}

        # ── Calculate winnings ────────────────────────────────────────────────
        p1_wins = p2_wins = 0
        result_title  = ""
        result_desc   = ""
        result_color  = EmbedColor.INFO

        if outcome == OUTCOME_SPLIT_SPLIT:
            half = prize // 2
            p1_wins = half
            p2_wins = prize - half   # handles odd prize rounding
            result_title = f"🤝 {sc('Both Split — Everyone Wins')}"
            result_desc  = (
                f"{player1.mention} and {player2.mention} **both chose to Split**.\n\n"
                f"The prize of **{currency} {prize:,}** is divided equally.\n\n"
                f"{player1.mention} receives **{currency} {p1_wins:,}**\n"
                f"{player2.mention} receives **{currency} {p2_wins:,}**"
            )
            result_color = EmbedColor.SUCCESS

        elif outcome == OUTCOME_SPLIT_STEAL:
            p2_wins = prize
            result_title = f"🦹 {sc('Betrayal — Steal Wins')}"
            result_desc  = (
                f"{player1.mention} chose to **Split** in good faith.\n"
                f"{player2.mention} chose to **Steal**.\n\n"
                f"{player2.mention} takes the entire prize of **{currency} {prize:,}**.\n"
                f"{player1.mention} walks away with **nothing**."
            )
            result_color = EmbedColor.ERROR

        elif outcome == OUTCOME_STEAL_SPLIT:
            p1_wins = prize
            result_title = f"🦹 {sc('Betrayal — Steal Wins')}"
            result_desc  = (
                f"{player1.mention} chose to **Steal**.\n"
                f"{player2.mention} chose to **Split** in good faith.\n\n"
                f"{player1.mention} takes the entire prize of **{currency} {prize:,}**.\n"
                f"{player2.mention} walks away with **nothing**."
            )
            result_color = EmbedColor.ERROR

        elif outcome == OUTCOME_STEAL_STEAL:
            result_title = f"💀 {sc('Mutual Destruction')}"
            result_desc  = (
                f"Both {player1.mention} and {player2.mention} chose to **Steal**.\n\n"
                f"Greed destroyed the prize. **No one** receives anything.\n"
                f"The {currency} {prize:,} vanishes into the void."
            )
            result_color = EmbedColor.ERROR

        # ── Apply balance changes ─────────────────────────────────────────────
        if p1_wins > 0:
            await self.db.add_balance(player1.id, guild_id, p1_wins)
        if p2_wins > 0:
            await self.db.add_balance(player2.id, guild_id, p2_wins)

        # ── Build result embed ────────────────────────────────────────────────
        embed = EmbedFactory.create(
            title=result_title,
            description=result_desc,
            color=result_color,
            fields=[
                {
                    "name": sc("choices revealed"),
                    "value": (
                        f"{player1.mention} → **{choice_icon[c1]}**\n"
                        f"{player2.mention} → **{choice_icon[c2]}**"
                    ),
                    "inline": False
                },
                {
                    "name": sc("prize pool"),
                    "value": f"{currency} {prize:,}",
                    "inline": True
                },
                {
                    "name": sc("result"),
                    "value": (
                        f"{player1.mention} +{currency} {p1_wins:,}\n"
                        f"{player2.mention} +{currency} {p2_wins:,}"
                    ) if p1_wins or p2_wins else "No payouts.",
                    "inline": True
                }
            ]
        )
        embed.set_footer(text=sc("rioshin") + " • " + sc("rioshinbot"))

        await channel.send(embed=embed)
        logger.info(f"Split or Steal revealed: {player1} ({c1}) vs {player2} ({c2}), prize={prize}")

    # ── /cancelgame ───────────────────────────────────────────────────────────
    @app_commands.command(
        name="cancelgame",
        description="Cancel the current Split or Steal game (Admin)"
    )
    @is_admin()
    async def cancel_game(self, interaction: discord.Interaction):
        """Cancel the active game without a payout."""
        if interaction.guild.id not in self.games:
            await interaction.response.send_message(
                embed=EmbedFactory.error("No Active Game", "There is no game to cancel."),
                ephemeral=True
            )
            return

        self.games.pop(interaction.guild.id)
        await interaction.response.send_message(
            embed=EmbedFactory.success("Game Cancelled", "The Split or Steal game has been cancelled. No prizes were awarded."),
            ephemeral=True
        )


# ── Force-reveal confirmation view ────────────────────────────────────────────
class ForceRevealView(discord.ui.View):
    """Confirmation buttons when a player hasn't chosen yet."""

    def __init__(self, cog: SplitOrSteal, guild_id: int):
        super().__init__(timeout=60)
        self.cog      = cog
        self.guild_id = guild_id

    @discord.ui.button(label="Force Reveal", style=discord.ButtonStyle.danger, emoji="⚡")
    async def force_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        game = self.cog.games.get(self.guild_id)
        if not game:
            await interaction.response.edit_message(
                embed=EmbedFactory.error("Game Gone", "The game no longer exists."), view=None)
            return

        # Missing choices default to STEAL
        if not game["choices"].get(game["player1"]):
            game["choices"][game["player1"]] = STEAL
        if not game["choices"].get(game["player2"]):
            game["choices"][game["player2"]] = STEAL

        c1 = game["choices"][game["player1"]]
        c2 = game["choices"][game["player2"]]

        currency = self.cog.config.get("modules", {}).get("economy", {}).get("currency_symbol", "💎")
        guild    = self.cog.bot.get_guild(self.guild_id)
        player1  = guild.get_member(game["player1"]) or await self.cog.bot.fetch_user(game["player1"])
        player2  = guild.get_member(game["player2"]) or await self.cog.bot.fetch_user(game["player2"])
        channel  = self.cog.bot.get_channel(game["channel_id"])

        await interaction.response.edit_message(
            embed=EmbedFactory.info("Revealing…", "Calculating results now."), view=None)

        self.cog.games.pop(self.guild_id, None)
        await self.cog._do_reveal(channel, game, player1, player2, currency, c1, c2, self.guild_id)

    @discord.ui.button(label="Wait Longer", style=discord.ButtonStyle.secondary, emoji="⏳")
    async def wait_longer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=EmbedFactory.info("Waiting", "Game is still active. Players can still submit their choices."),
            view=None
        )


async def setup(bot: commands.Bot):
    """Setup function for cog loading."""
    await bot.add_cog(SplitOrSteal(bot, bot.db, bot.config))
