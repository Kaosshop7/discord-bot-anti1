import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import datetime
import time
import asyncio

# ==========================================
# ⚙️ CONFIGURATION (ตั้งค่าส่วนนี้)
# ==========================================
# ใส่ Token ตรงนี้ หรือถ้าใช้ Cloud ให้ใส่ใน Environment Variables ชื่อ 'DISCORD_TOKEN'
TOKEN = os.getenv('DISCORD_TOKEN') or 'ใส่_TOKEN_ของคุณตรงนี้' 
BADWORDS_FILE = 'badwords.json'
WARNING_DELETE_TIME = 5 # วินาทีที่จะลบคำเตือน
SPAM_COOLDOWN = 3       # ถ้าโดนเตือนซ้ำใน 3 วิ จะไม่ส่ง Embed เตือน (กันรก)

# ==========================================
# 🛡️ SYSTEM SETUP
# ==========================================
intents = discord.Intents.default()
intents.message_content = True  # ⚠️ ต้องเปิดใน Developer Portal
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.remove_command('help') # ลบคำสั่ง help เดิมออก

# ตัวแปรระบบกัน Spam
last_warning = {}

# ==========================================
# 💾 DATABASE MANAGER (Crash Proof)
# ==========================================
def load_data():
    if not os.path.exists(BADWORDS_FILE):
        return []
    try:
        with open(BADWORDS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # กรองข้อมูลขยะ: ต้องเป็น string และไม่ว่างเปล่า
            return [w for w in data if isinstance(w, str) and w.strip()]
    except (json.JSONDecodeError, Exception) as e:
        print(f"⚠️ Database Error: {e} - Creating new database.")
        return []

def save_data(words):
    try:
        # ลบคำซ้ำและคำว่างเปล่าก่อนบันทึก
        clean_words = list(set([w.strip().lower() for w in words if w.strip()]))
        with open(BADWORDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(clean_words, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"❌ Critical Save Error: {e}")
        return False

# ==========================================
# 🎨 UI / EMBED BUILDER
# ==========================================
def create_embed(style, title, description):
    """
    style: 'error', 'success', 'warning', 'info'
    """
    colors = {
        'error': 0xFF3B30,   # Red
        'success': 0x34C759, # Green
        'warning': 0xFFCC00, # Orange
        'info': 0x007AFF     # Blue
    }
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=colors.get(style, 0x5865F2),
        timestamp=datetime.datetime.now()
    )
    # ใส่ Footer เพื่อความสวยงาม
    embed.set_footer(text="🛡️ PDR Anti Profanity")
    return embed

# ==========================================
# 🤖 BOT EVENTS
# ==========================================
@bot.event
async def on_ready():
    print("------------------------------------")
    print(f"🚀 Bot Online: {bot.user}")
    print(f"🆔 ID: {bot.user.id}")
    print("------------------------------------")
    
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash Commands Synced: {len(synced)} commands")
    except Exception as e:
        print(f"❌ Sync Error: {e}")

@bot.event
async def on_message(message):
    # 1. ไม่ตรวจสอบตัวเองและบอทอื่น
    if message.author.bot:
        return

    # 2. โหลดคำหยาบ (ถ้าไม่มีก็ข้ามเลยเพื่อประหยัด Resource)
    badwords = load_data()
    if not badwords:
        await bot.process_commands(message)
        return

    # 3. เตรียมข้อมูล
    content_lower = message.content.lower()
    user_id = message.author.id
    
    # 4. ตรวจจับ (Detection Logic)
    found = False
    for word in badwords:
        if word in content_lower:
            found = True
            break
    
    if found:
        # ตรวจสอบสิทธิ์บอทก่อนลบ (Safety Check)
        if not message.channel.permissions_for(message.guild.me).manage_messages:
            print(f"⚠️ Missing Permission: Cannot delete message in {message.channel.name}")
            return # หยุดทำงานถ้าไม่มีสิทธิ์

        try:
            await message.delete()
        except discord.NotFound:
            pass # ข้อความหายไปแล้ว
        except Exception as e:
            print(f"Delete Error: {e}")

        # ระบบ Anti-Spam Embed (ไม่ให้บอทรกแชท)
        now = time.time()
        if user_id in last_warning:
            if now - last_warning[user_id] < SPAM_COOLDOWN:
                return # ลบเงียบๆ ไม่ต้องส่ง Embed
        
        last_warning[user_id] = now
        
        # ส่ง Embed แจ้งเตือน
        embed = create_embed(
            'error', 
            "🚫 ตรวจพบคำไม่สุภาพ", 
            f"{message.author.mention} ข้อความของคุณถูกลบ เนื่องจากมีคำที่ไม่เหมาะสม"
        )
        try:
            await message.channel.send(embed=embed, delete_after=WARNING_DELETE_TIME)
        except:
            pass # ส่งไม่ได้ช่างมัน
            
        return # จบการทำงาน ไม่ต้อง process command อื่น

    await bot.process_commands(message)

# ==========================================
# 🛠️ SLASH COMMANDS (ADMIN ONLY)
# ==========================================

# 1. ADD WORD
@bot.tree.command(name="addword", description="เพิ่มคำหยาบเข้าสู่ระบบ (เฉพาะ Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def add_badword(interaction: discord.Interaction, word: str):
    word = word.strip().lower()
    
    # Validation: ห้ามเพิ่มคำว่างเปล่า
    if not word or len(word) < 1:
        embed = create_embed('warning', "⚠️ ข้อมูลไม่ถูกต้อง", "ไม่สามารถเพิ่มช่องว่างหรือข้อความเปล่าได้")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    badwords = load_data()
    
    if word in badwords:
        embed = create_embed('warning', "⚠️ ข้อมูลซ้ำ", f"คำว่า **'{word}'** มีอยู่ในระบบแล้ว")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        badwords.append(word)
        if save_data(badwords):
            embed = create_embed('success', "✅ บันทึกสำเร็จ", f"เพิ่มคำว่า **'{word}'** เข้าสู่ระบบแล้ว")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = create_embed('error', "❌ บันทึกผิดพลาด", "ไม่สามารถบันทึกไฟล์ได้ โปรดตรวจสอบ Console")
            await interaction.response.send_message(embed=embed, ephemeral=True)

# 2. REMOVE WORD
@bot.tree.command(name="removeword", description="ลบคำหยาบออกจากระบบ (เฉพาะ Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def remove_badword(interaction: discord.Interaction, word: str):
    word = word.strip().lower()
    badwords = load_data()

    if word in badwords:
        badwords.remove(word)
        save_data(badwords)
        embed = create_embed('success', "🗑️ ลบข้อมูลสำเร็จ", f"เอาคำว่า **'{word}'** ออกจากระบบแล้ว")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = create_embed('error', "❌ ไม่พบข้อมูล", f"ไม่พบคำว่า **'{word}'** ในรายการ")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# 3. LIST WORDS
@bot.tree.command(name="listwords", description="ดูรายการคำหยาบทั้งหมด (เฉพาะ Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def list_badwords(interaction: discord.Interaction):
    badwords = load_data()
    
    if not badwords:
        embed = create_embed('info', "📂 รายการคำหยาบ", "ขณะนี้ยังไม่มีข้อมูลในระบบ")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # จัดรูปแบบการแสดงผล (ป้องกัน Embed ยาวเกิน 4096 ตัวอักษร)
    display_list = []
    current_length = 0
    
    for w in badwords:
        entry = f"`{w}`"
        if current_length + len(entry) + 2 > 3500: # เผื่อที่ไว้หน่อย
            display_list.append("... (รายการยาวเกินไปที่จะแสดงทั้งหมด)")
            break
        display_list.append(entry)
        current_length += len(entry) + 2

    text_content = ", ".join(display_list)
    
    embed = create_embed('info', f"📜 รายการคำหยาบ ({len(badwords)} คำ)", text_content)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==========================================
# 🚨 GLOBAL ERROR HANDLER
# ==========================================
@bot.tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        embed = create_embed('error', "⛔ ไม่มีสิทธิ์", "คำสั่งนี้ใช้ได้เฉพาะ **Administrator** เท่านั้น")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        # Log error จริงๆ ไว้ที่ Console ฝั่งโฮส
        print(f"⚠️ Interaction Error: {error}")
        embed = create_embed('error', "⚠️ เกิดข้อผิดพลาด", "ระบบขัดข้องชั่วคราว โปรดลองใหม่")
        # เช็คว่าตอบกลับไปหรือยัง
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

# รันบอท
if __name__ == "__main__":
    if TOKEN == 'ใส่_TOKEN_ของคุณตรงนี้' and not os.getenv('DISCORD_TOKEN'):
        print("❌ Error: กรุณาใส่ Bot Token ในไฟล์ หรือตั้งค่า Environment Variable")
    else:
        bot.run(TOKEN)
