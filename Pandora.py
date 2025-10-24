import os
import math
import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
from dotenv import load_dotenv
from discord import ui


load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", 0)) if os.getenv("DISCORD_GUILD_ID") else 0
POKEAPI_BASE = "https://pokeapi.co/api/v2"
PREFIX = "/"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# MAPA DE APOIO
TYPE_EMOJI = {
    "normal": "⚪", "fire": "🔥", "water": "💧", "grass": "🌿", "electric": "⚡",
    "ice": "❄️", "fighting": "🥊", "poison": "☠️", "ground": "🌍", "flying": "🕊️",
    "psychic": "🧠", "bug": "🐛", "rock": "🪨", "ghost": "👻", "dragon": "🐉",
    "dark": "🌑", "steel": "⚙️", "fairy": "✨"
}

CATEGORY_ICON = {
    "physical": "⚔️",
    "special": "🧠",
    "status": "✴️"
}

NATURE_MAP = {
    "adamant": ("attack", "special-attack"), "bashful": (None, None), "bold": ("defense", "attack"),
    "brave": ("attack", "speed"), "calm": ("special-defense", "attack"), "careful": ("special-defense", "special-attack"),
    "docile": (None, None), "gentle": ("special-defense", "defense"), "hardy": (None, None),
    "hasty": ("speed", "defense"), "impish": ("defense", "special-attack"), "jolly": ("speed", "special-attack"),
    "lax": ("defense", "special-defense"), "lonely": ("attack", "defense"), "mild": ("special-attack", "defense"),
    "modest": ("special-attack", "attack"), "naive": ("speed", "special-defense"), "naughty": ("attack", "special-defense"),
    "quiet": ("special-attack", "speed"), "quirky": (None, None), "rash": ("special-attack", "special-defense"),
    "relaxed": ("defense", "speed"), "sassy": ("special-defense", "speed"), "serious": (None, None),
    "timid": ("speed", "attack"),
}

# SESSÃO HTTP
async def get_session():
    if not hasattr(bot, "http_session") or bot.http_session.closed:
        bot.http_session = aiohttp.ClientSession()
    return bot.http_session

async def close_session():
    if hasattr(bot, "http_session") and not bot.http_session.closed:
        await bot.http_session.close()

async def fetch_json(url: str):
    session = await get_session()
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                raise ValueError(f"erro ao acessar {url} (status {resp.status})")
            return await resp.json()
    except asyncio.TimeoutError:
        raise ValueError(f"timeout ao acessar {url}")

# FUNÇOES AUXILIAR
def nature_magnitude(level: int) -> int:
    if level <= 4: return 1
    if level <= 9: return 2
    if level <= 14: return 3
    return 4

async def fetch_pokemon(pokemon_name: str) -> dict:
    url = f"{POKEAPI_BASE}/pokemon/{pokemon_name.lower()}"
    return await fetch_json(url)

async def fetch_species_forms(pokemon_name: str) -> list[str]:
    url = f"{POKEAPI_BASE}/pokemon-species/{pokemon_name.lower()}"
    try:
        data = await fetch_json(url)
    except Exception:
        return []
    varieties = data.get("varieties", [])
    return [v["pokemon"]["name"] for v in varieties if v["pokemon"]["name"] != pokemon_name.lower()]

async def fetch_type_weaknesses(type_names: list[str]) -> list[tuple]:
    weaknesses = {}
    tasks = [fetch_json(f"{POKEAPI_BASE}/type/{t_name}") for t_name in type_names]
    results = []
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:
        pass
    for res in results:
        if isinstance(res, Exception) or not isinstance(res, dict):
            continue
        for dmg in res.get('damage_relations', {}).get('double_damage_from', []):
            name = dmg['name']
            weaknesses[name] = weaknesses.get(name, 0) + 1
    sorted_weak = sorted(weaknesses.items(), key=lambda x: -x[1])
    return sorted_weak

def plaque_type_icons(types_list):
    types_pretty, types_names = [], []
    for t in types_list:
        name = t['type']['name']
        emoji = TYPE_EMOJI.get(name, "")
        types_pretty.append(f"{emoji} {name.capitalize()}" if emoji else name.capitalize())
        types_names.append(name)
    return types_pretty, types_names

def stat_key_to_label(key: str) -> str:
    return {
        "hp": "HP", "attack": "ATK", "defense": "DEF",
        "special-attack": "SP.ATK", "special-defense": "SP.DEF", "speed": "SPD"
    }.get(key, key)

