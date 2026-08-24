import os
from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog,
    QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QInputDialog, QApplication, QComboBox,
    QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QBrush


class ChannelManagerWindow(QMainWindow):
    """Окно управления каналами с 4 столбцами"""
    
    channels_updated = Signal()
    
    # Режимы сортировки
    SORT_BY_WEEK = 0      # Как в week.xml
    SORT_BY_ALPHABET = 1  # По алфавиту (Название (вывод))
    SORT_BY_CHANNEL = 2   # По списку каналов (порядок из каналов)
    
    def __init__(self, config, channels_from_xml: Dict = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📡 Управление каналами")
        self.setGeometry(100, 100, 950, 700)
        
        self.config = config
        self.channels_from_xml = channels_from_xml or {}
        self.channels: List[Dict] = []  # [{xml_name, display_name, number, active}]
        self.modified = False
        self.config_file = os.path.join("data", "channel_config.txt")
        self._updating_table = False
        
        # Порядок каналов из week.xml (сохраняется при загрузке)
        self.week_order: List[str] = []
        self.sort_mode = self.SORT_BY_WEEK
        
        self._init_ui()
        self._load_data()
    
    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(5)
        
        # Заголовок
        header = QHBoxLayout()
        header.addWidget(QLabel("📡 Управление каналами"))
        header.addStretch()
        
        # Кнопки сортировки
        self.sort_btn = QPushButton("📊 Сортировка: по week")
        self.sort_btn.clicked.connect(self._toggle_sort)
        self.sort_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        header.addWidget(self.sort_btn)
        
        self.btn_add = QPushButton("➕ Добавить канал")
        self.btn_add.clicked.connect(self._add_channel)
        header.addWidget(self.btn_add)
        
        self.btn_add_from_xml = QPushButton("📥 Добавить из week.xml")
        self.btn_add_from_xml.clicked.connect(self._add_from_xml)
        header.addWidget(self.btn_add_from_xml)
        
        self.btn_save = QPushButton("💾 Сохранить")
        self.btn_save.clicked.connect(self._save_channels)
        self.btn_save.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        header.addWidget(self.btn_save)
        
        self.btn_close = QPushButton("✖ Закрыть")
        self.btn_close.clicked.connect(self.close)
        header.addWidget(self.btn_close)
        
        main_layout.addLayout(header)
        
        # Информация
        info_layout = QHBoxLayout()
        self.lbl_total = QLabel("Всего каналов: 0")
        info_layout.addWidget(self.lbl_total)
        info_layout.addStretch()
        main_layout.addLayout(info_layout)
        
        # Таблица с 4 столбцами
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Название (week.xml)", "Название (вывод)", "Номер", "Активен"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self._on_item_changed)
        
        main_layout.addWidget(self.table)
        
        # Поиск
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍 Поиск:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите название канала...")
        self.search_input.textChanged.connect(self._filter_channels)
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)
        
        # Инструкция
        help_label = QLabel("💡 Для удаления канала: выделите строку и нажмите Delete")
        help_label.setStyleSheet("color: gray; font-size: 9px;")
        main_layout.addWidget(help_label)
        
        self.setStyleSheet("""
            QTableWidget::item:selected {
                background-color: #0078D7;
                color: white;
            }
            QTableWidget::item {
                padding: 5px;
            }
            QPushButton {
                padding: 5px 10px;
                border-radius: 3px;
            }
            QPushButton:hover {
                background: #e0e0e0;
            }
            QLineEdit {
                padding: 5px;
                border: 1px solid #ccc;
                border-radius: 3px;
            }
        """)
        
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.keyPressEvent = self._on_key_press
    
    def _toggle_sort(self):
        """Переключает режим сортировки"""
        self.sort_mode = (self.sort_mode + 1) % 3
        
        if self.sort_mode == self.SORT_BY_WEEK:
            self.sort_btn.setText("📊 Сортировка: по week")
            self.sort_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        elif self.sort_mode == self.SORT_BY_ALPHABET:
            self.sort_btn.setText("📊 Сортировка: по алфавиту")
            self.sort_btn.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        else:
            self.sort_btn.setText("📊 Сортировка: по списку")
            self.sort_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        
        self._sort_channels()
        self._update_table()
    
    def _sort_channels(self):
        """Сортирует каналы согласно текущему режиму"""
        if self.sort_mode == self.SORT_BY_WEEK:
            # Сортировка по порядку из week.xml
            if self.week_order:
                order_map = {name: idx for idx, name in enumerate(self.week_order)}
                self.channels.sort(key=lambda x: order_map.get(x['xml_name'], len(self.week_order)))
        elif self.sort_mode == self.SORT_BY_ALPHABET:
            # Сортировка по алфавиту (по отображаемому имени)
            self.channels.sort(key=lambda x: x['display_name'].lower())
        else:  # SORT_BY_CHANNEL
            # Сортировка по списку каналов (по номеру канала, числовое значение)
            self.channels.sort(key=lambda x: int(x['number']) if x['number'] and x['number'].isdigit() else 9999)
    
    def _on_key_press(self, event):
        if event.key() == Qt.Key_Delete:
            self._remove_selected()
        else:
            QTableWidget.keyPressEvent(self.table, event)
    
    def _load_data(self):
        """Загружает данные из channel_config.txt"""
        self.channels = []
        self.week_order = []
        
        # Пробуем загрузить из файла
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('|')
                        if len(parts) >= 3:
                            xml_name = parts[0].strip()
                            display_name = parts[1].strip() if len(parts) > 1 else xml_name
                            number = parts[2].strip() if len(parts) > 2 else ""
                            active = False
                            if len(parts) >= 4:
                                active = parts[3].strip().lower() == 'true'
                            self.channels.append({
                                'xml_name': xml_name,
                                'display_name': display_name,
                                'number': number,
                                'active': active
                            })
                print(f"✅ Загружено {len(self.channels)} каналов из {self.config_file}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки {self.config_file}: {e}")
        
        # Добавляем каналы из XML, которых нет в списке (с active=False)
        self._add_missing_from_xml()
        
        # Сортируем
        self._sort_channels()
        
        self._update_table()
        self._update_info()
    
    def _add_missing_from_xml(self):
        """Добавляет каналы из week.xml, которых нет в списке (с active=False)"""
        if not self.channels_from_xml:
            return
        
        existing = {c['xml_name'] for c in self.channels}
        added = 0
        
        for xml_name in sorted(self.channels_from_xml.keys()):
            # Сохраняем порядок из week.xml
            self.week_order.append(xml_name)
            
            if xml_name not in existing:
                display_name = xml_name
                programs = self.channels_from_xml.get(xml_name, [])
                if programs and 'display_name' in programs[0]:
                    display_name = programs[0]['display_name']
                
                self.channels.append({
                    'xml_name': xml_name,
                    'display_name': display_name if display_name != xml_name else xml_name,
                    'number': '',
                    'active': False
                })
                added += 1
        
        if added > 0:
            print(f"📥 Добавлено {added} новых каналов из week.xml (неактивны)")
            self.modified = True
    
    def _update_table(self):
        """Обновляет таблицу (4 столбца)"""
        self._updating_table = True
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        
        for row, channel in enumerate(self.channels):
            self.table.insertRow(row)
            
            # Название из week.xml (НЕ РЕДАКТИРУЕТСЯ) - channel id
            xml_item = QTableWidgetItem(channel.get('xml_name', ''))
            xml_item.setFlags(xml_item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, xml_item)
            
            # Название для вывода (редактируемое)
            display_item = QTableWidgetItem(channel.get('display_name', ''))
            self.table.setItem(row, 1, display_item)
            
            # Номер (редактируемый)
            num_item = QTableWidgetItem(channel.get('number', ''))
            num_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, num_item)
            
            # Активен (чекбокс)
            active_cb = QCheckBox()
            active_cb.setChecked(channel.get('active', False))
            active_cb.stateChanged.connect(lambda state, r=row: self._on_active_changed(state, r))
            self.table.setCellWidget(row, 3, active_cb)
            
            # Подсветка если нет номера
            if not channel.get('number', ''):
                num_item.setBackground(QBrush(QColor(255, 200, 200)))
            
            # Подсветка если неактивен
            if not channel.get('active', False):
                for col in range(2):
                    item = self.table.item(row, col)
                    if item:
                        item.setBackground(QBrush(QColor(240, 240, 240)))
                        item.setForeground(QBrush(QColor(150, 150, 150)))
        
        self.table.blockSignals(False)
        self._updating_table = False
        self.table.resizeColumnsToContents()
    
    def _on_active_changed(self, state, row):
        """Обработчик изменения состояния чекбокса"""
        if self._updating_table:
            return
        if 0 <= row < len(self.channels):
            self.channels[row]['active'] = bool(state)
            self.modified = True
            self._update_info()
            # Обновляем внешний вид строки
            channel = self.channels[row]
            for col in range(2):
                item = self.table.item(row, col)
                if item:
                    if channel.get('active', False):
                        item.setBackground(QBrush(QColor(255, 255, 255)))
                        item.setForeground(QBrush(QColor(0, 0, 0)))
                    else:
                        item.setBackground(QBrush(QColor(240, 240, 240)))
                        item.setForeground(QBrush(QColor(150, 150, 150)))
    
    def _update_info(self):
        total = len(self.channels)
        active = sum(1 for c in self.channels if c.get('active', False))
        without_num = sum(1 for c in self.channels if not c.get('number', ''))
        self.lbl_total.setText(f"Всего каналов: {total} (активно: {active}, без номера: {without_num})")
    
    def _filter_channels(self, text: str):
        text_lower = text.lower().strip()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                channel = item.text().lower()
                display_item = self.table.item(row, 1)
                display_text = display_item.text().lower() if display_item else ""
                self.table.setRowHidden(row, text_lower not in channel and text_lower not in display_text)
    
    def _on_item_changed(self, item):
        if self._updating_table:
            return
        row = item.row()
        col = item.column()
        
        if col == 1:
            self.channels[row]['display_name'] = item.text().strip()
            self.modified = True
            # После изменения названия, если сортировка по алфавиту, пересортируем
            if self.sort_mode == self.SORT_BY_ALPHABET:
                self._sort_channels()
                self._update_table()
        elif col == 2:
            self.channels[row]['number'] = item.text().strip()
            self.modified = True
            self._update_info()
            # После изменения номера, если сортировка по списку, пересортируем
            if self.sort_mode == self.SORT_BY_CHANNEL:
                self._sort_channels()
                self._update_table()
    
    def _add_channel(self):
        xml_name, ok = QInputDialog.getText(
            self, "Добавить канал",
            "Введите название канала (как в week.xml):"
        )
        if not ok or not xml_name:
            return
        
        xml_name = xml_name.strip()
        
        for c in self.channels:
            if c['xml_name'] == xml_name:
                QMessageBox.warning(self, "Ошибка", f"Канал '{xml_name}' уже существует")
                return
        
        display_name, ok = QInputDialog.getText(
            self, "Название для вывода",
            f"Введите название для отображения канала '{xml_name}':"
        )
        if not ok:
            display_name = xml_name
        
        number, ok = QInputDialog.getText(
            self, "Номер канала",
            f"Введите номер для канала '{xml_name}':"
        )
        
        self.channels.append({
            'xml_name': xml_name,
            'display_name': display_name.strip() if display_name else xml_name,
            'number': number.strip() if ok else '',
            'active': False
        })
        self.modified = True
        
        self._sort_channels()
        self._update_table()
        self._update_info()
        self._scroll_to_channel(xml_name)
    
    def _add_from_xml(self):
        if not self.channels_from_xml:
            QMessageBox.warning(self, "Ошибка", "Сначала загрузите week.xml в главной программе")
            return
        
        existing = {c['xml_name'] for c in self.channels}
        added = 0
        
        for xml_name in self.channels_from_xml.keys():
            if xml_name not in existing:
                display_name = xml_name
                programs = self.channels_from_xml.get(xml_name, [])
                if programs and 'display_name' in programs[0]:
                    display_name = programs[0]['display_name']
                
                self.channels.append({
                    'xml_name': xml_name,
                    'display_name': display_name if display_name != xml_name else xml_name,
                    'number': '',
                    'active': False
                })
                added += 1
        
        if added > 0:
            self.modified = True
            self._sort_channels()
            self._update_table()
            self._update_info()
            QMessageBox.information(self, "Готово", f"Добавлено {added} новых каналов (по умолчанию неактивны)")
        else:
            QMessageBox.information(self, "Информация", "Нет новых каналов для добавления")
    
    def _remove_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        
        xml_item = self.table.item(row, 0)
        if not xml_item:
            return
        
        xml_name = xml_item.text()
        
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить канал '{xml_name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            del self.channels[row]
            self.modified = True
            self._update_table()
            self._update_info()
    
    def _scroll_to_channel(self, channel_name: str):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.text() == channel_name:
                self.table.scrollToItem(item)
                self.table.selectRow(row)
                break
    
    def _save_channels(self):
        if not self.modified:
            QMessageBox.information(self, "Информация", "Нет изменений для сохранения")
            return
        
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            lines = ["# Название из week|Название для вывода|Номер канала|Активен"]
            for channel in self.channels:
                active_str = "True" if channel.get('active', False) else "False"
                lines.append(
                    f"{channel['xml_name']}|{channel['display_name']}|{channel.get('number', '')}|{active_str}"
                )
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
            
            self._update_config()
            
            self.modified = False
            self._update_info()
            self.channels_updated.emit()
            
            QMessageBox.information(
                self, "Готово",
                f"Сохранено {len(self.channels)} каналов в:\n{self.config_file}"
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить:\n{e}")
    
    def _update_config(self):
        if not self.config:
            return
        
        self.config.channels_id = {}
        self.config.channels_names = {}
        self.config.channels_numbers = {}
        self.config.channels_active = {}
        
        for channel in self.channels:
            xml_name = channel['xml_name']
            display_name = channel['display_name']
            number = channel.get('number', '')
            active = channel.get('active', False)
            
            if xml_name:
                if display_name:
                    self.config.channels_id[xml_name] = display_name
                    self.config.channels_names[xml_name] = display_name
                if number:
                    self.config.channels_numbers[xml_name] = number
                self.config.channels_active[xml_name] = active
    
    def get_channel_numbers(self) -> Dict[str, str]:
        result = {}
        for channel in self.channels:
            if channel.get('active', False) and channel.get('xml_name') and channel.get('number'):
                result[channel['xml_name']] = channel['number']
        return result
    
    def get_channel_names(self) -> Dict[str, str]:
        result = {}
        for channel in self.channels:
            if channel.get('active', False) and channel.get('xml_name') and channel.get('display_name'):
                result[channel['xml_name']] = channel['display_name']
        return result
    
    def closeEvent(self, event):
        if self.modified:
            reply = QMessageBox.question(
                self, "Несохраненные изменения",
                "У вас есть несохраненные изменения. Сохранить перед выходом?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Yes:
                self._save_channels()
                event.accept()
            elif reply == QMessageBox.No:
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def show_channel_manager(config, channels_from_xml: Dict = None, parent=None):
    window = ChannelManagerWindow(config, channels_from_xml, parent)
    window.show()
    return window