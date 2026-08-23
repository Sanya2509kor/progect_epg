import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re


class EPGParser:
    def __init__(self, config: 'ConfigLoader'):
        self.config = config
        self.channel_map: Dict[str, str] = {}  # id -> display-name
        self.day_offset = 0
    
    def parse_week_xml(self, xml_path: str) -> Dict[str, List[Dict]]:
        """Парсит XMLTV файл и возвращает программы по каналам"""
        print(f"📂 Парсинг {xml_path}...")
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except Exception as e:
            raise Exception(f"Ошибка парсинга XML: {e}")
        
        # Собираем соответствие ID канала -> display-name
        for channel in root.findall('channel'):
            channel_id = channel.get('id')
            display_name = channel.find('display-name')
            if display_name is not None:
                self.channel_map[channel_id] = display_name.text
        
        programs_by_channel: Dict[str, List[Dict]] = {}
        total = 0
        skipped = 0
        
        for programme in root.findall('programme'):
            channel_id = programme.get('channel')
            start_time = programme.get('start')
            stop_time = programme.get('stop')
            
            # Получаем название
            title_elem = programme.find('title')
            title = title_elem.text if title_elem is not None else ""
            
            # Пропускаем пустые программы
            if not title or title.strip() == '':
                skipped += 1
                continue
            
            # Применяем замены
            title = self.config.replace_name(title)
            
            # Пропускаем мусорные программы
            if not self.config.is_valid_program(title):
                skipped += 1
                continue
            
            # Получаем рейтинг
            rating = self.config.get_rating(title)
            if not rating:
                rating_elem = programme.find('rating')
                if rating_elem is not None:
                    value = rating_elem.find('value')
                    if value is not None:
                        rating = value.text
            
            # Добавляем + к рейтингу если его нет
            if rating and rating.isdigit():
                rating = f"{rating}+"
            
            # Получаем название канала
            # Используем channel_id как основное имя (оно будет в столбце "Название (week.xml)")
            channel_name = channel_id  # <-- ИСПОЛЬЗУЕМ ID, А НЕ DISPLAY-NAME
            
            # ===== ПОЛУЧАЕМ НОМЕР СЕРИИ ИЗ SUB-TITLE =====
            sub_title_elem = programme.find('sub-title')
            sub_title = sub_title_elem.text if sub_title_elem is not None else ""
            
            episode_num = None
            desc = self._get_description(programme)
            
            # 1. Ищем в sub-title (самый надежный источник)
            if sub_title:
                episode_match = re.search(r'(\d+)-я\s*серия', sub_title, re.IGNORECASE)
                if episode_match:
                    episode_num = episode_match.group(1)
                else:
                    episode_match = re.search(r'(?:серия|c\.|эпизод)\s*(\d+)', sub_title, re.IGNORECASE)
                    if episode_match:
                        episode_num = episode_match.group(1)
                    else:
                        episode_match = re.search(r'(\d+)\s*(?:серия|с\.|c\.|эпизод)', sub_title, re.IGNORECASE)
                        if episode_match:
                            episode_num = episode_match.group(1)
            
            # 2. Если не нашли в sub-title — ищем в названии
            if not episode_num:
                episode_match = re.search(r'(?:серия|c\.|эпизод|episode|series|season)\s*(\d+)', title, re.IGNORECASE)
                if episode_match:
                    episode_num = episode_match.group(1)
                else:
                    episode_match = re.search(r'(\d+)\s*(?:серия|с\.|c\.|эпизод)', title, re.IGNORECASE)
                    if episode_match:
                        episode_num = episode_match.group(1)
            
            # 3. Если не нашли — ищем в описании
            if not episode_num and desc:
                episode_match = re.search(r'(?:серия|c\.|эпизод)\s*(\d+)', desc, re.IGNORECASE)
                if episode_match:
                    episode_num = episode_match.group(1)
            
            # ===== ДОБАВЛЯЕМ НОМЕР СЕРИИ В ФОРМАТЕ "N с." =====
            if episode_num:
                # Убираем старые форматы если они есть
                title = re.sub(r'\s*c\.\s*\d+', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*серия\s*\d+', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*\([^)]*серия[^)]*\)', '', title, flags=re.IGNORECASE)
                # Добавляем в формате "номер с."
                title = f"{title} {episode_num} с."
            
            program_data = {
                'start': start_time,
                'stop': stop_time,
                'channel': channel_name,  # Это channel_id
                'channel_id': channel_id,
                'display_name': self.channel_map.get(channel_id, channel_id),  # Сохраняем display-name для отображения
                'title': title,
                'rating': rating or '',
                'description': desc,
                'sub_title': sub_title,
                'date': start_time[:8] if start_time else ''
            }
            
            if channel_name not in programs_by_channel:
                programs_by_channel[channel_name] = []
            programs_by_channel[channel_name].append(program_data)
            total += 1
        
        # ===== ДОБАВЛЯЕМ АВТОМАТИЧЕСКУЮ НУМЕРАЦИЮ ДЛЯ ПРОГРАММ БЕЗ НОМЕРА =====
        programs_by_channel = self._add_episode_numbers(programs_by_channel)
        
        print(f"✅ Загружено {len(programs_by_channel)} каналов, {total} программ (пропущено {skipped})")
        return programs_by_channel
    
    def _add_episode_numbers(self, programs_by_channel: Dict) -> Dict:
        """Добавляет номера серий для повторяющихся программ без номеров"""
        for channel, programs in programs_by_channel.items():
            # Сортируем по времени
            programs.sort(key=lambda x: x.get('start', ''))
            
            # Считаем повторяющиеся названия без номеров
            title_counter = {}
            for prog in programs:
                title = prog.get('title', '')
                # Пропускаем если уже есть номер серии
                if re.search(r'\d+\s*с\.', title, re.IGNORECASE):
                    continue
                # Проверяем, является ли это сериалом (есть sub-title с серией или повторяется)
                sub_title = prog.get('sub_title', '')
                is_series = bool(re.search(r'серия', sub_title, re.IGNORECASE)) if sub_title else False
                
                # Если есть sub-title с серией — считаем что это сериал
                if not is_series:
                    # Если название повторяется больше 2 раз — это сериал
                    count = sum(1 for p in programs if p.get('title', '') == title and not re.search(r'\d+\s*с\.', p.get('title', ''), re.IGNORECASE))
                    if count <= 2:
                        continue
                
                if title in title_counter:
                    title_counter[title] += 1
                    # Проверяем, не добавили ли уже номер
                    if not re.search(r'\d+\s*с\.', prog['title'], re.IGNORECASE):
                        prog['title'] = f"{title} {title_counter[title]} с."
                else:
                    title_counter[title] = 1
        return programs_by_channel
    
    def _get_description(self, programme) -> str:
        desc = programme.find('desc')
        return desc.text if desc is not None else ""
    
    def filter_by_date(self, programs_by_channel: Dict, date: datetime) -> Dict:
        """Фильтрует программы по конкретной дате"""
        date_str = date.strftime('%Y%m%d')
        filtered = {}
        
        for channel, programs in programs_by_channel.items():
            filtered_programs = []
            for prog in programs:
                start = prog.get('start', '')
                if start.startswith(date_str):
                    filtered_programs.append(prog)
            if filtered_programs:
                filtered[channel] = filtered_programs
        
        return filtered
    
    def filter_by_week(self, programs_by_channel: Dict, start_date: datetime) -> Dict:
        """Фильтрует программы на неделю (7 дней)"""
        filtered = {}
        date_strs = []
        
        for i in range(7):
            date = start_date + timedelta(days=i)
            date_strs.append(date.strftime('%Y%m%d'))
        
        for channel, programs in programs_by_channel.items():
            filtered_programs = []
            for prog in programs:
                start = prog.get('start', '')
                for date_str in date_strs:
                    if start.startswith(date_str):
                        filtered_programs.append(prog)
                        break
            if filtered_programs:
                filtered[channel] = filtered_programs
        
        return filtered
    
    def filter_by_channels(self, programs_by_channel: Dict, selected_channels: List[str]) -> Dict:
        """Фильтрует программы по выбранным каналам"""
        return {ch: prog for ch, prog in programs_by_channel.items() if ch in selected_channels}
    
    def format_time(self, time_str: str) -> str:
        """Форматирует время для CSV: ДДЧЧММ"""
        if not time_str or len(time_str) < 12:
            return ""
        day = time_str[6:8]
        hhmm = time_str[8:12]
        return f"{day}{hhmm}"
    
    def detect_category(self, title: str) -> str:
        """Определяет категорию программы с добавлением слэша"""
        if not title:
            return "Х/ф"
        
        # Проверяем по списку фильмов
        for film in self.config.film_list:
            if film['name'] in title and film['type']:
                ctg = film['type']
                if ctg == 'Хф':
                    ctg = 'Х/ф'
                elif ctg == 'Тс':
                    ctg = 'Т/с'
                elif ctg == 'Мф':
                    ctg = 'М/ф'
                return ctg
        
        # Автоопределение
        title_lower = title.lower()
        if "т/с" in title_lower or "серия" in title_lower or "сезон" in title_lower:
            return "Т/с"
        elif "м/ф" in title_lower or "м/с" in title_lower:
            return "М/ф"
        elif "х/ф" in title_lower:
            return "Х/ф"
        else:
            return "Х/ф"
    
    def get_program_day(self, program: Dict) -> str:
        """Возвращает день недели для программы"""
        start = program.get('start', '')
        if len(start) >= 8:
            try:
                dt = datetime.strptime(start[:8], '%Y%m%d')
                return dt.strftime('%d.%m.%Y')
            except:
                pass
        return ''