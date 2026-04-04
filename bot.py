import os
import sys
import random
import threading
import logging
import time
import asyncio
from flask import Flask
from pymongo import MongoClient, DESCENDING
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- LOGGING ---
logging.basicConfig(level=logging.ERROR)
# Disabilita i log di Flask (Werkzeug) per risparmiare CPU e pulire la console
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# ID Admin: Inserire qui gli ID abilitati
ADMIN_IDS = [17707024030, 15838296578]
TEMPO_RISPOSTA = 60

# Inizializzazione MongoDB
client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = client.quiz_milionario
players = db.players

# --- DATABASE DOMANDE ---
QUESTIONS = [
    {"q": "Qual è il colore del cielo in una giornata di sole?", "o": {"A": "Verde", "B": "Rosso", "C": "Azzurro", "D": "Giallo"}, "c": "C"},
    {"q": "Quante zampe ha un ragno?", "o": {"A": "4", "B": "6", "C": "8", "D": "10"}, "c": "C"},
    {"q": "Qual è la capitale d'Italia?", "o": {"A": "Milano", "B": "Roma", "C": "Napoli", "D": "Torino"}, "c": "B"},
    {"q": "Come si chiama il giovane burattino di legno di Collodi?", "o": {"A": "Lucignolo", "B": "Geppetto", "C": "Pinocchio", "D": "Grillo"}, "c": "C"},
    {"q": "Quale animale è noto per la sua lentaggine?", "o": {"A": "Lepre", "B": "Lumaca", "C": "Ghepardo", "D": "Lupo"}, "c": "B"},

    {"q": "In quale continente si trova il fiume Rio delle Amazzoni?", "o": {"A": "Africa", "B": "Asia", "C": "Sud America", "D": "Australia"}, "c": "C"},
    {"q": "Quale pianeta è famoso per i suoi grandi anelli visibili?", "o": {"A": "Marte", "B": "Nettuno", "C": "Saturno", "D": "Urano"}, "c": "C"},
    {"q": "Chi è l'autore della celebre opera 'La Gioconda'?", "o": {"A": "Michelangelo", "B": "Raffaello", "C": "Leonardo da Vinci", "D": "Caravaggio"}, "c": "C"},
    {"q": "Qual è il metallo più leggero esistente in natura?", "o": {"A": "Oro", "B": "Litio", "C": "Ferro", "D": "Piombo"}, "c": "B"},
    {"q": "In che anno è scoppiata la Prima Guerra Mondiale?", "o": {"A": "1914", "B": "1918", "C": "1939", "D": "1890"}, "c": "A"},

    {"q": "Qual è la capitale dell'Australia?", "o": {"A": "Sydney", "B": "Melbourne", "C": "Canberra", "D": "Perth"}, "c": "C"},
    {"q": "Quale di questi elementi ha come simbolo chimico 'K'?", "o": {"A": "Cripton", "B": "Potassio", "C": "Calcio", "D": "Cobalto"}, "c": "B"},
    {"q": "In quale anno è stato pubblicato il romanzo 'I promessi sposi' (edizione definitiva)?", "o": {"A": "1821", "B": "1827", "C": "1840", "D": "1850"}, "c": "C"},
    {"q": "Chi fu il primo presidente della Repubblica Italiana?", "o": {"A": "Enrico De Nicola", "B": "Luigi Einaudi", "C": "Alcide De Gasperi", "D": "Sandro Pertini"}, "c": "A"},
    {"q": "Quale particella atomica ha carica elettrica positiva?", "o": {"A": "Elettrone", "B": "Neutrone", "C": "Protone", "D": "Fotone"}, "c": "C"}
]

# --- UTILS ---
def genera_pubblico(corretta, idx):
    prob = max(35, 85 - (idx * 4))
    opzioni = ["A", "B", "C", "D"]
    voti = {corretta: random.randint(int(prob), 95)}
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
    if random.randint(1, 100) <= aff: return f"📞 'Pronto? Sì! La risposta è la *{corretta}*!'"
    return "📞 'Pronto? Non ne ho idea, mi spiace!'"

