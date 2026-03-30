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
# Uso minuscolo per un confronto più sicuro
ADMIN_USERS = ["@Lady_unknow", "@Tuc0Pacific0"] 
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

# --- LOGICA AIUTI ---
def genera_pubblico(corretta, idx):
    prob_corretta = max(35, 85 - (idx * 4))
    opzioni = ["A", "B", "C", "D"]
    voti = {corretta: random.randint(int(prob_corretta), 95)}
    rimanente = 100 - voti[corretta]
    altre = [k for k in opzioni if k != corretta]
    random.shuffle(altre)
    
    v1 = random.randint(0, rimanente)
    voti[altre[0]] = v1 # Corretto l'indice
    rimanente -= v1
    v2 = random.randint(0, rimanente)
    voti[altre[1]] = v2 # Corretto l'indice
    voti[altre[2]] = 100 - (voti[corretta] + v1 + v2) # Corretto l'indice
    
    res = "📊 *Risultato del pubblico:*\n\n"
    for k in sorted(voti.keys()):
        res += f"*{k}*: {voti[k]}%\n"
    return res

def genera_tel(corretta, idx):
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
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    players.update_one({"user_id": user.id}, {"$set": {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}}, upsert=True)
    benvenuto = "🏆 *BENVENUTO AL MILIONARIO!*\n\n⏳ Hai *60 secondi* per rispondere.\n🎭 *50:50*: Toglie 2 errori.\n👥 *Pubblico*: Vota la risposta.\n📞 *Tel*: Chiama un amico.\n\nPronto?"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Inizia il Quiz 🚀", callback_data="game_start")]])
    await update.message.reply_text(benvenuto, reply_markup=kb, parse_mode="Markdown")

async def callback_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = (query.from_user.username or "").lower() # Gestione case-insensitive
    p = players.find_one({"user_id": user_id})
    if not p: return
    data = query.data

    # Logica Admin (Controllo stringa corretto)
    if data.startswith("adm_") and username in ADMIN_USERS:
        if data == "adm_view":
            top = list(players.find().sort("current_q", -1).limit(10))
            txt = "🏆 *Classifica*\n\n" + "\n".join([f"{i+1}. @{x.get('username')} - Liv {x.get('current_q')+1}" for i, x in enumerate(top)])
            # Se la classifica è vuota
            if not top: txt = "🏆 *Classifica*\n\nNessun giocatore registrato."
            await query.message.reply_text(txt, parse_mode="Markdown")
        elif data == "adm_conf_reset":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Conferma Reset", callback_data="adm_reset_class")], [InlineKeyboardButton("❌ Annulla", callback_data="adm_panel")]])
            await query.edit_message_text("⚠️ Resettare la classifica?", reply_markup=kb)
        elif data == "adm_reset_class":
            players.delete_many({}); await query.edit_message_text("✅ Classifica resettata.")
        elif data == "adm_conf_db":
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔥 Conferma Eliminazione", callback_data="adm_drop_db")], [InlineKeyboardButton("❌ Annulla", callback_data="adm_panel")]])
            await query.edit_message_text("⚠️ Eliminare il database?", reply_markup=kb)
        elif data == "adm_drop_db":
            client.drop_database('quiz_milionario'); await query.edit_message_text("💥 DB Eliminato.")
        elif data == "adm_panel":
            await admin_panel_msg(query)
        await query.answer(); return

    # Logica Gioco
    if data == "game_start":
        await invia_domanda(update, context, 0)
    elif data.startswith("ans_"):
        ans = data.replace("ans_", "")
        q = QUESTIONS[p["current_q"]]
        await pulisci_aiuti(user_id, context)
        if ans == q["c"]:
            if p["current_q"] == 14:
                await query.edit_message_text("🏆 *MILIONARIO!*")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await invia_domanda(update, context, p["current_q"] + 1)
        else:
            await query.edit_message_text(f"❌ *Sbagliato!* Era {q['c']}.")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    elif data.startswith("h_"):
        tipo = data.replace("h_", "")
        q = QUESTIONS[p["current_q"]]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, p["current_q"], rimosse)
        else:
            txt = genera_pubblico(q["c"], p["current_q"]) if tipo == "pub" else genera_tel(q["c"], p["current_q"])
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
    await query.answer()

async def admin_panel_msg(q_or_u):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Vedi Classifica", callback_data="adm_view")],[InlineKeyboardButton("Reset Classifica", callback_data="adm_conf_reset")],[InlineKeyboardButton("Elimina Database", callback_data="adm_conf_db")]])
    if isinstance(q_or_u, Update): await q_or_u.message.reply_text("🛠 *Pannello Admin*", reply_markup=kb, parse_mode="Markdown")
    else: await q_or_u.edit_message_text("🛠 *Pannello Admin*", reply_markup=kb, parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = (update.effective_user.username or "").lower()
    if username in ADMIN_USERS: await admin_panel_msg(update)

# --- SERVER ---
server = Flask(__name__)

@server.route('/')
def home():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    server.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_logic))
    app.run_polling(drop_pending_updates=True)
