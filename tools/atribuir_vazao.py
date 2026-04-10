from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsWkbTypes, QgsField, QgsProject, QgsFeature
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class AtribuirVazaoTool(AqueductTool):
    """
    Ferramenta para atribuir valor de Vazão Manualmente 
    às linhas selecionadas.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_atribuir_vazao.svg')
        
        self.action = QAction(QIcon(icon_path), 'Atribuir Vazão Manual', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def is_destructive(self):
        return True

    def run(self):
        layer = self.iface.activeLayer()
        self.run_with_layer(layer)

    def run_automated(self, params=None):
        """Executa via IA."""
        vazao = params.get('vazao', params.get('v'))
        if vazao is None:
            raise Exception("Parâmetro 'vazao' não fornecido.")
            
        layer_name = params.get('camada')
        if layer_name:
            layers = QgsProject.instance().mapLayersByName(layer_name)
            if not layers:
                raise Exception(f"Camada '{layer_name}' não encontrada.")
            layer = layers[0]
        else:
            layer = self.iface.activeLayer()

        self.run_with_layer(layer, vazao_override=vazao)

    def run_with_layer(self, layer, vazao_override=None):
        # 1. Validação da Camada
        if not layer or layer.type() != QgsMapLayerType.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        # 2. Validação da Seleção (Obrigatória se manual, facultativa se auto?) 
        # Para IA, se não houver seleção, vamos aplicar em TUDO? 
        # Melhor respeitar seleção ou pedir confirmação de "Aplicar em tudo".
        selected_count = layer.selectedFeatureCount()
        features = layer.selectedFeatures()
        
        if selected_count == 0:
            if vazao_override is not None:
                # Se for via IA e não tiver seleção, aplica em todos (com cuidado)
                features = list(layer.getFeatures())
                selected_count = len(features)
            else:
                self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma linha selecionada.", level=2, duration=5)
                return

        # 3. Input da Vazão
        if vazao_override is not None:
            vazao_val = float(vazao_override)
        else:
            vazao_val, ok = QInputDialog.getDouble(
                self.iface.mainWindow(),
                "Aqueduct - Definir Vazão",
                f"Informe a Vazão (m³/h) para as {selected_count} linhas:",
                0.0, 0.0, 100000.0, 2
            )
            if not ok: return

        # 4. Gerenciamento do Campo 'V'
        field_name = "V"
        idx = layer.fields().indexOf(field_name)
        
        layer.startEditing()
        
        if idx == -1:
            # Cria campo Double para Vazão
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Double, len=10, prec=2)])
            layer.updateFields()
            idx = layer.fields().indexOf(field_name)

        # 5. Atualização
        count = 0
        for feat in features:
            layer.changeAttributeValue(feat.id(), idx, round(vazao_val, 2))
            count += 1
        
        layer.commitChanges()

        # 6. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            f"Vazão {vazao_val} atribuída com sucesso a {count} linhas.", 
            level=0, 
            duration=3
        )
