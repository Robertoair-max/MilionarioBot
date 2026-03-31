import os
import random
import threading
import asyncio
import time
import requests
import logging
from flask import Flask
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
ADMIN_USERS = ["Lady_unknow", "Tuc0Pacific0"]
TEMPO_RISPOSTA = 60

# Inizializzazione MongoDB
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

# --- LOGICA AIUTI E UTILS ---
def genera_pubblico(corretta, idx):
    prob_corretta = max(35, 85 - (idx * 4))
    opzioni = ["A", "B", "C", "D"]
    voti = {corretta: random.randint(int(prob_corretta), 95)}
    rimanente = 100 - voti[corretta]
    altre = [k for k in opzioni if k != corretta]
    random.shuffle(altre)
    v1 = random.randint(0, rimanente); voti[altre[0]] = v1; rimanente -= v1
    v2 = random.randint(0, rimanente); voti[altre[1]] = v2
    voti[altre[2]] = 100 - (voti[corretta] + v1 + v2)
    res = "📊 *Risultato del pubblico:*\n\n"
    for k in sorted(voti.keys()): res += f"*{k}*: {voti[k]}%\n"
    return res

def genera_tel(corretta, idx):
    aff = max(30, 90 - (idx * 5))
    sorte = random.randint(1, 100)
    errata = random.choice([k for k in ["A", "B", "C", "D"] if k != corretta])
    if sorte <= aff: return f"📞 'Pronto? Sì! Guarda, la risposta è la *{corretta}*!'"
    elif sorte <= aff + 25: return f"📞 'Mmm... tra la *{corretta}* e la *{errata}*, punterei sulla prima...'"
    return "📞 'Pronto? No, guarda... non ne ho idea!'"

async def pulisci_aiuti(user_id, context):
    p = players.find_one({"user_id": user_id})
    if p and p.get("temp_msg_ids"):
        for m_id in p["temp_msg_ids"]:
            try: await context.bot.delete_message(chat_id=user_id, message_id=m_id)
            except: pass
        players.update_one({"user_id": user_id}, {"$set": {"temp_msg_ids": []}})

async def timeout_scaduto(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    await pulisci_aiuti(user_id, context)
    try: await context.bot.send_message(user_id, "⏰ *TEMPO SCADUTO!*\nIl gioco è terminato.", parse_mode="Markdown")
    except: pass

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    if idx >= len(QUESTIONS): return
    q = QUESTIONS[idx]
    
    if context.job_queue:
        for j in context.job_queue.get_jobs_by_name(str(user_id)): j.schedule_removal()
        context.job_queue.run_once(timeout_scaduto, TEMPO_RISPOSTA, user_id=user_id, name=str(user_id))
    
    txt = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    for k, v in q['o'].items():
        if rimosse and k in rimosse: continue
        txt += f"*{k}*: {v}\n"
    
    r1 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["A", "B"] if not (rimosse and k in rimosse)]
    r2 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["C", "D"] if not (rimosse and k in rimosse)]
    rh = []
    if p["h"]["5050"]: rh.append(InlineKeyboardButton("50:50 🎭", callback_data="h_5050"))
    if p["h"]["pub"]: rh.append(InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"))
    if p["h"]["tel"]: rh.append(InlineKeyboardButton("Tel 📞", callback_data="h_tel"))
    
    kb = InlineKeyboardMarkup([r1, r2, rh])
    if update.callback_query: await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
    else: await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    players.update_one({"user_id": user.id}, {"$set": {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}}, upsert=True)
    
    regole = (
        "🏆 *BENVENUTO AL MILIONARIO!*\n\n"
        "📜 *REGOLAMENTO:*\n"
        "1️⃣ Hai **60 secondi** per ogni domanda.\n"
        "2️⃣ Se il tempo scade o sbagli, il gioco finisce.\n"
        "3️⃣ Hai 3 aiuti (50:50, Pubblico, Telefonata).\n\n"
        "Sei pronto?"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Inizia il Quiz 🚀", callback_data="game_init")]])
    await update.message.reply_text(regole, reply_markup=kb, parse_mode="Markdown")

async def callback_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    p = players.find_one({"user_id": user_id})
    if not p: return
    
    data = query.data

    if data == "game_init":
        await invia_domanda(update, context, 0)
        await query.answer(); return

    if p.get("game_over"):
        await query.answer("Gioco terminato.", show_alert=True); return

    if data.startswith("ans_"):
        ans = data.replace("ans_", "")
        current_idx = p["current_q"]
        q = QUESTIONS[current_idx]
        
        if context.job_queue:
            for j in context.job_queue.get_jobs_by_name(str(user_id)): j.schedule_removal()
        
        await pulisci_aiuti(user_id, context)
        
        if ans == q["c"]:
            if current_idx == 14:
                await query.edit_message_text("🏆 *MILIONARIO!*")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                new_idx = current_idx + 1
                players.update_one({"user_id": user_id}, {"$set": {"current_q": new_idx}})
                await invia_domanda(update, context, new_idx)
        else:
            await query.edit_message_text(f"❌ *SBAGLIATO!*\nEra: {q['c']}.")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})

    elif data.startswith("h_"):
        tipo = data.replace("h_", "")
        current_idx = p["current_q"]
        q = QUESTIONS[current_idx]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, current_idx, rimosse)
        else:
            txt = genera_pubblico(q["c"], current_idx) if tipo == "pub" else genera_tel(q["c"], current_idx)
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
    
    await query.answer()

# --- SERVER FLASK (OTTIMIZZATO PER CRON) ---
server = Flask(__name__)
# Riduciamo l'output al minimo per evitare errori di buffer nei cronjob
@server.route('/')
def home(): return "OK", 200 

def run_flask():
    logging.getLogger('werkzeug').setLevel(logging.ERROR) # Silenzia i log di accesso
    server.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))

# --- MAIN ---
if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_logic))
    app.run_polling(drop_pending_updates=True)
