from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from app.config import get_settings
from app.db import create_tables
from app.discord_embed import build_job_embed_payload
from app.normalization.schemas import NormalizedJob
from app.scrapers.sources import ALL_SOURCES
from app.services.filters import (
    get_user_filter_text,
    supported_sources,
    update_user_filter_text,
)
from app.services.jobs import (
    get_active_job,
    get_active_job_count,
    get_job_stats,
    list_jobs,
    reset_user_jobs,
    set_user_job_state,
)
from app.services.scraping import scrape_for_user


logger = logging.getLogger(__name__)

MENU_TEXT = """
Use Discord slash commands. Start typing `/` to see command hints and parameter fields.

Search:
`/scrape` - start background scrape with your current filters
`/scrape source:all` - start background scrape for every supported source
`/new` - show first active matching job
`/next` - show next matching job
`/latest` - show latest saved jobs

Filters:
`/filters`
`/set_source`
`/set_keywords`
`/set_experience`
`/set_english`
`/set_location`
`/include`
`/exclude`
`/clear_location`
`/clear_include`
`/clear_exclude`

State:
`/count`
`/stats`
`/reset_seen`
""".strip()


def run_discord_bot() -> None:
    settings = get_settings()
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to run the Discord bot")

    create_tables()

    intents = discord.Intents.default()
    bot = commands.Bot(command_prefix="/", intents=intents, help_command=None)
    running_scrapes: set[str] = set()

    @bot.event
    async def on_ready() -> None:
        if getattr(bot, "_jobhunt_synced", False):
            return

        try:
            synced_count = await _sync_slash_commands(bot)
        except discord.DiscordException:
            logger.exception("Discord slash command sync failed")
            synced_count = 0

        bot._jobhunt_synced = True  # type: ignore[attr-defined]
        print(f"Discord bot logged in as {bot.user}; synced commands={synced_count}")

    @bot.tree.command(name="menu", description="Show JobHunt command menu")
    async def menu_command(interaction: discord.Interaction) -> None:
        _ensure_discord_user(interaction)
        await _send_message(interaction, embed=_menu_embed(), ephemeral=True)

    @bot.tree.command(name="count", description="Show total saved jobs")
    async def count_command(interaction: discord.Interaction) -> None:
        total = get_job_stats()["saved_vacancies"]
        await _send_message(interaction, f"Saved jobs: `{total}`", ephemeral=True)

    @bot.tree.command(name="stats", description="Show saved and active job stats")
    async def stats_command(interaction: discord.Interaction) -> None:
        user_key = _interaction_user_key(interaction)
        stats = get_job_stats()
        active_total = get_active_job_count(user_key)

        embed = discord.Embed(title="JobHunt Stats", color=discord.Color.blurple())
        embed.add_field(name="Saved jobs", value=str(stats["saved_vacancies"]), inline=True)
        embed.add_field(name="Active jobs", value=str(active_total), inline=True)
        by_source = stats["by_source"]
        sources = "\n".join(
            f"- {source}: {total}" for source, total in sorted(by_source.items())
        )
        embed.add_field(name="By source", value=sources or "No saved jobs yet.", inline=False)
        await _send_message(interaction, embed=embed, ephemeral=True)

    @bot.tree.command(name="filters", description="Show your current job filters")
    async def filters_command(interaction: discord.Interaction) -> None:
        user_key = _interaction_user_key(interaction)
        filters_text = get_user_filter_text(user_key)
        await _send_message(interaction, f"```text\n{filters_text}\n```", ephemeral=True)

    @bot.tree.command(name="set_source", description="Set source filter")
    @app_commands.describe(source="Job source to use")
    @app_commands.choices(source=_source_choices())
    async def set_source_command(
        interaction: discord.Interaction,
        source: str,
    ) -> None:
        await _update_filter(interaction, source=source)

    @bot.tree.command(name="set_keywords", description="Set search keywords")
    @app_commands.describe(value="Example: Python FastAPI")
    async def set_keywords_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "search_keywords", value)

    @bot.tree.command(name="set_experience", description="Set experience levels")
    @app_commands.describe(value="Example: no_exp,1y")
    async def set_experience_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "experience_levels", value)

    @bot.tree.command(name="set_english", description="Set English levels")
    @app_commands.describe(value="Example: pre,intermediate,upper")
    async def set_english_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "english_levels", value)

    @bot.tree.command(name="set_location", description="Set location keywords")
    @app_commands.describe(value="Example: remote poznan")
    async def set_location_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "location", value)

    @bot.tree.command(name="include", description="Set required post-filter keywords")
    @app_commands.describe(value="Example: python sql backend")
    async def include_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "include_keywords", value)

    @bot.tree.command(name="exclude", description="Set excluded post-filter keywords")
    @app_commands.describe(value="Example: senior lead manager")
    async def exclude_command(
        interaction: discord.Interaction,
        value: str,
    ) -> None:
        await _update_required_filter(interaction, "exclude_keywords", value)

    @bot.tree.command(name="clear_location", description="Clear location filter")
    async def clear_location_command(interaction: discord.Interaction) -> None:
        await _update_filter(interaction, location=None)

    @bot.tree.command(name="clear_include", description="Clear required keywords")
    async def clear_include_command(interaction: discord.Interaction) -> None:
        await _update_filter(interaction, include_keywords=None)

    @bot.tree.command(name="clear_exclude", description="Clear excluded keywords")
    async def clear_exclude_command(interaction: discord.Interaction) -> None:
        await _update_filter(interaction, exclude_keywords=None)

    @bot.tree.command(name="scrape", description="Scrape jobs with your current filters")
    @app_commands.describe(source="Optional source override")
    @app_commands.choices(source=_source_choices())
    async def scrape_command(
        interaction: discord.Interaction,
        source: str | None = None,
    ) -> None:
        user_key = _interaction_user_key(interaction)
        scrape_key = "global"
        if scrape_key in running_scrapes:
            await _send_message(
                interaction,
                "Scrape is already running. I will post the result when it finishes.",
                ephemeral=True,
            )
            return

        running_scrapes.add(scrape_key)
        requested_source = source or "current filters"
        await _send_message(
            interaction,
            f"Scrape started in background for `{requested_source}`. "
            "I will post the result in the channel when it finishes.",
            ephemeral=True,
        )
        task = asyncio.create_task(
            _run_scrape_background(
                bot=bot,
                user_key=user_key,
                source=source,
                destination_channel_id=interaction.channel_id,
            )
        )
        task.add_done_callback(lambda _task: running_scrapes.discard(scrape_key))

    @bot.tree.command(name="new", description="Show first active matching job")
    async def new_command(interaction: discord.Interaction) -> None:
        await _send_active_job(interaction, reset_offset=True)

    @bot.tree.command(name="next", description="Show next active matching job")
    async def next_command(interaction: discord.Interaction) -> None:
        await _send_active_job(interaction, offset_delta=1)

    @bot.tree.command(name="prev", description="Show previous active matching job")
    async def prev_command(interaction: discord.Interaction) -> None:
        await _send_active_job(interaction, offset_delta=-1)

    @bot.tree.command(name="latest", description="Show latest saved jobs")
    @app_commands.describe(source="Optional source filter")
    @app_commands.choices(source=_source_choices())
    async def latest_command(
        interaction: discord.Interaction,
        source: str | None = None,
    ) -> None:
        selected_source = None if source in {None, ALL_SOURCES} else source

        vacancies = list_jobs(source=selected_source, limit=5)
        if not vacancies:
            await _send_message(interaction, "No saved jobs yet.", ephemeral=True)
            return

        await _send_jobs(interaction, vacancies)

    @bot.tree.command(name="reset_seen", description="Return hidden jobs to the active list")
    async def reset_seen_command(interaction: discord.Interaction) -> None:
        removed = reset_user_jobs(_interaction_user_key(interaction))
        await _send_message(
            interaction,
            f"Returned hidden/seen jobs to active list: `{removed}`",
            ephemeral=True,
        )

    bot.run(settings.discord_bot_token)


