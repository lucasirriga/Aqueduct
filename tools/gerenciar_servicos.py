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
class ServicoManager:
    def __init__(self):
        # Caminho do arquivo JSON no perfil do usuário do QGIS
        self.filepath = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_servicos.json')
        self.servicos = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    self.servicos = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar serviços: {e}")
                self.servicos = {}
        else:
            self.servicos = {}

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump(self.servicos, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar serviços: {e}")
            return False

    def add_update(self, descricao, data):
        self.servicos[descricao] = data
        self.save()

    def remove(self, descricao):
        if descricao in self.servicos:
            del self.servicos[descricao]
            self.save()
            return True
        return False
        
    def get(self, descricao):
        return self.servicos.get(descricao)
        
    def list_names(self):
        return sorted(self.servicos.keys())

# Interface Gráfica
class ServicoDialog(QDialog):
    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Aqueduct - Gerenciador de Serviços")
        self.resize(600, 400)
        
        self.current_name = None 
        
        self.setup_ui()
        self.refresh_list()

    def setup_ui(self):
        layout = QHBoxLayout()
        
        # --- Lado Esquerdo: Lista ---
        left_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self.on_item_clicked)
        left_layout.addWidget(QLabel("Serviços Cadastrados:"))
        left_layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_new = QPushButton("Novo Serviço")
        self.btn_new.clicked.connect(self.on_new)
        self.btn_delete = QPushButton("Excluir")
        self.btn_delete.clicked.connect(self.on_delete)
        
        btn_layout.addWidget(self.btn_new)
        btn_layout.addWidget(self.btn_delete)
        left_layout.addLayout(btn_layout)
        
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        
        # --- Lado Direito: Formulário ---
        right_group = QGroupBox("Detalhes do Serviço")
        form_layout = QFormLayout()
        
        self.edit_desc = QLineEdit() # Descrição é a chave
        self.spin_valor = QDoubleSpinBox()
        self.spin_valor.setRange(0.0, 999999.0)
        self.spin_valor.setDecimals(2)
        self.spin_valor.setPrefix("R$ ")
        
        form_layout.addRow("Descrição:", self.edit_desc)
        form_layout.addRow("Valor Unitário:", self.spin_valor)
        
        self.btn_save = QPushButton("Salvar Serviço")
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

    def refresh_list(self):
        self.list_widget.clear()
        names = self.manager.list_names()
        self.list_widget.addItems(names)

    def on_item_clicked(self, item):
        desc = item.text()
        data = self.manager.get(desc)
        if data:
            self.current_name = desc
            self.edit_desc.setText(desc)
            self.edit_desc.setEnabled(False) # Chave primária
            self.spin_valor.setValue(data.get('valor', 0.0))

    def on_new(self):
        self.clear_form()
        self.edit_desc.setFocus()

    def clear_form(self):
        self.current_name = None
        self.list_widget.clearSelection()
        self.edit_desc.setEnabled(True)
        self.edit_desc.clear()
        self.spin_valor.setValue(0.0)

    def on_save(self):
        desc = self.edit_desc.text().strip()
        if not desc:
            QMessageBox.warning(self, "Aviso", "A descrição do serviço é obrigatória.")
            return
            
        data = {
            "valor": self.spin_valor.value()
        }
        
        self.manager.add_update(desc, data)
        self.refresh_list()
        self.clear_form()
        QMessageBox.information(self, "Sucesso", "Serviço salvo com sucesso!")

    def on_delete(self):
        item = self.list_widget.currentItem()
        if not item:
            return
            
        desc = item.text()
        res = QMessageBox.question(self, "Confirmar", f"Deseja excluir o serviço '{desc}'?", QMessageBox.Yes | QMessageBox.No)
        
        if res == QMessageBox.Yes:
            self.manager.remove(desc)
            self.refresh_list()
            self.clear_form()

# Tool Wrapper
class GerenciarServicosTool(AqueductTool):
    """
    Ferramenta para abrir o gerenciador CRUD de serviços (Global).
    """
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_servicos.svg')
        self.action = QAction(QIcon(icon_path), 'Gerenciar Serviços', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        manager = ServicoManager()
        dlg = ServicoDialog(manager, self.iface.mainWindow())
        dlg.exec_()
