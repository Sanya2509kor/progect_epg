import os
import re
from typing import Dict, List, Optional

class ConfigLoader:
    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        self.channels_id: Dict[str, str] = {}
        self.channels_names: Dict[str, str] = {}
        self.channels_numbers: Dict[str, str] = {}
        self.channels_active: Dict[str, bool] = {}
        self.auto_replace: Dict[str, str] = {}
        self.auto_replace_epg: Dict[str, str] = {}
        self.film_list: List[Dict[str, str]] = []
        self.ratings: Dict[str, str] = {}
        
        self._load_all()
    
    def _load_all(self):
        # Загружаем из единого файла channel_config.txt
        self._load_channel_config()
        
        # Загружаем остальные файлы
        self._load_key_value("avtozamena.txt", self.auto_replace)
        self._load_key_value("avtozamenaEPG.txt", self.auto_replace_epg)
        self._load_film_list()
        self._load_ratings()
    
    def _load_channel_config(self):
        """Загружает каналы из channel_config.txt"""
        path = os.path.join(self.data_dir, "channel_config.txt")
        if not os.path.exists(path):
            print(f"⚠️ Файл channel_config.txt не найден. Создайте его через Управление каналами")
            return
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('|')
                    if len(parts) >= 3:  # минимум: xml_name|display_name|number
                        xml_name = parts[0].strip()
                        display_name = parts[1].strip() if len(parts) > 1 else xml_name
                        number = parts[2].strip() if len(parts) > 2 else ""
                        active = True
                        if len(parts) >= 4:
                            active = parts[3].strip().lower() == 'true'
                        
                        self.channels_id[xml_name] = display_name
                        self.channels_names[xml_name] = display_name
                        if number:
                            self.channels_numbers[xml_name] = number
                        self.channels_active[xml_name] = active
            print(f"✅ Загружено {len(self.channels_numbers)} каналов из channel_config.txt")
        except Exception as e:
            print(f"⚠️ Ошибка загрузки channel_config.txt: {e}")
    
    def save_channel_config(self):
        """Сохраняет конфигурацию каналов в channel_config.txt"""
        path = os.path.join(self.data_dir, "channel_config.txt")
        try:
            # Собираем все каналы
            all_channels = set(self.channels_names.keys()) | set(self.channels_numbers.keys())
            
            with open(path, 'w', encoding='utf-8') as f:
                f.write("# Название из week|Название для вывода|Номер канала|Активен\n")
                for channel in sorted(all_channels):
                    display_name = self.channels_names.get(channel, channel)
                    number = self.channels_numbers.get(channel, "")
                    active = self.channels_active.get(channel, True)
                    f.write(f"{channel}|{display_name}|{number}|{active}\n")
            print(f"✅ Сохранен channel_config.txt ({len(all_channels)} каналов)")
        except Exception as e:
            print(f"⚠️ Ошибка сохранения channel_config.txt: {e}")
    
    def _load_key_value(self, filename: str, target_dict: Dict):
        """Загружает файлы с автодетектом кодировки"""
        path = os.path.join(self.data_dir, filename)
        if not os.path.exists(path):
            print(f"⚠️ Файл не найден: {filename}")
            return
        
        encodings = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        if '=' in line:
                            key, value = line.split('=', 1)
                            target_dict[key.strip()] = value.strip()
                print(f"✅ Загружен {filename} (кодировка: {encoding})")
                return
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # Если ничего не помогло
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if '=' in line:
                        key, value = line.split('=', 1)
                        target_dict[key.strip()] = value.strip()
            print(f"⚠️ Загружен {filename} (с пропуском ошибок)")
        except Exception as e:
            print(f"❌ Не удалось загрузить {filename}: {e}")
    
    def _load_film_list(self):
        """Загружает список фильмов из Новый текстовый документ.txt"""
        path = os.path.join(self.data_dir, "Новый текстовый документ.txt")
        if not os.path.exists(path):
            return
        
        encodings = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(';')
                        if len(parts) >= 3:
                            self.film_list.append({
                                'type': parts[0].strip(),
                                'name': parts[1].strip('"'),
                                'rating': parts[2].strip()
                            })
                print(f"✅ Загружен Новый текстовый документ.txt (кодировка: {encoding})")
                return
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(';')
                    if len(parts) >= 3:
                        self.film_list.append({
                            'type': parts[0].strip(),
                            'name': parts[1].strip('"'),
                            'rating': parts[2].strip()
                        })
            print(f"⚠️ Загружен Новый текстовый документ.txt (с пропуском ошибок)")
        except Exception as e:
            print(f"❌ Не удалось загрузить Новый текстовый документ.txt: {e}")
    
    def _load_ratings(self):
        """Загружает рейтинги из raiting.txt"""
        path = os.path.join(self.data_dir, "raiting.txt")
        if not os.path.exists(path):
            return
        
        encodings = ['utf-8', 'cp1251', 'windows-1251', 'koi8-r']
        
        for encoding in encodings:
            try:
                with open(path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                    if len(lines) > 1:  # Пропускаем заголовок
                        for line in lines[1:]:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split(';')
                            if len(parts) >= 3:
                                self.ratings[parts[1].strip()] = parts[2].strip()
                print(f"✅ Загружен raiting.txt (кодировка: {encoding})")
                return
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                if len(lines) > 1:
                    for line in lines[1:]:
                        line = line.strip()
                        if not line:
                            continue
                        parts = line.split(';')
                        if len(parts) >= 3:
                            self.ratings[parts[1].strip()] = parts[2].strip()
            print(f"⚠️ Загружен raiting.txt (с пропуском ошибок)")
        except Exception as e:
            print(f"❌ Не удалось загрузить raiting.txt: {e}")
    
    def get_channel_id(self, name: str) -> str:
        return self.channels_id.get(name, "")
    
    def get_channel_name(self, name: str) -> str:
        return self.channels_names.get(name, name)
    
    def get_channel_number(self, name: str) -> str:
        return self.channels_numbers.get(name, "")
    
    def is_channel_active(self, name: str) -> bool:
        """Проверяет, активен ли канал"""
        return self.channels_active.get(name, False)
    
    def get_active_channels(self) -> Dict[str, str]:
        """Возвращает словарь активных каналов с их номерами"""
        return {ch: num for ch, num in self.channels_numbers.items() if self.is_channel_active(ch)}
    
    def get_rating(self, title: str) -> str:
        """Получает рейтинг для названия из raiting.txt"""
        if not title:
            return ""
        for name, rating in self.ratings.items():
            if name and (name in title or title in name):
                return rating
        return ""
    
    def replace_name(self, name: str) -> str:
        """Применяет все замены к названию"""
        if not name:
            return ""
        
        # Сначала замены из auto_replace_epg (специальные для EPG)
        for old, new in self.auto_replace_epg.items():
            if old and old in name:
                name = name.replace(old, new)
        
        # Затем общие замены из auto_replace
        for old, new in self.auto_replace.items():
            if old and old in name:
                name = name.replace(old, new)
        
        # Заменяем <NL> на перенос строки
        if '<NL>' in name:
            name = name.replace('<NL>', '\n')
        
        return name
    
    def is_valid_program(self, title: str) -> bool:
        """Проверяет, является ли программа валидной"""
        if not title or title.strip() == '':
            return False
        
        # Список пустых/мусорных названий
        invalid_titles = [
            'Х/ф', 'Т/с', 'М/ф',
            'Х/ф Х/ф', 'Х/ф Х/ф Х/ф',
            'Т/с Т/с', 'М/ф М/ф',
            'Х/ф  ', '  Х/ф'
        ]
        
        title_clean = title.strip()
        if title_clean in invalid_titles:
            return False
        
        # Если название слишком короткое (меньше 3 символов)
        if len(title_clean) < 3:
            return False
        
        return True