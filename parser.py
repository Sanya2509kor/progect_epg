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
            
            # Коррекция часового пояса
            start_time = self._fix_timezone(start_time)
            stop_time = self._fix_timezone(stop_time)
            
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
            
            # Получаем категорию из XML
            category = ""
            category_elem = programme.find('category')
            if category_elem is not None and category_elem.text:
                category = category_elem.text.strip()
                if category in ['Хф', 'Х/ф']:
                    category = 'Х/ф'
                elif category in ['Тс', 'Т/с']:
                    category = 'Т/с'
                elif category in ['Мф', 'М/ф']:
                    category = 'М/ф'
            
            # Получаем рейтинг
            rating = self.config.get_rating(title)
            if not rating:
                rating_elem = programme.find('rating')
                if rating_elem is not None:
                    value = rating_elem.find('value')
                    if value is not None:
                        rating = value.text
            
            if rating and rating.isdigit():
                rating = f"{rating}+"
            
            channel_name = channel_id
            
            # ===== ПОЛУЧАЕМ НОМЕР СЕРИИ ИЗ SUB-TITLE (ТОЛЬКО ЕСЛИ ЕСТЬ В XML) =====
            sub_title_elem = programme.find('sub-title')
            sub_title = sub_title_elem.text if sub_title_elem is not None else ""
            
            # Номер серии берем ТОЛЬКО из sub-title, если он там есть
            episode_num = None
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
            
            # НЕ ищем в названии и описании - только в sub-title!
            # Это гарантирует, что номера серий будут только там, где они есть в исходном XML
            
            # ===== ДОБАВЛЯЕМ НОМЕР СЕРИИ ЕСЛИ НАШЛИ =====
            if episode_num:
                # Убираем старые форматы если они есть
                title = re.sub(r'\s*c\.\s*\d+', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*серия\s*\d+', '', title, flags=re.IGNORECASE)
                title = re.sub(r'\s*\([^)]*серия[^)]*\)', '', title, flags=re.IGNORECASE)
                title = f"{title} {episode_num} с."
            
            program_data = {
                'start': start_time,
                'stop': stop_time,
                'channel': channel_name,
                'channel_id': channel_id,
                'display_name': self.channel_map.get(channel_id, channel_id),
                'title': title,
                'category': category,
                'rating': rating or '',
                'description': desc if 'desc' in locals() else '',
                'sub_title': sub_title,
                'date': start_time[:8] if start_time else ''
            }
            
            if channel_name not in programs_by_channel:
                programs_by_channel[channel_name] = []
            programs_by_channel[channel_name].append(program_data)
            total += 1
        
        # ===== УБИРАЕМ АВТОМАТИЧЕСКУЮ НУМЕРАЦИЮ =====
        # Больше не добавляем номера серий автоматически
        
        print(f"✅ Загружено {len(programs_by_channel)} каналов, {total} программ (пропущено {skipped})")
        return programs_by_channel
    
    def _fix_timezone(self, time_str: str) -> str:
        """Исправляет часовой пояс на красноярский (UTC+7)"""
        if not time_str:
            return time_str
        
        match = re.match(r'(\d{14})\s*([+-]\d{4})?', time_str)
        if not match:
            return time_str
        
        dt_str = match.group(1)
        tz_str = match.group(2) or '+0300'
        
        try:
            dt = datetime.strptime(dt_str, '%Y%m%d%H%M%S')
            
            if tz_str:
                tz_hours = int(tz_str[1:3])
                tz_minutes = int(tz_str[3:5])
                if tz_str[0] == '-':
                    tz_hours = -tz_hours
                tz_offset = timedelta(hours=tz_hours, minutes=tz_minutes)
            else:
                tz_offset = timedelta(hours=3)
            
            dt_utc = dt - tz_offset
            dt_kras = dt_utc + timedelta(hours=7)
            
            return dt_kras.strftime('%Y%m%d%H%M%S') + ' +0700'
            
        except Exception as e:
            print(f"⚠️ Ошибка преобразования времени {time_str}: {e}")
            return time_str
    
    def _get_description(self, programme) -> str:
        desc = programme.find('desc')
        return desc.text if desc is not None else ""
    
    def filter_by_date(self, programs_by_channel: Dict, date: datetime) -> Dict:
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
        return {ch: prog for ch, prog in programs_by_channel.items() if ch in selected_channels}
    
    def format_time(self, time_str: str) -> str:
        """Форматирует время для CSV: ДДЧЧММ"""
        if not time_str or len(time_str) < 14:
            return ""
        day = time_str[6:8]
        hhmm = time_str[8:12]
        return f"{day}{hhmm}"
    
    def detect_category(self, title: str) -> str:
        if not title:
            return ""
        
        for film in self.config.film_list:
            if film['name'] in title and film['type']:
                ctg = film['type']
                if ctg == 'Хф':
                    return 'Х/ф'
                elif ctg == 'Тс':
                    return 'Т/с'
                elif ctg == 'Мф':
                    return 'М/ф'
                return ctg
        
        title_lower = title.lower()
        if "т/с" in title_lower or "серия" in title_lower or "сезон" in title_lower:
            return "Т/с"
        elif "м/ф" in title_lower or "м/с" in title_lower:
            return "М/ф"
        elif "х/ф" in title_lower:
            return "Х/ф"
        else:
            return ""
    
    def get_program_day(self, program: Dict) -> str:
        start = program.get('start', '')
        if len(start) >= 8:
            try:
                dt = datetime.strptime(start[:8], '%Y%m%d')
                return dt.strftime('%d.%m.%Y')
            except:
                pass
        return ''