def compute_stats(base_stats: dict, level: int, nature_name: str):
    hp_base = base_stats.get('hp', 0)
    hp_final = hp_base + max(0, (level - 1) * 5)
    derived = {k: math.ceil(v / 10.0) for k, v in base_stats.items() if k != 'hp'}
    inc_stat, dec_stat = NATURE_MAP.get(nature_name.lower(), (None, None))
    magnitude = nature_magnitude(level)
    if inc_stat and inc_stat in derived:
        derived[inc_stat] += magnitude
    if dec_stat and dec_stat in derived:
        derived[dec_stat] -= magnitude
    top3_all = sorted(base_stats.items(), key=lambda x: x[1], reverse=True)
    top3 = [k for k, v in top3_all if k != 'hp'][:3]
    for k in top3:
        if k in derived:
            derived[k] += max(0, level - 1)
    derived = {k: max(0, v) for k, v in derived.items()}
    return {
        'hp': hp_final,
        'attack': derived.get('attack', 0),
        'defense': derived.get('defense', 0),
        'special-attack': derived.get('special-attack', 0),
        'special-defense': derived.get('special-defense', 0),
        'speed': derived.get('speed', 0)
    }, top3

async def extract_abilities(poke_json):
    abilities = []
    for ab in poke_json.get('abilities', []):
        try:
            ab_info = await fetch_json(ab['ability']['url'])
        except Exception:
            ab_info = {}
        name_pt = next((n["name"] for n in ab_info.get("names", []) if n["language"]["name"] in ["pt", "pt-BR", "es"]), None)
        effect_entry = next((e for e in ab_info.get("effect_entries", []) if e["language"]["name"] in ["pt", "pt-BR", "es"]), None)
        if not name_pt:
            name_pt = ab_info.get('name', "").replace("-", " ").title() if isinstance(ab_info, dict) else ab['ability']['name'].replace("-", " ").title()
        if effect_entry:
            effect_pt = effect_entry.get("short_effect") or effect_entry.get("effect")
        else:
            effect_pt = next((e.get("short_effect") or e.get("effect") for e in ab_info.get("effect_entries", []) if e["language"]["name"] == "en"), "")
        abilities.append({
            "name": name_pt or "Desconhecido",
            "effect": effect_pt or "",
            "is_hidden": ab.get('is_hidden', False)
        })
    return abilities

# ON READY
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user} — sincronizando comandos...")
    try:
        if GUILD_ID:
            await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
            print(f"✅ Comandos sincronizados para guild {GUILD_ID}.")
        else:
            await bot.tree.sync()
            print(f"✅ Comandos sincronizados globalmente.")
    except Exception as e:
        print("❌ Erro ao sincronizar comandos:", e)

@bot.event
async def on_close():
    await close_session()

