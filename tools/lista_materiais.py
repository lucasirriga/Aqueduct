from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QTableWidget, 
    QTableWidgetItem, QLabel, QLineEdit, QDoubleSpinBox, QPushButton, 
    QMessageBox, QWidget, QHeaderView, QAbstractItemView, QFileDialog
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import QgsProject, QgsApplication
import os
import json
import csv

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager  # Reusing the Global Parts Manager class

class ProjectBOMManager:
    def __init__(self):
        self.project = QgsProject.instance()
        self.filepath = self.get_project_bom_path()
        self.items = [] # List of dicts: name, qty, unit_price
        self.load()

    def get_project_bom_path(self):
        project_home = self.project.homePath()
        if not project_home:
            return None
        return os.path.join(project_home, 'lista_materiais.json')

    def load(self):
        path = self.get_project_bom_path()
        if path and os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.items = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar BOM do projeto: {e}")
                self.items = []
        else:
            self.items = []

    def save(self):
        path = self.get_project_bom_path()
        if not path:
            return False
            
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.items, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar BOM do projeto: {e}")
            return False

    def add_item(self, nome, preco_unitario, quantidade=1):
        # Check if item exists, if so, ignore or update? Let's add new entry for simplicity or update qty if exactly same price?
        # Simplify: Check by name. If exists, update qty?
        found = False
        for item in self.items:
            if item['nome'] == nome:
                # Se o preço for diferente, avisa? Ou assume o novo?
                # Vamos manter entradas distintas se o preço for diferente? Não, melhor agregar.
                # Mas o usuário pode querer editar o preço manualmente depois.
                # Vamos adicionar como novo se não existir, senão incrementa.
                item['quantidade'] += quantidade
                # Atualiza preço se necessário? Não, mantem o que estava ou o usuário edita.
                found = True
                break
        
        if not found:
            self.items.append({
                'nome': nome,
                'quantidade': quantidade,
                'preco_unitario': preco_unitario
            })
        self.save()

    def update_item(self, index, quantidade, preco_unitario):
        if 0 <= index < len(self.items):
            self.items[index]['quantidade'] = quantidade
            self.items[index]['preco_unitario'] = preco_unitario
            self.save()

    def remove_item(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self.save()

class ListaMateriaisDialog(QDialog):
    def __init__(self, global_manager, project_manager, parent=None):
        super().__init__(parent)
        self.global_manager = global_manager
        self.project_manager = project_manager
        
        self.setWindowTitle("Aqueduct - Lista de Materiais do Projeto")
        self.resize(900, 600)
        
        self.setup_ui()
        self.refresh_global_list()
        self.refresh_project_table()

    def setup_ui(self):
        main_layout = QHBoxLayout()
        
        # --- Lado Esquerdo: Peças Globais ---
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("<b>Catálogo Global de Peças</b>"))
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
        self.lbl_project = QLabel("<b>Lista de Materiais do Projeto (BOM)</b>")
        if not self.project_manager.get_project_bom_path():
            self.lbl_project.setText("<b>Lista de Materiais (Projeto não salvo!)</b>")
            self.lbl_project.setStyleSheet("color: red;")
            
        right_layout.addWidget(self.lbl_project)
        
        self.table_project = QTableWidget()
        self.table_project.setColumnCount(4)
        self.table_project.setHorizontalHeaderLabels(["Item", "Qtd", "Preço Unit (R$)", "Total (R$)"])
        header = self.table_project.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        
        self.table_project.itemChanged.connect(self.on_table_changed)
        right_layout.addWidget(self.table_project)
        
        # Total Geral
        self.lbl_total_geral = QLabel("Total do Projeto: R$ 0.00")
        self.lbl_total_geral.setStyleSheet("font-size: 14pt; font-weight: bold; color: blue;")
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
            
            # Nome (Read-only)
            item_name = QTableWidgetItem(item['nome'])
            item_name.setFlags(item_name.flags() ^ 2) # Remove Edit flag (Qt.ItemIsEditable is 2)
            self.table_project.setItem(i, 0, item_name)
            
            # Qtd (Editable)
            item_qty = QTableWidgetItem(str(item['quantidade']))
            self.table_project.setItem(i, 1, item_qty)
            
            # Preço Unit (Editable)
            item_price = QTableWidgetItem(f"{item['preco_unitario']:.2f}")
            self.table_project.setItem(i, 2, item_price)
            
            # Total (Calculated, Read-only)
            total = item['quantidade'] * item['preco_unitario']
            total_geral += total
            item_total = QTableWidgetItem(f"{total:.2f}")
            item_total.setFlags(item_total.flags() ^ 2)
            self.table_project.setItem(i, 3, item_total)
            
        self.lbl_total_geral.setText(f"Total do Projeto: R$ {total_geral:.2f}")
        self.table_project.blockSignals(False)

    def on_add(self):
        selected_items = self.list_global.selectedItems()
        if not selected_items:
            return
            
        for item in selected_items:
            nome = item.text()
            data = self.global_manager.get(nome)
            if data:
                # Calcula Preço com Lucro
                custo = data.get('custo', 0.0)
                lucro = data.get('lucro', 0.0)
                preco_final = custo * (1 + lucro/100)
                
                self.project_manager.add_item(nome, preco_final)
        
        self.refresh_project_table()

    def on_table_changed(self, item):
        row = item.row()
        col = item.column()
        
        # Só reagimos a mudanças em Qtd (1) e Preço (2)
        if col not in [1, 2]:
            return
            
        try:
            qty_item = self.table_project.item(row, 1)
            price_item = self.table_project.item(row, 2)
            
            qty = float(qty_item.text().replace(',', '.'))
            price = float(price_item.text().replace('R$', '').replace(',', '.'))
            
            # Atualiza no manager
            self.project_manager.update_item(row, qty, price)
            
            # Recalcula a linha e total (refresh full é mais seguro)
            self.refresh_project_table()
            
        except ValueError:
            # Se usuário digitou texto inválido, ignora ou alerta
            pass

    def on_remove(self):
        row = self.table_project.currentRow()
        if row < 0:
            return
            
        self.project_manager.remove_item(row)
        self.refresh_project_table()

    def on_export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar Lista CSV", 
            os.path.join(QgsProject.instance().homePath() or "", "lista_materiais.csv"),
            "CSV (*.csv)"
        )
        
        if not path:
            return
            
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(["Item", "Quantidade", "Preço Unitário", "Total"])
                
                for item in self.project_manager.items:
                    total = item['quantidade'] * item['preco_unitario']
                    writer.writerow([
                        item['nome'], 
                        item['quantidade'], 
                        f"{item['preco_unitario']:.2f}", 
                        f"{total:.2f}"
                    ])
            
            QMessageBox.information(self, "Sucesso", f"Arquivo exportado: {path}")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Falha ao exportar: {e}")

class ListaMateriaisTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_lista_materiais.svg')
        self.action = QAction(QIcon(icon_path), 'Lista de Materiais', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        global_mgr = PecaManager()
        project_mgr = ProjectBOMManager()
        
        if not project_mgr.filepath:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto QGIS antes de criar uma lista de materiais!")
            return

        dlg = ListaMateriaisDialog(global_mgr, project_mgr, self.iface.mainWindow())
        dlg.exec_()
