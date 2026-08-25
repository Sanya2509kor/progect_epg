import os
import sys
import re
from datetime import datetime, timedelta

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QMessageBox, QProgressBar, QTextEdit,
    QGroupBox, QSplitter, QComboBox,
    QApplication, QTimeEdit
)
from PySide6.QtCore import Qt, QThread, Signal, QTime
from PySide6.QtGui import QFont, QTextCursor


class ParseThread(QThread):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(int)
    log = Signal(str)
    
    def __init__(self, xml_path: str):
        super().__init__()
        self.xml_path = xml_path
        self.config = None
        self.parser = None
    
    def run(self):
        try:
            self.log.emit("📂 Загрузка конфигурации...")
            from config_loader import ConfigLoader
            from parser import EPGParser
            self.config = ConfigLoader("data")
            self.parser = EPGParser(self.config)
            
            self.log.emit(f"📂 Парсинг {self.xml_path}...")
            self.progress.emit(30)
            
            programs = self.parser.parse_week_xml(self.xml_path)
            
            self.progress.emit(60)
            total = sum(len(v) for v in programs.values())
            self.log.emit(f"✅ Загружено {len(programs)} каналов, {total} программ")
            
            self.progress.emit(100)
            self.finished.emit({
                'all_programs': programs,
                'config': self.config,
                'parser': self.parser,
                'total': total
            })
            
        except Exception as e:
            self.error.emit(str(e))


