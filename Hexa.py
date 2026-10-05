import os
import asyncio
import re
import random
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections import deque

from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import MessageIdInvalidError

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
TELEGRAM_SESSION = os.environ["TELEGRAM_SESSION"].strip().strip('"').strip("'")

client = TelegramClient(StringSession(TELEGRAM_SESSION), API_ID, API_HASH)

PORT = int(os.environ.get("PORT", "10000"))

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health"):
            body = b"HexaRenderAuto is online"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def start_health_server():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler)
    server.serve_forever()

start_health_server_thread = threading.Thread(target=start_health_server, daemon=True)
start_health_server_thread.start()

legendary_poks = ["Rayquaza", "Kyogre", "Groudon", "Dialga", "Kyurem", "Reshiram", "Zekrom", "Yveltal", 
                  "Xerneas", "Zygarde", "Cosmog", "Cosmoem", "Necrozma", "Ho-oh", "Lugia", "Arceus", 
                  "Zeraora", "Pheromosa", "Mewtwo", "Victini", "Regigigas", "Deoxys", "Marshadow", "A wild Mewtwo", "A wild Latias", "A wild Latios", "A wild Rayquaza", "A wild Lugia", "A wild Celebi", "A wild Ho-Oh", "A wild Kyogre", "A wild Groudon", "A wild Dialga", "A wild Regigigas", "A wild Arceus", "A wild Giratina", "A wild Victini", "A wild Terrakion", "A wild Kyurem", "A wild Zekrom", "A wild Zacian", "A wild Zamazenta", "A wild Eternatus", "A wild Kubfu", "A wild Urshifu", "A wild Regieleki", "A wild Regidrago", "A wild Glastrier", "A wild Spectrier", "A wild Calyrex"]

regular_poks_repeat = ["A wild Mewtwo", "A wild Latias", "A wild Latios", "A wild Rayquaza", "A wild Lugia", "A wild Celebi", "A wild Ho-Oh", "A wild Kyogre", "A wild Groudon", "A wild Dialga", "A wild Regigigas", "A wild Arceus", "A wild Giratina", "A wild Victini", "A wild Terrakion", "A wild Kyurem", "A wild Zekrom", "A Wild Zacian", "A Wild Zamazenta", "A Wild Eternatus", "A Wild Kubfu", "A Wild Regieleki", "A Wild Regidrago", "A Wild Glastrier", "A Wild Spectrier", "A Wild Calyrex"]

regular_ball = ["A wild Alakazam", "A wild Slowbro", "A wild Kangaskhan", "A wild Pinsir", "A wild Gyarados", "A wild Aerodactyl", "A wild Ampharos", "A wild Steelix", "A wild Scizor", "A wild Heracross", "A wild Tyranitar", "A wild Sceptile", "A wild Blaziken", "A wild Swampert", "A wild Gardevoir", "A wild Sableye", "A wild Mawile", "A wild Aggron", "A wild Medicham", "A wild Manectric", "A wild Sharpedo", "A wild Camerupt", "A wild Altaria", "A wild Banette", "A wild Absol", "A wild Glalie", "A wild Salamence", "A wild Metagross", "A wild Lopunny", "A wild Garchomp", "A wild Lucario", "A wild Abomasnow", "A wild Gallade", "A wild Audino", "A wild Bulbasaur", "A wild Ivysaur", "A wild Venusaur", "A wild Charmander", "A wild Charizard", "A wild Blastoise", "A wild Kakuna", "A wild Beedrill", "A wild Pidgeot", "A wild Growlithe", "A wild Shellder", "A wild Gengar", "A wild Totodile", "A wild Togepi", "A wild Togetic", "A wild Houndoom", "A wild Slakoth", "A wild Vigoroth", "A wild Nincada", "A wild Chimchar", "A wild Buneary", "A Wild Fennekin", "A Wild Braixen", "A Wild Froakie", "A Wild Frogadier", "A Wild Barraskewda", "A Wild Arrokuda", "A Wild Darumaka", "A Wild Drakloak", "A Wild Dragapult", "A Wild Dracovish", "A Wild Duraludon", "A Wild Raboot", "A Wild Cinderace", "A Wild Scorbunny", "A Wild Sobble", "A Wild Drizzile", "A Wild Inteleon", "A Wild Grookey", "A Wild Thwackey", "A Wild Rillaboom", "A Wild Sizzlipede", "A Wild Centiskorch", "A Wild Morgrem", "A Wild Impidimp", "A Wild Grimmsnarl", "A Wild Toxel", "A Wild Toxtricity", "A Wild Rookidee", "A Wild Corvisquire","A Wild Corviknight"]

