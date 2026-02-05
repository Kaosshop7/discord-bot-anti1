import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime
import time
from flask import Flask
from threading import Thread

# ==========================================
# 🌐 WEB SERVER (ส่วนที่แก้ Render Error & UptimeRobot)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    return "<h1>Bot is Online and Healthy!</h1>"

def run():
    # Render จะส่ง Port มาให้ทาง Environment Variable ถ้าไม่มีจะใช้ 8080
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==========================================
# ⚙️ CONFIGURATION
# ==========================================
TOKEN = os.getenv('DISCORD_TOKEN') # หรือใส่ Token ตรงนี้ถ้าเทสในคอม
BADWORDS_FILE = 'badwords.json'
CONFIG_FILE = 'config.json' # เก็บข้อมูลห้องที่ Setup
WARNING_DELETE_TIME = 5

# ==========================================
# 🛡️ SYSTEM SETUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help')

# ตัวแปรระบบกัน Spam
last_warning = {}

# ==========================================
# 💾 DATABASE MANAGER
# ==========================================
def load_json(filename):
    if not os.path.exists(filename):
        return [] if filename == BADWORDS_FILE else {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # ถ้าเป็นไฟล์ config ต้องคืนค่าเป็น dict, ถ้า badwords เป็น list
            if filename == CONFIG_FILE and not isinstance(data, dict): return {}
            if filename == BADWORDS_FILE and not isinstance(data, list): return []
            return data
    except:
        return [] if filename == BADWORDS_FILE else {}

def save_json(filename, data):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"Save Error: {e}")
        return False

# ==========================================
# 🎨 UI / EMBED BUILDER
# ==========================================
def create_embed(style, title, description):
    colors = {
        'error': 0xFF3B30,   # Red
        'success': 0x34C759, # Green
        'warning': 0xFFCC00, # Orange
        'info': 0x007AFF,    # Blue
        'ping': 0xFF00FF     # Magenta
    }
    embed = discord.Embed(
        title=title,
        description=description,
        color=colors.get(style, 0x5865F2),
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="🛡️ PDR Anti Profanity")
    return embed

# ==========================================
# 🤖 BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    print(f"🚀 Bot Online: {bot.user}")
    try:
        await bot.tree.sync()
        print(f"✅ Slash Commands Synced")
    except Exception as e:
        print(f"❌ Sync Error: {e}")

@bot.event
async def on_message(message):
    if message.author.bot: return

    # 1. โหลด Config ดูว่าห้องนี้เปิดใช้งานบอทไหม
    config = load_json(CONFIG_FILE)
    guild_id = str(message.guild.id)
    
    # ถ้า Server นี้ยังไม่เคย Setup เลย หรือ ห้องนี้ไม่ได้อยู่ใน list ที่เปิดใช้งาน
    # (ถ้าอยากให้ Default คือป้องกันทุกห้อง ให้ลบ Logic ส่วนนี้ออก)
    if guild_id not in config:
        # ยังไม่ Setup -> ไม่ทำงาน (หรือจะให้ทำงานทุกห้องก็ได้แล้วแต่ดีไซน์)
        # ในที่นี้สมมุติว่าต้อง Setup ก่อนถึงจะทำงาน
        await bot.process_commands(message)
        return
    
    allowed_channels = config[guild_id]
    # เช็คว่าห้องปัจจุบัน หรือหมวดหมู่ปัจจุบัน อยู่ใน list ที่ตั้งค่าไหม
    is_protected = False
    if str(message.channel.id) in allowed_channels:
        is_protected = True
    elif message.channel.category and str(message.channel.category.id) in allowed_channels:
        is_protected = True

    if not is_protected:
        await bot.process_commands(message)
        return

    # 2. ตรวจคำหยาบ (Logic เดิม)
    badwords = load_json(BADWORDS_FILE)
    content_lower = message.content.lower()
    
    found = False
    for word in badwords:
        if word in content_lower:
            found = True
            break
    
    if found:
        if not message.channel.permissions_for(message.guild.me).manage_messages:
            return

        try:
            await message.delete()
        except:
            pass

        # Anti-Spam Logic
        user_id = message.author.id
        now = time.time()
        if user_id in last_warning and now - last_warning[user_id] < 3:
            return
        
        last_warning[user_id] = now
        embed = create_embed('error', "🚫 ตรวจพบคำไม่สุภาพ", f"{message.author.mention} ข้อความถูกลบเนื่องจากมีคำหยาบ")
        try:
            await message.channel.send(embed=embed, delete_after=WARNING_DELETE_TIME)
        except:
            pass
        return

    await bot.process_commands(message)

# ==========================================
# 🛠️ SLASH COMMANDS
# ==========================================

