from __future__ import annotations

from typing import Any

import discord
from discord.ext import commands
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, create_tables
from app.discord_embed import build_job_embed_payload
from app.flow import scrape_and_save
from app.models import (
    SentVacancy,
    Vacancy,
    clear_sent_vacancies,
    count_vacancies,
    count_vacancies_by_source,
    format_vacancy_filter,
    get_active_vacancies,
    get_latest_vacancies,
    get_or_create_bot_state,
    get_or_create_user,
    get_or_create_vacancy_filter,
    supported_filter_sources,
    update_bot_offset,
    update_vacancy_filter,
)
from app.normalization.schemas import NormalizedJob
from app.scrapers.sources import ALL_SOURCES


MENU_TEXT = """
**JobHunt Discord Commands**

**Search**
`!scrape` - scrape current source from your filters
`!scrape all` - scrape every supported source
`!new` - show first unsent matching job
`!next` - show next matching job
`!latest [source]` - show latest saved jobs

**Filters**
`!filters` - show current filters
`!set_source all|djinni|praca_pl`
`!set_keywords Python FastAPI`
`!set_experience no_exp,1y`
`!set_english pre,intermediate,upper`
`!set_location remote poznan`
`!include python sql backend`
`!exclude senior lead manager`
`!clear_location`
`!clear_include`
`!clear_exclude`

**State**
`!count` - saved jobs count
`!stats` - saved and active job stats
`!reset_seen` - show hidden/seen jobs again
""".strip()


def run_discord_bot() -> None:
    settings = get_settings()
    if not settings.discord_bot_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required to run the Discord bot")

    create_tables()

    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(
        command_prefix=settings.discord_command_prefix,
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready() -> None:
        print(f"Discord bot logged in as {bot.user}")

    @bot.command(name="start")
    async def start_command(ctx: commands.Context) -> None:
        _ensure_discord_user(str(ctx.author.id))
        await ctx.send(embed=_menu_embed())

    @bot.command(name="help")
    async def help_command(ctx: commands.Context) -> None:
        await ctx.send(embed=_menu_embed())

    @bot.command(name="menu")
    async def menu_command(ctx: commands.Context) -> None:
        await ctx.send(embed=_menu_embed())

    @bot.command(name="count")
    async def count_command(ctx: commands.Context) -> None:
        with SessionLocal() as db:
            total = count_vacancies(db)
        await ctx.send(f"Saved jobs: `{total}`")

    @bot.command(name="stats")
    async def stats_command(ctx: commands.Context) -> None:
        chat_id = _chat_id(ctx)
        with SessionLocal() as db:
            vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
            active_total = len(get_active_vacancies(db, chat_id, vacancy_filter))
            saved_total = count_vacancies(db)
            by_source = count_vacancies_by_source(db)

        embed = discord.Embed(title="JobHunt Stats", color=discord.Color.blurple())
        embed.add_field(name="Saved jobs", value=str(saved_total), inline=True)
        embed.add_field(name="Active jobs", value=str(active_total), inline=True)
        sources = "\n".join(
            f"- {source}: {total}" for source, total in sorted(by_source.items())
        )
        embed.add_field(name="By source", value=sources or "No saved jobs yet.", inline=False)
        await ctx.send(embed=embed)

    @bot.command(name="filters")
    async def filters_command(ctx: commands.Context) -> None:
        chat_id = _chat_id(ctx)
        with SessionLocal() as db:
            vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
            filters_text = format_vacancy_filter(vacancy_filter)
        await ctx.send(f"```text\n{filters_text}\n```")

    @bot.command(name="set_source")
    async def set_source_command(ctx: commands.Context, source: str = "") -> None:
        if source not in supported_filter_sources():
            await ctx.send(_unsupported_source_message())
            return
        await _update_filter(ctx, source=source)

    @bot.command(name="set_keywords")
    async def set_keywords_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "search_keywords", value)

    @bot.command(name="set_experience")
    async def set_experience_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "experience_levels", value)

    @bot.command(name="set_english")
    async def set_english_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "english_levels", value)

    @bot.command(name="set_location")
    async def set_location_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "location", value)

    @bot.command(name="include")
    async def include_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "include_keywords", value)

    @bot.command(name="exclude")
    async def exclude_command(ctx: commands.Context, *, value: str = "") -> None:
        await _update_required_filter(ctx, "exclude_keywords", value)

    @bot.command(name="clear_location")
    async def clear_location_command(ctx: commands.Context) -> None:
        await _update_filter(ctx, location=None)

    @bot.command(name="clear_include")
    async def clear_include_command(ctx: commands.Context) -> None:
        await _update_filter(ctx, include_keywords=None)

    @bot.command(name="clear_exclude")
    async def clear_exclude_command(ctx: commands.Context) -> None:
        await _update_filter(ctx, exclude_keywords=None)

    @bot.command(name="scrape")
    async def scrape_command(ctx: commands.Context, source: str = "") -> None:
        chat_id = _chat_id(ctx)
        async with ctx.typing():
            with SessionLocal() as db:
                vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
                filters = vacancy_filter.to_scrape_filters()

            if source:
                if source not in supported_filter_sources():
                    await ctx.send(_unsupported_source_message())
                    return
                filters = filters.model_copy(update={"source": source})

            vacancies = scrape_and_save(source=filters.source, filters=filters)

        await ctx.send(f"Scraped and saved jobs: `{len(vacancies)}`")
        await _send_active_job(ctx, reset_offset=True)

    @bot.command(name="new")
    async def new_command(ctx: commands.Context) -> None:
        await _send_active_job(ctx, reset_offset=True)

    @bot.command(name="next")
    async def next_command(ctx: commands.Context) -> None:
        await _send_active_job(ctx, offset_delta=1)

    @bot.command(name="prev")
    async def prev_command(ctx: commands.Context) -> None:
        await _send_active_job(ctx, offset_delta=-1)

    @bot.command(name="latest")
    async def latest_command(ctx: commands.Context, source: str = "") -> None:
        selected_source = None if source in {"", ALL_SOURCES} else source
        if selected_source and selected_source not in supported_filter_sources():
            await ctx.send(_unsupported_source_message())
            return

        with SessionLocal() as db:
            vacancies = get_latest_vacancies(db, limit=5, source=selected_source)

        if not vacancies:
            await ctx.send("No saved jobs yet.")
            return

        for vacancy in vacancies:
            await _send_job(ctx, vacancy)

    @bot.command(name="reset_seen")
    async def reset_seen_command(ctx: commands.Context) -> None:
        chat_id = _chat_id(ctx)
        with SessionLocal() as db:
            removed = clear_sent_vacancies(db, chat_id)
            update_bot_offset(db, chat_id, 0)
        await ctx.send(f"Returned hidden/seen jobs to active list: `{removed}`")

    bot.run(settings.discord_bot_token)


