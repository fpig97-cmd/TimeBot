import discord
from discord import app_commands
import asyncio
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

TOKEN = "여기에_봇_토큰"

# ===== DB 설정 =====
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


# ===== 봇 클래스 =====
class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        self.loop.create_task(self.check_reservations())

    async def check_reservations(self):
        await self.wait_until_ready()
        while not self.is_closed():
            now = datetime.now(ZoneInfo("Asia/Seoul"))

            cursor.execute("SELECT * FROM reservations")
            rows = cursor.fetchall()

            for row in rows:
                rid, guild_id, channel_id, user_id, send_time, content = row
                send_dt = datetime.strptime(send_time, "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=ZoneInfo("Asia/Seoul")
                )

                if now >= send_dt:
                    channel = self.get_channel(channel_id)
                    if channel:
                        await channel.send(f"📢 예약 메시지\n{content}")

                    cursor.execute("DELETE FROM reservations WHERE id = ?", (rid,))
                    conn.commit()

            await asyncio.sleep(5)


bot = Bot()


# ===== 예약 생성 =====
@bot.tree.command(name="예약", description="특정 날짜/시간에 메시지를 예약합니다.")
@app_commands.describe(
    날짜="예: 2026-02-20 18:30:00",
    내용="보낼 메시지"
)
async def 예약(interaction: discord.Interaction, 날짜: str, 내용: str):
    try:
        send_dt = datetime.strptime(날짜, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=ZoneInfo("Asia/Seoul")
        )
    except ValueError:
        await interaction.response.send_message(
            "❌ 날짜 형식이 올바르지 않습니다.\n예: 2026-02-20 18:30:00",
            ephemeral=True
        )
        return

    if send_dt <= datetime.now(ZoneInfo("Asia/Seoul")):
        await interaction.response.send_message(
            "❌ 현재 시간 이후로 설정해주세요.",
            ephemeral=True
        )
        return

    cursor.execute(
        "INSERT INTO reservations (guild_id, channel_id, user_id, send_time, content) VALUES (?, ?, ?, ?, ?)",
        (
            interaction.guild_id,
            interaction.channel_id,
            interaction.user.id,
            send_dt.strftime("%Y-%m-%d %H:%M:%S"),
            내용
        )
    )
    conn.commit()

    await interaction.response.send_message("✅ 예약이 완료되었습니다.", ephemeral=True)


# ===== 예약 목록 =====
@bot.tree.command(name="예약목록", description="내 예약 목록을 확인합니다.")
async def 예약목록(interaction: discord.Interaction):
    cursor.execute(
        "SELECT id, send_time, content FROM reservations WHERE user_id = ?",
        (interaction.user.id,)
    )
    rows = cursor.fetchall()

    if not rows:
        await interaction.response.send_message("📭 예약된 메시지가 없습니다.", ephemeral=True)
        return

    msg = "📋 예약 목록\n"
    for r in rows:
        msg += f"\nID: {r[0]}\n시간: {r[1]}\n내용: {r[2]}\n"

    await interaction.response.send_message(msg, ephemeral=True)


# ===== 예약 취소 =====
@bot.tree.command(name="예약취소", description="예약을 취소합니다.")
@app_commands.describe(id="취소할 예약 ID")
async def 예약취소(interaction: discord.Interaction, id: int):
    cursor.execute(
        "SELECT * FROM reservations WHERE id = ? AND user_id = ?",
        (id, interaction.user.id)
    )
    row = cursor.fetchone()

    if not row:
        await interaction.response.send_message("❌ 해당 예약을 찾을 수 없습니다.", ephemeral=True)
        return

    cursor.execute("DELETE FROM reservations WHERE id = ?", (id,))
    conn.commit()

    await interaction.response.send_message("🗑 예약이 취소되었습니다.", ephemeral=True)


bot.run(TOKEN)