class SaveThread(QThread):
    finished = Signal(str)
    error = Signal(str)
    log = Signal(str)
    
    def __init__(self, data, filename: str, save_type: str, 
                 start_date: datetime = None, 
                 time_start: str = "09:00", 
                 time_end: str = "24:00",
                 selected_channels: list = None,
                 sort_mode: str = "week"):
        super().__init__()
        self.data = data
        self.filename = filename
        self.save_type = save_type
        self.start_date = start_date or datetime.now()
        self.time_start = time_start
        self.time_end = time_end
        self.selected_channels = selected_channels or []
        self.sort_mode = sort_mode  # 'week', 'alphabet', 'channel'
    
    def run(self):
        try:
            os.makedirs("output", exist_ok=True)
            path = os.path.join("output", self.filename)
            
            if self.save_type == 'csv_week':
                self._save_csv_week(path)
            elif self.save_type == 'info_day':
                self._save_info_day(path)
            
            self.finished.emit(path)
            
        except Exception as e:
            self.error.emit(str(e))
    
    def _get_sorted_channels(self, programs: dict) -> list:
        """Возвращает список каналов, отсортированных согласно выбранному режиму"""
        config = self.data['config']
        
        # Получаем список каналов
        channels = list(programs.keys())
        
        if self.sort_mode == "alphabet":
            # Сортировка по алфавиту (по отображаемому имени)
            channels.sort(key=lambda x: config.get_channel_name(x).lower())
        elif self.sort_mode == "channel":
            # Сортировка по номеру канала
            channels.sort(key=lambda x: int(config.get_channel_number(x)) if config.get_channel_number(x) and config.get_channel_number(x).isdigit() else 9999)
        # else: "week" - сохраняем порядок как в programs (из XML)
        
        return channels
    
    def _get_filtered_programs(self):
        programs = self.data['all_programs']
        if self.selected_channels:
            return {ch: prog for ch, prog in programs.items() if ch in self.selected_channels}
        return programs
    
    def _save_csv_week(self, path: str):
        programs = self._get_filtered_programs()
        config = self.data['config']
        parser = self.data['parser']
        
        # Получаем отсортированный список каналов
        sorted_channels = self._get_sorted_channels(programs)
        
        with open(path, 'w', encoding='windows-1251') as f:
            f.write("Start;Stop;Chanel;Num;Ctg;NameSer;Ratio\n")
            
            for channel_id in sorted_channels:
                prog_list = programs.get(channel_id, [])
                if not prog_list:
                    continue
                    
                display_name = config.get_channel_name(channel_id)
                if not display_name or display_name == channel_id:
                    display_name = channel_id
                
                channel_num = config.get_channel_number(channel_id) or "0"
                sorted_progs = sorted(prog_list, key=lambda x: x.get('start', ''))
                
                for prog in sorted_progs:
                    start = parser.format_time(prog.get('start', ''))
                    stop = parser.format_time(prog.get('stop', ''))
                    title = prog.get('title', '').replace(';', ',')
                    rating = prog.get('rating', '')
                    ctg = prog.get('category', '')
                    if ctg:
                        ctg = self._fix_category(ctg)
                    rating = self._fix_rating(rating)
                    
                    if ctg:
                        f.write(f"{start};{stop};{display_name};{channel_num};{ctg};{title};{rating}\n")
                    else:
                        f.write(f"{start};{stop};{display_name};{channel_num};;{title};{rating}\n")
    
    def _save_info_day(self, path: str):
        programs = self._get_filtered_programs()
        parser = self.data['parser']
        config = self.data['config']
        date = self.start_date
        
        start_minutes = self._time_to_minutes(self.time_start)
        end_minutes = self._time_to_minutes(self.time_end)
        if end_minutes == 0:
            end_minutes = 1440
        
        date_str = date.strftime('%Y%m%d')
        
        months = {
            '01': 'января', '02': 'февраля', '03': 'марта',
            '04': 'апреля', '05': 'мая', '06': 'июня',
            '07': 'июля', '08': 'августа', '09': 'сентября',
            '10': 'октября', '11': 'ноября', '12': 'декабря'
        }
        month_num = date.strftime('%m')
        date_display = f"{date.strftime('%d')} {months.get(month_num, '')}"
        
        # Разрешенные категории для FD_info
        allowed_categories = ['Х/ф', 'Т/с', 'М/ф', 'М/с']
        
        # Получаем отсортированный список каналов
        sorted_channels = self._get_sorted_channels(programs)
        
        # Словарь для подсчета программ без рейтинга ТОЛЬКО среди разрешенных категорий
        channels_without_rating = {}
        
        with open(path, 'w', encoding='windows-1251') as f:
            for channel_id in sorted_channels:
                prog_list = programs.get(channel_id, [])
                if not prog_list:
                    continue
                    
                display_name = config.get_channel_name(channel_id)
                if not display_name or display_name == channel_id:
                    display_name = channel_id
                
                channel_num = config.get_channel_number(channel_id) or "0"
                
                filtered_progs = []
                for prog in prog_list:
                    start = prog.get('start', '')
                    if not start.startswith(date_str):
                        continue
                    
                    if len(start) >= 12:
                        hours = int(start[8:10])
                        minutes = int(start[10:12])
                        prog_minutes = hours * 60 + minutes
                        
                        if start_minutes <= prog_minutes < end_minutes:
                            filtered_progs.append(prog)
                
                if not filtered_progs:
                    continue
                
                filtered_progs.sort(key=lambda x: x.get('start', ''))
                
                prog_lines = []
                for prog in filtered_progs:
                    time = self._format_time_for_info(prog.get('start', ''))
                    title = prog.get('title', '')
                    rating = prog.get('rating', '')
                    
                    ctg = prog.get('category', '')
                    
                    # Проверка: есть ли категория
                    if not ctg:
                        continue
                    
                    # Нормализуем категорию для сравнения
                    ctg_normalized = ctg
                    if ctg in ['Хф', 'Х/ф']:
                        ctg_normalized = 'Х/ф'
                    elif ctg in ['Тс', 'Т/с']:
                        ctg_normalized = 'Т/с'
                    elif ctg in ['Мф', 'М/ф']:
                        ctg_normalized = 'М/ф'
                    elif ctg in ['Мс', 'М/с']:
                        ctg_normalized = 'М/с'
                    
                    # Проверяем, разрешена ли категория
                    if ctg_normalized not in allowed_categories:
                        continue
                    
                    # Проверяем рейтинг ТОЛЬКО для программ, которые попадут в FD_info
                    if not rating or rating.strip() == '' or rating == '[]':
                        if channel_id not in channels_without_rating:
                            channels_without_rating[channel_id] = []
                        if title not in [p['title'] for p in channels_without_rating[channel_id]]:
                            channels_without_rating[channel_id].append({
                                'title': title,
                                'time': prog.get('start', '')
                            })
                    
                    ctg = self._fix_category(ctg)
                    rating = self._fix_rating(rating)
                    
                    title = self._clean_text(title)
                    prog_lines.append(f"{time} {ctg} {title} {rating}")
                
                # Если после фильтрации нет программ - пропускаем канал
                if not prog_lines:
                    continue
                
                programs_str = "<NL>".join(prog_lines)
                line = f"<ST6><AC>На канале {display_name} ({channel_num})<NL>{date_display}<NL><NL>{programs_str}"
                f.write(line + "\n")
        
        # Выводим лог ТОЛЬКО по программам, которые попали в FD_info
        if channels_without_rating:
            self.log.emit("")
            self.log.emit("⚠️ ВНИМАНИЕ! В сгенерированном FD_info.txt есть программы без рейтинга:")
            self.log.emit("=" * 50)
            total_without_rating = 0
            for channel_id, progs in channels_without_rating.items():
                display_name = config.get_channel_name(channel_id)
                if not display_name or display_name == channel_id:
                    display_name = channel_id
                self.log.emit(f"📺 {display_name} — {len(progs)} программ без рейтинга")
                for i, prog in enumerate(progs[:3]):
                    time_str = self._format_time_for_log(prog['time'])
                    self.log.emit(f"   {time_str} {prog['title']}")
                if len(progs) > 3:
                    self.log.emit(f"   ... и еще {len(progs) - 3} программ")
                total_without_rating += len(progs)
            self.log.emit("=" * 50)
            self.log.emit(f"📊 Всего программ без рейтинга в FD_info: {total_without_rating}")
            self.log.emit("")
        else:
            self.log.emit("✅ Все программы в FD_info имеют рейтинг")
        
        # Дополнительная информация: сколько всего каналов и программ записано
        self.log.emit(f"📄 Сохранено {len([c for c in sorted_channels if c in programs])} каналов в FD_info.txt")
        
        print(f"✅ Сохранен INFO файл: {path}")
    
    def _format_time_for_log(self, time_str: str) -> str:
        if not time_str or len(time_str) < 12:
            return ""
        hours = time_str[8:10]
        minutes = time_str[10:12]
        return f"{hours}:{minutes}"
    
    def _fix_category(self, ctg: str) -> str:
        if not ctg:
            return ""
        if '/' in ctg:
            return ctg
        if ctg == 'Хф' or ctg == 'Хф ':
            return 'Х/ф'
        elif ctg == 'Тс' or ctg == 'Тс ':
            return 'Т/с'
        elif ctg == 'Мф' or ctg == 'Мф ':
            return 'М/ф'
        if len(ctg) == 2:
            if ctg[1] == 'ф':
                return f"{ctg[0]}/ф"
            elif ctg[1] == 'с':
                return f"{ctg[0]}/с"
        return ctg
    
    def _fix_rating(self, rating: str) -> str:
        if not rating:
            return "[]"
        rating_clean = rating.strip('[]')
        if rating_clean and rating_clean.isdigit():
            return f"[{rating_clean}+]"
        if rating_clean and rating_clean.endswith('+'):
            return f"[{rating_clean}]"
        if rating_clean:
            return f"[{rating_clean}]"
        return "[]"

    def _clean_text(self, text: str) -> str:
        if not text:
            return ""
        replacements = {
            '\u2014': '-', '\u2013': '-',
            '\u201c': '"', '\u201d': '"',
            '\u2018': "'", '\u2019': "'",
            '\u00ab': '"', '\u00bb': '"',
            '\u2026': '...',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r'[^\w\s\-\.\,\:\;\(\)\[\]\"\'\?\!]', '', text)
        return text
    
    def _format_time_for_info(self, time_str: str) -> str:
        if not time_str or len(time_str) < 14:
            return ""
        hours = time_str[8:10]
        minutes = time_str[10:12]
        return f"{hours}:{minutes}"
    
    def _time_to_minutes(self, time_str: str) -> int:
        try:
            if ':' in time_str:
                parts = time_str.split(':')
                hours = int(parts[0])
                minutes = int(parts[1]) if len(parts) > 1 else 0
                return hours * 60 + minutes
            else:
                return int(time_str)
        except:
            return 0


