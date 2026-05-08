from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QListWidget, QLineEdit, QPushButton, QMessageBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField
)
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool
from .gerenciar_blocos import BlocoManager
from .lista_materiais import ProjectBOMManager

class AtribuirBlocoDialog(QDialog):
    def __init__(self, blocos, qtde_selecionada, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Atribuir Bloco ao Cavalete")
        self.resize(500, 400)
        self.bloco_selecionado = None
        
        layout = QVBoxLayout()
        
        lbl_info = QLabel(f"Feições selecionadas no mapa: <b>{qtde_selecionada}</b>")
        lbl_info.setStyleSheet("font-size: 11pt; margin-bottom: 5px;")
        layout.addWidget(lbl_info)
        
        layout.addWidget(QLabel("Selecione o Bloco para vincular a esses pontos:"))
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Pesquisar bloco...")
        self.search_bar.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_bar)
        
        self.list_blocos = QListWidget()
        self.list_blocos.addItems(blocos)
        self.list_blocos.itemDoubleClicked.connect(self.on_ok)
        self.list_blocos.setStyleSheet("QListWidget::item { padding: 5px; } QListWidget::item:selected { background-color: #3498db; color: white; }")
        layout.addWidget(self.list_blocos)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Aplicar e Atualizar Inventário")
        btn_ok.clicked.connect(self.on_ok)
        btn_ok.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px;")
        
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)
        btn_cancel.setStyleSheet("padding: 6px;")
        
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)
        
    def filter_list(self, text):
        for i in range(self.list_blocos.count()):
            item = self.list_blocos.item(i)
            item.setHidden(text.lower() not in item.text().lower())
            
    def on_ok(self):
        item = self.list_blocos.currentItem()
        if not item:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione um bloco na lista.")
            return
        self.bloco_selecionado = item.text()
        self.accept()


class AtribuirBlocoTool(AqueductTool):
    """
    Ferramenta para vincular um Bloco de Peças a pontos no mapa,
    atualizando o inventário do projeto (BOM) automaticamente e proporcionalmente.
    """
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_atribuir_bloco.svg')
        self.action = QAction(QIcon(icon_path), 'Atribuir Bloco a Cavalete', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsVectorLayer.VectorLayer:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Selecione uma camada vetorial (pontos) válida no painel de camadas.")
            return
            
        if layer.geometryType() != 0: # 0 = Point
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "A camada ativa deve ser do tipo Ponto (Ex: Cavaletes).")
            return
            
        selected_features = layer.selectedFeatures()
        if not selected_features:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Selecione ao menos um ponto no mapa (ferramenta de seleção) para atribuir o bloco.")
            return
            
        bloco_mgr = BlocoManager()
        blocos_disponiveis = bloco_mgr.list_names()
        
        if not blocos_disponiveis:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Nenhum Bloco cadastrado. Crie blocos no 'Gerenciar Blocos' primeiro.")
            return
            
        # Pede selecao do bloco para o usuario
        dlg = AtribuirBlocoDialog(blocos_disponiveis, len(selected_features), self.iface.mainWindow())
        if not dlg.exec_() or not dlg.bloco_selecionado:
            return
            
        novo_bloco = dlg.bloco_selecionado
        
        # Iniciar processo de inventario
        project_bom = ProjectBOMManager()
        if not project_bom.filepath:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto do QGIS primeiro para que o inventário possa ser registrado na pasta do projeto.")
            return

        # Verifica e cria a coluna bloco_id se não existir
        layer.startEditing()
        idx_bloco = layer.fields().indexOf('bloco_id')
        if idx_bloco == -1:
            layer.dataProvider().addAttributes([QgsField('bloco_id', QVariant.String, len=100)])
            layer.updateFields()
            idx_bloco = layer.fields().indexOf('bloco_id')

        mudancas_sucesso = 0
        
        for feature in selected_features:
            bloco_antigo = feature.attributes()[idx_bloco] if idx_bloco != -1 and len(feature.attributes()) > idx_bloco else None
            
            # Subtrai o antigo da lista de materiais do projeto
            if bloco_antigo and isinstance(bloco_antigo, str) and bloco_antigo in bloco_mgr.blocos:
                project_bom.add_bloco_project(bloco_antigo, -1, save=False)
                
            # Atualiza o atributo do ponto na camada
            layer.changeAttributeValue(feature.id(), idx_bloco, novo_bloco)
            
            # Adiciona o novo bloco à lista de materiais do projeto
            project_bom.add_bloco_project(novo_bloco, 1, save=False)
            mudancas_sucesso += 1
            
        # Salvar edições de projeto (Camada QGIS)
        layer.commitChanges()
        
        # Limpar blocos zerados (Caso o bloco antigo tenha sido removido de todos os pontos)
        project_blocos = project_bom.project_blocos
        to_remove = [i for i, b in enumerate(project_blocos) if b['quantidade'] <= 0]
        for i in reversed(to_remove):
            project_bom.remove_bloco_project(i, save=False)
            
        # Salvar inventário (BOM JSON)
        project_bom.save()
        
        QMessageBox.information(self.iface.mainWindow(), "Sucesso", f"Bloco '{novo_bloco}' atribuído a {mudancas_sucesso} cavalete(s)!\nO inventário do projeto foi atualizado automaticamente.")