async def pulisci_aiuti(user_id, context):
    p = players.find_one({"user_id": user_id})
    if p and p.get("temp_msg_ids"):
        for m_id in p["temp_msg_ids"]:
            try: await context.bot.delete_message(chat_id=user_id, message_id=m_id)
            except: pass
        players.update_one({"user_id": user_id}, {"$set": {"temp_msg_ids": []}})

async def timeout_scaduto(context: ContextTypes.DEFAULT_TYPE):
    user_id = context.job.user_id
    p = players.find_one({"user_id": user_id})
    livello = p.get("current_q", 0) if p else 0
    players.update_one({"user_id": user_id}, {"$set": {"game_over": True}}, upsert=True)
    await pulisci_aiuti(user_id, context)
    try: await context.bot.send_message(user_id, f"⏰ *TEMPO SCADUTO!*\n🎯 Risposte corrette: *{livello}*", parse_mode="Markdown")
    except: pass

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    if not p or idx >= len(QUESTIONS): return
    q = QUESTIONS[idx]
    
    if context.job_queue:
        for j in context.job_queue.get_jobs_by_name(str(user_id)): j.schedule_removal()
        context.job_queue.run_once(timeout_scaduto, TEMPO_RISPOSTA, user_id=user_id, name=str(user_id))
    
    txt = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    for k, v in q['o'].items():
        if rimosse and k in rimosse: continue
        txt += f"*{k}*: {v}\n"
    txt += f"[\u200c](http://{time.time()})"

    r1 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["A", "B"] if not (rimosse and k in rimosse)]
    r2 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["C", "D"] if not (rimosse and k in rimosse)]
    rh = []
    if p["h"].get("5050"): rh.append(InlineKeyboardButton("50:50 🎭", callback_data="h_5050"))
    if p["h"].get("pub"): rh.append(InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"))
    if p["h"].get("tel"): rh.append(InlineKeyboardButton("Tel 📞", callback_data="h_tel"))
    
    kb = InlineKeyboardMarkup([r1, r2, rh])
    try:
        if update.callback_query: await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
        else: await update.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")
    except: pass

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    p = players.find_one({"user_id": user.id})
    if p and p.get("game_over") and user.id not in ADMIN_IDS:
        await update.message.reply_text("🚫 *Hai già giocato!*\nLa tua partecipazione è stata registrata.", parse_mode="Markdown")
        return

    players.update_one({"user_id": user.id}, {"$set": {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}}, upsert=True)
    
    regole = (
        "🏆 *BENVENUTO AL CHI VUOL ESSERE MILIONARIO!*\n\n"
        "📜 *REGOLE DEL GIOCO:*\n"
        "• Hai **15 domande** per arrivare alla gloria.\n"
        "• Hai **60 secondi** per rispondere a ogni domanda.\n"
        "• Se sbagli o scade il tempo, il gioco finisce.\n\n"
        "🎭 *AIUTI DISPONIBILI (1 solo uso):*\n"
        "• **50:50**: Elimina due risposte errate.\n"
        "• **Pubblico**: Chiedi il parere della sala.\n"
        "• **Telefonata**: Chiama un amico per un consiglio.\n\n"
        "Sei pronto a sfidare la sorte?"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Gioca 🚀", callback_data="game_start")]])
    await update.message.reply_text(regole, reply_markup=kb, parse_mode="Markdown")

async def callback_logic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer() 

    p = players.find_one({"user_id": user_id})
    if not p and not data.startswith("adm_"): return

    if data == "game_start": 
        await invia_domanda(update, context, 0)
    elif data.startswith("ans_"):
        if p.get("game_over") and user_id not in ADMIN_IDS: return
        ans = data.replace("ans_", ""); q = QUESTIONS[p["current_q"]]; await pulisci_aiuti(user_id, context)
        if ans == q["c"]:
            nuovo = p["current_q"] + 1
            players.update_one({"user_id": user_id}, {"$set": {"current_q": nuovo}})
            if nuovo == 15:
                if context.job_queue: [j.schedule_removal() for j in context.job_queue.get_jobs_by_name(str(user_id))]
                await query.edit_message_text("🏆 *MILIONARIO!*\n🎯 Risposte corrette: *15*")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else: await invia_domanda(update, context, nuovo)
        else:
            if context.job_queue: [j.schedule_removal() for j in context.job_queue.get_jobs_by_name(str(user_id))]
            await query.edit_message_text(f"❌ Era {q['c']}.\n🎯 Livello: *{p['current_q']}*")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
    elif data.startswith("h_"):
        tipo = data.replace("h_", "")
        if not p["h"].get(tipo): return 
        q_attuale = QUESTIONS[p["current_q"]]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q_attuale["c"]], 2)
            await invia_domanda(update, context, p["current_q"], rimosse)
        else:
            txt = genera_pubblico(q_attuale["c"], p["current_q"]) if tipo == "pub" else genera_tel(q_attuale["c"], p["current_q"])
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
            await invia_domanda(update, context, p["current_q"])
    elif data.startswith("adm_"):
        if user_id not in ADMIN_IDS: return
        if data == "adm_view":
            top = list(players.find({}, {"username": 1, "current_q": 1, "user_id": 1}).sort("current_q", -1).limit(50))
            txt = "🏆 *CLASSIFICA*\n\n"
            for i, x in enumerate(top):
                name = f"@{x.get('username')}" if x.get('username') else f"ID:{x['user_id']}"
                txt += f"{i+1}. {name} — Risposte: *{x.get('current_q', 0)}*\n"
            await query.edit_message_text(txt or "Nessun dato.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Indietro", callback_data="adm_panel")]]), parse_mode="Markdown")
        elif data == "adm_conf_reset":
            await query.edit_message_text("⚠️ Reset Classifica?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Sì", callback_data="adm_reset_class")], [InlineKeyboardButton("❌ No", callback_data="adm_panel")]]))
        elif data == "adm_reset_class":
            players.update_many({}, {"$set": {"current_q": 0, "game_over": True}})
            await query.edit_message_text("✅ Reset fatto.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Indietro", callback_data="adm_panel")]]))
        elif data == "adm_conf_db":
            await query.edit_message_text("⚠️ Reset Database?", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Sì", callback_data="adm_db_drop")], [InlineKeyboardButton("❌ Annulla", callback_data="adm_panel")]]), parse_mode="Markdown")
        elif data == "adm_db_drop":
            players.drop()
            await query.edit_message_text("✅ Reset fatto.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Indietro", callback_data="adm_panel")]]), parse_mode="Markdown")
        elif data == "adm_panel": await admin_panel_msg(query)

