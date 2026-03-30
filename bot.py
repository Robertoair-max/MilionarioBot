
# --- LOGICA AIUTI ---
def genera_pubblico(corretta, idx):
    prob_corretta = max(35, 85 - (idx * 4))
    opzioni = ["A", "B", "C", "D"]
    voti = {corretta: random.randint(int(prob_corretta), 95)}
    rimanente = 100 - voti[corretta]
    altre = [k for k in opzioni if k != corretta]
    random.shuffle(altre)
    v1 = random.randint(0, rimanente)
    voti[altre[0]] = v1
    rimanente -= v1
    v2 = random.randint(0, rimanente)
    voti[altre[1]] = v2
    voti[altre[2]] = 100 - (voti[corretta] + v1 + v2)
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
