import os
import sqlite3
import secrets
import random
import asyncio
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.environ.get('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError('Set DISCORD_TOKEN as a private environment variable')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)
DB = os.environ.get('DATABASE_PATH', 'dizzy.db')
Path = __import__('pathlib').Path
Path(DB).parent.mkdir(parents=True, exist_ok=True)

def db():
    con = sqlite3.connect(DB)
    con.execute('CREATE TABLE IF NOT EXISTS deals (id TEXT PRIMARY KEY, buyer INTEGER, seller INTEGER, guild INTEGER, reviewed_by INTEGER, reviewed_at TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS feedback (deal_id TEXT PRIMARY KEY, reviewer INTEGER, recipient INTEGER, rating INTEGER, note TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS listings (id TEXT PRIMARY KEY, guild INTEGER, seller INTEGER, kind TEXT, title TEXT, price REAL, status TEXT, message_id INTEGER, created_at TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS applications (guild INTEGER, member INTEGER, status TEXT, PRIMARY KEY(guild,member))')
    con.execute('CREATE TABLE IF NOT EXISTS tournaments (id TEXT PRIMARY KEY, guild INTEGER, name TEXT, date_utc TEXT, rules TEXT, status TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS entrants (tournament_id TEXT, member INTEGER, PRIMARY KEY(tournament_id,member))')
    con.execute('CREATE TABLE IF NOT EXISTS matches (id TEXT PRIMARY KEY, tournament_id TEXT, player1 INTEGER, player2 INTEGER, winner INTEGER, reported_by INTEGER)')
    con.execute('CREATE TABLE IF NOT EXISTS giveaways (id TEXT PRIMARY KEY, guild INTEGER, prize TEXT, deadline TEXT, eligibility TEXT, winner INTEGER, status TEXT)')
    con.execute('CREATE TABLE IF NOT EXISTS giveaway_entries (giveaway_id TEXT, member INTEGER, PRIMARY KEY(giveaway_id,member))')
    con.execute('CREATE TABLE IF NOT EXISTS tickets (guild INTEGER, member INTEGER, channel INTEGER, kind TEXT, status TEXT, PRIMARY KEY(guild,channel))')
    return con

CATEGORIES = {
 '📌 START HERE': [('👋・welcome','text'),('📜・server-rules','text'),('📢・announcements','text'),('✅・verification','text'),('🎭・choose-roles','text'),('📚・how-to-trade','text'),('🎫・open-a-ticket','text')],
 '💜 COMMUNITY': [('💬・general-chat','text'),('👋・introductions','text'),('📸・show-your-pulls','text'),('💎・collection-showcase','text'),('🔍・card-price-checks','text'),('📰・tcg-news','text'),('💡・suggestions','text')],
 '💰 TCG MARKETPLACE': [('🛒・buying-cards','forum'),('💵・selling-cards','forum'),('🔄・trading-cards','forum'),('📦・sealed-products','forum'),('✨・graded-cards','forum'),('🎲・mystery-packs','forum'),('🔎・looking-for-cards','forum'),('⭐・completed-deals','text')],
 '⚔️ BATTLE ARENA': [('⚔️・find-a-battle','text'),('🃏・deck-building','text'),('🎮・tcg-live','text'),('🏆・tournament-signups','text'),('📅・tournament-schedule','text'),('🥇・leaderboard','text'),('📊・match-results','text')],
 '🎉 EVENTS & GIVEAWAYS': [('🎁・giveaways','text'),('🎟️・event-announcements','text'),('📦・live-pack-rips','text'),('🎯・community-challenges','text')],
 '🔊 VOICE LOUNGES': [('Collector Lounge','voice'),('Battle Room 1','voice'),('Battle Room 2','voice'),('Pack Opening Live','voice'),('Tournament Lobby','voice')],
 '🔒 STAFF ONLY': [('🛡️・staff-chat','text'),('📋・mod-logs','text'),('🚨・scam-reports','text'),('⚖️・trade-disputes','text'),('📑・seller-applications','text'),('🤖・bot-commands','text')]
}
ROLE_NAMES = ['💜 Administrator','🛡️ Moderator','🤝 Trade Mediator','✅ Verified Seller','🔄 Verified Trader','💎 VIP Collector','🏆 Tournament Champion','⚔️ Battler','👤 Verified Member','🌱 New Member']
RULES = ('**Dizzy TCG Marketplace Rules**\n1. Respect all members. No harassment or hate speech.\n2. No scams, counterfeit cards sold as authentic, or misleading listings.\n3. Clearly label custom cards and proxies.\n4. Include accurate condition, price, shipping details, and timestamped photos.\n5. No unsolicited advertising.\n6. Keep personal and payment information private.\n7. Use payment methods with buyer/seller protection.\n8. Agree on trade and shipping terms before sending.\n9. No cheating or falsified tournament results.\n10. Giveaways require staff approval and must comply with law and Discord policies.\n11. Report suspicious activity using private tickets.\n12. No unauthorized gambling or paid games of chance.\n13. Staff may moderate listings and disputes; verification is not a guarantee.\n14. Follow Discord Terms and Community Guidelines.')

def find_channel(guild, suffix):
    return discord.utils.find(lambda c: c.name.endswith(suffix), guild.channels)

def staff(member):
    return member.guild_permissions.manage_guild or any(r.name in ('🛡️ Moderator','🤝 Trade Mediator','💜 Administrator') for r in member.roles)

@bot.event
async def on_ready():
    if not getattr(bot, '_synced', False):
        await bot.tree.sync()
        bot._synced = True
    print(f'Logged in as {bot.user} ({bot.user.id})')

@bot.tree.command(description='Create Dizzy TCG Marketplace channels and roles (server owner only)')
@app_commands.guild_only()
async def setup(interaction: discord.Interaction):
    guild = interaction.guild
    if interaction.user.id != guild.owner_id:
        return await interaction.response.send_message('Only the server owner can run setup.', ephemeral=True)

    # Discord requires the initial acknowledgement within 3 seconds.
    await interaction.response.defer(ephemeral=True, thinking=True)
    me = guild.me
    if not me or not me.guild_permissions.manage_channels or not me.guild_permissions.manage_roles:
        return await interaction.followup.send(
            'Missing permissions: give Dizzy TCG Bot **Manage Channels** and **Manage Roles**, then retry /setup.',
            ephemeral=True)

    created = 0
    skipped = 0
    errors = []
    async def report(message):
        # Followups work after defer and keep the owner informed of progress.
        try:
            await interaction.followup.send(message, ephemeral=True)
        except discord.HTTPException:
            pass

    await report('Setup started. Existing channels and roles will be skipped. This may take a few minutes.')

    for name in ROLE_NAMES:
        if discord.utils.get(guild.roles, name=name):
            skipped += 1
            continue
        try:
            await guild.create_role(name=name, colour=discord.Colour.from_rgb(167, 85, 247), reason='Dizzy TCG setup')
            created += 1
        except (discord.Forbidden, discord.HTTPException) as exc:
            errors.append(f'Role {name}: {type(exc).__name__} ({getattr(exc, "code", "unknown")})')

    await report(f'Roles processed. Created {created}; skipped {skipped}. Creating categories and channels now.')
    for category_name, channels in CATEGORIES.items():
        cat = discord.utils.get(guild.categories, name=category_name)
        if cat is None:
            overwrites = None
            if category_name == '🔒 STAFF ONLY':
                overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
                for role in guild.roles:
                    if role.name in ('💜 Administrator', '🛡️ Moderator', '🤝 Trade Mediator'):
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
                overwrites[me] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
            try:
                cat = await guild.create_category(category_name, overwrites=overwrites, reason='Dizzy TCG setup')
                created += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                errors.append(f'Category {category_name}: {type(exc).__name__} ({getattr(exc, "code", "unknown")})')
                continue
        else:
            skipped += 1

        for name, kind in channels:
            if discord.utils.get(cat.channels, name=name):
                skipped += 1
                continue
            try:
                if kind == 'forum':
                    try:
                        await guild.create_forum(name, category=cat, reason='Dizzy TCG setup')
                    except discord.HTTPException:
                        await guild.create_text_channel(name, category=cat, reason='Forum unavailable; text fallback')
                elif kind == 'voice':
                    await guild.create_voice_channel(name, category=cat, reason='Dizzy TCG setup')
                else:
                    await guild.create_text_channel(name, category=cat, reason='Dizzy TCG setup')
                created += 1
            except (discord.Forbidden, discord.HTTPException) as exc:
                errors.append(f'Channel {name}: {type(exc).__name__} ({getattr(exc, "code", "unknown")})')

        await report(f'Processed {category_name}. Created {created} total; skipped {skipped}; errors {len(errors)}.')

    rules = find_channel(guild, 'server-rules')
    if isinstance(rules, discord.TextChannel):
        try:
            # Do not repost rules on every retry.
            recent = [m async for m in rules.history(limit=30)]
            if not any(m.author.id == bot.user.id and 'Dizzy TCG Marketplace Rules' in m.content for m in recent):
                await rules.send(RULES)
        except (discord.Forbidden, discord.HTTPException) as exc:
            errors.append(f'Posting rules: {type(exc).__name__}')

    summary = f'Setup finished: **{created} created**, **{skipped} already existed**, **{len(errors)} errors**.'
    if errors:
        summary += '\nFirst errors: ' + '; '.join(errors[:5])
    summary += '\nReview channel visibility and role permissions before inviting members.'
    await report(summary)

async def listing(interaction, channel_suffix, title, body):
    channel = find_channel(interaction.guild, channel_suffix)
    if not channel:
        return await interaction.followup.send('Run /setup first.', ephemeral=True)
    if isinstance(channel, discord.ForumChannel):
        thread = await channel.create_thread(name=title[:100], content=body, allowed_mentions=discord.AllowedMentions.none())
        msg_id = thread.message.id if thread.message else 0
    elif isinstance(channel, discord.TextChannel):
        message = await channel.send(body, allowed_mentions=discord.AllowedMentions.none())
        msg_id = message.id
    else:
        return await interaction.followup.send('Unsupported listing channel.', ephemeral=True)
    return msg_id

@bot.tree.command(description='Post a Pokémon card sale listing')
@app_commands.guild_only()
async def sell(interaction: discord.Interaction, card: str, price_usd: float, condition: str, shipping_from: str):
    if not any(r.name == '✅ Verified Seller' for r in interaction.user.roles):
        return await interaction.response.send_message('Apply for seller verification using /verify first.', ephemeral=True)
    if not 0 < price_usd < 1000000:
        return await interaction.response.send_message('Enter a valid positive price.', ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    listing_id = secrets.token_hex(4).upper()
    body = (f'**Sale listing `{listing_id}`** by {interaction.user.mention}\n'
            f'Card: {discord.utils.escape_markdown(card)}\nPrice: ${price_usd:.2f}\n'
            f'Condition: {discord.utils.escape_markdown(condition)}\n'
            f'Ships from: {discord.utils.escape_markdown(shipping_from)}\n'
            '**Seller must add timestamped photos and payment/shipping terms.**')
    message_id = await listing(interaction, 'selling-cards', f'{card} — ${price_usd:.2f}', body)
    if message_id is None:
        return
    with db() as con:
        con.execute('INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?)',
                    (listing_id, interaction.guild_id, interaction.user.id, 'sale', card[:150], price_usd,
                     'open', message_id, datetime.now(timezone.utc).isoformat()))
    await interaction.followup.send(f'Sale listing `{listing_id}` published. Close it with `/close_listing {listing_id}`.', ephemeral=True)

@bot.tree.command(description='Post a Pokémon card trade listing')
@app_commands.guild_only()
async def trade(interaction: discord.Interaction, offering: str, looking_for: str, condition: str):
    if not any(r.name == '🔄 Verified Trader' for r in interaction.user.roles):
        return await interaction.response.send_message('Ask staff for the Verified Trader role before posting.', ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    listing_id = secrets.token_hex(4).upper()
    body = (f'**Trade listing `{listing_id}`** by {interaction.user.mention}\n'
            f'Offering: {discord.utils.escape_markdown(offering)}\n'
            f'Looking for: {discord.utils.escape_markdown(looking_for)}\n'
            f'Condition: {discord.utils.escape_markdown(condition)}\n'
            '**Add timestamped photos and agree on shipping terms before trading.**')
    message_id = await listing(interaction, 'trading-cards', f'Trade: {offering}', body)
    if message_id is None:
        return
    with db() as con:
        con.execute('INSERT INTO listings VALUES (?,?,?,?,?,?,?,?,?)',
                    (listing_id, interaction.guild_id, interaction.user.id, 'trade', offering[:150], None,
                     'open', message_id, datetime.now(timezone.utc).isoformat()))
    await interaction.followup.send(f'Trade listing `{listing_id}` published. Close it with `/close_listing {listing_id}`.', ephemeral=True)

@bot.tree.command(description='Submit a private seller verification application')
@app_commands.guild_only()
async def verify(interaction: discord.Interaction, experience: str, selling_details: str):
    ch = find_channel(interaction.guild, 'seller-applications')
    if not isinstance(ch, discord.TextChannel):
        return await interaction.response.send_message('Staff application channel missing. Ask the owner to run /setup.', ephemeral=True)
    with db() as con: con.execute('INSERT INTO applications VALUES (?,?,?) ON CONFLICT(guild,member) DO UPDATE SET status=excluded.status', (interaction.guild_id,interaction.user.id,'pending'))
    await ch.send(f'**Seller application**\nApplicant: {interaction.user.mention} ({interaction.user.id})\nExperience: {discord.utils.escape_markdown(experience)}\nPlans: {discord.utils.escape_markdown(selling_details)}\nStaff must manually review and assign Verified Seller role.')
    await interaction.response.send_message('Your application was submitted privately to staff. Do not post sensitive documents in public channels.', ephemeral=True)

@bot.tree.command(description='Open a private support or dispute ticket')
@app_commands.guild_only()
async def ticket(interaction: discord.Interaction, reason: str):
    g = interaction.guild
    category = discord.utils.get(g.categories, name='🔒 STAFF ONLY')
    if not category:
        return await interaction.response.send_message('Run /setup first.', ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    name = f'ticket-{interaction.user.id}'
    existing = discord.utils.get(category.text_channels, name=name)
    if existing:
        return await interaction.followup.send(f'You already have a ticket: {existing.mention}', ephemeral=True)
    overwrites = {g.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True,send_messages=True), g.me: discord.PermissionOverwrite(view_channel=True,send_messages=True)}
    for r in g.roles:
        if r.name in ('💜 Administrator','🛡️ Moderator','🤝 Trade Mediator'):
            overwrites[r] = discord.PermissionOverwrite(view_channel=True,send_messages=True)
    ch = await g.create_text_channel(name, category=category, overwrites=overwrites, reason='Private support ticket')
    with db() as con: con.execute('INSERT OR REPLACE INTO tickets VALUES (?,?,?,?,?)',(g.id,interaction.user.id,ch.id,'support','open'))
    await ch.send(f'Ticket opened by {interaction.user.mention}\nReason: {discord.utils.escape_markdown(reason)}\nStaff will review. Use /close_ticket to close.')
    await interaction.followup.send(f'Your private ticket is {ch.mention}', ephemeral=True)

@bot.tree.command(description='Close a private ticket')
@app_commands.guild_only()
async def close_ticket(interaction: discord.Interaction):
    ch = interaction.channel
    if not isinstance(ch, discord.TextChannel) or not ch.name.startswith('ticket-'):
        return await interaction.response.send_message('Use this inside a ticket channel.', ephemeral=True)
    if not staff(interaction.user) and ch.name != f'ticket-{interaction.user.id}':
        return await interaction.response.send_message('You cannot close this ticket.', ephemeral=True)
    await interaction.response.send_message('Closing ticket.', ephemeral=True)
    with db() as con: con.execute('UPDATE tickets SET status=? WHERE guild=? AND channel=?',('closed',interaction.guild_id,ch.id))
    await ch.delete(reason=f'Closed by {interaction.user}')

@bot.tree.command(description='Staff: approve a completed transaction for feedback')
@app_commands.guild_only()
async def approve_deal(interaction: discord.Interaction, buyer: discord.Member, seller: discord.Member):
    if not staff(interaction.user):
        return await interaction.response.send_message('Staff only.', ephemeral=True)
    if buyer.id == seller.id:
        return await interaction.response.send_message('Buyer and seller must differ.', ephemeral=True)
    deal_id = secrets.token_hex(4).upper()
    with db() as con:
        con.execute('INSERT INTO deals VALUES (?,?,?,?,?,?)',(deal_id,buyer.id,seller.id,interaction.guild_id,interaction.user.id,datetime.now(timezone.utc).isoformat()))
    await interaction.response.send_message(f'Deal `{deal_id}` approved for feedback between {buyer.mention} and {seller.mention}. Staff should verify evidence before approving.', ephemeral=True)

@bot.tree.command(description='Leave feedback on a staff-approved completed deal')
@app_commands.guild_only()
async def rep(interaction: discord.Interaction, deal_id: str, rating: app_commands.Range[int,1,5], note: str):
    deal_id = deal_id.strip().upper()
    with db() as con:
        deal = con.execute('SELECT buyer,seller FROM deals WHERE id=? AND guild=?',(deal_id,interaction.guild_id)).fetchone()
        if not deal or interaction.user.id not in deal:
            return await interaction.response.send_message('No eligible approved deal found.', ephemeral=True)
        recipient = deal[1] if interaction.user.id == deal[0] else deal[0]
        if con.execute('SELECT 1 FROM feedback WHERE deal_id=?',(deal_id,)).fetchone():
            return await interaction.response.send_message('Feedback has already been submitted for this deal.', ephemeral=True)
        con.execute('INSERT INTO feedback VALUES (?,?,?,?,?)',(deal_id,interaction.user.id,recipient,rating,note[:500]))
    await interaction.response.send_message('Feedback recorded. Note: one review per deal in this starter version.', ephemeral=True)

@bot.tree.command(description='Staff: announce a free-entry TCG Live tournament')
@app_commands.guild_only()
async def tournament(interaction: discord.Interaction, name: str, date_utc: str, format_rules: str):
    if not staff(interaction.user):
        return await interaction.response.send_message('Staff only.', ephemeral=True)
    ch = find_channel(interaction.guild, 'tournament-signups')
    if not isinstance(ch, discord.TextChannel):
        return await interaction.response.send_message('Tournament channel missing.', ephemeral=True)
    if not utc_date(date_utc):
        return await interaction.response.send_message('Use an ISO UTC date such as 2026-12-15T19:00:00Z.', ephemeral=True)
    tid=secrets.token_hex(4).upper()
    with db() as con: con.execute('INSERT INTO tournaments VALUES (?,?,?,?,?,?)',(tid,interaction.guild_id,name[:150],date_utc[:80],format_rules[:500],'open'))
    await ch.send(f'🏆 **{discord.utils.escape_markdown(name)}**\nDate/time (UTC): {discord.utils.escape_markdown(date_utc)}\nFormat: {discord.utils.escape_markdown(format_rules)}\n**Free entry.** Register with `/join_tournament {tid}`. Staff manages matches and results.')
    await interaction.response.send_message('Tournament announcement posted.', ephemeral=True)

@bot.tree.command(description='Staff: announce a free-entry giveaway')
@app_commands.guild_only()
async def giveaway(interaction: discord.Interaction, prize: str, deadline_utc: str, eligibility: str):
    if not staff(interaction.user):
        return await interaction.response.send_message('Staff only.', ephemeral=True)
    ch = find_channel(interaction.guild, 'giveaways')
    if not isinstance(ch, discord.TextChannel):
        return await interaction.response.send_message('Giveaway channel missing.', ephemeral=True)
    if not utc_date(deadline_utc) or utc_date(deadline_utc) <= datetime.now(timezone.utc):
        return await interaction.response.send_message('Use a future ISO UTC deadline such as 2026-12-15T19:00:00Z.', ephemeral=True)
    gid=secrets.token_hex(4).upper()
    with db() as con: con.execute('INSERT INTO giveaways VALUES (?,?,?,?,?,?,?)',(gid,interaction.guild_id,prize[:150],deadline_utc[:80],eligibility[:500],None,'open'))
    await ch.send(f'🎁 **Free Giveaway**\nPrize: {discord.utils.escape_markdown(prize)}\nDeadline (UTC): {discord.utils.escape_markdown(deadline_utc)}\nEligibility: {discord.utils.escape_markdown(eligibility)}\nNo purchase necessary. Staff must publish official terms. Enter with `/enter_giveaway {gid}` before deadline. Not sponsored by Discord or Pokémon.')
    await interaction.response.send_message('Giveaway announcement posted.', ephemeral=True)



def utc_date(value: str):
    try:
        dt = datetime.fromisoformat(value.strip().replace('Z','+00:00'))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except ValueError:
        return None

@bot.tree.command(description='Close your sale or trade listing')
@app_commands.guild_only()
async def close_listing(interaction: discord.Interaction, listing_id: str):
    with db() as con:
        record=con.execute('SELECT seller,status FROM listings WHERE id=? AND guild=?',(listing_id.upper(),interaction.guild_id)).fetchone()
        if not record: return await interaction.response.send_message('Listing not found.',ephemeral=True)
        if interaction.user.id!=record[0] and not staff(interaction.user): return await interaction.response.send_message('Not your listing.',ephemeral=True)
        con.execute('UPDATE listings SET status=? WHERE id=? AND guild=?',('closed',listing_id.upper(),interaction.guild_id))
    await interaction.response.send_message('Listing marked closed. Edit the original post if necessary.',ephemeral=True)

@bot.tree.command(description='View a listing status')
@app_commands.guild_only()
async def listing_info(interaction: discord.Interaction, listing_id: str):
    with db() as con: row=con.execute('SELECT seller,kind,title,price,status FROM listings WHERE id=? AND guild=?',(listing_id.upper(),interaction.guild_id)).fetchone()
    if not row: return await interaction.response.send_message('Listing not found.',ephemeral=True)
    await interaction.response.send_message(f'`{listing_id.upper()}` • {row[1]} • {discord.utils.escape_markdown(row[2])}\nOwner: <@{row[0]}> • Status: **{row[4]}**'+(f' • ${row[3]:.2f}' if row[3] is not None else ''),ephemeral=True)

@bot.tree.command(description='Staff: approve or reject a seller application')
@app_commands.guild_only()
@app_commands.choices(decision=[app_commands.Choice(name='Approve',value='approve'),app_commands.Choice(name='Reject',value='reject')])
async def review_seller(interaction: discord.Interaction, member: discord.Member, decision: app_commands.Choice[str]):
    if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
    with db() as con:
        row=con.execute('SELECT status FROM applications WHERE guild=? AND member=?',(interaction.guild_id,member.id)).fetchone()
        if not row: return await interaction.response.send_message('No application found.',ephemeral=True)
    if decision.value=='approve':
        role=discord.utils.get(interaction.guild.roles,name='✅ Verified Seller')
        if not role: return await interaction.response.send_message('Verified Seller role missing.',ephemeral=True)
        await member.add_roles(role,reason=f'Approved by {interaction.user}')
    with db() as con: con.execute('UPDATE applications SET status=? WHERE guild=? AND member=?',(decision.value,interaction.guild_id,member.id))
    await interaction.response.send_message(f'{member.mention}: {decision.value}.',ephemeral=True)

@bot.tree.command(description='Staff: grant or revoke Verified Trader status')
@app_commands.guild_only()
async def trader_role(interaction: discord.Interaction, member: discord.Member, approved: bool):
    if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
    role=discord.utils.get(interaction.guild.roles,name='🔄 Verified Trader')
    if not role: return await interaction.response.send_message('Run /setup first.',ephemeral=True)
    if approved: await member.add_roles(role,reason=f'Trader approved by {interaction.user}')
    else: await member.remove_roles(role,reason=f'Trader revoked by {interaction.user}')
    await interaction.response.send_message('Trader role updated.',ephemeral=True)

@bot.tree.command(description='Report a scam privately to staff')
@app_commands.guild_only()
async def report_scam(interaction: discord.Interaction, member: discord.Member, details: str):
    channel=find_channel(interaction.guild,'scam-reports')
    if not isinstance(channel,discord.TextChannel): return await interaction.response.send_message('Scam reports channel missing.',ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    await channel.send(f'🚨 **Private scam report**\nReporter: <@{interaction.user.id}>\nReported account: <@{member.id}>\nDetails: {discord.utils.escape_markdown(details[:1200])}',allowed_mentions=discord.AllowedMentions.none())
    await interaction.followup.send('Report sent to staff. Save evidence and do not post private information publicly.',ephemeral=True)

@bot.tree.command(description='View a member’s completed-deal feedback')
@app_commands.guild_only()
async def reputation(interaction: discord.Interaction, member: discord.Member):
    with db() as con:
        rows=con.execute('SELECT rating FROM feedback JOIN deals ON deals.id=feedback.deal_id WHERE deals.guild=? AND feedback.recipient=?',(interaction.guild_id,member.id)).fetchall()
    if not rows: return await interaction.response.send_message('No recorded feedback for this member.',ephemeral=True)
    await interaction.response.send_message(f'{member.mention}: **{sum(r[0] for r in rows)/len(rows):.2f}/5** across {len(rows)} reviews. Feedback is not a guarantee of safety.',ephemeral=True)

@bot.tree.command(description='Join an open tournament')
@app_commands.guild_only()
async def join_tournament(interaction: discord.Interaction, tournament_id: str):
    tid=tournament_id.upper()
    with db() as con:
        row=con.execute('SELECT status,date_utc FROM tournaments WHERE id=? AND guild=?',(tid,interaction.guild_id)).fetchone()
        if not row or row[0]!='open': return await interaction.response.send_message('Tournament not open.',ephemeral=True)
        deadline=utc_date(row[1])
        if deadline and datetime.now(timezone.utc)>deadline: return await interaction.response.send_message('Registration has ended.',ephemeral=True)
        con.execute('INSERT OR IGNORE INTO entrants VALUES (?,?)',(tid,interaction.user.id))
    await interaction.response.send_message(f'You are registered for `{tid}`.',ephemeral=True)

@bot.tree.command(description='Leave a tournament')
@app_commands.guild_only()
async def leave_tournament(interaction: discord.Interaction, tournament_id: str):
    with db() as con:
        row=con.execute('SELECT status FROM tournaments WHERE id=? AND guild=?',(tournament_id.upper(),interaction.guild_id)).fetchone()
        if not row or row[0]!='open': return await interaction.response.send_message('Tournament registration is closed.',ephemeral=True)
        con.execute('DELETE FROM entrants WHERE tournament_id=? AND member=?',(tournament_id.upper(),interaction.user.id))
    await interaction.response.send_message('Registration removed.',ephemeral=True)

@bot.tree.command(description='Staff: close tournament registration and generate first-round pairings')
@app_commands.guild_only()
async def start_tournament(interaction: discord.Interaction, tournament_id: str):
    if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
    tid=tournament_id.upper()
    with db() as con:
        row=con.execute('SELECT status FROM tournaments WHERE id=? AND guild=?',(tid,interaction.guild_id)).fetchone()
        if not row or row[0]!='open': return await interaction.response.send_message('Tournament not open.',ephemeral=True)
        players=[r[0] for r in con.execute('SELECT member FROM entrants WHERE tournament_id=?',(tid,)).fetchall()]
        if len(players)<2: return await interaction.response.send_message('At least two entrants required.',ephemeral=True)
        random.SystemRandom().shuffle(players)
        pairs=list(zip(players[::2],players[1::2]))
        lines=[]
        for a,b in pairs:
            mid=secrets.token_hex(4).upper()
            con.execute('INSERT INTO matches VALUES (?,?,?,?,?,?)',(mid,tid,a,b,None,None))
            lines.append(f'`{mid}` <@{a}> vs <@{b}>')
        if len(players)%2: lines.append(f'<@{players[-1]}> has a first-round bye (staff handles advancement).')
        con.execute('UPDATE tournaments SET status=? WHERE id=?',('started',tid))
    ch=find_channel(interaction.guild,'tournament-signups')
    if isinstance(ch,discord.TextChannel): await ch.send(f'🏆 Tournament `{tid}` started!\n'+'\n'.join(lines),allowed_mentions=discord.AllowedMentions.none())
    await interaction.response.send_message('First-round pairings generated. Staff must create subsequent rounds manually.',ephemeral=True)

@bot.tree.command(description='Staff: record a tournament match winner')
@app_commands.guild_only()
async def match_result(interaction: discord.Interaction, match_id: str, winner: discord.Member):
    if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
    with db() as con:
        row=con.execute('SELECT player1,player2 FROM matches JOIN tournaments ON tournaments.id=matches.tournament_id WHERE matches.id=? AND tournaments.guild=?',(match_id.upper(),interaction.guild_id)).fetchone()
        if not row or winner.id not in row: return await interaction.response.send_message('Match not found or winner is not a participant.',ephemeral=True)
        con.execute('UPDATE matches SET winner=?,reported_by=? WHERE id=?',(winner.id,interaction.user.id,match_id.upper()))
    ch=find_channel(interaction.guild,'match-results')
    if isinstance(ch,discord.TextChannel): await ch.send(f'🏆 Match `{match_id.upper()}` winner: {winner.mention}',allowed_mentions=discord.AllowedMentions.none())
    await interaction.response.send_message('Result saved.',ephemeral=True)

@bot.tree.command(description='View tournament entrants and match results')
@app_commands.guild_only()
async def tournament_info(interaction: discord.Interaction, tournament_id: str):
    with db() as con:
        row=con.execute('SELECT name,status FROM tournaments WHERE id=? AND guild=?',(tournament_id.upper(),interaction.guild_id)).fetchone()
        if not row: return await interaction.response.send_message('Tournament not found.',ephemeral=True)
        count=con.execute('SELECT COUNT(*) FROM entrants WHERE tournament_id=?',(tournament_id.upper(),)).fetchone()[0]
        matches=con.execute('SELECT COUNT(*),SUM(CASE WHEN winner IS NOT NULL THEN 1 ELSE 0 END) FROM matches WHERE tournament_id=?',(tournament_id.upper(),)).fetchone()
    await interaction.response.send_message(f'🏆 **{discord.utils.escape_markdown(row[0])}** • {row[1]}\nEntrants: {count} • Matches: {matches[0]} • Results: {matches[1] or 0}',ephemeral=True)

@bot.tree.command(description='Enter a free giveaway before the deadline')
@app_commands.guild_only()
async def enter_giveaway(interaction: discord.Interaction, giveaway_id: str):
    gid=giveaway_id.upper()
    with db() as con:
        row=con.execute('SELECT deadline,status FROM giveaways WHERE id=? AND guild=?',(gid,interaction.guild_id)).fetchone()
        if not row or row[1]!='open': return await interaction.response.send_message('Giveaway not open.',ephemeral=True)
        deadline=utc_date(row[0])
        if not deadline: return await interaction.response.send_message('Staff must correct the giveaway deadline.',ephemeral=True)
        if datetime.now(timezone.utc)>=deadline: return await interaction.response.send_message('Entry period has ended.',ephemeral=True)
        con.execute('INSERT OR IGNORE INTO giveaway_entries VALUES (?,?)',(gid,interaction.user.id))
    await interaction.response.send_message('Entry recorded. No purchase required.',ephemeral=True)

@bot.tree.command(description='Staff: randomly draw a free giveaway winner after its deadline')
@app_commands.guild_only()
async def draw_giveaway(interaction: discord.Interaction, giveaway_id: str):
    if not staff(interaction.user): return await interaction.response.send_message('Staff only.',ephemeral=True)
    gid=giveaway_id.upper()
    with db() as con:
        row=con.execute('SELECT deadline,status,prize FROM giveaways WHERE id=? AND guild=?',(gid,interaction.guild_id)).fetchone()
        if not row or row[1]!='open': return await interaction.response.send_message('Giveaway not open.',ephemeral=True)
        deadline=utc_date(row[0])
        if not deadline or datetime.now(timezone.utc)<deadline: return await interaction.response.send_message('Wait until the valid UTC deadline has passed.',ephemeral=True)
        entrants=[r[0] for r in con.execute('SELECT member FROM giveaway_entries WHERE giveaway_id=?',(gid,)).fetchall()]
        if not entrants: return await interaction.response.send_message('No entrants.',ephemeral=True)
        winner=random.SystemRandom().choice(entrants)
        con.execute('UPDATE giveaways SET winner=?,status=? WHERE id=?',(winner,'drawn',gid))
    ch=find_channel(interaction.guild,'giveaways')
    if isinstance(ch,discord.TextChannel): await ch.send(f'🎉 Giveaway `{gid}` winner: <@{winner}>! Prize: {discord.utils.escape_markdown(row[2])}\nStaff must verify eligibility and arrange fulfillment.',allowed_mentions=discord.AllowedMentions.none())
    await interaction.response.send_message(f'Winner drawn: <@{winner}>. Check eligibility before awarding.',ephemeral=True)

@bot.tree.command(description='Staff: view leaderboard of recorded match wins')
@app_commands.guild_only()
async def leaderboard(interaction: discord.Interaction):
    with db() as con:
        rows=con.execute('SELECT matches.winner,COUNT(*) FROM matches JOIN tournaments ON tournaments.id=matches.tournament_id WHERE tournaments.guild=? AND matches.winner IS NOT NULL GROUP BY matches.winner ORDER BY COUNT(*) DESC LIMIT 10',(interaction.guild_id,)).fetchall()
    await interaction.response.send_message('🏆 **Recorded match wins**\n'+('\n'.join(f'{i}. <@{uid}> — {wins}' for i,(uid,wins) in enumerate(rows,1)) if rows else 'No results yet.'),ephemeral=True)

@bot.tree.error
async def on_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f'Command error ({interaction.command}): {error!r}')
    message='Command failed. Check the Railway deploy logs; verify bot permissions and role hierarchy.'
    try:
        if interaction.response.is_done(): await interaction.followup.send(message,ephemeral=True)
        else: await interaction.response.send_message(message,ephemeral=True)
    except discord.HTTPException: pass

bot.run(TOKEN)
