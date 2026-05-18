"""
Tickets Cog for Logiq
Fully customizable support ticket system with modal-based setup.
"""

import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional
import logging
import asyncio

from utils.embeds import EmbedFactory, EmbedColor, sc
from utils.permissions import is_admin
from database.db_manager import DatabaseManager

logger = logging.getLogger(__name__)

BUTTON_STYLES = {
    "green": discord.ButtonStyle.success,
    "blue":  discord.ButtonStyle.primary,
    "red":   discord.ButtonStyle.danger,
    "grey":  discord.ButtonStyle.secondary,
}

_FOOTER = sc("rioshin") + " • " + sc("rioshinbot")


# ── Ticket button ──────────────────────────────────────────────────────────────
class TicketButton(discord.ui.Button):
    """Create-ticket button. custom_id is always 'create_ticket' for persistence."""

    def __init__(
        self,
        cog: "Tickets",
        *,
        label: str = "Create Ticket",
        emoji: str = "🎫",
        style: discord.ButtonStyle = discord.ButtonStyle.success,
    ):
        super().__init__(
            label=label,
            emoji=emoji or None,
            style=style,
            custom_id="create_ticket",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.create_ticket_for_user(interaction)


# ── Views ──────────────────────────────────────────────────────────────────────
class TicketCreateView(discord.ui.View):
    """Default persistent view — registered on startup so buttons survive restarts."""

    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.add_item(TicketButton(cog))


class TicketPanelView(discord.ui.View):
    """Panel view built from stored config — custom label / emoji / colour."""

    def __init__(
        self,
        cog: "Tickets",
        *,
        label: str,
        emoji: str,
        style: discord.ButtonStyle,
    ):
        super().__init__(timeout=None)
        self.add_item(TicketButton(cog, label=label, emoji=emoji, style=style))


class TicketControlView(discord.ui.View):
    """Close-ticket button inside a ticket channel."""

    def __init__(self, cog: "Tickets"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(
        label="Close Ticket",
        style=discord.ButtonStyle.danger,
        custom_id="close_ticket_btn",
        emoji="🔒",
    )
    async def close_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket_for_user(interaction, "Closed by user")


# ── Setup modal ────────────────────────────────────────────────────────────────
class TicketSetupModal(discord.ui.Modal, title="🎫  Ticket Panel Setup"):
    """Editable fields for the ticket panel appearance."""

    panel_title = discord.ui.TextInput(
        label="Panel Title",
        placeholder="e.g.  Support Tickets",
        default="Support Tickets",
        max_length=100,
    )
    panel_desc = discord.ui.TextInput(
        label="Panel Description",
        style=discord.TextStyle.paragraph,
        placeholder="What should users know before opening a ticket?",
        default="Need help? Click the button below to open a private support ticket.\nA staff member will assist you shortly.",
        max_length=1000,
    )
    button_label = discord.ui.TextInput(
        label="Button Label",
        placeholder="e.g.  Open Ticket",
        default="Create Ticket",
        max_length=80,
    )
    button_emoji = discord.ui.TextInput(
        label="Button Emoji  (optional)",
        placeholder="e.g.  🎫  or leave blank",
        default="🎫",
        required=False,
        max_length=20,
    )
    welcome_msg = discord.ui.TextInput(
        label="Ticket Welcome Message",
        style=discord.TextStyle.paragraph,
        placeholder="First message shown when a ticket channel is created.",
        default="Hello! Please describe your issue and a staff member will assist you shortly.",
        max_length=1000,
    )

    def __init__(
        self,
        cog: "Tickets",
        *,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel,
        support_role: Optional[discord.Role],
        button_color: str,
    ):
        super().__init__()
        self.cog          = cog
        self.category     = category
        self.log_channel  = log_channel
        self.support_role = support_role
        self.button_color = button_color

    async def on_submit(self, interaction: discord.Interaction):
        guild_config = await self.cog.db.get_guild(interaction.guild.id)
        if not guild_config:
            await self.cog.db.create_guild(interaction.guild.id)

        emoji = self.button_emoji.value.strip() or "🎫"

        update = {
            "ticket_category":     self.category.id,
            "ticket_log_channel":  self.log_channel.id,
            "ticket_panel_title":  self.panel_title.value,
            "ticket_panel_desc":   self.panel_desc.value,
            "ticket_button_label": self.button_label.value,
            "ticket_button_emoji": emoji,
            "ticket_button_color": self.button_color,
            "ticket_welcome_msg":  self.welcome_msg.value,
        }
        if self.support_role:
            update["support_role"] = self.support_role.id

        await self.cog.db.update_guild(interaction.guild.id, update)

        embed = discord.Embed(
            title=f"✦ {sc('Ticket System Configured')}",
            color=EmbedColor.SUCCESS,
        )
        embed.add_field(name=sc("panel title"),  value=self.panel_title.value,    inline=True)
        embed.add_field(name=sc("button"),       value=f"{emoji} **{self.button_label.value}** ({self.button_color})", inline=True)
        embed.add_field(name=sc("category"),     value=self.category.mention,     inline=True)
        embed.add_field(name=sc("log channel"),  value=self.log_channel.mention,  inline=True)
        embed.add_field(name=sc("support role"), value=self.support_role.mention if self.support_role else "*none*", inline=True)
        embed.add_field(
            name=sc("next step"),
            value="Run `/ticket-panel` in the channel where you want the panel to appear.",
            inline=False,
        )
        embed.set_footer(text=_FOOTER)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        logger.info(f"{interaction.user} configured ticket system in {interaction.guild}")


# ── Cog ────────────────────────────────────────────────────────────────────────
class Tickets(commands.Cog):
    """Support ticket system cog."""

    def __init__(self, bot: commands.Bot, db: DatabaseManager, config: dict):
        self.bot    = bot
        self.db     = db
        self.config = config
        self.module_config = config.get("modules", {}).get("tickets", {})
        bot.add_view(TicketCreateView(self))
        bot.add_view(TicketControlView(self))

    # ── Helpers ───────────────────────────────────────────────────────────────
    async def _get_ticket_config(self, guild: discord.Guild) -> dict:
        """Return guild config with sensible defaults for ticket fields."""
        raw = await self.db.get_guild(guild.id) or {}
        return {
            "panel_title":  raw.get("ticket_panel_title",  "Support Tickets"),
            "panel_desc":   raw.get("ticket_panel_desc",   "Need help? Click the button below to open a private support ticket."),
            "btn_label":    raw.get("ticket_button_label", "Create Ticket"),
            "btn_emoji":    raw.get("ticket_button_emoji", "🎫"),
            "btn_color":    raw.get("ticket_button_color", "green"),
            "welcome_msg":  raw.get("ticket_welcome_msg",  "Please describe your issue and a staff member will assist you shortly."),
            "category_id":  raw.get("ticket_category"),
            "log_id":       raw.get("ticket_log_channel"),
            "support_role": raw.get("support_role"),
        }

    async def create_ticket_for_user(self, interaction: discord.Interaction):
        """Create a ticket channel for the interacting user."""
        guild_config = await self.db.get_guild(interaction.guild.id)
        if not guild_config:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Configured", "Run `/ticketsetup` first to configure the ticket system."),
                ephemeral=True,
            )
            return

        ticket_category_id = guild_config.get("ticket_category")
        if not ticket_category_id:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Configured", "No ticket category set. Run `/ticketsetup`."),
                ephemeral=True,
            )
            return

        category = interaction.guild.get_channel(ticket_category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Error", "Ticket category not found — reconfigure with `/ticketsetup`."),
                ephemeral=True,
            )
            return

        # One open ticket per user
        safe_name = interaction.user.name.lower()
        existing = [ch for ch in category.channels if ch.name.startswith(f"ticket-{safe_name}")]
        if existing:
            await interaction.response.send_message(
                embed=EmbedFactory.warning("Ticket Exists", f"You already have an open ticket: {existing[0].mention}"),
                ephemeral=True,
            )
            return

        try:
            overwrites = {
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user:               discord.PermissionOverwrite(read_messages=True, send_messages=True),
                interaction.guild.me:           discord.PermissionOverwrite(read_messages=True, send_messages=True),
            }
            support_role_id = guild_config.get("support_role")
            if support_role_id:
                role = interaction.guild.get_role(support_role_id)
                if role:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

            channel = await category.create_text_channel(
                name=f"ticket-{interaction.user.name}",
                overwrites=overwrites,
            )

            ticket_data = {
                "guild_id":  interaction.guild.id,
                "user_id":   interaction.user.id,
                "channel_id": channel.id,
                "category":  "General Support",
                "status":    "open",
            }
            ticket_id = await self.db.create_ticket(ticket_data)

            # Welcome embed inside the ticket
            welcome_text = guild_config.get("ticket_welcome_msg", "Please describe your issue and a staff member will assist you shortly.")
            welcome_embed = discord.Embed(
                title=f"🎫 {sc('Ticket')} — {interaction.user.display_name}",
                description=f"{interaction.user.mention}\n\n{welcome_text}\n\n**{sc('ticket id')}** `{ticket_id}`",
                color=EmbedColor.PRIMARY,
            )
            welcome_embed.set_thumbnail(url=interaction.user.display_avatar.url)
            welcome_embed.set_footer(text=_FOOTER)

            ping_msg = interaction.user.mention
            if support_role_id:
                role = interaction.guild.get_role(support_role_id)
                if role:
                    ping_msg += f" | {role.mention}"

            await channel.send(content=ping_msg, embed=welcome_embed, view=TicketControlView(self))

            # Log to ticket log channel
            log_ch_id = guild_config.get("ticket_log_channel")
            if log_ch_id:
                log_ch = interaction.guild.get_channel(log_ch_id)
                if log_ch:
                    log_embed = discord.Embed(
                        title=f"🎫 {sc('New Ticket')}",
                        color=EmbedColor.SUCCESS,
                    )
                    log_embed.add_field(name=sc("ticket"),     value=channel.mention,              inline=True)
                    log_embed.add_field(name=sc("opened by"),  value=interaction.user.mention,     inline=True)
                    log_embed.add_field(name=sc("ticket id"),  value=f"`{ticket_id}`",             inline=True)
                    log_embed.set_footer(text=_FOOTER)
                    await log_ch.send(embed=log_embed)

            await interaction.response.send_message(
                embed=EmbedFactory.success("Ticket Created", f"Your ticket is ready: {channel.mention}"),
                ephemeral=True,
            )
            logger.info(f"Ticket created for {interaction.user} in {interaction.guild}")

        except discord.Forbidden:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Permission Error", "I don't have permission to create channels."),
                ephemeral=True,
            )

    async def close_ticket_for_user(self, interaction: discord.Interaction, reason: str = "Resolved"):
        """Close and delete a ticket channel."""
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not a Ticket", "This command can only be used inside a ticket channel."),
                ephemeral=True,
            )
            return

        guild_config = await self.db.get_guild(interaction.guild.id)
        support_role_id = guild_config.get("support_role") if guild_config else None

        is_owner = interaction.channel.name == f"ticket-{interaction.user.name}"
        is_staff = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        has_role = (
            support_role_id
            and isinstance(interaction.user, discord.Member)
            and interaction.guild.get_role(support_role_id) in interaction.user.roles
        )

        if not (is_owner or is_staff or has_role):
            await interaction.response.send_message(
                embed=EmbedFactory.error("No Permission", "Only the ticket owner or staff can close this ticket."),
                ephemeral=True,
            )
            return

        # Log closure
        if guild_config:
            log_ch_id = guild_config.get("ticket_log_channel")
            if log_ch_id:
                log_ch = interaction.guild.get_channel(log_ch_id)
                if log_ch:
                    log_embed = discord.Embed(
                        title=f"🔒 {sc('Ticket Closed')}",
                        color=EmbedColor.WARNING,
                    )
                    log_embed.add_field(name=sc("ticket"),     value=interaction.channel.name,  inline=True)
                    log_embed.add_field(name=sc("closed by"),  value=interaction.user.mention,  inline=True)
                    log_embed.add_field(name=sc("reason"),     value=reason,                    inline=False)
                    log_embed.set_footer(text=_FOOTER)
                    await log_ch.send(embed=log_embed)

        closing_embed = discord.Embed(
            title=f"🔒 {sc('Closing Ticket')}",
            description=f"Closed by {interaction.user.mention}\n**{sc('reason')}** {reason}\n\nChannel will be deleted in **5 seconds**.",
            color=EmbedColor.WARNING,
        )
        closing_embed.set_footer(text=_FOOTER)
        await interaction.response.send_message(embed=closing_embed)

        try:
            await self.db.db.tickets.update_one(
                {"channel_id": interaction.channel.id},
                {"$set": {"status": "closed", "closed_by": interaction.user.id, "close_reason": reason}},
            )
        except Exception as e:
            logger.error(f"Error updating ticket in DB: {e}")

        logger.info(f"Ticket {interaction.channel.name} closed by {interaction.user}")

        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.Forbidden:
            logger.error(f"No permission to delete ticket channel: {interaction.channel.name}")
        except Exception as e:
            logger.error(f"Error deleting ticket channel: {e}")

    # ── Commands ──────────────────────────────────────────────────────────────

    @app_commands.command(name="ticketsetup", description="Configure the ticket system — opens an editable form (Admin)")
    @app_commands.describe(
        category="Category where ticket channels will be created",
        log_channel="Channel for ticket open/close logs",
        support_role="Role that can view and manage all tickets",
        button_color="Colour of the Create Ticket button",
    )
    @app_commands.choices(button_color=[
        app_commands.Choice(name="🟢 Green",  value="green"),
        app_commands.Choice(name="🔵 Blue",   value="blue"),
        app_commands.Choice(name="🔴 Red",    value="red"),
        app_commands.Choice(name="⚪ Grey",   value="grey"),
    ])
    @is_admin()
    async def ticketsetup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel,
        support_role: Optional[discord.Role] = None,
        button_color: str = "green",
    ):
        """Open the ticket system setup modal."""
        modal = TicketSetupModal(
            self,
            category=category,
            log_channel=log_channel,
            support_role=support_role,
            button_color=button_color,
        )
        await interaction.response.send_modal(modal)

    @app_commands.command(name="ticket-panel", description="Send the ticket creation panel (Admin)")
    @app_commands.describe(channel="Channel to send the panel in (defaults to current channel)")
    @is_admin()
    async def ticket_panel(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        """Send persistent ticket panel using stored config."""
        cfg = await self._get_ticket_config(interaction.guild)

        if not cfg["category_id"]:
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Configured", "Run `/ticketsetup` first."),
                ephemeral=True,
            )
            return

        target = channel or interaction.channel
        style  = BUTTON_STYLES.get(cfg["btn_color"], discord.ButtonStyle.success)
        view   = TicketPanelView(self, label=cfg["btn_label"], emoji=cfg["btn_emoji"], style=style)

        panel_embed = discord.Embed(
            title=f"🎫 {cfg['panel_title']}",
            description=cfg["panel_desc"],
            color=EmbedColor.PRIMARY,
        )
        panel_embed.set_footer(text=_FOOTER)

        await target.send(embed=panel_embed, view=view)

        await interaction.response.send_message(
            embed=EmbedFactory.success("Panel Sent", f"Ticket panel posted in {target.mention}."),
            ephemeral=True,
        )

    @app_commands.command(name="close-ticket", description="Close a ticket (staff or owner)")
    @app_commands.describe(reason="Reason for closing")
    async def close_ticket(self, interaction: discord.Interaction, reason: Optional[str] = "Resolved"):
        """Close the current ticket channel."""
        await self.close_ticket_for_user(interaction, reason)

    @app_commands.command(name="tickets", description="View all open tickets (Admin)")
    @is_admin()
    async def view_tickets(self, interaction: discord.Interaction):
        """List all open ticket channels."""
        guild_config = await self.db.get_guild(interaction.guild.id)
        if not guild_config or not guild_config.get("ticket_category"):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Not Configured", "Run `/ticketsetup` first."),
                ephemeral=True,
            )
            return

        category = interaction.guild.get_channel(guild_config["ticket_category"])
        if not category or not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                embed=EmbedFactory.error("Error", "Ticket category not found."),
                ephemeral=True,
            )
            return

        ticket_channels = [ch for ch in category.channels if ch.name.startswith("ticket-")]

        if not ticket_channels:
            await interaction.response.send_message(
                embed=EmbedFactory.info("No Active Tickets", "There are currently no open tickets."),
                ephemeral=True,
            )
            return

        lines = "\n".join(
            f"🎫 {ch.mention} — **{ch.name.replace('ticket-', '')}**"
            for ch in ticket_channels[:25]
        )
        embed = discord.Embed(
            title=f"🎫 {sc('Active Tickets')} ({len(ticket_channels)})",
            description=lines,
            color=EmbedColor.INFO,
        )
        embed.set_footer(text=_FOOTER)
        await interaction.response.send_message(embed=embed)

    # Keep old command name as alias
    @app_commands.command(name="ticket-setup", description="Configure the ticket system (Admin) — use /ticketsetup instead")
    @app_commands.describe(
        category="Category for ticket channels",
        log_channel="Channel for ticket logs",
        support_role="Role to ping for new tickets (optional)",
    )
    @is_admin()
    async def ticket_setup_legacy(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        log_channel: discord.TextChannel,
        support_role: Optional[discord.Role] = None,
    ):
        """Legacy alias — redirects to the modal setup."""
        modal = TicketSetupModal(
            self,
            category=category,
            log_channel=log_channel,
            support_role=support_role,
            button_color="green",
        )
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    """Setup function for cog loading."""
    await bot.add_cog(Tickets(bot, bot.db, bot.config))