async def admin_panel_msg(q_or_u):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Classifica", callback_data="adm_view")],
        [InlineKeyboardButton("🧹 Reset Classifica", callback_data="adm_conf_reset")],
        [InlineKeyboardButton("🧹 Reset Database", callback_data="adm_conf_db")]
    ])
    txt = "🛠 *Pannello Admin*"
    if isinstance(q_or_u, Update): await q_or_u.message.reply_text(txt, reply_markup=kb, parse_mode="Markdown")
    else: await q_or_u.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id in ADMIN_IDS: await admin_panel_msg(update)

# --- SERVER WEB (Struttura identica al secondo codice) ---
webapp = Flask(__name__)

@webapp.route('/')
def health():
    return "OK", 200

def run_flask():
    port = int(os.environ.get('PORT', 10000))
    try:
        webapp.run(host='0.0.0.0', port=port, threaded=True, debug=False, use_reloader=False)
    except Exception as e:
        pass

# --- MAIN ---
if __name__ == "__main__":
    # Avvio del thread Flask prima del bot
    threading.Thread(target=run_flask, daemon=True).start()
    time.sleep(2)
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CallbackQueryHandler(callback_logic))
    
    players.create_index([("current_q", DESCENDING)])
    app.run_polling(drop_pending_updates=True)
