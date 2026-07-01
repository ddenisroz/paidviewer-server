"""
Утилита для умного поиска категорий с поддержкой алиасов и переводов.
Используется для команд в чате (!category, !game).
"""
from typing import List, Dict, Any, Optional
import re
CATEGORY_ALIASES = {'dbd': ['Dead by Daylight'], 'rdr2': ['Red Dead Redemption 2'], 'rdr': ['Red Dead Redemption', 'Red Dead Redemption 2'], 'gta': ['Grand Theft Auto V', 'GTA V', 'GTA Online'], 'gtav': ['Grand Theft Auto V'], 'gtao': ['GTA Online'], 'cod': ['Call of Duty', 'Warzone'], 'cs': ['Counter-Strike', 'Counter-Strike 2', 'CS:GO'], 'cs2': ['Counter-Strike 2'], 'csgo': ['CS:GO'], 'lol': ['League of Legends'], 'dota': ['Dota 2'], 'dota2': ['Dota 2'], 'wow': ['World of Warcraft'], 'ow': ['Overwatch', 'Overwatch 2'], 'ow2': ['Overwatch 2'], 'val': ['VALORANT'], 'valorant': ['VALORANT'], 'apex': ['Apex Legends'], 'fortnite': ['Fortnite'], 'fn': ['Fortnite'], 'minecraft': ['Minecraft'], 'mc': ['Minecraft'], 'pubg': ['PUBG: BATTLEGROUNDS'], 'eft': ['Escape from Tarkov'], 'tarkov': ['Escape from Tarkov'], 'rust': ['Rust'], 'ark': ['ARK'], 'poe': ['Path of Exile'], 'fifa': ['FC 24', 'EA SPORTS FC 24', 'FIFA', 'FC 25'], 'фифа': ['FC 24', 'EA SPORTS FC 24', 'FIFA', 'FC 25'], 'fc24': ['FC 24', 'EA SPORTS FC 24'], 'fc25': ['FC 25', 'EA SPORTS FC 25'], 'fc': ['FC 24', 'FC 25', 'EA SPORTS FC'], 'rl': ['Rocket League'], 'wot': ['World of Tanks'], 'hs': ['Hearthstone'], 'sc2': ['StarCraft II'], 'starcraft': ['StarCraft'], 'diablo': ['Diablo IV', 'Diablo III'], 'd4': ['Diablo IV'], 'd3': ['Diablo III'], 'd2': ['Diablo II', 'Destiny 2'], 'bf': ['Battlefield'], 'r6': ['Rainbow Six Siege'], 'siege': ['Rainbow Six Siege'], 'destiny': ['Destiny 2'], 'destiny2': ['Destiny 2'], 'tf2': ['Team Fortress 2'], 'l4d': ['Left 4 Dead'], 'l4d2': ['Left 4 Dead 2'], 'cyberpunk': ['Cyberpunk 2077'], 'cp2077': ['Cyberpunk 2077'], 'eldenring': ['Elden Ring'], 'er': ['Elden Ring'], 'darksouls': ['Dark Souls'], 'ds': ['Dark Souls'], 'ds3': ['Dark Souls III'], 'sekiro': ['Sekiro'], 'witcher': ['The Witcher 3'], 'witcher3': ['The Witcher 3'], 'w3': ['The Witcher 3'], 'skyrim': ['Skyrim'], 'fallout': ['Fallout'], 'fo4': ['Fallout 4'], 'fo76': ['Fallout 76'], 'gow': ['God of War'], 'tlou': ['The Last of Us'], 'spiderman': ['Spider-Man'], 'hogwarts': ['Hogwarts Legacy'], 'hl': ['Hogwarts Legacy', 'Half-Life'], 'resident': ['Resident Evil'], 're': ['Resident Evil'], 're4': ['Resident Evil 4'], 'silenthill': ['Silent Hill'], 'sh': ['Silent Hill'], 'phasmophobia': ['Phasmophobia'], 'phasmo': ['Phasmophobia'], 'lethal': ['Lethal Company'], 'fnaf': ["Five Nights at Freddy's"], '7dtd': ['7 Days to Die'], 'dayz': ['DayZ'], 'terraria': ['Terraria'], 'stardew': ['Stardew Valley'], 'sdv': ['Stardew Valley'], 'sims': ['The Sims 4'], 'sims4': ['The Sims 4'], 'cities': ['Cities: Skylines'], 'civ': ['Civilization VI'], 'civ6': ['Civilization VI'], 'aoe': ['Age of Empires'], 'aoe2': ['Age of Empires II'], 'aoe4': ['Age of Empires IV'], 'ff': ['Final Fantasy'], 'ff14': ['Final Fantasy XIV'], 'ffxiv': ['Final Fantasy XIV'], 'pokemon': ['Pokémon'], 'zelda': ['The Legend of Zelda'], 'botw': ['Breath of the Wild'], 'totk': ['Tears of the Kingdom'], 'mario': ['Super Mario'], 'smash': ['Super Smash Bros.'], 'mk': ['Mortal Kombat'], 'sf': ['Street Fighter'], 'sf6': ['Street Fighter 6'], 'tekken': ['Tekken'], 'amongus': ['Among Us'], 'among': ['Among Us'], 'fallguys': ['Fall Guys'], 'roblox': ['Roblox'], 'vrchat': ['VRChat'], 'beatsaber': ['Beat Saber'], 'дота': ['Dota 2'], 'кс': ['Counter-Strike', 'Counter-Strike 2', 'CS:GO'], 'контр': ['Counter-Strike', 'Counter-Strike 2'], 'майнкрафт': ['Minecraft'], 'майн': ['Minecraft'], 'варфейс': ['Warface'], 'танки': ['World of Tanks'], 'корабли': ['World of Warships'], 'варкрафт': ['World of Warcraft', 'Warcraft III'], 'вов': ['World of Warcraft'], 'ведьмак': ['The Witcher 3', 'The Witcher'], 'скайрим': ['Skyrim'], 'фоллаут': ['Fallout', 'Fallout 4'], 'сталкер': ['S.T.A.L.K.E.R.'], 'метро': ['Metro Exodus', 'Metro'], 'раст': ['Rust'], 'тарков': ['Escape from Tarkov'], 'побег': ['Escape from Tarkov'], 'апекс': ['Apex Legends'], 'форт': ['Fortnite'], 'фортнайт': ['Fortnite'], 'валорант': ['VALORANT'], 'овервотч': ['Overwatch', 'Overwatch 2'], 'хартстоун': ['Hearthstone'], 'варфрейм': ['Warframe'], 'дестини': ['Destiny 2'], 'роблокс': ['Roblox'], 'амонг': ['Among Us'], 'фазмо': ['Phasmophobia'], 'хогвартс': ['Hogwarts Legacy'], 'elden': ['Elden Ring'], 'элден': ['Elden Ring'], 'киберпанк': ['Cyberpunk 2077'], 'ракет': ['Rocket League'], 'лига': ['Rocket League', 'League of Legends'], 'террария': ['Terraria'], 'геншин': ['Genshin Impact'], 'лол': ['League of Legends'], 'пубг': ['PUBG: BATTLEGROUNDS'], 'гта': ['Grand Theft Auto V', 'GTA V'], 'паладинс': ['Paladins'], 'смайт': ['SMITE'], 'хотс': ['Heroes of the Storm'], 'старкрафт': ['StarCraft II'], 'диабло': ['Diablo IV', 'Diablo III'], 'симс': ['The Sims 4'], 'симулятор': ['Farming Simulator', 'Euro Truck Simulator 2'], 'евротрак': ['Euro Truck Simulator 2'], 'американтрак': ['American Truck Simulator'], 'спинтайрс': ['Spintires'], 'сноуранер': ['SnowRunner'], 'аркрыцари': ['ARK: Survival Evolved'], 'дейз': ['DayZ'], 'зомбоид': ['Project Zomboid'], 'лес': ['The Forest'], 'сыновьялеса': ['Sons of the Forest'], 'саншайн': ['Satisfactory'], 'факторио': ['Factorio'], 'римворлд': ['RimWorld'], 'кислород': ['Oxygen Not Included'], 'города': ['Cities: Skylines'], 'цивилизация': ['Civilization VI'], 'война': ['Total War: Warhammer III'], 'аоэ': ['Age of Empires IV'], 'хои': ['Hearts of Iron IV'], 'еу': ['Europa Universalis IV'], 'стелларис': ['Stellaris'], 'крусейдер': ['Crusader Kings III'], 'ресидент': ['Resident Evil 4'], 'сайлент': ['Silent Hill 2'], 'хоррор': ['Horror'], 'фнаф': ["Five Nights at Freddy's"], 'летал': ['Lethal Company'], 'контент': ['Content Warning'], 'исаак': ['The Binding of Isaac'], 'хадес': ['Hades'], 'холлоу': ['Hollow Knight'], 'селеста': ['Celeste'], 'капхед': ['Cuphead'], 'андертейл': ['Undertale'], 'дельтарун': ['Deltarune'], 'стардью': ['Stardew Valley'], 'портал': ['Portal 2'], 'халфлайф': ['Half-Life'], 'биошок': ['BioShock'], 'дишоноред': ['Dishonored'], 'прей': ['Prey'], 'хитман': ['Hitman 3'], 'асасин': ["Assassin's Creed"], 'фаркрай': ['Far Cry'], 'радуга': ['Rainbow Six Siege'], 'дивизион': ['The Division 2'], 'нба': ['NBA 2K'], 'формула': ['F1 24'], 'форза': ['Forza Horizon 5'], 'гранд': ['Gran Turismo 7'], 'нфс': ['Need for Speed'], 'флайт': ['Microsoft Flight Simulator'], 'мортал': ['Mortal Kombat'], 'стрит': ['Street Fighter 6'], 'теккен': ['Tekken 8'], 'смешбросы': ['Super Smash Bros. Ultimate'], 'покемон': ['Pokémon'], 'зельда': ['The Legend of Zelda'], 'марио': ['Super Mario'], 'сплатун': ['Splatoon 3'], 'метроид': ['Metroid'], 'байонетта': ['Bayonetta'], 'финалка': ['Final Fantasy XIV'], 'моник': ['Monster Hunter'], 'персона': ['Persona'], 'якудза': ['Yakuza'], 'нир': ['NieR: Automata'], 'блэк': ['Black Desert Online'], 'лост': ['Lost Ark'], 'нью': ['New World'], 'рунескейп': ['Old School RuneScape', 'RuneScape'], 'общение': ['Just Chatting', 'Говорим и смотрим', 'Разговоры', 'Talk Shows & Podcasts'], 'разговоры': ['Just Chatting', 'Говорим и смотрим', 'Talk Shows & Podcasts'], 'болталка': ['Just Chatting', 'Говорим и смотрим'], 'чат': ['Just Chatting', 'Говорим и смотрим'], 'музыка': ['Music', 'Музыка'], 'творчество': ['Art', 'Creative', 'Творчество', 'Makers & Crafting'], 'готовка': ['Cooking', 'Готовим', 'Food & Drink', 'Кулинария'], 'готовим': ['Cooking', 'Готовим', 'Кулинария'], 'еда': ['Food & Drink', 'Cooking', 'Кулинария'], 'кулинария': ['Food & Drink', 'Cooking', 'Кулинария'], 'искусство': ['Art', 'Искусство', 'Creative', 'Творчество'], 'рисование': ['Art', 'Искусство', 'Digital Art', 'Творчество'], 'игры': ['Gaming', 'Games', 'Игры', 'Retro', 'Slots'], 'реальная': ['IRL', 'Реальная жизнь'], 'жизнь': ['IRL', 'Реальная жизнь'], 'ирл': ['IRL', 'Реальная жизнь'], 'спорт': ['Sports', 'Спорт'], 'фитнес': ['Fitness & Health'], 'азартные': ['Slots', 'Casino', 'Азартные игры', 'Poker'], 'казино': ['Slots', 'Casino', 'Азартные игры'], 'слоты': ['Slots', 'Азартные игры'], 'покер': ['Poker', 'Азартные игры'], 'шахматы': ['Chess', 'Шахматы', 'Интеллектуальные игры'], 'интеллектуальные': ['Chess', 'Интеллектуальные игры'], 'наука': ['Science & Technology', 'Технологии'], 'технологии': ['Science & Technology', 'Технологии'], 'путешествия': ['Travel & Outdoors', 'Путешествия'], 'путешествие': ['Travel & Outdoors', 'Путешествия'], 'природа': ['Travel & Outdoors', 'Путешествия'], 'мероприятия': ['Special Events', 'Мероприятия'], 'события': ['Special Events', 'Мероприятия'], 'аниме': ['Anime'], 'асмр': ['ASMR', 'АСМР'], 'красота': ['Beauty'], 'подкаст': ['Podcasts', 'Talk Shows & Podcasts', 'Говорим и смотрим'], 'chatting': ['Just Chatting', 'Говорим и смотрим', 'Talk Shows & Podcasts'], 'just': ['Just Chatting', 'Говорим и смотрим'], 'chat': ['Just Chatting', 'Говорим и смотрим'], 'talking': ['Just Chatting', 'Говорим и смотрим', 'Talk Shows & Podcasts'], 'music': ['Music', 'Музыка'], 'creative': ['Creative', 'Art', 'Творчество'], 'cooking': ['Cooking', 'Готовим', 'Food & Drink', 'Кулинария'], 'food': ['Food & Drink', 'Кулинария', 'Cooking'], 'drink': ['Food & Drink', 'Кулинария'], 'art': ['Art', 'Искусство', 'Creative', 'Творчество'], 'digital': ['Digital Art', 'Творчество'], 'makers': ['Makers & Crafting', 'Творчество'], 'crafting': ['Makers & Crafting', 'Творчество'], 'gaming': ['Gaming', 'Игры', 'Games'], 'games': ['Gaming', 'Игры', 'Games'], 'irl': ['IRL', 'Реальная жизнь'], 'sports': ['Sports', 'Спорт'], 'fitness': ['Fitness & Health'], 'health': ['Fitness & Health'], 'slots': ['Slots', 'Азартные игры'], 'casino': ['Slots', 'Casino', 'Азартные игры'], 'poker': ['Poker', 'Азартные игры'], 'chess': ['Chess', 'Шахматы', 'Интеллектуальные игры'], 'science': ['Science & Technology', 'Технологии'], 'technology': ['Science & Technology', 'Технологии'], 'tech': ['Science & Technology', 'Технологии'], 'travel': ['Travel & Outdoors', 'Путешествия'], 'outdoors': ['Travel & Outdoors', 'Путешествия'], 'special': ['Special Events', 'Мероприятия'], 'events': ['Special Events', 'Мероприятия'], 'anime': ['Anime'], 'asmr': ['ASMR', 'АСМР'], 'beauty': ['Beauty'], 'podcast': ['Podcasts', 'Talk Shows & Podcasts', 'Говорим и смотрим'], 'talk': ['Talk Shows & Podcasts', 'Говорим и смотрим']}

