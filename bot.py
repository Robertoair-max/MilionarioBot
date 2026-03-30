import os
import random
import urllib.parse
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERS = ["Lady_unknow", "Tuc0Pacific0"]

# Connessione a MongoDB
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
def logica_pubblico(idx, corretta):
    prob_corretta = max(30, 90 - (idx * 4))
    perc = {k: 0 for k in ["A", "B", "C", "D"]}
    perc[corretta] = random.randint(prob_corretta, min(100, prob_corretta + 10))
    rimanente = 100 - perc[corretta]
    errate = [k for k in perc if k != corretta]
    random.shuffle(errate)
    p1 = random.randint(0, rimanente)
    p2 = random.randint(0, max(0, rimanente - p1))
    perc[errate[0]], perc[errate[1]], perc[errate[2]] = p1, p2, rimanente - p1 - p2
    return perc

def logica_telefonata(idx, corretta):
    affidabilita = max(10, 85 - (idx * 5))
    if random.randint(0, 100) <= affidabilita:
        return f"📞 'Sono certo, la risposta è la {corretta}!'"
    elif random.randint(0, 100) <= 30:
        errata = random.choice([k for k in ["A", "B", "C", "D"] if k != corretta])
        return f"📞 'Mmm... sono indeciso tra la {corretta} e la {errata}...'"
    return "📞 'Mi spiace, questa proprio non la so!'"

# --- GESTIONE CORE ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = players.find_one({"user_id": user.id})
    if player and player.get("game_over") and user.username not in ADMIN_USERS:
        await update.message.reply_text(f"⛔️ Hai già giocato!\nSolo @Lady_unknow e @Tuc0Pacific0 possono giocare sempre.")
        return
    init = {"user_id": user.id, "username": user.username, "current_q": 0, "game_over": False, "h": {"5050": True, "pub": True, "tel": True}}
    players.update_one({"user_id": user.id}, {"$set": init}, upsert=True)
    await invia_domanda(update, context, 0)

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    q = QUESTIONS[idx]
    
    txt = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    for k, v in q['o'].items():
        if rimosse and k in rimosse: continue
        txt += f"*{k}*: {v}\n"
    
    # Bottoni risposte (nasconde quelle rimosse dal 5050)
    row1 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["A", "B"] if not (rimosse and k in rimosse)]
    row2 = [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["C", "D"] if not (rimosse and k in rimosse)]
    
    # Bottoni aiuti (mostra solo quelli disponibili)
    row_h = []
    if p["h"]["5050"]: row_h.append(InlineKeyboardButton("50:50 🎭", callback_data="h_5050"))
    if p["h"]["pub"]: row_h.append(InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"))
    if p["h"]["tel"]: row_h.append(InlineKeyboardButton("Tel 📞", callback_data="h_tel"))
    
    kb = [row1, row2, row_h]
    if update.message: await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup([r for r in kb if r]), parse_mode="Markdown")
    else: await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([r for r in kb if r]), parse_mode="Markdown")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id, username = query.from_user.id, query.from_user.username
    p = players.find_one({"user_id": user_id})
    if not p or (p.get("game_over") and username not in ADMIN_USERS and not query.data.startswith("adm_")): return
    
    data, idx = query.data, p["current_q"]
    q = QUESTIONS[idx]

    if data.startswith("ans_"):
        if data.split("_")[1] == q["c"]:
            if idx == 14:
                await query.edit_message_text("🏆 *HAI VINTO IL MILIONE!* 🏆", parse_mode="Markdown")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await query.answer("Esatto! ✅")
                await invia_domanda(update, context, idx + 1)
        else:
            await query.edit_message_text(f"❌ *SBAGLIATO!*\nEra la {q['c']}. Gioco finito.", parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})

    elif data.startswith("h_"):
        tipo = data.split("_")[1]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, idx, rimosse=rimosse)
        elif tipo == "pub":
            res = logica_pubblico(idx, q["c"])
            await query.message.reply_text("📊 *Pubblico*:\n" + "\n".join([f"{k}: {v}%" for k, v in res.items()]), parse_mode="Markdown")
            await invia_domanda(update, context, idx)
        elif tipo == "tel":
            await query.message.reply_text(logica_telefonata(idx, q["c"]))
            await invia_domanda(update, context, idx)
        await query.answer()

    elif data.startswith("adm_"):
        if username not in ADMIN_USERS: return
        if data == "adm_view":
            top = players.find().sort("current_q", -1).limit(10)
            txt = "🏆 *CLASSIFICA*\n\n" + "\n".join([f"{i+1}. @{x.get('username')} - Liv {x.get('current_q')+1}" for i, x in enumerate(top)])
            await query.message.reply_text(txt or "Nessun dato.", parse_mode="Markdown")
        elif data == "adm_conf":
            kb = [[InlineKeyboardButton("✅ SÌ", callback_data="adm_del"), InlineKeyboardButton("❌ NO", callback_data="adm_view")]]
            await query.edit_message_text("⚠️ Vuoi resettare la classifica?", reply_markup=InlineKeyboardMarkup(kb))
        elif data == "adm_del":
            players.delete_many({})
            await query.edit_message_text("✅ Dati cancellati.")
        await query.answer()

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", lambda u, c: admin_panel(u, c) if u.effective_user.username in ADMIN_USERS else None))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

async def admin_panel(update, context):
    kb = [[InlineKeyboardButton("📊 Vedi Classifica", callback_data="adm_view")], [InlineKeyboardButton("🗑 Cancella Classifica", callback_data="adm_conf")]]
    await update.message.reply_text("🛠 *PANNELLO ADMIN*", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
