import discord
import os
from discord import app_commands
import asyncio
import sqlite3
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.getenv("DISCORD_TOKEN")

KST = ZoneInfo("Asia/Seoul")

# ===== DB =====
conn = sqlite3.connect("reservations.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    channel_id INTEGER,
    user_id INTEGER,
    send_time TEXT,
    content TEXT
)
""")
conn.commit()


# ===== 봇 =====
class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 봇이 들어가 있는 모든 서버에 명령어 동기화
        for guild in self.guilds:
            try:
                await self.tree.sync(guild=guild)
                print(f"[{guild.name}]({guild.id}) 에 슬래시 명령어 동기화됨")
            except Exception as e:
                print(f"[{guild.name}]({guild.id}) 동기화 실패: {repr(e)}")

        # 예약 체크 루프 시작
        self.loop.create_task(self.check_reservations())

    async def check_reservations(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(KST)

            cursor.execute("SELECT * FROM reservations")
            rows = cursor.fetchall()

            for row in rows:
                rid, guild_id, channel_id, user_id, send_time, content = row
                send_dt = (
                    datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S")
                    .replace(tzinfo=KST)
                )

                if now >= send_dt:
    channel = self.get_channel(channel_id)
    if channel:
        ts = int(send_dt.timestamp())
        await channel.send(
            f"{content}\n\n"
            f"예약 시간: <t:{ts}:f> (<t:{ts}:R>)"
        )

                    cursor.execute("DELETE FROM reservations WHERE id = ?", (rid,))
                    conn.commit()

            await asyncio.sleep(5)


bot = Bot()


# ===== 날짜 파싱 함수 =====
def parse_korean_datetime(text: str):
    now = datetime.now(KST)

    # 1️⃣ 상대 시간 (예: 3시간 뒤 / 10분 뒤 / 30초 뒤)
    rel = re.match(r"(\d+)(시간|분|초)\s*뒤", text)
    if rel:
        num = int(rel.group(1))
        unit = rel.group(2)

        if unit == "시간":
            return now + timedelta(hours=num)
        if unit == "분":
            return now + timedelta(minutes=num)
        if unit == "초":
            return now + timedelta(seconds=num)

    # 2️⃣ 오늘 / 내일 (예: 오늘 오후 3시 10분 00초)
    pattern2 = r"(오늘|내일)\s*(오전|오후)\s*(\d+)시\s*(\d+)분\s*(\d+)초"
    match2 = re.match(pattern2, text)
    if match2:
        dayword, ampm, hour, minute, second = match2.groups()
        hour = int(hour)
        minute = int(minute)
        second = int(second)

        if ampm == "오후" and hour != 12:
            hour += 12
        if ampm == "오전" and hour == 12:
            hour = 0

        base = now
        if dayword == "내일":
            base = now + timedelta(days=1)

        return datetime(
            base.year, base.month, base.day, hour, minute, second, tzinfo=KST
        )

    # 3️⃣ 전체 날짜 (예: 2026년 2월 20일 오후 6시 30분 00초)
    pattern3 = (
        r"(\d+)년\s*(\d+)월\s*(\d+)일\s*(오전|오후)\s*(\d+)시\s*(\d+)분\s*(\d+)초"
    )
    match3 = re.match(pattern3, text)
    if match3:
        year, month, day, ampm, hour, minute, second = match3.groups()

        year = int(year)
        month = int(month)
        day = int(day)
        hour = int(hour)
        minute = int(minute)
        second = int(second)

        if ampm == "오후" and hour != 12:
            hour += 12
        if ampm == "오전" and hour == 12:
            hour = 0

        return datetime(year, month, day, hour, minute, second, tzinfo=KST)

    return None


# ===== 예약 생성 =====
@bot.tree.command(name="예약", description="한국어 날짜로 예약합니다.")
@app_commands.describe(
    날짜="예: 2026년 2월 20일 오후 6시 30분 00초 / 오늘 오후 6시 30분 00초 / 3시간 뒤",
    내용="보낼 메시지",
    채널="보낼 채널 (관리자만 다른 채널 가능)",
)
async def 예약(
    interaction: discord.Interaction,
    날짜: str,
    내용: str,
    채널: discord.TextChannel = None,
):
    send_dt = parse_korean_datetime(날짜)

    if not send_dt:
        await interaction.response.send_message(
            "❌ 날짜 형식이 올바르지 않습니다.", ephemeral=True
        )
        return

    if send_dt <= datetime.now(KST):
        await interaction.response.send_message(
            "❌ 현재 시간 이후로 설정해주세요.", ephemeral=True
        )
        return

    target_channel = 채널 if 채널 else interaction.channel

    if 채널 and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ 다른 채널 지정은 관리자만 가능합니다.", ephemeral=True
        )
        return

    cursor.execute(
        "INSERT INTO reservations (guild_id, channel_id, user_id, send_time, content) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            interaction.guild_id,
            target_channel.id,
            interaction.user.id,
            send_dt.strftime("%Y-%m-%d %H:%M:%S"),
            내용,
        ),
    )
    conn.commit()

    ts = int(send_dt.timestamp())
    await interaction.response.send_message(
        "✅ 예약 완료!\n"
        f"채널: {target_channel.mention}\n"
        f"시간: {send_dt.strftime('%Y-%m-%d %H:%M:%S')} (<t:{ts}:R>)",
        ephemeral=True,
    )


# ===== 예약 목록 =====
@bot.tree.command(name="예약목록", description="내 예약 목록을 확인합니다.")
async def 예약목록(interaction: discord.Interaction):
    cursor.execute(
        "SELECT id, send_time, content FROM reservations WHERE user_id = ?",
        (interaction.user.id,),
    )
    rows = cursor.fetchall()

    if not rows:
        await interaction.response.send_message("📭 예약이 없습니다.", ephemeral=True)
        return

    msg_lines = ["📋 예약 목록"]
    for r in rows:
        rid, send_time, content = r
        send_dt = datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=KST
        )
        ts = int(send_dt.timestamp())
        msg_lines.append(
            f"\nID: {rid}\n"
            f"시간: {send_time} (<t:{ts}:R>)\n"
            f"내용: {content}"
        )

    await interaction.response.send_message("\n".join(msg_lines), ephemeral=True)


# ===== 예약 취소 =====
@bot.tree.command(name="예약취소", description="예약을 취소합니다.")
@app_commands.describe(id="취소할 예약 ID")
async def 예약취소(interaction: discord.Interaction, id: int):
    cursor.execute(
        "SELECT * FROM reservations WHERE id = ? AND user_id = ?",
        (id, interaction.user.id),
    )
    row = cursor.fetchone()

    if not row:
        await interaction.response.send_message(
            "❌ 해당 예약을 찾을 수 없습니다.", ephemeral=True
        )
        return

    cursor.execute("DELETE FROM reservations WHERE id = ?", (id,))
    conn.commit()

    await interaction.response.send_message("🗑 예약이 취소되었습니다.", ephemeral=True)


bot.run(TOKEN)
