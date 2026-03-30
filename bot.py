# ... (Import e QUESTIONS restano invariati)

TEMPO_RISPOSTA = 60 # Aggiornato a 60 secondi

# --- LOGICA DI GIOCO ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # Controllo se ha già giocato
    if players.find_one({"user_id": user.id, "game_over": True}) and user.username not in ADMIN_USERS:
        await update.message.reply_text("⛔️ Hai già giocato! Solo gli admin possono rigiocare.")
        return

    regole = (
        "🏆 *BENVENUTO AL QUIZ MILIONARIO!*\n\n"
        "📖 *REGOLE:*\n"
        "1. Hai 15 domande totali.\n"
        "2. Hai *60 secondi* per rispondere a ogni domanda.\n"
        "3. Hai 3 aiuti: 50:50, Pubblico e Telefonata.\n"
        "4. Se sbagli o scade il tempo, il gioco finisce.\n\n"
        "Clicca il tasto qui sotto quando sei pronto a iniziare!"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 INIZIA IL GIOCO", callback_data="game_start")]])
    await update.message.reply_text(regole, reply_markup=kb, parse_mode="Markdown")

async def invia_domanda(update, context, idx, rimosse=None):
    user_id = update.effective_user.id
    p = players.find_one({"user_id": user_id})
    q = QUESTIONS[idx]
    
    # Reset e avvio Timer
    for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
    context.job_queue.run_once(timeout_scaduto, TEMPO_RISPOSTA, user_id=user_id, name=str(user_id))
    
    txt = f"❓ *DOMANDA {idx+1}/15*\n\n{q['q']}\n\n"
    # Costruzione tastiera risposte
    buttons = []
    for k, v in q['o'].items():
        if rimosse and k in rimosse: continue
        buttons.append(InlineKeyboardButton(f"{k}: {v}", callback_data=f"ans_{k}"))
    
    # Layout 2x2 per risposte + riga aiuti
    row1, row2 = buttons[:2], buttons[2:]
    row_h = []
    if p["h"]["5050"]: row_h.append(InlineKeyboardButton("50:50 🎭", callback_data="h_5050"))
    if p["h"]["pub"]: row_h.append(InlineKeyboardButton("Pubblico 👥", callback_data="h_pub"))
    if p["h"]["tel"]: row_h.append(InlineKeyboardButton("Tel 📞", callback_data="h_tel"))
    
    kb = InlineKeyboardMarkup([row1, row2, row_h])
    
    # Se è la prima domanda (da callback) o successiva
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=kb, parse_mode="Markdown")
    else:
        await context.bot.send_message(user_id, txt, reply_markup=kb, parse_mode="Markdown")

# --- CALLBACK HANDLER AGGIORNATO ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username
    data = query.data
    
    # 1. Inizio effettivo del gioco
    if data == "game_start":
        init = {"user_id": user_id, "username": username, "current_q": 0, "game_over": False, 
                "h": {"5050": True, "pub": True, "tel": True}, "temp_msg_ids": []}
        players.update_one({"user_id": user_id}, {"$set": init}, upsert=True)
        await invia_domanda(update, context, 0)
        await query.answer()
        return

    p = players.find_one({"user_id": user_id})
    if not p or (p.get("game_over") and username not in ADMIN_USERS):
        await query.answer("Sessione scaduta o partita terminata.", show_alert=True)
        return

    idx = p["current_q"]
    q = QUESTIONS[idx]

    # 2. Gestione Risposte
    if data.startswith("ans_"):
        await pulisci_messaggi_aiuto(user_id, context)
        scelta = data.split("_")[1] # Prende la lettera (A, B, C, D)
        
        if scelta == q["c"]:
            if idx == 14:
                for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
                await query.edit_message_text("🏆 *MILIONARIO!* Hai completato la scalata!")
                players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})
            else:
                players.update_one({"user_id": user_id}, {"$inc": {"current_q": 1}})
                await invia_domanda(update, context, idx + 1)
        else:
            for job in context.job_queue.get_jobs_by_name(str(user_id)): job.schedule_removal()
            await query.edit_message_text(f"❌ *SBAGLIATO!* La risposta corretta era {q['c']}.")
            players.update_one({"user_id": user_id}, {"$set": {"game_over": True}})

    # 3. Gestione Aiuti (Fix sintassi)
    elif data.startswith("h_"):
        tipo = data.split("_")[1]
        players.update_one({"user_id": user_id}, {"$set": {f"h.{tipo}": False}})
        if tipo == "5050":
            rimosse = random.sample([k for k in ["A", "B", "C", "D"] if k != q["c"]], 2)
            await invia_domanda(update, context, idx, rimosse=rimosse)
        else:
            txt = f"📊 *Pubblico*: {q['c']}" if tipo == "pub" else f"📞 *Esperto*: 'È la {q['c']}!'"
            m = await context.bot.send_message(user_id, txt, parse_mode="Markdown")
            players.update_one({"user_id": user_id}, {"$push": {"temp_msg_ids": m.message_id}})
    
    await query.answer()

# ... (Resto del codice main come prima)