def expand_query_with_aliases(query: str) -> List[str]:
    """
    Расширяет поисковый запрос с учётом алиасов.
    
    Args:
        query: Исходный запрос (например, "dbd", "общение", "rdr2")
        
    Returns:
        Список запросов для поиска (исходный + все варианты из алиасов)
        
    Examples:
        >>> expand_query_with_aliases("dbd")
        ["dbd", "Dead by Daylight"]
        
        >>> expand_query_with_aliases("общение")
        ["общение", "Just Chatting", "Говорим и смотрим"]
    """
    queries = [query]
    normalized_query = query.lower().strip()
    if normalized_query in CATEGORY_ALIASES:
        queries.extend(CATEGORY_ALIASES[normalized_query])
    return queries

def calculate_relevance(category_name: str, query: str) -> float:
    """
    Вычисляет релевантность категории для запроса.
    Чем меньше score, тем выше релевантность.
    
    Args:
        category_name: Название категории
        query: Поисковый запрос
        
    Returns:
        Число от 0 (идеальное совпадение) до 100 (нерелевантно)
    """
    cat_lower = category_name.lower()
    query_lower = query.lower()
    if cat_lower == query_lower:
        return 0
    if cat_lower.startswith(query_lower):
        return 1
    cat_words = [w for w in re.split(r'[\\s\\-:]+', cat_lower) if len(w) > 0]
    query_words = [w for w in re.split(r'[\\s\\-:]+', query_lower) if len(w) > 0]
    all_words_match = True
    exact_word_matches = 0
    partial_word_matches = 0
    for query_word in query_words:
        found_match = False
        for cat_word in cat_words:
            if cat_word == query_word:
                exact_word_matches += 1
                found_match = True
                break
            elif cat_word.startswith(query_word) or query_word.startswith(cat_word):
                partial_word_matches += 1
                found_match = True
                break
            elif query_word in cat_word:
                found_match = True
                break
        if not found_match:
            all_words_match = False
    if exact_word_matches == len(query_words):
        query_pattern = '[\\s\\-:]+'.join(query_words)
        if re.search(query_pattern, category_name, re.IGNORECASE):
            return 1.5
        return 2
    if all_words_match:
        return 3 + (len(query_words) - exact_word_matches) * 0.5
    best_word_match = 100
    for query_word in query_words:
        for (i, cat_word) in enumerate(cat_words):
            if cat_word == query_word:
                best_word_match = min(best_word_match, 5 + i * 0.5)
            elif cat_word.startswith(query_word):
                best_word_match = min(best_word_match, 6 + i * 0.5)
            elif query_word.startswith(cat_word) and len(cat_word) >= 3:
                best_word_match = min(best_word_match, 7 + i * 0.5)
            elif query_word in cat_word:
                best_word_match = min(best_word_match, 10 + i * 0.5)
    if best_word_match < 100:
        return best_word_match
    if query_lower in cat_lower:
        return 15
    match_count = 0
    last_index = -1
    for char in query_lower:
        index = cat_lower.find(char, last_index + 1)
        if index > last_index:
            match_count += 1
            last_index = index
    fuzzy_score = match_count / len(query_lower) if len(query_lower) > 0 else 0
    if fuzzy_score > 0.8:
        return 20
    if fuzzy_score > 0.6:
        return 25
    if fuzzy_score > 0.4:
        return 30
    return 100

