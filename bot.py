import os
import random
import threading
from flask import Flask
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERS = ["Lady_unknow", "Tuc0Pacific0"]
TEMPO_RISPOSTA = 60 

# Connessione sicura a MongoDB
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client.quiz_milionario
    players = db.players
except Exception as e:
    print(f"ERRORE MONGODB: {e}")

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

# --- LOGICA AIUTI ---
def genera_percentuali_pubblico(corretta, idx):
    prob_corretta = max(35, 85 - (idx * 4))
    altre = [k for k in ["A", "B", "C", "D"] if k != corretta]
    voti = {corretta: random.randint(int(prob_corretta), 100)}
    rimanente = 100 - voti[corretta]
    random.shuffle(altre)
    v1 = random.randint(0, rimanente)
    voti[altre] = v1
    rimanente -= v1
    v2 = random.randint(0, rimanente)
    voti[altre] = v2
    voti[altre] = 100 - (voti[corretta] + v1 + v2)
    res = "📊 *Risultato del pubblico:*\n"
    for k in sorted(voti.keys()):
        res += f"*{k}*: {voti[k]}%\n"
    return res

def genera_dialogo_telefonata(corretta, idx):
    affidabilita = max(30, 90 - (idx * 5))
    sorte = random.randint(1, 100)
    errata = random.choice([k for k in ["A", "B", "C", "D"] if k != corretta])
    if sorte <= affidabilita:
        return f"📞 'Pronto? Sì! Guarda, ne sono quasi certo... la risposta è la *{corretta}*!'"
    elif sorte <= affidabilita + 25:
        return f"📞 'Mmm... sono indeciso tra la *{corretta}* e la *{errata}*, ma punterei sulla prima...'"
    else:
        return "📞 'Pronto? No, guarda, questa è davvero difficile... non ne ho idea!'"

# --- UTILS ---
async def pulisci_messaggi_aiuto(user_id, context):
    p = players.find_one({"user_id": user_id})
    if p and p.get("temp_msg_ids"):
        for m_id in p["temp_msg_ids"]:
            try: await context.bot.delete_message(chat_id=user_id, message_id=m_id)
            except: pass
        players.update_one({"user_id": user_id}, {"$set": {"temp_msg_ids": []}})

async def timeout_scaduto(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    await pulisci_messaggi_aiuto(user_id, context)
    try: await context.bot.send_message(user_id, "⏰ *TEMPO SCADUTO!*\nIl gioco finisce qui.", parse_mode="Markdown")
    except: pass

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
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
    await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    p_exist = players.find_one({"user_id": user.id})
    if p_exist and p_exist.get("game_over") and user.username not in ADMIN_USERS:
        await update.message.reply_text("⛔️ Hai già giocato!")
        return
    
    init = {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}
    players.update_one({"user_id": user.id}, {"$set": init}, upsert=True)
    
    benvenuto = (
        "🏆 *BENVENUTO AL MILIONARIO!*\n\n"
        "⏳ Hai *60 secondi* per rispondere a ogni domanda.\n"
        "🎭 *50:50*: Toglie due risposte errate.\n"
        "👥 *Pubblico*: Vota la risposta (attenzione ai livelli alti!).\n"
        "📞 *Tel*: Chiama un amico per un consiglio.\n\n"
        "Buona fortuna!"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Inizia il Quiz 🚀", callback_data="game_start")]])
    await update.message.reply_text(benvenuto, reply_markup=kb, parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id, username = query.from_user.id, query.from_user.username
    p = players.find_one({"user_id": user_id})
    if not p: return
    data = query.data

    # Gestione Avvio Quiz
    if data == "game_start":
        await invia_domanda(update, context, 0)
        await query.answer()
        return

    # Azioni Admin
    if data.startswith("adm_") and username in ADMIN_USERS:
        if data == "adm_view":
            top = list(players.find().sort("current_q", -1).limit(10))
            txt = "🏆 *Classifica*\n\n" + "\n".join([f"{i+1}. @{x.get('username')} - Liv {x.get('current_q')+1}" for i, x in enumerate(top)])
            await query.message.reply_text(txt or "Nessun dato.", parse_mode="Markdown")
        elif data == "adm_conf_reset":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Conferma Reset", callback_data="adm_reset_class")], [InlineKeyboardButton("❌ Annulla", callback_data="adm_panel")]])
            await query.edit_message_text("⚠️ Resettare la classifica?", reply_markup=kb)
        elif data == "adm_reset_class":
            players.delete_many({}); await query.edit_message_text("✅ Classifica resettata.")
        elif data == "adm_conf_db":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Conferma Drop DB", callback_data="adm_drop_db")], [InlineKeyboardButton("❌ Annulla", callback_data="adm_panel")]])
            await query.edit_message_text("⚠️ ELIMINARE TUTTO IL DB?", reply_markup=kb)
        elif data == "adm_drop_db":
            client.drop_database('quiz_milionario'); await query.edit_message_text("💥 DB Eliminato.")
        elif data == "adm_panel":
            await admin_panel_msg(query)
        await query.answer(); return

    # Logica Gioco
    idx = p["current_q"]
    q = QUESTIONS[idx]

    if data.startswith("ans_"):
        scelta = data.replace("ans_", "")
        await pulisci_messaggi_aiuto(user_id, context)
        if scelta == q["c"]:
            if idx == 14:
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
                await query.edit_message_text("🏆 *MILIONARIO!*")
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await invia_domanda(update, context, idx + 1)
        else:
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            await query.edit_message_text(f"❌ *Sbagliato!* Era la risposta {q['c']}.")
    
    elif data.startswith("h_"):
        tipo = data.replace("h_", "")
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            errate = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, idx, rimosse=errate)
        elif tipo == "pub":
            msg = await context.bot.send_message(user_id, genera_percentuali_pubblico(q['c'], idx), parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": msg.message_id}})
        elif tipo == "tel":
            msg = await context.bot.send_message(user_id, genera_dialogo_telefonata(q['c'], idx), parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": msg.message_id}})
    await query.answer()

async def admin_panel_msg(query_or_update):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Vedi Classifica", callback_data="adm_view")],[InlineKeyboardButton("Reset Classifica", callback_data="adm_conf_reset")],[InlineKeyboardButton("Elimina Database", callback_data="adm_conf_db")]])
    if isinstance(query_or_update, Update): await query_or_update.message.reply_text("🛠 *Pannello Admin*", reply_markup=kb, parse_mode="Markdown")
    else: await query_or_update.edit_message_text("🛠 *Pannello Admin*", reply_markup=kb, parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username in ADMIN_USERS: await admin_panel_msg(update)

# --- FLASK SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running", 200

def run_flask():
    # Render usa la variabile PORT, se manca usiamo 10000
    port = int(os.environ.get("PORT", 10000))
    # Importante: use_reloader=False evita che il thread parta due volte
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# --- MAIN ---
if __name__ == "__main__":
    # Avviamo il server web in un thread separato
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    
    print("Server Flask avviato... Inizializzazione Bot Telegram.")
    
    # Avvia Telegram Bot
    application = Application.builder().token(TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_cmd))
    application.add_handler(CallbackQueryHandler(handle_callback))
    
    # Avvio polling
    print("Bot pronto al polling.")
    application.run_polling(drop_pending_updates=True)