# ============================================================
# POKEMON -> BALL MAPPING
# Add a Pokemon name to the list for the ball you want HexaAuto
# to select automatically.
#
# Example:
#   regular_ball = ["Abra", ...]
#   ultra_ball   = ["Regigigas", ...]
#
# Names are normalized below, so both "Regigigas" and
# "A wild Regigigas" work.
# ============================================================

ultra_ball = [
    "Rayquaza", "Kyogre", "Groudon", "Dialga", "Kyurem", "Reshiram", "Zekrom", "Yveltal",
    "Xerneas", "Zygarde", "Cosmog", "Cosmoem", "Necrozma", "Ho-oh", "Lugia", "Arceus",
    "Zeraora", "Pheromosa", "Mewtwo", "Victini", "Regigigas", "Deoxys", "Marshadow",
    "A wild Mewtwo", "A wild Latias", "A wild Latios", "A wild Rayquaza", "A wild Lugia",
    "A wild Celebi", "A wild Ho-Oh", "A wild Kyogre", "A wild Groudon", "A wild Dialga",
    "A wild Regigigas", "A wild Arceus", "A wild Giratina", "A wild Victini",
    "A wild Terrakion", "A wild Kyurem", "A wild Zekrom", "A wild Zacian",
    "A wild Zamazenta", "A wild Eternatus", "A wild Kubfu", "A wild Urshifu",
    "A wild Regieleki", "A wild Regidrago", "A wild Glastrier", "A wild Spectrier",
    "A wild Calyrex",
]

# Your requested example: Abra uses a Regular Ball.
regular_ball.append("Abra")

# Normalize the existing lists so battle messages such as
# "Wild Regigigas" match entries written as "A wild Regigigas".
def normalize_pokemon_name(name):
    name = re.sub(r"^a\s+wild\s+", "", str(name).strip(), flags=re.IGNORECASE)
    name = re.sub(r"^wild\s+", "", name, flags=re.IGNORECASE)
    return name.casefold()

regular_ball = {normalize_pokemon_name(name) for name in regular_ball}
repeat_ball = {
    normalize_pokemon_name(name)
    for name in (regular_poks_repeat + legendary_poks)
}
ultra_ball = {normalize_pokemon_name(name) for name in ultra_ball}

# Button labels used by the Telegram game. The fallback keeps the
# automation working if the game displays "Ultra Ball" instead of "Ultra".
BALL_BUTTONS = {
    "Regular": ("Regular", "Regular Ball"),
    "Repeat": ("Repeat", "Repeat Ball"),
    "Ultra": ("Ultra", "Ultra Ball"),
}

def ball_for_pokemon(pokemon_name):
    name = normalize_pokemon_name(pokemon_name)
    if name in ultra_ball:
        return "Ultra"
    if name in regular_ball:
        return "Regular"
    if name in repeat_ball:
        return "Repeat"
    return None

async def click_ball(event, ball_name):
    for label in BALL_BUTTONS.get(ball_name, (ball_name,)):
        try:
            await event.click(text=label)
            print(f"Selected {label} Ball for the encounter.")
            return True
        except Exception:
            continue
    print(f"Could not find the {ball_name} Ball button.")
    return False

cooldown = random.randint(1, 2)
low_lvl = False