async def _send_active_job(
    ctx: commands.Context,
    offset_delta: int = 0,
    reset_offset: bool = False,
) -> None:
    chat_id = _chat_id(ctx)
    with SessionLocal() as db:
        state = get_or_create_bot_state(db, chat_id)
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        active_vacancies = get_active_vacancies(db, chat_id, vacancy_filter)
        total = len(active_vacancies)

        if total == 0:
            update_bot_offset(db, chat_id, 0)
            await ctx.send("No active jobs for current filters.")
            return

        current_offset = 0 if reset_offset else state.current_offset + offset_delta
        if current_offset < 0:
            current_offset = total - 1
        if current_offset >= total:
            current_offset = 0

        vacancy = active_vacancies[current_offset]
        update_bot_offset(db, chat_id, current_offset)
        position = current_offset + 1

    await _send_job(ctx, vacancy, position=position, total=total)


async def _send_job(
    ctx: commands.Context,
    vacancy: Vacancy,
    position: int | None = None,
    total: int | None = None,
) -> None:
    embed = _vacancy_to_embed(vacancy)
    if position is not None and total is not None:
        embed.set_footer(text=f"{embed.footer.text} | {position}/{total}")
    destination = await _destination_channel(ctx)
    await destination.send(embed=embed, view=JobActionView(vacancy.id, vacancy.url))


