from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsWkbTypes, QgsField, QgsProject, QgsFeature
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class AtribuirDnTool(AqueductTool):
    """
    Ferramenta para atribuir valor de Diâmetro Nominal (DN) 
    às linhas selecionadas.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_atribuir_dn.svg')
        
        self.action = QAction(QIcon(icon_path), 'Atribuir Diâmetro Nominal (DN)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validação da Camada
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        # Verifica Geometria (Linha)
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        # 2. Validação da Seleção (Obrigatória)
        selected_count = layer.selectedFeatureCount()
        if selected_count == 0:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma linha selecionada. Selecione as linhas que deseja atualizar.", level=2, duration=5)
            return

        # 3. Input do DN
        dn_value, ok = QInputDialog.getInt(
            self.iface.mainWindow(),
            "Aqueduct - Definir DN",
            f"Informe o Diâmetro Nominal (DN) para as {selected_count} linhas selecionadas:",
            50, 0, 5000, 1
        )
        
        if not ok:
            return

        # 4. Gerenciamento do Campo 'DN'
        field_name = "DN"
        idx = layer.fields().indexOf(field_name)
        
        layer.startEditing()
        
        if idx == -1:
            # Cria campo Inteiro para DN
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Int)])
            layer.updateFields()
            idx = layer.fields().indexOf(field_name)

        # 5. Atualização
        count = 0
        features = layer.selectedFeatures()
        
        for feat in features:
            layer.changeAttributeValue(feat.id(), idx, dn_value)
            count += 1
        
        layer.commitChanges()

        # 6. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            f"DN {dn_value} atribuído com sucesso a {count} linhas.", 
            level=0, 
            duration=3
        )
