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

repeat_ball = regular_poks_repeat + legendary_poks
cooldown = random.randint(1, 2)
low_lvl = False

@client.on(events.NewMessage(from_users=572621020))
async def dailyLimit(event):
    if "Daily hunt limit reached" in event.raw_text:
    	await client.disconnect()
    
    
@client.on(events.NewMessage(from_users=572621020))
async def hunt_or_pass(event):
    if "✨ Shiny pokemon found!" in event.raw_text:  
        await event.client.send_message(-1001237867208, "@uxnor shiny aaya jaldi dekh") 
        await client.disconnect()
    elif "A wild" in event.raw_text:
        global cooldown
        pok_name = event.raw_text.split("wild ")[1].split(" (")[0]
        print(pok_name)
        if pok_name in regular_ball or pok_name in repeat_ball:
            await asyncio.sleep(cooldown)
            await event.click(0, 0)
        else:
            await asyncio.sleep(cooldown)
            await client.send_message(572621020, '/hunt')
            
            

@client.on(events.NewMessage(from_users=572621020))
async def battlefirst(event):
    global low_lvl
    global cooldown
    if "Battle begins!" in event.raw_text:
        wild_pokemon_name_match = re.search(r"Wild (\w+) \[.*\]\nLv\. \d+  •  HP \d+/\d+", event.raw_text)
        
        if wild_pokemon_name_match:
            pok_name = wild_pokemon_name_match.group(1)
            
            wild_pokemon_hp_match = re.search(r"Wild .* \[.*\]\nLv\. \d+  •  HP (\d+)/(\d+)", event.raw_text)

            if wild_pokemon_hp_match:
                wild_max_hp = int(wild_pokemon_hp_match.group(2))
                if wild_max_hp <= 50:
                    low_lvl = True
                    print("low lvl set to true")
                    await asyncio.sleep(cooldown)
                    await event.click(text="Poke Balls")
                    print("cliked on btn poke balls")
                else:
                    await asyncio.sleep(2)
                    await event.click(0, 0)
                    
                    
 

def calculate_health_percentage(max_hp, current_hp):
    if max_hp <= 0:
        raise ValueError("Total health must be greater than zero.")

    if current_hp < 0 or current_hp > max_hp:
        raise ValueError("Current health must be between 0 and the total health.")

    health_percentage = round((current_hp / max_hp) * 100)
    return health_percentage



@client.on(events.MessageEdited(from_users=572621020))
async def battle(event):
    global low_lvl
    if "Wild" in event.raw_text:
        wild_pokemon_name_match = re.search(r"Wild (\w+) \[.*\]\nLv\. \d+  •  HP \d+/\d+", event.raw_text)

        if wild_pokemon_name_match:
            pok_name = wild_pokemon_name_match.group(1)

            wild_pokemon_hp_match = re.search(r"Wild .* \[.*\]\nLv\. \d+  •  HP (\d+)/(\d+)", event.raw_text)

            if wild_pokemon_hp_match:
                wild_max_hp = int(wild_pokemon_hp_match.group(2))
                wild_current_hp = int(wild_pokemon_hp_match.group(1))
                wild_health_percentage = calculate_health_percentage(wild_max_hp, wild_current_hp)
                if low_lvl == True:
                    await asyncio.sleep(cooldown)
                    await event.click(text="Poke Balls")
                    if pok_name in regular_ball:
                        await asyncio.sleep(1)
                        await event.click(text="Regular")
                    elif pok_name in repeat_ball:
                        await asyncio.sleep(1)
                        await event.click(text="Repeat")
                elif wild_health_percentage > 50:
                    await asyncio.sleep(1)
                    await event.click(0, 0)
                elif wild_health_percentage <= 50:
                    await asyncio.sleep(1)
                    await event.click(text="Poke Balls")
                    if pok_name in regular_ball:
                        await asyncio.sleep(1)
                        await event.click(text="Regular")
                    elif pok_name in repeat_ball:
                        await asyncio.sleep(1)
                        await event.click(text="Repeat")
                print(f"{pok_name} health percentage: {wild_health_percentage}%")
            else:
                print(f"Wild Pokemon {pok_name} HP not found in the battle description.")
        else:
            print("Wild Pokemon name not found in the battle description.")
            
            
            
            
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
    print(f"Telegram session connected: {getattr(me, "username", None) or me.id}")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