def _vacancy_to_embed(vacancy: Vacancy) -> discord.Embed:
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
        _set_user_job_state(
            chat_id=_interaction_chat_id(interaction),
            vacancy_id=self.vacancy_id,
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
        _set_user_job_state(
            chat_id=_interaction_chat_id(interaction),
            vacancy_id=self.vacancy_id,
            is_hidden=1,
            is_viewed=1,
        )
        await interaction.response.send_message("Hidden.", ephemeral=True)


async def _respond_with_offset(
    interaction: discord.Interaction,
    offset_delta: int,
) -> None:
    chat_id = _interaction_chat_id(interaction)
    with SessionLocal() as db:
        state = get_or_create_bot_state(db, chat_id)
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        active_vacancies = get_active_vacancies(db, chat_id, vacancy_filter)
        total = len(active_vacancies)
        if total == 0:
            await interaction.response.send_message(
                "No active jobs for current filters.",
                ephemeral=True,
            )
            return

        current_offset = state.current_offset + offset_delta
        if current_offset < 0:
            current_offset = total - 1
        if current_offset >= total:
            current_offset = 0

        vacancy = active_vacancies[current_offset]
        update_bot_offset(db, chat_id, current_offset)

    embed = _vacancy_to_embed(vacancy)
    embed.set_footer(text=f"{embed.footer.text} | {current_offset + 1}/{total}")
    await interaction.response.edit_message(
        embed=embed,
        view=JobActionView(vacancy.id, vacancy.url),
    )


def _set_user_job_state(
    *,
    chat_id: str,
    vacancy_id: int,
    is_saved: int | None = None,
    is_viewed: int | None = None,
    is_hidden: int | None = None,
) -> None:
    with SessionLocal() as db:
        user = get_or_create_user(db, chat_id)
        vacancy_filter = get_or_create_vacancy_filter(db, chat_id)
        row = db.execute(
            select(SentVacancy).where(
                SentVacancy.chat_id == chat_id,
                SentVacancy.vacancy_id == vacancy_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = SentVacancy(
                user_id=user.id,
                chat_id=chat_id,
                vacancy_id=vacancy_id,
                filter_id=vacancy_filter.id,
            )
            db.add(row)

        if is_saved is not None:
            row.is_saved = is_saved
        if is_viewed is not None:
            row.is_viewed = is_viewed
        if is_hidden is not None:
            row.is_hidden = is_hidden

        db.commit()


async def _update_required_filter(
    ctx: commands.Context,
    field_name: str,
    value: str,
) -> None:
    value = value.strip()
    if not value:
        await ctx.send(f"Value is empty. Example: `!{ctx.command.name} Python`")
        return
    await _update_filter(ctx, **{field_name: value})


async def _update_filter(ctx: commands.Context, **values: str | None) -> None:
    chat_id = _chat_id(ctx)
    with SessionLocal() as db:
        vacancy_filter = update_vacancy_filter(db, chat_id, **values)
        update_bot_offset(db, chat_id, 0)
        filters_text = format_vacancy_filter(vacancy_filter)
    await ctx.send(f"Filters updated:\n```text\n{filters_text}\n```")


def _ensure_discord_user(user_id: str) -> None:
    chat_id = f"discord:{user_id}"
    with SessionLocal() as db:
        get_or_create_user(db, chat_id)
        get_or_create_bot_state(db, chat_id)
        get_or_create_vacancy_filter(db, chat_id)


def _chat_id(ctx: commands.Context) -> str:
    return f"discord:{ctx.author.id}"


def _interaction_chat_id(interaction: discord.Interaction) -> str:
    return f"discord:{interaction.user.id}"


def _menu_embed() -> discord.Embed:
    embed = discord.Embed(
        title="JobHunt Menu",
        description=MENU_TEXT,
        color=discord.Color.blurple(),
    )
    embed.set_footer(text="Discord output uses normalized_data JSONB.")
    return embed


def _unsupported_source_message() -> str:
    sources = ", ".join(sorted(supported_filter_sources()))
    return f"Unsupported source. Use one of: `{sources}`"


async def _destination_channel(ctx: commands.Context):
    settings = get_settings()
    if settings.discord_channel_id:
        try:
            channel_id = int(settings.discord_channel_id)
        except ValueError:
            channel_id = None
        if channel_id is not None:
            channel = ctx.bot.get_channel(channel_id)
            if channel is not None:
                return channel
            try:
                return await ctx.bot.fetch_channel(channel_id)
            except discord.DiscordException:
                return ctx.channel
    return ctx.channel
