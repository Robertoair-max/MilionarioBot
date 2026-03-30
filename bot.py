import os
import random
import asyncio
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERS = ["Lady_unknow", "Tuc0Pacific0"]
TEMPO_RISPOSTA = 45 

client = MongoClient(MONGO_URI)
db = client.quiz_milionario
players = db.players

# --- DATABASE DOMANDE ---
QUESTIONS = [
    {"q": "Qual è la capitale d'Italia?", "o": {"A": "Milano", "B": "Roma", "C": "Napoli", "D": "Torino"}, "c": "B"},
    {"q": "Quanti pianeti ci sono nel sistema solare?", "o": {"A": "7", "B": "9", "C": "8", "D": "10"}, "c": "C"},
    {"q": "Chi ha dipinto la Gioconda?", "o": {"A": "Michelangelo", "B": "Raffaello", "C": "Leonardo", "D": "Donatello"}, "c": "C"},
    {"q": "Qual è l'elemento chimico con simbolo O?", "o": {"A": "Oro", "B": "Ossigeno", "C": "Osmio", "D": "Olio"}, "c": "B"},
    {"q": "In che anno è iniziata la Seconda Guerra Mondiale?", "o": {"A": "1914", "B": "1939", "C": "1945", "D": "1929"}, "c": "B"},
    {"q": "Quale organo pompa il sangue nel corpo?", "o": {"A": "Polmoni", "B": "Cervello", "C": "Fegato", "D": "Cuore"}, "c": "D"},
    {"q": "Chi scrisse la Divina Commedia?", "o": {"A": "Petrarca", "B": "Boccaccio", "C": "Dante Alighieri", "D": "Leopardi"}, "c": "C"},
    {"q": "Qual è il fiume più lungo del mondo?", "o": {"A": "Nilo", "B": "Rio delle Amazzoni", "C": "Mississippi", "D": "Tevere"}, "c": "B"},
    {"q": "In quale continente si trova il deserto del Sahara?", "o": {"A": "Asia", "B": "America", "C": "Africa", "D": "Australia"}, "c": "C"},
    {"q": "Qual è il metallo più prezioso tra questi?", "o": {"A": "Argento", "B": "Bronzo", "C": "Oro", "D": "Rame"}, "c": "C"},
    {"q": "Quante corde ha un violino standard?", "o": {"A": "4", "B": "6", "C": "5", "D": "3"}, "c": "A"},
    {"q": "Chi è l'autore di 'I Promessi Sposi'?", "o": {"A": "Pascoli", "B": "Manzoni", "C": "Pirandello", "D": "Svevo"}, "c": "B"},
    {"q": "Qual è la velocità della luce (circa)?", "o": {"A": "300.000 km/s", "B": "150.000 km/s", "C": "1.000.000 km/s", "D": "50.000 km/s"}, "c": "A"},
    {"q": "Quale paese ha vinto più Mondiali di calcio?", "o": {"A": "Italia", "B": "Germania", "C": "Brasile", "D": "Argentina"}, "c": "C"},
    {"q": "Chi fu il primo uomo sulla Luna?", "o": {"A": "Yuri Gagarin", "B": "Buzz Aldrin", "C": "Neil Armstrong", "D": "Michael Collins"}, "c": "C"},
]

# --- UTILS ---
async def pulisci_messaggi_aiuto(user_id, context):
    p = players.find_one({"user_id": user_id})
    if p:
        for m_id in p.get("temp_msg_ids", []):
            try: await context.bot.delete_message(chat_id=user_id, message_id=m_id)
            except: pass
        players.update_one({"user_id": user_id}, {"$set": {"temp_msg_ids": []}})