@client.on(events.NewMessage(from_users=572621020))
async def dailyLimit(event):
    if "Daily hunt limit reached" in event.raw_text:
    	await client.disconnect()
    
    
@client.on(events.NewMessage(from_users=572621020))
async def hunt_or_pass(event):
    global cooldown

    if "✨ Shiny pokemon found!" in event.raw_text:
        await event.client.send_message(-1001237867208, "@uxnor shiny aaya jaldi dekh")
        await client.disconnect()
        return

    if "A wild" not in event.raw_text:
        return

    # The current game UI starts every catch with a "Catch" button.
    pok_name_match = re.search(r"A wild (.+?) \(Lv\.", event.raw_text, flags=re.IGNORECASE)
    if not pok_name_match:
        print("Could not read wild Pokemon name.")
        return

    pok_name = pok_name_match.group(1).strip()
    selected_ball = ball_for_pokemon(pok_name)
    print(f"Wild Pokemon: {pok_name} | Ball: {selected_ball}")

    if not selected_ball:
        await asyncio.sleep(cooldown)
        await client.send_message(572621020, "/hunt")
        return

    try:
        await asyncio.sleep(cooldown)
        await event.click(text="Catch")
        print(f"Clicked Catch for {pok_name}.")
    except Exception as exc:
        print(f"Could not click Catch for {pok_name}: {exc}")


@client.on(events.MessageEdited(from_users=572621020))
async def auto_throw_ball(event):
    global cooldown

    if "Throw Ball" not in event.raw_text:
        return

    pok_name_match = re.search(r"A wild (.+?) \(Lv\.", event.raw_text, flags=re.IGNORECASE)
    if not pok_name_match:
        print("Could not read Pokemon name before throwing.")
        return

    pok_name = pok_name_match.group(1).strip()
    selected_ball = ball_for_pokemon(pok_name)

    if not selected_ball:
        print(f"No ball mapping for {pok_name}.")
        return

    try:
        await asyncio.sleep(cooldown)

        # First click the game's "Throw Ball" button.
        await event.click(text="Throw Ball")
        print(f"Clicked Throw Ball for {pok_name}.")

        # The ball buttons appear after the Throw Ball click, so fetch
        # the freshly edited message before selecting the actual ball.
        await asyncio.sleep(0.8)
        updated = await client.get_messages(572621020, ids=event.id)

        if await click_ball(updated, selected_ball):
            print(f"Threw {selected_ball} Ball at {pok_name}.")
        else:
            print(f"Failed to select {selected_ball} Ball for {pok_name}.")
    except Exception as exc:
        print(f"Auto throw failed for {pok_name}: {exc}")


def calculate_health_percentage(max_hp, current_hp):
    if max_hp <= 0:
        raise ValueError("Total health must be greater than zero.")

    if current_hp < 0 or current_hp > max_hp:
        raise ValueError("Current health must be between 0 and total health.")

    return round((current_hp / max_hp) * 100)


@client.on(events.MessageEdited(from_users=572621020))
async def skip(event):
    if any(substring in event.raw_text for substring in ["fled", "💵", "You caught"]):
        global cooldown
        global low_lvl
        low_lvl = False
        await asyncio.sleep(cooldown)
        await client.send_message(572621020, '/hunt')        
    	
@client.on(events.NewMessage(from_users=572621020))
async def skipTrainer(event):
    if "An expert trainer" in event.raw_text:
        global cooldown
        await asyncio.sleep(cooldown)
        await client.send_message(572621020, '/hunt')        
 

@client.on(events.MessageEdited(from_users=572621020))
async def pokeSwitch(event):
    if "Choose your next pokemon." in event.raw_text:
        buttons_to_click = ["Golurk", "Malamar", "Drampa", "Chesnaught", "Xerneas"]
        for button in buttons_to_click:
            try:
                await event.click(text=button)
            except:
                pass
                
                



   	
async def main():
    await client.start()
    me = await client.get_me()
    print(f"Telegram session connected: {getattr(me, 'username', None) or me.id}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