# /f
@bot.tree.command(name="f", description="Gera ficha Pokémon")
async def slash_ficha(interaction: discord.Interaction, nome: str, nivel: int, natureza: str = "hardy"):
    await interaction.response.defer(thinking=True)
    
    try:
        poke = await fetch_pokemon(nome)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}")
        return

    # Escolha de forma
    try:
        species = await fetch_json(f"{POKEAPI_BASE}/pokemon-species/{nome.lower()}")
        formas = [f["pokemon"]["name"] for f in species.get("varieties", []) if f["pokemon"]["name"] != nome.lower()]
    except Exception:
        formas = []

    if formas:
        msg_formas = "**Este Pokémon tem formas alternativas. Escolha uma (ou 0 para forma padrão):**\n"
        for i, f in enumerate(formas, 1):
            msg_formas += f"{i}. {f.capitalize().replace('-', ' ')}\n"
        await interaction.followup.send(msg_formas)
        def check_form(m): return m.author == interaction.user and m.channel == interaction.channel and m.content.strip().isdigit()
        try:
            resposta = await bot.wait_for("message", timeout=60, check=check_form)
            idx = int(resposta.content.strip())
            if idx > 0 and idx <= len(formas):
                poke = await fetch_pokemon(formas[idx - 1])
        except asyncio.TimeoutError:
            await interaction.followup.send("⏰ Tempo esgotado, continuando com a forma padrão...")
        except Exception:
            await interaction.followup.send("❌ Forma inválida, continuando com padrão...")

    # Base Stats
    base_stats = {s['stat']['name']: s['base_stat'] for s in poke['stats']}
    final_stats, top3 = compute_stats(base_stats, nivel, natureza)

    # Habilidades
    abilities = await extract_abilities(poke)
    msg = "**Escolha uma habilidade:**\n"
    for i, ab in enumerate(abilities, 1):
        msg += f"{i}. {ab['name']} — {ab['effect']}\n"
    await interaction.followup.send(msg)
    def check_ability(m): return m.author == interaction.user and m.channel == interaction.channel
    try:
        resposta = await bot.wait_for("message", timeout=60, check=check_ability)
        idx = int(resposta.content.strip()) - 1
        habilidade = abilities[idx]
    except Exception:
        await interaction.followup.send("❌ Habilidade inválida.")
        return

    # Moves
    moves_raw = poke.get("moves", [])
    moves_por_nivel = []
    for mv in moves_raw:
        for det in mv.get("version_group_details", []):
            if det["move_learn_method"]["name"] == "level-up" and det["level_learned_at"] <= nivel:
                try:
                    move_data = await fetch_json(mv["move"]["url"])
                except Exception:
                    continue
                tipo = move_data.get("type", {}).get("name", "")
                categoria = (move_data.get("damage_class") or {}).get("name", "")
                power = move_data.get("power")
                accuracy = move_data.get("accuracy")
                moves_por_nivel.append((det["level_learned_at"], mv["move"]["name"], tipo, categoria, power, accuracy))
    moves_unicos = {}
    for lvl, nome_mv, tipo, categoria, power, acc in moves_por_nivel:
        moves_unicos[nome_mv] = (lvl, tipo, categoria, power, acc)
    moves_filtrados = sorted(moves_unicos.items(), key=lambda x: (x[1][0], x[0]))

    msg_moves = "**Escolha até 4 movimentos (separe por vírgula):**\n"
    for i, (nome_mv, (lvl, tipo, categoria, power, acc)) in enumerate(moves_filtrados, 1):
        tipo_icon = TYPE_EMOJI.get(tipo, "")
        cat_icon = CATEGORY_ICON.get(categoria, "")
        power_str = f"Power {power}" if power else ""
        acc_str = f"Acc {acc}%" if acc else ""
        extra = " | ".join([x for x in [power_str, acc_str] if x])
        extra = f" ({extra})" if extra else ""
        msg_moves += f"{i}. {nome_mv.replace('-', ' ').title()} — Nv {lvl} {tipo_icon} {tipo.capitalize() if tipo else ''} {cat_icon} {categoria.capitalize() if categoria else ''}{extra}\n"
    await interaction.followup.send(msg_moves)

    def check_moves(m): return m.author == interaction.user and m.channel == interaction.channel
    try:
        resposta = await bot.wait_for("message", timeout=120, check=check_moves)
        indices = [int(x.strip()) for x in resposta.content.split(",") if x.strip().isdigit()]
        moves_escolhidos = [moves_filtrados[i - 1] for i in indices if 1 <= i <= len(moves_filtrados)][:4]
    except Exception:
        moves_escolhidos = []

    # Shiny
    await interaction.followup.send("✨ O Pokémon é **shiny**? (responda `sim` ou `não`)")
    def check_shiny(m): return m.author == interaction.user and m.channel == interaction.channel
    try:
        resposta = await bot.wait_for("message", timeout=30, check=check_shiny)
        shiny = resposta.content.strip().lower() in ["sim", "s", "yes", "y"]
    except asyncio.TimeoutError:
        shiny = False
        await interaction.followup.send("⏰ Tempo esgotado — considerado **não shiny**.")
    except Exception:
        shiny = False
        await interaction.followup.send("❌ Resposta inválida — considerado **não shiny**.")

    # Ficha
    types_pretty, type_names = plaque_type_icons(poke['types'])
    fraquezas = await fetch_type_weaknesses(type_names)
    nome_final = poke['name'].upper().replace("-", " ")
    ficha = f"**{nome_final} — Nível {nivel}**\nNature: {natureza.capitalize()}\nTipo: {' | '.join(types_pretty)}\n🏅 Habilidade: {habilidade['name']} — {habilidade['effect']}\n\n💖 **Stats:**\n"
    for k, v in final_stats.items():
        ficha += f"• {stat_key_to_label(k)}: {v}\n"
    ficha += "\n⚠️ **Fraquezas:**\n"
    if fraquezas:
        for t, mult in fraquezas:
            ficha += f"- {TYPE_EMOJI.get(t, '')} {t.capitalize()} (x{2**mult})\n"
    else:
        ficha += "Nenhuma fraqueza.\n"

    ficha += "\n🎯 **Movimentos:**\n"
    if moves_escolhidos:
        for nome_mv, (lvl, tipo, categoria, power, acc) in moves_escolhidos:
            tipo_icon = TYPE_EMOJI.get(tipo, "")
            cat_icon = CATEGORY_ICON.get(categoria, "")
            power_str = f"Power {power}" if power else ""
            acc_str = f"Acc {acc}%" if acc else ""
            extra = " | ".join([x for x in [power_str, acc_str] if x])
            extra = f" ({extra})" if extra else ""
            ficha += f"• {nome_mv.replace('-', ' ').title()} — {tipo_icon} {tipo.capitalize() if tipo else ''} {cat_icon} {categoria.capitalize() if categoria else ''}{extra}\n"
    else:
        ficha += "Nenhum movimento selecionado.\n"

    await interaction.followup.send(f"```{ficha}```")
    img = (poke.get("sprites") or {}).get("other", {}).get("official-artwork", {}).get("front_default")
    if shiny:
        shiny_img = (poke.get("sprites") or {}).get("other", {}).get("official-artwork", {}).get("front_shiny")
        if shiny_img:
            await interaction.followup.send(shiny_img)
        elif img:
            await interaction.followup.send(img)
    else:
        if img:
            await interaction.followup.send(img)

# RODA
try:
    bot.run(TOKEN)
finally:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(close_session())
        else:
            loop.run_until_complete(close_session())
    except Exception:
        pass