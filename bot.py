import os
import random
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- CONFIGURAZIONE ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_USERS = ["Lady_unknow", "Tuc0Pacific0"]

client = MongoClient(MONGO_URI)
db = client.quiz_milionario
players = db.players

# --- DATABASE DOMANDE (15 LIVELLI) ---
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
    {"q": "Chi è l'autore di 'Promessi Sposi'?", "o": {"A": "Pascoli", "B": "Manzoni", "C": "Pirandello", "D": "Svevo"}, "c": "B"},
    {"q": "Qual è la velocità della luce (circa)?", "o": {"A": "300.000 km/s", "B": "150.000 km/s", "C": "1.000.000 km/s", "D": "50.000 km/s"}, "c": "A"},
    {"q": "Quale paese ha vinto più Mondiali di calcio?", "o": {"A": "Italia", "B": "Germania", "C": "Brasile", "D": "Argentina"}, "c": "C"},
    {"q": "Chi fu il primo uomo sulla Luna?", "o": {"A": "Yuri Gagarin", "B": "Buzz Aldrin", "C": "Neil Armstrong", "D": "Michael Collins"}, "c": "C"},
]

# --- LOGICA AIUTI ---
def logica_pubblico(idx, corretta):
    # L'affidabilità scende col tempo
    prob_corretta = max(30, 90 - (idx * 4))
    perc = {k: 0 for k in ["A", "B", "C", "D"]}
    perc[corretta] = random.randint(prob_corretta, min(100, prob_corretta + 15))
    rimanente = 100 - perc[corretta]
    errate = [k for k in perc if k != corretta]
    random.shuffle(errate)
    p1 = random.randint(0, rimanente)
    p2 = random.randint(0, rimanente - p1)
    p3 = rimanente - p1 - p2
    for i, e in enumerate(errate):
        perc[e] = [p1, p2, p3][i]
    return perc

def logica_telefonata(idx, corretta):
    affidabilita = max(10, 85 - (idx * 5))
    roll = random.randint(0, 100)
    if roll <= affidabilita:
        return f"📞 'Sono quasi certo che sia la {corretta}!'"
    elif roll <= affidabilita + 25:
        errata = random.choice([k for k in ["A", "B", "C", "D"] if k != corretta])
        scelte = [corretta, errata]
        random.shuffle(scelte)
        return f"📞 'Mah... sono indeciso tra la {scelte[0]} e la {scelte[1]}...'"
    else:
        return "📞 'Mi dispiace, proprio non lo so...'"

# --- GESTIONE BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    player = players.find_one({"user_id": user.id})
    
    if player and player.get("game_over") and user.username not in ADMIN_USERS:
        await update.message.reply_text("⛔️ Hai già esaurito il tuo tentativo!")
        return

    init = {
        "user_id": user.id, "username": user.username, "current_q": 0, "game_over": False,
        "h": {"5050": True, "pub": True, "tel": True}
    }
    players.update_one({"user_id": user.id}, {"$set": init}, upsert=True)
    await invia_domanda(update, context, 0)

async def invia_domanda(update, context, idx):
    q = QUESTIONS[idx]
    testo = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    for k, v in q['o'].items():
        testo += f"*{k}*: {v}\n"
    
    kb = [
        [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["A", "B"]],
        [InlineKeyboardButton(f"Risp. {k}", callback_data=f"ans_{k}") for k in ["C", "D"]],
        [InlineKeyboardButton("50:50 🎭", callback_data="h_5050"),
         InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"),
         InlineKeyboardButton("Tel 📞", callback_data="h_tel")]
    ]
    
    if update.message:
        await update.message.reply_text(testo, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(testo, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def handle_interaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    p = players.find_one({"user_id": user_id})
    if not p or (p.get("game_over") and query.from_user.username not in ADMIN_USERS):
        return

    idx = p["current_q"]
    q = QUESTIONS[idx]
    data = query.data

    if data.startswith("ans_"):
        scelta = data.split("_")[1]
        if scelta == q["c"]:
            if idx == 14:
                await query.edit_message_text("🏆 *COMPLIMENTI! HAI VINTO IL MILIONE!* 🏆", parse_mode="Markdown")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await query.answer("Corretto! ✅")
                await invia_domanda(update, context, idx + 1)
        else:
            await query.edit_message_text(f"❌ *SBAGLIATO!*\nLa risposta corretta era la {q['c']}.\nIl gioco finisce qui.", parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})

    elif data.startswith("h_"):
        tipo = data.split("_")[1]
        if not p["h"].get(tipo):
            await query.answer("⚠️ Aiuto già utilizzato!", show_alert=True)
            return
        
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            errate = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await query.message.reply_text(f"🎭 *50:50*: Due risposte errate rimosse. (Non sono la {errate[0]} né la {errate[1]})", parse_mode="Markdown")
        elif tipo == "pub":
            perc = logica_pubblico(idx, q["c"])
            txt = "📊 *Risultato Pubblico*:\n" + "\n".join([f"{k}: {v}%" for k, v in perc.items()])
            await query.message.reply_text(txt, parse_mode="Markdown")
        elif tipo == "tel":
            msg = logica_telefonata(idx, q["c"])
            await query.message.reply_text(msg)
        await query.answer()

if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_interaction))
    app.run_polling()