def sort_categories_by_relevance(categories: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Сортирует категории по релевантности к запросу.
    
    Args:
        categories: Список категорий с полями 'id', 'name', и т.д.
        query: Поисковый запрос
        
    Returns:
        Отсортированный список категорий (от самой релевантной к наименее)
    """
    if not query or not query.strip():
        return categories

    def sort_key(cat):
        relevance = calculate_relevance(cat.get('name', ''), query)
        name = cat.get('name', '')
        return (relevance, name)
    return sorted(categories, key=sort_key)

def find_best_category_match(categories: List[Dict[str, Any]], query: str) -> Optional[Dict[str, Any]]:
    """
    Находит наиболее подходящую категорию для запроса.
    Используется для команд !category, !game в чате.
    
    Args:
        categories: Список доступных категорий
        query: Запрос от пользователя (может быть сокращением или переводом)
        
    Returns:
        Наиболее подходящая категория или None
        
    Examples:
        >>> categories = [{"id": "1", "name": "Dead by Daylight"}, ...]
        >>> find_best_category_match(categories, "dbd")
        {"id": "1", "name": "Dead by Daylight"}
    """
    if not categories:
        return None
    sorted_cats = sort_categories_by_relevance(categories, query)
    if sorted_cats:
        best_match = sorted_cats[0]
        relevance = calculate_relevance(best_match.get('name', ''), query)
        if relevance < 50:
            return best_match
    return None
