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
TEMPO_RISPOSTA = 60 

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
        await update.message.reply_text("⛔️ Hai già giocato!\nSolo @Lady_unknow e @Tuc0Pacific0 possono rigiocare.")
        return
    
    msg = (
        "🏆 *BENVENUTO AL QUIZ MILIONARIO!*\n\n"
        "📖 *REGOLE:*\n"
        f"• Hai {TEMPO_RISPOSTA} secondi per ogni domanda.\n"
        "• 15 domande totali.\n"
        "• Hai 3 aiuti utilizzabili una sola volta.\n\n"
        "Clicca il tasto sotto quando sei pronto a iniziare la scalata!"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 INIZIA IL GIOCO", callback_data="game_start")]])
    await update.message.reply_text(msg, reply_markup=kb, parse_mode="Markdown")

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    q = QUESTIONS[idx]
    
    # Gestione Timer
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
    
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await context.bot.send_message(user_id, txt, reply_markup=kb, parse_mode="Markdown")

# --- ADMIN PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username not in ADMIN_USERS: return
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Classifica", callback_data="adm_view")],
        [InlineKeyboardButton("🧹 Reset Classifica", callback_data="adm_del_class")],
        [InlineKeyboardButton("🔥 ELIMINA DB", callback_data="adm_conf_db")]
    ])
    await update.message.reply_text("🛠 *PANNELLO ADMIN*", reply_markup=kb, parse_mode="Markdown")

# --- CALLBACK HANDLER ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id, username = query.from_user.id, query.from_user.username
    data = query.data

    # Logica Inizio Gioco
    if data == "game_start":
        init = {"user_id": user_id, "username": username, "current_q": 0, "game_over": False, 
                "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}
        players.update_one({"user_id": user_id}, {"$set": init}, upsert=True)
        await invia_domanda(update, context, 0)
        await query.answer(); return

    # Logica Admin
    if data.startswith("adm_") and username in ADMIN_USERS:
        if data == "adm_view":
            top = players.find().sort("current_q", -1).limit(10)
            txt = "🏆 *CLASSIFICA*\n\n" + "\n".join([f"{i+1}. @{x.get('username')} - Liv {x.get('current_q')+1}" for i, x in enumerate(top)])
            await query.message.reply_text(txt or "Nessun dato.", parse_mode="Markdown")
        elif data == "adm_conf_db":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 SÌ, ELIMINA TUTTO", callback_data="adm_drop_db")]])
            await query.edit_message_text("⚠️ Sicuro di voler piallare il database?", reply_markup=kb, parse_mode="Markdown")
        elif data == "adm_drop_db":
            client.drop_database('quiz_milionario')
            await query.edit_message_text("💥 Database eliminato.")
        elif data == "adm_del_class":
            players.delete_many({})
            await query.edit_message_text("✅ Classifica resettata.")
        await query.answer(); return

    # Logica di Gioco
    p = players.find_one({"user_id": user_id})
    if not p or (p.get("game_over") and username not in ADMIN_USERS):
        await query.answer("Partita finita!"); return

    idx = p["current_q"]
    q = QUESTIONS[idx]

    if data.startswith("ans_"):
        await pulisci_messaggi_aiuto(user_id, context)
        scelta = data.split("_")[1]
        if scelta == q["c"]:
            if idx == 14:
                for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
                await query.edit_message_text("🏆 *CONGRATULAZIONI MILIONARIO!* 🏆")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await invia_domanda(update, context, idx + 1)
        else:
            for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
            await query.edit_message_text(f"❌ *SBAGLIATO!* Era la risposta {q['c']}.")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    
    elif data.startswith("h_"):
        h_type = data.split("_")[1]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{h_type}": False}})
        if h_type == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, idx, rimosse=rimosse)
        else:
            txt = f"📊 *Pubblico*: {q['c']}" if h_type == "pub" else f"📞 *Telefono*: 'Per me è la {q['c']}'"
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
    
    await query.answer()

def main():
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(handle_callback))
    print("Bot online!")
    application.run_polling()

if __name__ == "__main__":
    main()