async def _send_active_job(
    interaction: discord.Interaction,
    offset_delta: int = 0,
    reset_offset: bool = False,
) -> None:
    result = get_active_job(
        user_key=_interaction_user_key(interaction),
        offset_delta=offset_delta,
        reset_offset=reset_offset,
    )
    if result.vacancy is None:
        await _send_message(
            interaction,
            "No active jobs for current filters.",
            ephemeral=True,
        )
        return

    await _send_job(
        interaction,
        result.vacancy,
        position=result.position,
        total=result.total,
    )


async def _send_jobs(
    interaction: discord.Interaction,
    vacancies,
) -> None:
    destination = await _destination_channel(interaction)
    if _is_interaction_channel(interaction, destination):
        for vacancy in vacancies:
            await _send_job(interaction, vacancy)
        return

    for vacancy in vacancies:
        await destination.send(
            embed=_vacancy_to_embed(vacancy),
            view=JobActionView(vacancy.id, vacancy.url),
        )
    await _send_message(
        interaction,
        f"Sent `{len(vacancies)}` jobs to the configured Discord channel.",
        ephemeral=True,
    )


async def _send_job(
    interaction: discord.Interaction,
    vacancy,
    position: int | None = None,
    total: int | None = None,
) -> None:
    embed = _vacancy_to_embed(vacancy)
    if position is not None and total is not None:
        footer = embed.footer.text or ""
        embed.set_footer(text=f"{footer} | {position}/{total}")

    destination = await _destination_channel(interaction)
    view = JobActionView(vacancy.id, vacancy.url)
    if _is_interaction_channel(interaction, destination):
        await _send_message(interaction, embed=embed, view=view)
        return

    await destination.send(embed=embed, view=view)
    await _send_message(interaction, "Sent to the configured Discord channel.", ephemeral=True)


