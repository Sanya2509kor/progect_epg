import os
import sys
import re
from datetime import datetime
from typing import List, Dict, Optional
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QFileDialog,
    QMessageBox, QSplitter, QListWidget, QListWidgetItem,
    QGroupBox, QScrollArea, QFrame,
    QApplication, QPlainTextEdit, QTextBrowser, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QTextCursor, QPainter, QColor, QPen


class Page:
    """Класс для хранения данных одной страницы"""
    def __init__(self, channel: str = "", channel_num: str = "", date: str = "", 
                 programs: List[str] = None, is_duplicate: bool = False):
        self.channel = channel
        self.channel_num = channel_num
        self.date = date
        self.programs = programs or []
        self.is_duplicate = is_duplicate
    
    def to_text(self) -> str:
        """Преобразует страницу в текст с тегами"""
        if not self.channel:
            return ""
        programs_text = "<NL>".join(self.programs)
        return f"<ST6><AC>На канале {self.channel} ({self.channel_num})<NL>{self.date}<NL><NL>{programs_text}"
    
    @classmethod
    def from_text(cls, text: str) -> 'Page':
        """Создает страницу из текста"""
        lines = text.split('<NL>')
        
        channel = ""
        channel_num = ""
        date = ""
        programs = []
        
        for i, line in enumerate(lines):
            if i == 0:
                # Убираем <ST6><AC> и парсим
                line_clean = re.sub(r'<ST6><AC>', '', line)
                match = re.search(r'На канале (.+?) \((\d+)\)', line_clean)
                if match:
                    channel = match.group(1).strip()
                    channel_num = match.group(2).strip()
            elif i == 1:
                date = line.strip()
            elif i >= 3:
                if line.strip():
                    programs.append(line.strip())
        
        return cls(channel=channel, channel_num=channel_num, date=date, programs=programs)