class TimeSelector(QWidget):
    time_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        layout.addWidget(QLabel("Время:"))
        layout.addWidget(QLabel("с"))
        self.time_start = QTimeEdit()
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setTime(QTime(9, 0))
        self.time_start.timeChanged.connect(self._on_time_changed)
        layout.addWidget(self.time_start)
        
        layout.addWidget(QLabel("до"))
        self.time_end = QTimeEdit()
        self.time_end.setDisplayFormat("HH:mm")
        self.time_end.setTime(QTime(23, 59))
        self.time_end.timeChanged.connect(self._on_time_changed)
        layout.addWidget(self.time_end)
        
        layout.addStretch()
    
    def _on_time_changed(self):
        self.time_changed.emit()
    
    def get_time_start(self) -> str:
        return self.time_start.time().toString("HH:mm")
    
    def get_time_end(self) -> str:
        return self.time_end.time().toString("HH:mm")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📺 EPG Parser v2.0")
        self.setGeometry(100, 100, 1100, 800)
        
        self.data = None
        self.config = None
        self.parser = None
        self.programs = None
        self.parse_thread = None
        self.save_thread = None
        self.channel_manager_window = None
        self._is_loading = False
        self._channels_loaded = False
        
        self._init_ui()
        self._load_config()
    
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(10)
        
        top_layout = QHBoxLayout()
        self.file_edit = QLineEdit("data/week.xml")
        self.file_edit.setMinimumWidth(400)
        self.file_edit.setReadOnly(True)
        top_layout.addWidget(QLabel("XML файл:"))
        top_layout.addWidget(self.file_edit)
        
        self.browse_btn = QPushButton("📂 Обзор")
        self.browse_btn.clicked.connect(self._browse_file)
        top_layout.addWidget(self.browse_btn)
        
        top_layout.addStretch()
        main_layout.addLayout(top_layout)
        
        info_date_layout = QHBoxLayout()
        info_date_layout.addWidget(QLabel("Дата для INFO:"))
        
        self.btn_info_yesterday = QPushButton("Вчера")
        self.btn_info_yesterday.clicked.connect(lambda: self._set_info_date(-1))
        info_date_layout.addWidget(self.btn_info_yesterday)
        
        self.btn_info_today = QPushButton("Сегодня")
        self.btn_info_today.clicked.connect(lambda: self._set_info_date(0))
        info_date_layout.addWidget(self.btn_info_today)
        
        self.btn_info_tomorrow = QPushButton("Завтра")
        self.btn_info_tomorrow.clicked.connect(lambda: self._set_info_date(1))
        info_date_layout.addWidget(self.btn_info_tomorrow)
        
        self.info_date_edit = QLineEdit()
        self.info_date_edit.setPlaceholderText("ДД.ММ.ГГГГ")
        self.info_date_edit.setMaximumWidth(120)
        info_date_layout.addWidget(self.info_date_edit)
        
        self.set_info_date_btn = QPushButton("Установить")
        self.set_info_date_btn.clicked.connect(self._set_custom_info_date)
        info_date_layout.addWidget(self.set_info_date_btn)
        
        info_date_layout.addStretch()
        main_layout.addLayout(info_date_layout)
        
        self._set_info_date(1)
        
        time_layout = QHBoxLayout()
        self.time_selector = TimeSelector()
        time_layout.addWidget(self.time_selector)
        time_layout.addStretch()
        main_layout.addLayout(time_layout)
        
        # Строка с сортировкой
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("📊 Сортировка каналов:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["по week (как в XML)", "по алфавиту", "по номеру канала"])
        self.sort_combo.setCurrentIndex(0)
        self.sort_combo.setToolTip("Выберите порядок сортировки каналов в выходных файлах")
        sort_layout.addWidget(self.sort_combo)
        sort_layout.addStretch()
        main_layout.addLayout(sort_layout)
        
        actions_layout = QHBoxLayout()
        
        self.load_btn = QPushButton("📂 Загрузить week.xml")
        self.load_btn.clicked.connect(self._load_xml)
        actions_layout.addWidget(self.load_btn)
        
        self.save_csv_btn = QPushButton("💾 Сохранить FD_onair(неделя)")
        self.save_csv_btn.clicked.connect(self._save_csv_week)
        self.save_csv_btn.setEnabled(False)
        actions_layout.addWidget(self.save_csv_btn)
        
        self.save_info_btn = QPushButton("📄 Сохранить FD_INFO(день)")
        self.save_info_btn.clicked.connect(self._save_info_day)
        self.save_info_btn.setEnabled(False)
        actions_layout.addWidget(self.save_info_btn)
        
        self.save_all_btn = QPushButton("📁 Сохранить всё")
        self.save_all_btn.clicked.connect(self._save_all)
        self.save_all_btn.setEnabled(False)
        actions_layout.addWidget(self.save_all_btn)
        
        # self.edit_info_btn = QPushButton("📝 Редактировать FD_info")
        # self.edit_info_btn.clicked.connect(self._open_editor)
        # self.edit_info_btn.setEnabled(False)
        # actions_layout.addWidget(self.edit_info_btn)
        
        self.manage_channels_btn = QPushButton("📡 Управление каналами")
        self.manage_channels_btn.clicked.connect(self._open_channel_manager)
        self.manage_channels_btn.setEnabled(True)
        actions_layout.addWidget(self.manage_channels_btn)
        
        actions_layout.addStretch()
        main_layout.addLayout(actions_layout)
        
        progress_layout = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(200)
        progress_layout.addWidget(self.progress)
        
        self.status_label = QLabel("Готово")
        progress_layout.addWidget(self.status_label)
        progress_layout.addStretch()
        main_layout.addLayout(progress_layout)
        
        log_group = QGroupBox("📋 Лог")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        log_layout.addWidget(self.log_text)
        
        main_layout.addWidget(log_group)
    
    def _get_sort_mode(self) -> str:
        """Возвращает режим сортировки из выпадающего списка"""
        index = self.sort_combo.currentIndex()
        if index == 0:
            return "week"
        elif index == 1:
            return "alphabet"
        else:
            return "channel"
    
    def _open_channel_manager(self):
        from channel_manager import show_channel_manager
        channels_from_xml = self.programs if self.programs else {}
        self.channel_manager_window = show_channel_manager(self.config, channels_from_xml, self)
        self.channel_manager_window.channels_updated.connect(self._on_channels_updated)
    
    def _on_channels_updated(self):
        self._update_channel_info()
        self._log("✅ Список каналов обновлен")
    
    def _update_channel_info(self):
        if not self.config:
            return
        
        active_channels = self.config.get_active_channels()
        total_channels = len(self.config.channels_numbers) if self.config.channels_numbers else 0
        
        self._log(f"📡 Активных каналов: {len(active_channels)} из {total_channels}")
        
        if active_channels:
            self._channels_loaded = True
            self.save_csv_btn.setEnabled(True)
            self.save_info_btn.setEnabled(True)
            self.save_all_btn.setEnabled(True)
            # self.edit_info_btn.setEnabled(True)
        else:
            self._channels_loaded = False
            self.save_csv_btn.setEnabled(False)
            self.save_info_btn.setEnabled(False)
            self.save_all_btn.setEnabled(False)
    
    def _open_editor(self):
        info_path = os.path.join("output", "FD_info.txt")
        if not os.path.exists(info_path):
            QMessageBox.warning(self, "Ошибка", f"Файл не найден:\n{info_path}\n\nСначала сохраните FD_info")
            return
        import subprocess
        subprocess.Popen([sys.executable, "info_editor.py", info_path])
    
    def _load_config(self):
        try:
            self._is_loading = True
            from config_loader import ConfigLoader
            from parser import EPGParser
            self.config = ConfigLoader("data")
            self.parser = EPGParser(self.config)
            
            self._update_channel_info()
            
            self._log("✅ Конфигурация загружена")
            self._is_loading = False
        except Exception as e:
            self._is_loading = False
            self._log(f"❌ Ошибка загрузки конфигурации: {e}")
    
    def _browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите week.xml",
            "",
            "XML files (*.xml);;All files (*.*)"
        )
        if path:
            self.file_edit.setText(path)
    
    def _set_info_date(self, offset: int):
        dt = datetime.now() + timedelta(days=offset)
        self.info_date_edit.setText(dt.strftime("%d.%m.%Y"))
    
    def _set_custom_info_date(self):
        date_str = self.info_date_edit.text()
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
            self._log(f"📅 Дата для INFO: {date_str}")
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Неверный формат даты!\nИспользуйте ДД.ММ.ГГГГ")
            self._set_info_date(1)
    
    def _get_info_date(self) -> datetime:
        date_str = self.info_date_edit.text()
        try:
            return datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            self._set_info_date(1)
            return datetime.strptime(self.info_date_edit.text(), "%d.%m.%Y")
    
    def _log(self, message: str):
        self.log_text.append(message)
        cursor = self.log_text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)
        QApplication.processEvents()
    
    def _load_xml(self):
        path = self.file_edit.text()
        if not os.path.exists(path):
            QMessageBox.warning(self, "Ошибка", f"Файл не найден: {path}")
            return
        
        self.load_btn.setEnabled(False)
        self.status_label.setText("Загрузка...")
        
        self.parse_thread = ParseThread(path)
        self.parse_thread.log.connect(self._log)
        self.parse_thread.progress.connect(self.progress.setValue)
        self.parse_thread.finished.connect(self._on_parse_finished)
        self.parse_thread.error.connect(self._on_parse_error)
        self.parse_thread.start()
    
    def _on_parse_finished(self, data):
        self._is_loading = True
        self.data = data
        self.programs = data['all_programs']
        self.config = data['config']
        self.parser = data['parser']
        
        self.manage_channels_btn.setEnabled(True)
        self.load_btn.setEnabled(True)
        
        self._update_channel_info()
        
        total = sum(len(v) for v in self.programs.values())
        self.status_label.setText(f"Загружено {len(self.programs)} каналов, {total} программ")
        self.progress.setValue(100)
        
        self._log(f"✅ Загружено {len(self.programs)} каналов, {total} программ")
        
        self._is_loading = False
        self.parse_thread = None
        
        if self.channel_manager_window:
            self.channel_manager_window.channels_from_xml = self.programs or {}
            self.channel_manager_window._load_data()
            self.channel_manager_window._update_table()
            self.channel_manager_window._update_info()
    
    def _on_parse_error(self, error_msg):
        self.load_btn.setEnabled(True)
        self.status_label.setText("Ошибка")
        self._log(f"❌ Ошибка: {error_msg}")
        QMessageBox.critical(self, "Ошибка", error_msg)
        self.parse_thread = None
    
    def _save_csv_week(self):
        if not self.data:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите week.xml")
            return
        
        # Получаем ТОЛЬКО активные каналы
        selected_channels = list(self.config.get_active_channels().keys())
        if not selected_channels:
            QMessageBox.warning(self, "Ошибка", "Нет активных каналов. Откройте Управление каналами и включите каналы")
            return
        
        sort_mode = self._get_sort_mode()
        sort_names = {"week": "по week", "alphabet": "по алфавиту", "channel": "по номеру"}
        
        # Используем выбранную пользователем дату для имени файла
        info_date = self._get_info_date()
        date_str = info_date.strftime("%d.%m.%Y")
        filename = f"FD_onairweek{date_str.replace('.', '')}.csv"
        
        self.status_label.setText(f"Сохранение {filename}...")
        self._log(f"📅 Дата для CSV: {date_str}")
        self._log(f"📊 Сортировка CSV: {sort_names.get(sort_mode, 'по week')}")
        
        self.save_thread = SaveThread(
            self.data, filename, 'csv_week',
            selected_channels=selected_channels,
            sort_mode=sort_mode
        )
        self.save_thread.log.connect(self._log)
        self.save_thread.finished.connect(lambda path: self._on_save_finished(path, filename))
        self.save_thread.error.connect(self._on_save_error)
        self.save_thread.start()
    
    def _save_info_day(self):
        if not self.data:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите week.xml")
            return
        
        selected_channels = list(self.config.get_active_channels().keys())
        if not selected_channels:
            QMessageBox.warning(self, "Ошибка", "Нет активных каналов. Откройте Управление каналами и включите каналы")
            return
        
        sort_mode = self._get_sort_mode()
        sort_names = {"week": "по week", "alphabet": "по алфавиту", "channel": "по номеру"}
        
        filename = "FD_info.txt"
        info_date = self._get_info_date()
        time_start = self.time_selector.get_time_start()
        time_end = self.time_selector.get_time_end()
        
        self.status_label.setText(f"Сохранение {filename}...")
        self._log(f"📊 Сортировка: {sort_names.get(sort_mode, 'по week')}")
        
        self.save_thread = SaveThread(
            self.data, filename, 'info_day',
            start_date=info_date,
            time_start=time_start,
            time_end=time_end,
            selected_channels=selected_channels,
            sort_mode=sort_mode
        )
        self.save_thread.log.connect(self._log)
        self.save_thread.finished.connect(lambda path: self._on_save_finished(path, filename))
        self.save_thread.error.connect(self._on_save_error)
        self.save_thread.start()
    
    def _save_all(self):
        """Сохраняет оба файла"""
        if not self.data:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите week.xml")
            return
        
        # Проверяем наличие активных каналов
        selected_channels = list(self.config.get_active_channels().keys())
        if not selected_channels:
            QMessageBox.warning(self, "Ошибка", "Нет активных каналов. Откройте Управление каналами и включите каналы")
            return
        
        sort_mode = self._get_sort_mode()
        sort_names = {"week": "по week", "alphabet": "по алфавиту", "channel": "по номеру"}
        self._log(f"📊 Сортировка для обоих файлов: {sort_names.get(sort_mode, 'по week')}")
        
        self._save_csv_week()
        import time
        time.sleep(0.5)
        self._save_info_day()
    
    def _on_save_finished(self, path: str, filename: str):
        self.status_label.setText(f"Сохранено: {filename}")
        self._log(f"💾 Сохранен {filename}")
        QMessageBox.information(self, "Готово", f"Файл сохранен:\n{path}")
        self.save_thread = None
    
    def _on_save_error(self, error_msg):
        self.status_label.setText("Ошибка сохранения")
        self._log(f"❌ Ошибка сохранения: {error_msg}")
        QMessageBox.critical(self, "Ошибка", error_msg)
        self.save_thread = None