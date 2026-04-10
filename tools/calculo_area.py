from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsWkbTypes, QgsField
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class CalculoAreaTool(AqueductTool):
    """
    Ferramenta para calcular a área de polígonos na camada ativa.
    Resultado em Hectares (ha).
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_area.svg')
        
        self.action = QAction(QIcon(icon_path), 'Calcular Área (Hectares)', self.iface.mainWindow())
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
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada selecionada.", level=3, duration=5)
            return

        if layer.type() != QgsMapLayerType.VectorLayer:
             self.iface.messageBar().pushMessage("Aqueduct", "A camada selecionada não é vetorial.", level=3, duration=5)
             return
             
        # Verifica se é Polígono ou MultiPolígono
        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "A camada deve ser de polígonos.", level=3, duration=5)
            return

        # 2. Definição do escopo (Selecionados vs Todos)
        selected_count = layer.selectedFeatureCount()
        if selected_count > 0:
            features_to_process = layer.selectedFeatures()
            mode_msg = "apenas nas feições selecionadas"
        else:
            features_to_process = layer.getFeatures()
            mode_msg = "em todas as feições"

        # 3. Preparação do Campo 'Area'
        field_name = "Area"
        idx = layer.fields().indexOf(field_name)
        
        layer.startEditing()
        
        if idx == -1:
            # Cria campo Double com precisão 3
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Double, len=10, prec=3)])
            layer.updateFields()
            idx = layer.fields().indexOf(field_name)

        # 4. Cálculo
        count = 0
        total_area = 0.0
        
        for feature in features_to_process:
            geom = feature.geometry()
            if geom:
                # Area no QGIS é em unidades do mapa. Assumindo projeção métrica.
                # 1 ha = 10,000 m²
                area_m2 = geom.area()
                area_ha = area_m2 / 10000.0
                
                layer.changeAttributeValue(feature.id(), idx, area_ha)
                total_area += area_ha
                count += 1
        
        layer.commitChanges()

        # 5. Relatório
        msg = f"Cálculo concluído {mode_msg}. Polígonos: {count}. Área Total: {total_area:.3f} ha."
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=5)
