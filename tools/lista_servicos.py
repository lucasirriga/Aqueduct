from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTableWidget, 
    QTableWidgetItem, QLabel, QPushButton, QMessageBox, QWidget, QHeaderView, QAbstractItemView, QFileDialog
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsProject
import os
import json
import csv

from .ferramenta_base import AqueductTool
from .gerenciar_servicos import ServicoManager

class ProjectServiceListManager:
    def __init__(self):
        self.project = QgsProject.instance()
        self.filepath = self.get_project_path()
        self.items = [] # List of dicts: descricao, quantidade, valor_unitario
        self.load()

    def get_project_path(self):
        project_home = self.project.homePath()
        if not project_home:
            return None
        return os.path.join(project_home, 'lista_servicos.json')

    def load(self):
        path = self.get_project_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.items = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar lista de serviços: {e}")
                self.items = []
        else:
            self.items = []

    def save(self):
        path = self.get_project_path()
        if not path:
            return False
            
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar lista de serviços: {e}")
            return False

    def add_item(self, descricao, valor_unitario, quantidade=1):
        found = False
        for item in self.items:
            if item['descricao'] == descricao:
                item['quantidade'] += quantidade
                found = True
                break
        
        if not found:
            self.items.append({
                'descricao': descricao,
                'quantidade': quantidade,
                'valor_unitario': valor_unitario
            })
        self.save()

    def update_item(self, index, quantidade, valor_unitario):
        if 0 <= index < len(self.items):
            self.items[index]['quantidade'] = quantidade
            self.items[index]['valor_unitario'] = valor_unitario
            self.save()

    def remove_item(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()

class ListaServicosDialog(QDialog):
    def __init__(self, global_manager, project_manager, parent=None):
        super().__init__(parent)
        self.global_manager = global_manager
        self.project_manager = project_manager
        
        self.setWindowTitle("Aqueduct - Lista de Serviços do Projeto")
        self.resize(900, 600)
        
        self.setup_ui()
        self.refresh_global_list()
        self.refresh_project_table()

    def setup_ui(self):
        main_layout = QHBoxLayout()
        
        # --- Lado Esquerdo: Serviços Globais ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("<b>Catálogo Global de Serviços</b>"))
        self.list_global = QListWidget()
        self.list_global.setSelectionMode(QAbstractItemView.ExtendedSelection)
        left_layout.addWidget(self.list_global)
        
        btn_add = QPushButton("Adicionar ao Projeto ->")
        btn_add.clicked.connect(self.on_add)
        left_layout.addWidget(btn_add)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        # --- Lado Direito: Lista do Projeto ---
        right_layout = QVBoxLayout()
        self.lbl_project = QLabel("<b>Lista de Serviços do Projeto</b>")
        if not self.project_manager.get_project_path():
            self.lbl_project.setText("<b>Lista de Serviços (Projeto não salvo!)</b>")
            self.lbl_project.setStyleSheet("color: red;")
            
        right_layout.addWidget(self.lbl_project)
        
        self.table_project = QTableWidget()
        self.table_project.setColumnCount(4)
        self.table_project.setHorizontalHeaderLabels(["Descrição", "Qtd", "Valor Unit (R$)", "Total (R$)"])
        header = self.table_project.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.table_project.itemChanged.connect(self.on_table_changed)
        right_layout.addWidget(self.table_project)
        
        # Total Geral
        self.lbl_total_geral = QLabel("Total: R$ 0.00")
        self.lbl_total_geral.setStyleSheet("font-size: 14pt; font-weight: bold; color: white;")
        right_layout.addWidget(self.lbl_total_geral)
        
        btn_actions_layout = QHBoxLayout()
        btn_remove = QPushButton("Remover Item")
        btn_remove.clicked.connect(self.on_remove)
        btn_export = QPushButton("Exportar CSV")
        btn_export.clicked.connect(self.on_export)
        
        btn_actions_layout.addWidget(btn_remove)
        btn_actions_layout.addWidget(btn_export)
        right_layout.addLayout(btn_actions_layout)
        
        right_widget = QWidget()
        right_widget.setLayout(right_layout)
        
        # --- Montagem ---
        main_layout.addWidget(left_widget, 1)
        main_layout.addWidget(right_widget, 2)
        self.setLayout(main_layout)

    def refresh_global_list(self):
        self.list_global.clear()
        names = self.global_manager.list_names()
        self.list_global.addItems(names)

    def refresh_project_table(self):
        self.table_project.blockSignals(True)
        self.table_project.setRowCount(0)
        
        total_geral = 0.0
        
        for i, item in enumerate(self.project_manager.items):
            self.table_project.insertRow(i)
            
            # Descrição (Nome) - Read-only
            item_desc = QTableWidgetItem(item['descricao'])
            item_desc.setFlags(item_desc.flags() ^ 2) 
            self.table_project.setItem(i, 0, item_desc)
            
            # Qtd (Editable)
            item_qty = QTableWidgetItem(str(item['quantidade']))
            self.table_project.setItem(i, 1, item_qty)
            
            # Valor Unit (Editable)
            item_valor = QTableWidgetItem(f"{item['valor_unitario']:.2f}")
            self.table_project.setItem(i, 2, item_valor)
            
            # Total (Calculated, Read-only)
            total = item['quantidade'] * item['valor_unitario']
            total_geral += total
            item_total = QTableWidgetItem(f"{total:.2f}")
            item_total.setFlags(item_total.flags() ^ 2)
            self.table_project.setItem(i, 3, item_total)
            
        self.lbl_total_geral.setText(f"Total: R$ {total_geral:.2f}")
        self.table_project.blockSignals(False)

    def on_add(self):
        selected_items = self.list_global.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            desc = item.text()
            data = self.global_manager.get(desc)
            if data:
                valor = data.get('valor', 0.0)
                self.project_manager.add_item(desc, valor)
        
        self.refresh_project_table()

    def on_table_changed(self, item):
        row = item.row()
        col = item.column()
        
        if col not in [1, 2]:
            return
            
        try:
            qty_item = self.table_project.item(row, 1)
            valor_item = self.table_project.item(row, 2)
            
            qty = float(qty_item.text().replace(',', '.'))
            valor = float(valor_item.text().replace('R$', '').replace(',', '.'))
            
            self.project_manager.update_item(row, qty, valor)
            self.refresh_project_table()
            
        except ValueError:
            pass

    def on_remove(self):
        row = self.table_project.currentRow()
        if row < 0:
            return
            
        self.project_manager.remove_item(row)
        self.refresh_project_table()

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Serviços CSV", 
            os.path.join(QgsProject.instance().homePath() or "", "lista_servicos.csv"),
            "CSV (*.csv)"
        )
        
        if not path:
            return
            
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Descrição", "Quantidade", "Valor Unitário", "Total"])
                
                for item in self.project_manager.items:
                    total = item['quantidade'] * item['valor_unitario']
                    writer.writerow([
                        item['descricao'], 
                        item['quantidade'], 
                        f"{item['valor_unitario']:.2f}", 
                        f"{total:.2f}"
                    ])
            
            QMessageBox.information(self, "Sucesso", f"Arquivo exportado: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao exportar: {e}")

class ListaServicosTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_lista_servicos.svg')
        self.action = QAction(QIcon(icon_path), 'Lista de Serviços', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        global_mgr = ServicoManager()
        project_mgr = ProjectServiceListManager()
        
        if not project_mgr.filepath:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto QGIS antes de criar uma lista de serviços!")
            return

        dlg = ListaServicosDialog(global_mgr, project_mgr, self.iface.mainWindow())
        dlg.exec_()