# --- /setup: เลือกห้อง/หมวดหมู่ที่จะป้องกัน ---
@bot.tree.command(name="setup", description="เลือกห้องหรือหมวดหมู่ที่ต้องการให้บอททำงาน")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(target="เลือกห้อง (Channel) หรือหมวดหมู่ (Category) ที่ต้องการป้องกัน")
async def setup(interaction: discord.Interaction, target: discord.abc.GuildChannel):
    guild_id = str(interaction.guild_id)
    target_id = str(target.id)
    target_name = target.name
    target_type = "หมวดหมู่" if isinstance(target, discord.CategoryChannel) else "ห้อง"

    config = load_json(CONFIG_FILE)
    
    if guild_id not in config:
        config[guild_id] = []
    
    if target_id not in config[guild_id]:
        config[guild_id].append(target_id)
        save_json(CONFIG_FILE, config)
        embed = create_embed('success', "✅ ตั้งค่าสำเร็จ", f"เปิดใช้งานระบบป้องกันใน {target_type}: **{target_name}** แล้ว")
    else:
        # ถ้ามีอยู่แล้ว ให้ถามว่าจะลบออกไหม (Toggle)
        config[guild_id].remove(target_id)
        save_json(CONFIG_FILE, config)
        embed = create_embed('warning', "⚠️ ยกเลิกการตั้งค่า", f"ปิดการใช้งานระบบป้องกันใน {target_type}: **{target_name}** แล้ว")

    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- /ping: เช็คสถานะ ---
@bot.tree.command(name="ping", description="เช็คความหน่วงของบอท")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = create_embed('ping', "🏓 Pong!", f"ความหน่วงระบบ: **{latency}ms**\nสถานะ: ปกติ")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- /help: คู่มือ ---
@bot.tree.command(name="help", description="ดูคำสั่งทั้งหมด")
async def help_command(interaction: discord.Interaction):
    desc = (
        "**👮 คำสั่งสำหรับ Admin**\n"
        "`/setup [channel/category]` - เปิด/ปิด การป้องกันในห้องนั้นๆ\n"
        "`/addword [คำ]` - เพิ่มคำหยาบ\n"
        "`/removeword [คำ]` - ลบคำหยาบ\n"
        "`/listwords` - ดูรายการคำหยาบทั้งหมด\n\n"
        "**🤖 คำสั่งทั่วไป**\n"
        "`/ping` - เช็คสถานะบอท"
    )
    embed = create_embed('info', "📖 คู่มือการใช้งาน", desc)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- คำสั่งเดิม (Add/Remove/List) ---
@bot.tree.command(name="addword", description="เพิ่มคำหยาบ")
@app_commands.checks.has_permissions(administrator=True)
async def add_badword(interaction: discord.Interaction, word: str):
    word = word.strip().lower()
    if not word: return
    badwords = load_json(BADWORDS_FILE)
    if word in badwords:
        await interaction.response.send_message(embed=create_embed('warning', "ซ้ำ", f"'{word}' มีอยู่แล้ว"), ephemeral=True)
    else:
        badwords.append(word)
        save_json(BADWORDS_FILE, badwords)
        await interaction.response.send_message(embed=create_embed('success', "สำเร็จ", f"เพิ่ม '{word}' แล้ว"), ephemeral=True)

@bot.tree.command(name="removeword", description="ลบคำหยาบ")
@app_commands.checks.has_permissions(administrator=True)
async def remove_badword(interaction: discord.Interaction, word: str):
    word = word.strip().lower()
    badwords = load_json(BADWORDS_FILE)
    if word in badwords:
        badwords.remove(word)
        save_json(BADWORDS_FILE, badwords)
        await interaction.response.send_message(embed=create_embed('success', "สำเร็จ", f"ลบ '{word}' แล้ว"), ephemeral=True)
    else:
        await interaction.response.send_message(embed=create_embed('error', "ไม่พบ", f"ไม่เจอ '{word}'"), ephemeral=True)

@bot.tree.command(name="listwords", description="ดูคำหยาบทั้งหมด")
@app_commands.checks.has_permissions(administrator=True)
async def list_badwords(interaction: discord.Interaction):
    badwords = load_json(BADWORDS_FILE)
    if not badwords:
        await interaction.response.send_message(embed=create_embed('info', "ว่างเปล่า", "ไม่มีข้อมูล"), ephemeral=True)
    else:
        text = ", ".join([f"`{w}`" for w in badwords])
        if len(text) > 4000: text = text[:4000] + "..."
        await interaction.response.send_message(embed=create_embed('info', "รายการคำหยาบ", text), ephemeral=True)

# ==========================================
# 🚀 STARTUP
# ==========================================
# รัน Web Server ใน Thread แยก (เพื่อให้ Render เจอ Port)
keep_alive()

# รันบอท
if __name__ == "__main__":
    if not TOKEN:
        print("❌ Error: Missing Token")
    else:
        bot.run(TOKEN)
    