async def _run_scrape_background(
    *,
    bot: commands.Bot,
    user_key: str,
    source: str | None,
    destination_channel_id: int | None,
) -> None:
    destination = await _channel_by_id(bot, destination_channel_id)
    try:
        result = await asyncio.to_thread(
            scrape_for_user,
            user_key=user_key,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Discord background scrape failed")
        await _send_channel_message(
            destination,
            f"Scrape failed: `{type(exc).__name__}: {exc}`",
        )
        return

    await _send_channel_message(
        destination,
        f"Scrape finished: `{result.saved_count}` jobs saved from `{result.source}`.",
    )

    active_job = get_active_job(user_key=user_key, reset_offset=True)
    if active_job.vacancy is None:
        await _send_channel_message(destination, "No active jobs for current filters.")
        return

    await _send_job_to_channel(
        destination,
        active_job.vacancy,
        position=active_job.position,
        total=active_job.total,
    )


async def _send_job_to_channel(
    channel,
    vacancy,
    position: int | None = None,
    total: int | None = None,
) -> None:
    if channel is None:
        logger.warning("Could not send job %s because destination channel is missing", vacancy.id)
        return

    embed = _vacancy_to_embed(vacancy)
    if position is not None and total is not None:
        footer = embed.footer.text or ""
        embed.set_footer(text=f"{footer} | {position}/{total}")

    try:
        await channel.send(embed=embed, view=JobActionView(vacancy.id, vacancy.url))
    except discord.DiscordException:
        logger.exception("Could not send Discord job message: job_id=%s", vacancy.id)


async def _send_channel_message(channel, content: str) -> None:
    if channel is None:
        logger.warning("Could not send Discord channel message: %s", content)
        return
    try:
        await channel.send(content)
    except discord.DiscordException:
        logger.exception("Could not send Discord channel message")


def _vacancy_to_embed(vacancy) -> discord.Embed:
    normalized = NormalizedJob.model_validate(vacancy.normalized_data)
    payload = build_job_embed_payload(normalized)
    return discord.Embed.from_dict(payload["embeds"][0])


class JobActionView(discord.ui.View):
    def __init__(self, vacancy_id: int, url: str) -> None:
        super().__init__(timeout=None)
        self.vacancy_id = vacancy_id
        self.add_item(discord.ui.Button(label="Open", url=url))

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary)
    async def previous_job(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await _respond_with_offset(interaction, offset_delta=-1)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next_job(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        await _respond_with_offset(interaction, offset_delta=1)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.success)
    async def save_job(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        set_user_job_state(
            user_key=_interaction_user_key(interaction),
            job_id=self.vacancy_id,
            is_saved=1,
            is_viewed=1,
        )
        await interaction.response.send_message("Saved.", ephemeral=True)

    @discord.ui.button(label="Hide", style=discord.ButtonStyle.danger)
    async def hide_job(
        self,
        interaction: discord.Interaction,
        _button: discord.ui.Button,
    ) -> None:
        set_user_job_state(
            user_key=_interaction_user_key(interaction),
            job_id=self.vacancy_id,
            is_hidden=1,
            is_viewed=1,
        )
        await interaction.response.send_message("Hidden.", ephemeral=True)


async def _respond_with_offset(
    interaction: discord.Interaction,
    offset_delta: int,
) -> None:
    result = get_active_job(
        user_key=_interaction_user_key(interaction),
        offset_delta=offset_delta,
    )
    if result.vacancy is None:
        await interaction.response.send_message(
            "No active jobs for current filters.",
            ephemeral=True,
        )
        return

    embed = _vacancy_to_embed(result.vacancy)
    footer = embed.footer.text or ""
    embed.set_footer(text=f"{footer} | {result.position}/{result.total}")
    await interaction.response.edit_message(
        embed=embed,
        view=JobActionView(result.vacancy.id, result.vacancy.url),
    )


async def _update_required_filter(
    interaction: discord.Interaction,
    field_name: str,
    value: str,
) -> None:
    value = value.strip()
    if not value:
        await _send_message(interaction, "Value is empty.", ephemeral=True)
        return
    await _update_filter(interaction, **{field_name: value})


async def _update_filter(
    interaction: discord.Interaction,
    **values: str | None,
) -> None:
    try:
        filters_text = update_user_filter_text(
            _interaction_user_key(interaction),
            **values,
        )
    except ValueError as exc:
        await _send_message(interaction, str(exc), ephemeral=True)
        return

    await _send_message(
        interaction,
        f"Filters updated:\n```text\n{filters_text}\n```",
        ephemeral=True,
    )


async def _send_message(
    interaction: discord.Interaction,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            content=content,
            embed=embed,
            view=view,
            ephemeral=ephemeral,
        )
        return

    await interaction.response.send_message(
        content=content,
        embed=embed,
        view=view,
        ephemeral=ephemeral,
    )


async def _destination_channel(interaction: discord.Interaction):
    settings = get_settings()
    if settings.discord_channel_id:
        try:
            channel_id = int(settings.discord_channel_id)
        except ValueError:
            channel_id = None

        if channel_id is not None:
            channel = interaction.client.get_channel(channel_id)
            if channel is not None:
                return channel
            try:
                return await interaction.client.fetch_channel(channel_id)
            except discord.DiscordException:
                pass

    return interaction.channel


async def _channel_by_id(
    bot: commands.Bot,
    channel_id: int | None,
):
    settings = get_settings()
    selected_channel_id = channel_id
    if settings.discord_channel_id:
        try:
            selected_channel_id = int(settings.discord_channel_id)
        except ValueError:
            logger.warning("Invalid DISCORD_CHANNEL_ID=%s", settings.discord_channel_id)

    if selected_channel_id is None:
        return None

    channel = bot.get_channel(selected_channel_id)
    if channel is not None:
        return channel

    try:
        return await bot.fetch_channel(selected_channel_id)
    except discord.DiscordException:
        logger.exception("Could not fetch Discord channel: id=%s", selected_channel_id)
        return None


async def _sync_slash_commands(bot: commands.Bot) -> int:
    settings = get_settings()
    if settings.discord_guild_id:
        try:
            guild_id = int(settings.discord_guild_id)
        except ValueError:
            logger.warning(
                "Invalid DISCORD_GUILD_ID=%s; syncing global commands",
                settings.discord_guild_id,
            )
        else:
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            return len(synced)

    synced = await bot.tree.sync()
    return len(synced)


def _ensure_discord_user(interaction: discord.Interaction) -> None:
    get_active_job_count(_interaction_user_key(interaction))


def _interaction_user_key(interaction: discord.Interaction) -> str:
    return f"discord:{interaction.user.id}"


def _menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="JobHunt Menu",
        description=MENU_TEXT,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Discord output uses normalized_data JSONB.")
    return embed


def _source_choices() -> list[app_commands.Choice[str]]:
    return [
        app_commands.Choice(name=source, value=source)
        for source in supported_sources()
    ]


def _is_interaction_channel(interaction: discord.Interaction, channel) -> bool:
    return getattr(channel, "id", None) == interaction.channel_id
