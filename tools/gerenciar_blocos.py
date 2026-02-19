from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, 
    QPushButton, QMessageBox, QWidget, QGroupBox, QFormLayout, 
    QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QInputDialog
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
import os
import json

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager

class BlocoManager:
    def __init__(self):
        self.filepath = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_blocos.json')
        self.blocos = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.blocos = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar blocos: {e}")
                self.blocos = {}
        else:
            self.blocos = {}

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.blocos, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar blocos: {e}")
            return False

    def add_update(self, nome, itens):
        """
        itens: list of dict {'nome': 'Peca X', 'quantidade': 2}
        """
        self.blocos[nome] = itens
        self.save()

    def remove(self, nome):
        if nome in self.blocos:
            del self.blocos[nome]
            self.save()
            return True
        return False
        
    def get(self, nome):
        return self.blocos.get(nome, [])
        
    def list_names(self):
        return sorted(self.blocos.keys())

class EditorBlocoDialog(QDialog):
    """Diálogo para criar/editar um bloco específico (adicionar peças a ele)"""
    def __init__(self, bloco_nome, bloco_itens, peca_manager, parent=None):
        super().__init__(parent)
        self.bloco_nome = bloco_nome
        self.itens = list(bloco_itens) # Copy
        self.peca_manager = peca_manager
        
        self.setWindowTitle(f"Editando Bloco: {bloco_nome}")
        self.resize(700, 500)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QHBoxLayout()
        
        # Esquerda: Peças Disponíveis
        left_layout = QVBoxLayout()
        left_layout.addWidget(QLabel("<b>Peças Disponíveis</b>"))
        self.list_pecas = QListWidget()
        self.list_pecas.addItems(self.peca_manager.list_names())
        left_layout.addWidget(self.list_pecas)
        
        add_layout = QHBoxLayout()
        self.spin_add_qtd = QSpinBox()
        self.spin_add_qtd.setRange(1, 9999)
        self.spin_add_qtd.setValue(1)
        btn_add = QPushButton("Adicionar >>")
        btn_add.clicked.connect(self.on_add)
        
        add_layout.addWidget(QLabel("Qtd:"))
        add_layout.addWidget(self.spin_add_qtd)
        add_layout.addWidget(btn_add)
        left_layout.addLayout(add_layout)
        
        # Direita: Itens do Bloco
        right_layout = QVBoxLayout()
        right_layout.addWidget(QLabel(f"<b>Conteúdo do Bloco: {self.bloco_nome}</b>"))
        
        self.table_itens = QTableWidget()
        self.table_itens.setColumnCount(2)
        self.table_itens.setHorizontalHeaderLabels(["Peça", "Qtd"])
        self.table_itens.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        right_layout.addWidget(self.table_itens)
        
        btn_remove = QPushButton("Remover Item Selecionado")
        btn_remove.clicked.connect(self.on_remove)
        right_layout.addWidget(btn_remove)
        
        # Bottom Buttons
        btn_save = QPushButton("Salvar Bloco")
        btn_save.clicked.connect(self.accept)
        
        # Layout Final
        layout.addLayout(left_layout, 1)
        layout.addLayout(right_layout, 1)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(layout)
        main_layout.addWidget(btn_save)
        
        self.setLayout(main_layout)
        self.refresh_table()
        
    def refresh_table(self):
        self.table_itens.setRowCount(0)
        for i, item in enumerate(self.itens):
            self.table_itens.insertRow(i)
            self.table_itens.setItem(i, 0, QTableWidgetItem(item['nome']))
            self.table_itens.setItem(i, 1, QTableWidgetItem(str(item['quantidade'])))
            
    def on_add(self):
        sel_items = self.list_pecas.selectedItems()
        if not sel_items:
            return
            
        nome_peca = sel_items[0].text()
        qtd = self.spin_add_qtd.value()
        
        # Check if exists, sum qty
        for item in self.itens:
            if item['nome'] == nome_peca:
                item['quantidade'] += qtd
                self.refresh_table()
                return

        # Else add new
        self.itens.append({'nome': nome_peca, 'quantidade': qtd})
        self.refresh_table()
        
    def on_remove(self):
        row = self.table_itens.currentRow()
        if row >= 0:
            del self.itens[row]
            self.refresh_table()
            
    def get_itens(self):
        return self.itens

class GerenciarBlocosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Gerenciar Blocos de Peças")
        self.resize(500, 400)
        
        self.manager = BlocoManager()
        self.peca_manager = PecaManager()
        
        self.setup_ui()
        self.refresh_list()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        self.list_blocos = QListWidget()
        self.list_blocos.itemDoubleClicked.connect(self.on_edit)
        layout.addWidget(QLabel("Blocos Cadastrados (Duplo clique para editar):"))
        layout.addWidget(self.list_blocos)
        
        btn_layout = QHBoxLayout()
        btn_new = QPushButton("Novo Bloco")
        btn_new.clicked.connect(self.on_new)
        btn_edit = QPushButton("Editar")
        btn_edit.clicked.connect(self.on_edit)
        btn_del = QPushButton("Excluir")
        btn_del.clicked.connect(self.on_delete)
        
        btn_layout.addWidget(btn_new)
        btn_layout.addWidget(btn_edit)
        btn_layout.addWidget(btn_del)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
    def refresh_list(self):
        self.list_blocos.clear()
        self.list_blocos.addItems(self.manager.list_names())
        
    def on_new(self):
        nome, ok = QInputDialog.getText(self, "Novo Bloco", "Nome do Bloco:")
        if ok and nome:
            if nome in self.manager.blocos:
                QMessageBox.warning(self, "Erro", "Já existe um bloco com este nome.")
                return
                
            # Open Editor directly
            dlg = EditorBlocoDialog(nome, [], self.peca_manager, self)
            if dlg.exec_():
                itens = dlg.get_itens()
                self.manager.add_update(nome, itens)
                self.refresh_list()
                
    def on_edit(self):
        item = self.list_blocos.currentItem()
        if not item: return
        
        nome = item.text()
        itens = self.manager.get(nome)
        
        dlg = EditorBlocoDialog(nome, itens, self.peca_manager, self)
        if dlg.exec_():
            novos_itens = dlg.get_itens()
            self.manager.add_update(nome, novos_itens)
            self.refresh_list()
            
    def on_delete(self):
        item = self.list_blocos.currentItem()
        if not item: return
        
        nome = item.text()
        if QMessageBox.question(self, "Confirmar", f"Excluir bloco '{nome}'?") == QMessageBox.Yes:
            self.manager.remove(nome)
            self.refresh_list()