class PagePreview(QWidget):
    """Виджет для предпросмотра страницы"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = Page()
        self.setMinimumHeight(300)
        self.setStyleSheet("""
            PagePreview {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 5px;
            }
        """)
    
    def set_page(self, page: Page):
        self.page = page
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Белый фон
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        
        # Рамка страницы
        margin = 15
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        painter.drawRect(rect)
        
        # Настройки шрифтов
        header_font = QFont("Arial", 13, QFont.Bold)
        date_font = QFont("Arial", 11)
        prog_font = QFont("Consolas", 10)
        
        y = rect.top() + 15
        x = rect.left() + 15
        width = rect.width() - 30
        
        # Заголовок - по центру
        channel_text = self.page.channel if self.page.channel else "Название канала"
        header_text = f"На канале {channel_text} ({self.page.channel_num or '00'})"
        
        painter.setFont(header_font)
        header_width = painter.fontMetrics().horizontalAdvance(header_text)
        header_x = rect.left() + (rect.width() - header_width) // 2
        painter.drawText(header_x, y, header_text)
        y += 30
        
        # Дата - по центру
        date_text = self.page.date if self.page.date else "Дата"
        painter.setFont(date_font)
        date_width = painter.fontMetrics().horizontalAdvance(date_text)
        date_x = rect.left() + (rect.width() - date_width) // 2
        painter.drawText(date_x, y, date_text)
        y += 30
        
        # Разделительная линия
        painter.setPen(QPen(QColor(200, 200, 200), 1, Qt.DashLine))
        painter.drawLine(rect.left() + 15, y, rect.right() - 15, y)
        y += 20
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        
        # Программы
        painter.setFont(prog_font)
        
        if self.page.programs:
            for prog in self.page.programs:
                prog_display = prog
                if painter.fontMetrics().horizontalAdvance(prog_display) > width:
                    while painter.fontMetrics().horizontalAdvance(prog_display + "...") > width:
                        prog_display = prog_display[:-1]
                    prog_display += "..."
                
                painter.drawText(x, y, prog_display)
                y += 22
        else:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(x, y, "(нет программ)")
        
        # Счетчик программ внизу
        painter.setPen(QColor(150, 150, 150))
        painter.setFont(QFont("Arial", 8))
        count_text = f"Всего программ: {len(self.page.programs)}"
        painter.drawText(rect.left() + 10, rect.bottom() - 10, count_text)


class PageEditor(QWidget):
    """Виджет для редактирования одной страницы"""
    content_changed = Signal()
    page_removed = Signal(int)
    page_duplicated = Signal(int)
    
    def __init__(self, page: Page, page_index: int, parent=None):
        super().__init__(parent)
        self.page = page
        self.page_index = page_index
        self.is_readonly = False
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # Заголовок
        header = QHBoxLayout()
        self.title_label = QLabel(f"📄 Страница {self.page_index + 1}")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header.addWidget(self.title_label)
        header.addStretch()
        
        self.dup_btn = QPushButton("📋 Дублировать")
        self.dup_btn.setFixedWidth(120)
        self.dup_btn.clicked.connect(lambda: self.page_duplicated.emit(self.page_index))
        header.addWidget(self.dup_btn)
        
        self.del_btn = QPushButton("🗑️ Удалить")
        self.del_btn.setFixedWidth(80)
        self.del_btn.setStyleSheet("color: red;")
        self.del_btn.clicked.connect(lambda: self.page_removed.emit(self.page_index))
        header.addWidget(self.del_btn)
        
        layout.addLayout(header)
        
        # Основной сплиттер
        splitter = QSplitter(Qt.Horizontal)
        
        # Левая панель - редактор
        edit_panel = QWidget()
        edit_layout = QVBoxLayout(edit_panel)
        edit_layout.setContentsMargins(0, 0, 5, 0)
        edit_layout.setSpacing(3)
        
        # Название канала
        edit_layout.addWidget(QLabel("Название канала:"))
        self.channel_edit = QTextEdit()
        self.channel_edit.setPlaceholderText("Название канала")
        self.channel_edit.setMaximumHeight(30)
        self.channel_edit.setFont(QFont("Arial", 10))
        self.channel_edit.textChanged.connect(self._on_content_changed)
        edit_layout.addWidget(self.channel_edit)
        
        # Номер канала
        num_layout = QHBoxLayout()
        num_layout.addWidget(QLabel("Номер:"))
        self.num_edit = QTextEdit()
        self.num_edit.setPlaceholderText("Номер")
        self.num_edit.setMaximumHeight(30)
        self.num_edit.setMaximumWidth(80)
        self.num_edit.setFont(QFont("Arial", 10))
        self.num_edit.textChanged.connect(self._on_content_changed)
        num_layout.addWidget(self.num_edit)
        num_layout.addStretch()
        edit_layout.addLayout(num_layout)
        
        # Дата
        edit_layout.addWidget(QLabel("Дата:"))
        self.date_edit = QTextEdit()
        self.date_edit.setPlaceholderText("Дата (например: 10 августа)")
        self.date_edit.setMaximumHeight(30)
        self.date_edit.setFont(QFont("Arial", 10))
        self.date_edit.textChanged.connect(self._on_content_changed)
        edit_layout.addWidget(self.date_edit)
        
        # Программы
        edit_layout.addWidget(QLabel("Программы (каждая с новой строки):"))
        self.programs_edit = QPlainTextEdit()
        self.programs_edit.setFont(QFont("Consolas", 10))
        self.programs_edit.setPlaceholderText(
            "Введите программы (каждая с новой строки)\n"
            "Пример:\n"
            "09:00 Х/ф Название [12+]\n"
            "10:30 Т/с Название серии [16+]"
        )
        self.programs_edit.textChanged.connect(self._on_content_changed)
        edit_layout.addWidget(self.programs_edit)
        
        # Счетчик
        self.prog_count_label = QLabel("Всего программ: 0")
        self.prog_count_label.setStyleSheet("color: gray; font-size: 9px;")
        edit_layout.addWidget(self.prog_count_label)
        
        splitter.addWidget(edit_panel)
        
        # Правая панель - предпросмотр
        preview_panel = QWidget()
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(5, 0, 0, 0)
        
        preview_layout.addWidget(QLabel("📄 Предпросмотр:"))
        self.preview = PagePreview()
        preview_layout.addWidget(self.preview)
        
        splitter.addWidget(preview_panel)
        splitter.setSizes([550, 450])
        
        layout.addWidget(splitter)
        
        # Загружаем данные страницы
        self._load_page()
    
    def _load_page(self):
        """Загружает данные страницы в поля редактирования"""
        self.channel_edit.setText(self.page.channel)
        self.num_edit.setText(self.page.channel_num)
        self.date_edit.setText(self.page.date)
        self.programs_edit.setPlainText("\n".join(self.page.programs))
        self._update_count()
        self.preview.set_page(self.page)
    
    def _update_count(self):
        count = len(self.get_programs())
        self.prog_count_label.setText(f"Всего программ: {count}")
    
    def _on_content_changed(self):
        """Обновляет данные при изменении"""
        self.page.channel = self.channel_edit.toPlainText().strip()
        self.page.channel_num = self.num_edit.toPlainText().strip()
        self.page.date = self.date_edit.toPlainText().strip()
        self.page.programs = self.get_programs()
        self._update_count()
        self.preview.set_page(self.page)
        self.content_changed.emit()
    
    def get_programs(self) -> List[str]:
        text = self.programs_edit.toPlainText()
        return [p.strip() for p in text.split('\n') if p.strip()]
    
    def get_page(self) -> Page:
        self.page.channel = self.channel_edit.toPlainText().strip()
        self.page.channel_num = self.num_edit.toPlainText().strip()
        self.page.date = self.date_edit.toPlainText().strip()
        self.page.programs = self.get_programs()
        return self.page
    
    def set_readonly(self, readonly: bool):
        self.is_readonly = readonly
        self.channel_edit.setReadOnly(readonly)
        self.num_edit.setReadOnly(readonly)
        self.date_edit.setReadOnly(readonly)
        self.programs_edit.setReadOnly(readonly)
        self.dup_btn.setEnabled(not readonly)
        self.del_btn.setEnabled(not readonly)


class InfoEditorWindow(QMainWindow):
    """Главное окно редактора FD_info"""
    
    def __init__(self, filepath: str = None):
        super().__init__()
        self.setWindowTitle("📄 Редактор FD_info")
        self.setGeometry(100, 100, 1300, 800)
        
        self.filepath = filepath
        self.pages: List[Page] = []
        self.current_page_index = 0
        self.is_readonly = False
        
        self._init_ui()
        
        if filepath and os.path.exists(filepath):
            self.load_file(filepath)
    
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # Левая панель - список страниц
        left_panel = QWidget()
        left_panel.setFixedWidth(250)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(5)
        
        left_layout.addWidget(QLabel("📑 Страницы:"))
        
        self.page_list = QListWidget()
        self.page_list.itemSelectionChanged.connect(self._on_page_selected)
        self.page_list.setFont(QFont("Arial", 10))
        left_layout.addWidget(self.page_list)
        
        # Кнопки управления
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(3)
        
        self.add_page_btn = QPushButton("➕ Добавить")
        self.add_page_btn.clicked.connect(self._add_empty_page)
        btn_layout.addWidget(self.add_page_btn)
        
        self.move_up_btn = QPushButton("⬆")
        self.move_up_btn.setFixedWidth(30)
        self.move_up_btn.clicked.connect(self._move_page_up)
        btn_layout.addWidget(self.move_up_btn)
        
        self.move_down_btn = QPushButton("⬇")
        self.move_down_btn.setFixedWidth(30)
        self.move_down_btn.clicked.connect(self._move_page_down)
        btn_layout.addWidget(self.move_down_btn)
        
        left_layout.addLayout(btn_layout)
        
        # Информация
        info_frame = QGroupBox("Информация")
        info_layout = QVBoxLayout(info_frame)
        self.total_pages_label = QLabel("Всего страниц: 0")
        info_layout.addWidget(self.total_pages_label)
        self.total_channels_label = QLabel("Всего каналов: 0")
        info_layout.addWidget(self.total_channels_label)
        left_layout.addWidget(info_frame)
        
        # Кнопки сохранения
        save_btn_layout = QVBoxLayout()
        self.save_btn = QPushButton("💾 Сохранить")
        self.save_btn.clicked.connect(self.save_file)
        save_btn_layout.addWidget(self.save_btn)
        
        self.save_as_btn = QPushButton("💾 Сохранить как...")
        self.save_as_btn.clicked.connect(self.save_file_as)
        save_btn_layout.addWidget(self.save_as_btn)
        
        self.readonly_cb = QCheckBox("Только чтение")
        self.readonly_cb.stateChanged.connect(self._toggle_readonly)
        save_btn_layout.addWidget(self.readonly_cb)
        
        left_layout.addLayout(save_btn_layout)
        main_layout.addWidget(left_panel)
        
        # Центральная панель - редактор
        self.page_editor_container = QWidget()
        self.page_editor_layout = QVBoxLayout(self.page_editor_container)
        self.page_editor_layout.setContentsMargins(0, 0, 0, 0)
        
        self.placeholder_label = QLabel("Выберите страницу для редактирования")
        self.placeholder_label.setAlignment(Qt.AlignCenter)
        self.placeholder_label.setStyleSheet("color: gray; font-size: 16px;")
        self.page_editor_layout.addWidget(self.placeholder_label)
        
        self.current_editor: Optional[PageEditor] = None
        
        main_layout.addWidget(self.page_editor_container, 1)
        
        # Статус бар
        self.status_label = QLabel("Готово")
        self.status_label.setStyleSheet("color: gray; padding: 5px;")
        main_layout.addWidget(self.status_label)
        
        self.setStyleSheet("""
            QTextEdit, QPlainTextEdit {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
                background-color: white;
            }
            QListWidget::item:selected {
                background: #0078D7;
                color: white;
            }
            QPushButton {
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
    
    def _get_russian_date(self) -> str:
        """Возвращает текущую дату на русском"""
        months = {
            'January': 'января', 'February': 'февраля', 'March': 'марта',
            'April': 'апреля', 'May': 'мая', 'June': 'июня',
            'July': 'июля', 'August': 'августа', 'September': 'сентября',
            'October': 'октября', 'November': 'ноября', 'December': 'декабря'
        }
        date_str = datetime.now().strftime("%d %B")
        for eng, rus in months.items():
            if eng in date_str:
                date_str = date_str.replace(eng, rus)
                break
        return date_str
    
    def _add_empty_page(self):
        page = Page(
            channel="Новый канал",
            channel_num="",
            date=self._get_russian_date(),
            programs=[]
        )
        self.pages.append(page)
        self._refresh_page_list()
        self._select_page(len(self.pages) - 1)
        self._update_info()
    
    def _remove_page(self, index: int):
        if len(self.pages) <= 1:
            QMessageBox.warning(self, "Предупреждение", "Нельзя удалить последнюю страницу")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить страницу {index + 1}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self.pages[index]
            self._refresh_page_list()
            if index >= len(self.pages):
                index = len(self.pages) - 1
            self._select_page(index)
            self._update_info()
    
    def _duplicate_page(self, index: int):
        page = self.pages[index]
        new_page = Page(
            channel=page.channel,
            channel_num=page.channel_num,
            date=page.date,
            programs=page.programs.copy()
        )
        if not new_page.channel.endswith("(продолжение)"):
            new_page.channel = f"{new_page.channel} (продолжение)"
        
        self.pages.insert(index + 1, new_page)
        self._refresh_page_list()
        self._select_page(index + 1)
        self._update_info()
    
    def _move_page_up(self):
        index = self.page_list.currentRow()
        if index > 0:
            self.pages[index], self.pages[index - 1] = self.pages[index - 1], self.pages[index]
            self._refresh_page_list()
            self._select_page(index - 1)
            self._update_info()
    
    def _move_page_down(self):
        index = self.page_list.currentRow()
        if 0 <= index < len(self.pages) - 1:
            self.pages[index], self.pages[index + 1] = self.pages[index + 1], self.pages[index]
            self._refresh_page_list()
            self._select_page(index + 1)
            self._update_info()
    
    def _refresh_page_list(self):
        self.page_list.clear()
        for i, page in enumerate(self.pages, 1):
            display_text = page.channel if page.channel else f"Страница {i}"
            if len(display_text) > 30:
                display_text = display_text[:27] + "..."
            
            if page.is_duplicate:
                display_text = f"📋 {display_text} (прод.)"
            else:
                display_text = f"📄 {display_text}"
            
            prog_count = len(page.programs)
            if prog_count > 0:
                display_text += f" [{prog_count}]"
            
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, i - 1)
            self.page_list.addItem(item)
        
        self.total_pages_label.setText(f"Всего страниц: {len(self.pages)}")
    
    def _select_page(self, index: int):
        if 0 <= index < len(self.pages):
            self.page_list.setCurrentRow(index)
            self._show_page(index)
    
    def _on_page_selected(self):
        index = self.page_list.currentRow()
        if index >= 0:
            self._show_page(index)
    
    def _show_page(self, index: int):
        if index < 0 or index >= len(self.pages):
            return
        
        self.current_page_index = index
        page = self.pages[index]
        
        # Очищаем контейнер
        while self.page_editor_layout.count():
            child = self.page_editor_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Создаем редактор с данными страницы
        editor = PageEditor(page, index)
        editor.content_changed.connect(self._on_content_changed)
        editor.page_removed.connect(self._remove_page)
        editor.page_duplicated.connect(self._duplicate_page)
        editor.set_readonly(self.is_readonly)
        
        self.current_editor = editor
        self.page_editor_layout.addWidget(editor)
        
        self.status_label.setText(f"Страница {index + 1} из {len(self.pages)}")
    
    def _on_content_changed(self):
        if self.current_editor:
            index = self.current_page_index
            if 0 <= index < len(self.pages):
                self.pages[index] = self.current_editor.get_page()
                self._update_page_list_item(index)
    
    def _update_page_list_item(self, index: int):
        if 0 <= index < len(self.pages):
            page = self.pages[index]
            display_text = page.channel if page.channel else f"Страница {index + 1}"
            if len(display_text) > 30:
                display_text = display_text[:27] + "..."
            
            if page.is_duplicate:
                display_text = f"📋 {display_text} (прод.)"
            else:
                display_text = f"📄 {display_text}"
            
            prog_count = len(page.programs)
            if prog_count > 0:
                display_text += f" [{prog_count}]"
            
            self.page_list.item(index).setText(display_text)
    
    def _update_info(self):
        channels = set()
        for page in self.pages:
            if page.channel:
                channels.add(page.channel)
        self.total_channels_label.setText(f"Всего каналов: {len(channels)}")
        self.total_pages_label.setText(f"Всего страниц: {len(self.pages)}")
    
    def _toggle_readonly(self, state):
        self.is_readonly = bool(state)
        if self.current_editor:
            self.current_editor.set_readonly(self.is_readonly)
    
    def load_file(self, filepath: str):
        """Загружает файл FD_info.txt"""
        self.filepath = filepath
        self.pages = []
        
        try:
            # ⚠️ ИСПРАВЛЕНО: пробуем разные кодировки
            encodings = ['windows-1251', 'utf-8', 'cp1251']
            content = None
            used_encoding = None
            
            for encoding in encodings:
                try:
                    with open(filepath, 'r', encoding=encoding) as f:
                        content = f.read()
                    used_encoding = encoding
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if content is None:
                raise Exception("Не удалось определить кодировку файла")
            
            print(f"✅ Файл загружен в кодировке: {used_encoding}")
            
            # Разбиваем на страницы по тегу <ST6><AC>
            page_texts = re.split(r'(?=<ST6><AC>)', content)
            page_texts = [p.strip() for p in page_texts if p.strip()]
            
            for text in page_texts:
                page = Page.from_text(text)
                # Сохраняем даже если нет номера — главное чтобы было название
                if page.channel:
                    self.pages.append(page)
                elif page.programs:
                    # Если нет названия, но есть программы — создаем страницу с именем "Без названия"
                    page.channel = "Без названия"
                    self.pages.append(page)
            
            if not self.pages:
                self.pages.append(Page(
                    channel="Новый канал",
                    channel_num="",
                    date=self._get_russian_date(),
                    programs=[]
                ))
            
            self._refresh_page_list()
            if self.pages:
                self._select_page(0)
            self._update_info()
            
            self.status_label.setText(f"Загружено {len(self.pages)} страниц")
            self.setWindowTitle(f"📄 Редактор FD_info - {os.path.basename(filepath)}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{e}")
            import traceback
            traceback.print_exc()
            
            self.pages = [Page(
                channel="Новый канал",
                channel_num="",
                date=self._get_russian_date(),
                programs=[]
            )]
            self._refresh_page_list()
            self._select_page(0)
            self._update_info()
    
    def reload_file(self):
        if self.filepath and os.path.exists(self.filepath):
            self.load_file(self.filepath)
    
    def save_file(self):
        """Сохраняет файл"""
        if not self.filepath:
            self.save_file_as()
            return
        
        try:
            if self.current_editor:
                self.pages[self.current_page_index] = self.current_editor.get_page()
            
            content = "\n".join([page.to_text() for page in self.pages if page.channel])
            
            # ⚠️ ИСПРАВЛЕНО: сохраняем в windows-1251
            with open(self.filepath, 'w', encoding='windows-1251') as f:
                f.write(content)
            
            self.status_label.setText(f"✅ Сохранено: {os.path.basename(self.filepath)}")
            QMessageBox.information(self, "Готово", f"Файл сохранен:\n{self.filepath}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{e}")
    
    def save_file_as(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить как",
            "FD_info.txt",
            "Text files (*.txt);;All files (*.*)"
        )
        if filepath:
            self.filepath = filepath
            self.save_file()
    
    def export_to_text(self):
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт в текст",
            "FD_info_export.txt",
            "Text files (*.txt);;All files (*.*)"
        )
        if not filepath:
            return
        
        try:
            if self.current_editor:
                self.pages[self.current_page_index] = self.current_editor.get_page()
            
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("="*60 + "\n")
                f.write("ПРОГРАММА ПЕРЕДАЧ\n")
                f.write("="*60 + "\n\n")
                
                for i, page in enumerate(self.pages, 1):
                    if not page.channel:
                        continue
                    f.write(f"--- СТРАНИЦА {i} ---\n")
                    f.write(f"Канал: {page.channel} ({page.channel_num})\n")
                    f.write(f"Дата: {page.date}\n")
                    f.write("-"*40 + "\n")
                    for prog in page.programs:
                        f.write(f"{prog}\n")
                    f.write("\n")
            
            QMessageBox.information(self, "Готово", f"Файл экспортирован:\n{filepath}")
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать файл:\n{e}")


def main():
    app = QApplication(sys.argv)
    
    filepath = None
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    
    window = InfoEditorWindow(filepath)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()