async def timeout_scaduto(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    await pulisci_messaggi_aiuto(user_id, context)
    await context.bot.send_message(user_id, "⏰ *TEMPO SCADUTO!*\nIl gioco finisce qui.", parse_mode="Markdown")

# --- GAME LOGIC ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if players.find_one({"user_id": user.id, "game_over": True}) and user.username not in ADMIN_USERS:
        await update.message.reply_text("⛔️ Hai già giocato!\nSolo @Lady_unknow e @Tuc0Pacific0 giocano sempre.")
        return
    init = {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}
    players.update_one({"user_id": user.id}, {"$set": init}, upsert=True)
    await update.message.reply_text("🏆 *BENVENUTO!* Hai 45 secondi a domanda.", parse_mode="Markdown")
    await invia_domanda(update, context, 0)

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    q = QUESTIONS[idx]
    for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
    context.job_queue.run_once(timeout_scaduto, TEMPO_RISPOSTA, user_id=user_id, name=str(user_id))
    txt = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    for k, v in q['o'].items():
        if rimosse and k in rimosse: continue
        txt += f"*{k}*: {v}\n"
    row1 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["A", "B"] if not (rimosse and k in rimosse)]
    row2 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["C", "D"] if not (rimosse and k in rimosse)]
    row_h = []
    if p["h"]["5050"]: row_h.append(InlineKeyboardButton("50:50 🎭", callback_data="h_5050"))
    if p["h"]["pub"]: row_h.append(InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"))
    if p["h"]["tel"]: row_h.append(InlineKeyboardButton("Tel 📞", callback_data="h_tel"))
    kb = InlineKeyboardMarkup([row1, row2, row_h])
    if update.message: await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

# --- CALLBACK HANDLER ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id, username = query.from_user.id, query.from_user.username
    p = players.find_one({"user_id": user_id})
    data = query.data

    # --- ADMIN ACTIONS ---
    if data.startswith("adm_") and username in ADMIN_USERS:
        if data == "adm_panel": await admin_panel(update, context)
        elif data == "adm_view":
            top = players.find().sort("current_q", -1).limit(10)
            txt = "🏆 *CLASSIFICA*\n\n" + "\n".join([f"{i+1}. @{x.get('username')} - Liv {x.get('current_q')+1}" for i, x in enumerate(top)])
            await query.message.reply_text(txt or "Nessun dato.", parse_mode="Markdown")
        elif data == "adm_conf_db":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 SÌ, ELIMINA TUTTO IL DB", callback_data="adm_drop_db")], [InlineKeyboardButton("❌ ANNULLA", callback_data="adm_panel")]])
            await query.edit_message_text("⚠️ *ATTENZIONE ESTREMA!*\nVuoi cancellare l'intero database di MongoDB? Questa azione eliminerà ogni traccia di gioco.", reply_markup=kb, parse_mode="Markdown")
        elif data == "adm_drop_db":
            client.drop_database('quiz_milionario')
            await query.edit_message_text("💥 *DATABASE ELIMINATO COMPLETAMENTE.*", parse_mode="Markdown")
        elif data == "adm_del_class":
            players.delete_many({})
            await query.edit_message_text("✅ Classifica resettata.")
        await query.answer()
        return

    # --- GAME ACTIONS ---
    if not p or (p.get("game_over") and username not in ADMIN_USERS): return
    idx = p["current_q"]
    q = QUESTIONS[idx]

    if data.startswith("ans_"):
        await pulisci_messaggi_aiuto(user_id, context)
        if data.split("_") == q["c"]:
            if idx == 14:
                await query.edit_message_text("🏆 *MILIONARIO!* 🏆")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await invia_domanda(update, context, idx + 1)
        else:
            await query.edit_message_text(f"❌ *SBAGLIATO!* Era {q['c']}.")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    
    elif data.startswith("h_"):
        players.update_one({"user_id": user_id}, {"$set": {f"h.{data.split('_')}: False}})
        if "5050" in data:
            await invia_domanda(update, context, idx, rimosse=random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2))
        else:
            txt = "📊 *Pubblico*: " + q['c'] if "pub" in data else f"📞 'Penso sia {q['c']}'"
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
            await invia_domanda(update, context, idx)
    await query.answer()

# --- ADMIN PANEL ---
async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username in ADMIN_USERS:
        await admin_panel(update, context)

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Vedi Classifica", callback_data="adm_view")],
        [InlineKeyboardButton("🗑 Reset Classifica", callback_data="adm_del_class")],
        [InlineKeyboardButton("🔥 ELIMINA DATABASE MONGO", callback_data="adm_conf_db")]
    ])
    if update.message: await update.message.reply_text("🛠 *PANNELLO ADMIN*", reply_markup=kb, parse_mode="Markdown")
    else: await update.callback_query.edit_message_text("🛠 *PANNELLO ADMIN*", reply_markup=kb, parse_mode="Markdown")

import threading
from flask import Flask

# Crea una piccola app web finta
app_web = Flask(__name__)
@app_web.route('/')
def home(): return "Bot is running!"

def run_flask():
    # Render assegna una porta automaticamente nella variabile PORT
    port = int(os.environ.get("PORT", 5000))
    app_web.run(host='0.0.0.0', port=port)

if __name__ == "__main__":
    # Avvia il sito web finto in un thread separato
    threading.Thread(target=run_flask).start()
    
    # Avvia il Bot Telegram normalmente
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.run_polling()
