from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsWkbTypes, QgsField, QgsProject, QgsFeature
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class LineLengthTool(AqueductTool):
    """
    Ferramenta para calcular o comprimento de linhas na camada ativa.
    """

    def initGui(self):
        # Usa o mesmo ícone por enquanto ou um específico se existisse
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_comprimento.svg')

        self.action = QAction(QIcon(icon_path), 'Calcular Comprimento de Linhas', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações Iniciais
        if not layer:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada selecionada.", level=3) # Critical
            return

        if layer.type() != layer.VectorLayer:
             self.iface.messageBar().pushMessage("Aqueduct", "A camada selecionada não é vetorial.", level=3)
             return
             
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "A camada deve ser de linhas.", level=3)
            return

        # 2. Definição do escopo (Selecionados vs Todos)
        selected_count = layer.selectedFeatureCount()
        if selected_count > 0:
            features_to_process = layer.selectedFeatures()
            mode_msg = "apenas nas feições selecionadas"
        else:
            features_to_process = layer.getFeatures()
            mode_msg = "em todas as feições"

        # 3. Preparação do Campo
        field_name = "L"
        idx = layer.fields().indexOf(field_name)
        
        layer.startEditing()
        
        if idx == -1:
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Double, len=10, prec=3)])
            layer.updateFields()
            idx = layer.fields().indexOf(field_name)

        # 4. Cálculo
        count = 0
        total_length = 0.0
        
        for feature in features_to_process:
            geom = feature.geometry()
            if geom:
                length = geom.length()
                layer.changeAttributeValue(feature.id(), idx, length)
                total_length += length
                count += 1
        
        layer.commitChanges()

        # 5. Relatório
        msg = f"Cálculo concluído {mode_msg}. Feições: {count}. Comprimento Total: {total_length:.3f} m."
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=5)
