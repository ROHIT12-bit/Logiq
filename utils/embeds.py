"""
Embed utilities for Logiq
Creates consistent, themed embeds with small caps styling
"""

import discord
from typing import Optional, List, Dict, Any
from datetime import datetime


_SC_MAP = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "ᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢᴀʙᴄᴅᴇꜰɢʜɪᴊᴋʟᴍɴᴏᴘǫʀꜱᴛᴜᴠᴡxʏᴢ"
)

def sc(text: str) -> str:
    """Convert text to small caps unicode"""
    return text.translate(_SC_MAP)


class EmbedColor:
    """Color palette for embeds"""
    PRIMARY  = 0x5865F2
    SUCCESS  = 0x57F287
    WARNING  = 0xFEE75C
    ERROR    = 0xED4245
    INFO     = 0x5865F2
    PREMIUM  = 0xF47FFF
    LEVELING = 0xFEE75C
    ECONOMY  = 0x57F287
    AI       = 0x00D9FF
    DARK     = 0x2B2D31


_FOOTER = sc("logiq") + "  ·  logiq bot"


class EmbedFactory:
    """Factory for creating themed embeds"""

    @staticmethod
    def create(
        title: Optional[str] = None,
        description: Optional[str] = None,
        color: int = EmbedColor.PRIMARY,
        footer: Optional[str] = None,
        thumbnail: Optional[str] = None,
        image: Optional[str] = None,
        fields: Optional[List[Dict[str, Any]]] = None,
        timestamp: bool = True
    ) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.utcnow() if timestamp else None
        )
        embed.set_footer(text=footer if footer else _FOOTER)

        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        if fields:
            for field in fields:
                embed.add_field(
                    name=field.get("name", ""),
                    value=field.get("value", ""),
                    inline=field.get("inline", True)
                )
        return embed

    @staticmethod
    def success(title: str, description: str) -> discord.Embed:
        return EmbedFactory.create(
            title=f"✦ {sc(title)}",
            description=f"{description}",
            color=EmbedColor.SUCCESS
        )

    @staticmethod
    def error(title: str, description: str) -> discord.Embed:
        return EmbedFactory.create(
            title=f"✗ {sc(title)}",
            description=f"{description}",
            color=EmbedColor.ERROR
        )

    @staticmethod
    def warning(title: str, description: str) -> discord.Embed:
        return EmbedFactory.create(
            title=f"⚠ {sc(title)}",
            description=f"{description}",
            color=EmbedColor.WARNING
        )

    @staticmethod
    def info(title: str, description: str) -> discord.Embed:
        return EmbedFactory.create(
            title=f"◈ {sc(title)}",
            description=f"{description}",
            color=EmbedColor.INFO
        )

    @staticmethod
    def ai_response(message: str, model: str = "AI") -> discord.Embed:
        return EmbedFactory.create(
            title=f"◎ {sc('AI Response')}",
            description=message,
            color=EmbedColor.AI,
            footer=f"{sc('powered by')} {model}  ·  {sc('logiq')}"
        )

    @staticmethod
    def level_up(user: discord.Member, new_level: int, xp: int) -> discord.Embed:
        return EmbedFactory.create(
            title=f"🎉 {sc('Level Up')}",
            description=f"{user.mention} just reached **{sc('Level')} {new_level}**!",
            color=EmbedColor.LEVELING,
            thumbnail=user.display_avatar.url,
            fields=[
                {"name": sc("level"),     "value": f"**{new_level}**", "inline": True},
                {"name": sc("total xp"),  "value": f"**{xp:,}**",     "inline": True},
            ]
        )

    @staticmethod
    def rank_card(user: discord.Member, level: int, xp: int, rank: int, next_level_xp: int) -> discord.Embed:
        current_xp   = xp % next_level_xp
        progress_pct = current_xp / next_level_xp
        filled       = int(progress_pct * 12)
        bar          = "█" * filled + "░" * (12 - filled)

        return EmbedFactory.create(
            title=f"◈ {sc('Rank')} — {user.display_name}",
            color=EmbedColor.LEVELING,
            thumbnail=user.display_avatar.url,
            description=f"`{bar}` {progress_pct * 100:.1f}%",
            fields=[
                {"name": sc("rank"),     "value": f"**#{rank}**",                       "inline": True},
                {"name": sc("level"),    "value": f"**{level}**",                       "inline": True},
                {"name": sc("xp"),       "value": f"**{current_xp:,}** / {next_level_xp:,}", "inline": True},
            ]
        )

    @staticmethod
    def economy_balance(user: discord.Member, balance: int, currency_symbol: str = "💎") -> discord.Embed:
        return EmbedFactory.create(
            title=f"{currency_symbol} {sc('Balance')}",
            color=EmbedColor.ECONOMY,
            thumbnail=user.display_avatar.url,
            description=f"{user.mention}\n{currency_symbol}  **{balance:,}**"
        )

    @staticmethod
    def moderation_action(
        action: str,
        user: discord.Member,
        moderator: discord.Member,
        reason: str
    ) -> discord.Embed:
        return EmbedFactory.create(
            title=f"🔨 {sc(action)}",
            color=EmbedColor.ERROR,
            fields=[
                {"name": sc("user"),      "value": f"{user.mention}\n`{user.id}`", "inline": True},
                {"name": sc("moderator"), "value": moderator.mention,              "inline": True},
                {"name": sc("reason"),    "value": reason,                         "inline": False},
            ]
        )

    @staticmethod
    def verification_prompt() -> discord.Embed:
        return EmbedFactory.create(
            title=f"🔐 {sc('Verification Required')}",
            description="Click the button below to verify yourself and unlock access to the server.",
            color=EmbedColor.PRIMARY,
            footer=sc("complete verification to unlock all channels") + "  ·  " + sc("logiq")
        )

    @staticmethod
    def ticket_created(ticket_id: str, category: str) -> discord.Embed:
        return EmbedFactory.create(
            title=f"🎫 {sc('Ticket Created')}",
            description="Your support ticket has been created.",
            color=EmbedColor.SUCCESS,
            fields=[
                {"name": sc("ticket id"), "value": f"`{ticket_id}`", "inline": True},
                {"name": sc("category"),  "value": category,         "inline": True},
            ]
        )

    @staticmethod
    def leaderboard(
        title: str,
        entries: List[Dict[str, Any]],
        field_name: str = "Rank",
        color: int = EmbedColor.LEVELING
    ) -> discord.Embed:
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, entry in enumerate(entries[:10], 1):
            medal = medals.get(i, f"`{i:>2}.`")
            lines.append(f"{medal} <@{entry['user_id']}>  —  **{entry.get(field_name, 0):,}**")

        return EmbedFactory.create(
            title=f"🏆 {sc(title)}",
            description="\n".join(lines) if lines else sc("no entries yet"),
            color=color
        )
