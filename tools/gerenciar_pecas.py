from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QLabel, 
    QLineEdit, QDoubleSpinBox, QPushButton, QMessageBox, QWidget, QGroupBox, QFormLayout
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
import os
import json

from .ferramenta_base import AqueductTool

# Classe para Persistência
class PecaManager:
    def __init__(self):
        # Caminho do arquivo JSON no perfil do usuário do QGIS
        self.filepath = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_pecas.json')
        self.pecas = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.pecas = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar peças: {e}")
                self.pecas = {}
        else:
            self.pecas = {}

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.pecas, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar peças: {e}")
            return False

    def add_update(self, nome, data):
        self.pecas[nome] = data
        self.save()

    def remove(self, nome):
        if nome in self.pecas:
            del self.pecas[nome]
            self.save()
            return True
        return False
        
    def get(self, nome):
        return self.pecas.get(nome)
        
    def list_names(self):
        return sorted(self.pecas.keys())

# Interface Gráfica
class PecaDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Aqueduct - Gerenciador de Peças")
        self.resize(600, 400)
        
        self.current_name = None # Rastreia qual item está sendo editado
        
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QHBoxLayout()
        
        # --- Lado Esquerdo: Lista ---
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        left_layout.addWidget(QLabel("Peças Cadastradas:"))
        left_layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("Nova Peça")
        self.btn_new.clicked.connect(self.on_new)
        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.clicked.connect(self.on_delete)
        
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_delete)
        left_layout.addLayout(btn_layout)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        # --- Lado Direito: Formulário ---
        right_group = QGroupBox("Detalhes da Peça")
        form_layout = QFormLayout()
        
        self.edit_nome = QLineEdit()
        # self.edit_desc removido
        self.spin_custo = QDoubleSpinBox()
        self.spin_custo.setRange(0.0, 999999.0)
        self.spin_custo.setDecimals(2)
        self.spin_custo.setPrefix("R$ ")
        
        self.spin_lucro = QDoubleSpinBox()
        self.spin_lucro.setRange(0.0, 1000.0)
        self.spin_lucro.setSuffix("%")
        self.spin_lucro.setValue(30.0) # Default
        
        self.lbl_preco_final = QLabel("R$ 0.00")
        self.lbl_preco_final.setStyleSheet("font-weight: bold; color: green;")
        
        # Conecta updates para calculo em tempo real
        self.spin_custo.valueChanged.connect(self.update_final_price)
        self.spin_lucro.valueChanged.connect(self.update_final_price)
        
        form_layout.addRow("Nome:", self.edit_nome)
        # form_layout.addRow("Descrição:", self.edit_desc) removido
        form_layout.addRow("Custo Unitário:", self.spin_custo)
        form_layout.addRow("Lucro (%):", self.spin_lucro)
        form_layout.addRow("Preço Final:", self.lbl_preco_final)
        
        self.btn_save = QPushButton("Salvar Peça")
        self.btn_save.clicked.connect(self.on_save)
        
        right_layout = QVBoxLayout()
        right_layout.addLayout(form_layout)
        right_layout.addWidget(self.btn_save)
        right_layout.addStretch()
        
        right_group.setLayout(right_layout)
        
        # --- Montagem Final ---
        layout.addWidget(left_widget, 1)
        layout.addWidget(right_group, 2)
        self.setLayout(layout)
        
        # Estado inicial
        self.clear_form()

    def update_final_price(self):
        custo = self.spin_custo.value()
        lucro_perc = self.spin_lucro.value()
        preco = custo * (1 + lucro_perc/100)
        self.lbl_preco_final.setText(f"R$ {preco:.2f}")

    def refresh_list(self):
        self.list_widget.clear()
        names = self.manager.list_names()
        self.list_widget.addItems(names)

    def on_item_clicked(self, item):
        nome = item.text()
        data = self.manager.get(nome)
        if data:
            self.current_name = nome
            self.edit_nome.setText(nome)
            self.edit_nome.setEnabled(False) # Não permite mudar chave primária na edição p/ simplificar
            # self.edit_desc removido
            self.spin_custo.setValue(data.get('custo', 0.0))
            self.spin_lucro.setValue(data.get('lucro', 0.0))
            self.update_final_price()

    def on_new(self):
        self.clear_form()
        self.edit_nome.setFocus()

    def clear_form(self):
        self.current_name = None
        self.list_widget.clearSelection()
        self.edit_nome.setEnabled(True)
        self.edit_nome.clear()
        # self.edit_desc removido
        self.spin_custo.setValue(0.0)
        self.spin_lucro.setValue(30.0)
        self.update_final_price()

    def on_save(self):
        nome = self.edit_nome.text().strip()
        if not nome:
            QMessageBox.warning(self, "Aviso", "O nome da peça é obrigatório.")
            return
            
        data = {
            # "descricao" removido
            "custo": self.spin_custo.value(),
            "lucro": self.spin_lucro.value()
        }
        
        self.manager.add_update(nome, data)
        self.refresh_list()
        self.clear_form()
        QMessageBox.information(self, "Sucesso", "Peça salva com sucesso!")

    def on_delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
            
        nome = item.text()
        res = QMessageBox.question(self, "Confirmar", f"Deseja excluir a peça '{nome}'?", QMessageBox.Yes | QMessageBox.No)
        
        if res == QMessageBox.Yes:
            self.manager.remove(nome)
            self.refresh_list()
            self.clear_form()

# Tool Wrapper
class GerenciarPecasTool(AqueductTool):
    """
    Ferramenta para abrir o gerenciador CRUD de peças.
    """
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_gerenciar_pecas.svg')
        self.action = QAction(QIcon(icon_path), 'Gerenciar Peças', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        manager = PecaManager()
        dlg = PecaDialog(manager, self.iface.mainWindow())
        dlg.exec_()
