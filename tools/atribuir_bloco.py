from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QListWidget, QLineEdit, QPushButton, QMessageBox
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsField,
    QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat, QgsTextBufferSettings,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol, Qgis
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor, QFont
import os
import random

from .ferramenta_base import AqueductTool
from .gerenciar_blocos import BlocoManager
from .lista_materiais import ProjectBOMManager

class AtribuirBlocoDialog(QDialog):
    def __init__(self, iface, blocos, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Atribuir Bloco ao Cavalete")
        self.resize(500, 400)
        self.setModal(False) # Não trava o QGIS
        
        layout = QVBoxLayout()
        
        lbl_info = QLabel("Selecione os pontos no mapa e escolha o bloco abaixo:")
        lbl_info.setStyleSheet("font-size: 11pt; margin-bottom: 5px;")
        layout.addWidget(lbl_info)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Pesquisar bloco...")
        self.search_bar.textChanged.connect(self.filter_list)
        layout.addWidget(self.search_bar)
        
        self.list_blocos = QListWidget()
        self.list_blocos.addItems(blocos)
        self.list_blocos.itemDoubleClicked.connect(self.on_apply)
        self.list_blocos.setStyleSheet("QListWidget::item { padding: 5px; } QListWidget::item:selected { background-color: #3498db; color: white; }")
        layout.addWidget(self.list_blocos)
        
        from qgis.PyQt.QtWidgets import QCheckBox
        self.chk_estilo = QCheckBox("Colorir e Rotular pontos automaticamente")
        self.chk_estilo.setChecked(True)
        self.chk_estilo.setToolTip("Gera cores diferentes para cada bloco e exibe o nome no mapa.")
        layout.addWidget(self.chk_estilo)
        
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Aplicar aos Pontos Selecionados")
        btn_ok.clicked.connect(self.on_apply)
        btn_ok.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px;")
        
        btn_cancel = QPushButton("Fechar")
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
            
    def on_apply(self):
        item = self.list_blocos.currentItem()
        if not item:
            QMessageBox.warning(self, "Aviso", "Por favor, selecione um bloco na lista.")
            return
            
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsVectorLayer.VectorLayer or layer.geometryType() != 0:
            QMessageBox.warning(self, "Aviso", "A camada ativa deve ser do tipo Ponto (Ex: Cavaletes).")
            return
            
        selected_features = layer.selectedFeatures()
        if not selected_features:
            QMessageBox.warning(self, "Aviso", "Selecione ao menos um ponto no mapa para atribuir o bloco.")
            return

        novo_bloco = item.text()
        bloco_mgr = BlocoManager()
        
        project_bom = ProjectBOMManager()
        if not project_bom.filepath:
            QMessageBox.warning(self, "Aviso", "Salve o projeto do QGIS primeiro para que o inventário possa ser registrado.")
            return

        layer.startEditing()
        idx_bloco = layer.fields().indexOf('bloco_id')
        if idx_bloco == -1:
            layer.dataProvider().addAttributes([QgsField('bloco_id', QVariant.String, len=100)])
            layer.updateFields()
            idx_bloco = layer.fields().indexOf('bloco_id')

        mudancas_sucesso = 0
        
        for feature in selected_features:
            bloco_antigo = feature.attributes()[idx_bloco] if idx_bloco != -1 and len(feature.attributes()) > idx_bloco else None
            
            if bloco_antigo and isinstance(bloco_antigo, str) and bloco_antigo in bloco_mgr.blocos:
                project_bom.add_bloco_project(bloco_antigo, -1, save=False)
                
            layer.changeAttributeValue(feature.id(), idx_bloco, novo_bloco)
            project_bom.add_bloco_project(novo_bloco, 1, save=False)
            mudancas_sucesso += 1
            
        layer.commitChanges()
        
        project_blocos = project_bom.project_blocos
        to_remove = [i for i, b in enumerate(project_blocos) if b['quantidade'] <= 0]
        for i in reversed(to_remove):
            project_bom.remove_bloco_project(i, save=False)
            
        project_bom.save()
        
        # Desmarca as feições após aplicar para evitar cliques duplos acidentais
        layer.removeSelection()
        
        if self.chk_estilo.isChecked():
            self.aplicar_estilo(layer)
        
        QMessageBox.information(self, "Sucesso", f"Bloco '{novo_bloco}' atribuído a {mudancas_sucesso} cavalete(s)!\nO inventário foi atualizado.")

    def aplicar_estilo(self, layer):
        idx_bloco = layer.fields().indexOf('bloco_id')
        if idx_bloco == -1: return

        # Rotular (Labels)
        settings = QgsPalLayerSettings()
        settings.fieldName = 'bloco_id'
        settings.isExpression = False
        settings.placement = Qgis.LabelPlacement.OverPoint
        settings.yOffset = -3
        
        text_format = QgsTextFormat()
        font = QFont("Arial")
        text_format.setFont(font)
        text_format.setSize(9)
        text_format.setColor(QColor("black"))
        
        buffer_settings = QgsTextBufferSettings()
        buffer_settings.setEnabled(True)
        buffer_settings.setSize(0.5)
        buffer_settings.setColor(QColor("white"))
        text_format.setBuffer(buffer_settings)
        
        settings.setFormat(text_format)
        
        layer.setLabelsEnabled(True)
        layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))

        # Categorizado (Cores)
        unique_values = layer.uniqueValues(idx_bloco)
        categories = []
        for value in unique_values:
            if not value: 
                value_str = ""
                label_str = "Sem Bloco"
                color = QColor(180, 180, 180) # Cinza para vazios
            else:
                value_str = str(value)
                label_str = value_str
                # Cores pseudo-aleatorias vibrantes
                color = QColor(random.randint(50, 200), random.randint(50, 200), random.randint(50, 200))
                
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            symbol.setSize(3.0)
            
            category = QgsRendererCategory(value_str, symbol, label_str)
            categories.append(category)
            
        renderer = QgsCategorizedSymbolRenderer('bloco_id', categories)
        layer.setRenderer(renderer)
        
        layer.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(layer.id())


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
        bloco_mgr = BlocoManager()
        blocos_disponiveis = bloco_mgr.list_names()
        
        if not blocos_disponiveis:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Nenhum Bloco cadastrado. Crie blocos no 'Gerenciar Blocos' primeiro.")
            return
            
        # Para garantir que não existam múltiplas instâncias abertas
        if not hasattr(self, 'dlg') or self.dlg is None:
            self.dlg = AtribuirBlocoDialog(self.iface, blocos_disponiveis, self.iface.mainWindow())
            # Libera a referencia quando fechado
            self.dlg.finished.connect(self.on_dialog_closed)
            
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
        
    def on_dialog_closed(self):
        self.dlg = None
