from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QTextEdit, QPushButton, QMessageBox, QLabel
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication
import os

from .ferramenta_base import AqueductTool

class TermosDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Termos de Serviço")
        self.resize(600, 500)
        
        # Caminho do arquivo de termos (Global)
        self.filepath = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_termos.txt')
        
        self.setup_ui()
        self.load_text()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        layout.addWidget(QLabel("<b>Defina os Termos de Serviço (Padrão Global):</b>"))
        
        self.text_edit = QTextEdit()
        layout.addWidget(self.text_edit)
        
        self.btn_save = QPushButton("Salvar Termos")
        self.btn_save.clicked.connect(self.save_text)
        layout.addWidget(self.btn_save)
        
        self.setLayout(layout)

    def load_text(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    self.text_edit.setPlainText(content)
            except Exception as e:
                self.text_edit.setPlainText(f"Erro ao carregar termos: {e}")
        else:
            self.text_edit.setPlainText("Digite aqui os termos de serviço padrão...")

    def save_text(self):
        content = self.text_edit.toPlainText()
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            QMessageBox.information(self, "Sucesso", "Termos de serviço salvos com sucesso!")
        except Exception as e:
            QMessageBox.warning(self, "Erro", f"Erro ao salvar: {e}")

class TermosServicoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_termos_servico.svg')
        self.action = QAction(QIcon(icon_path), 'Termos de Serviço', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = TermosDialog(self.iface.mainWindow())
        dlg.exec_()
