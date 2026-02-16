from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsWkbTypes, QgsField, QgsProject, QgsFeature
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

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validação da Camada
        if not layer or layer.type() != layer.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3)
            return

        # Verifica Geometria (Linha)
        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3)
            return

        # 2. Validação da Seleção (Obrigatória)
        selected_count = layer.selectedFeatureCount()
        if selected_count == 0:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma linha selecionada. Selecione as linhas que deseja atualizar.", level=2)
            return

        # 3. Input da Vazão
        vazao_val, ok = QInputDialog.getDouble(
            self.iface.mainWindow(),
            "Aqueduct - Definir Vazão",
            f"Informe a Vazão (m³/h ou L/s) para as {selected_count} linhas selecionadas:",
            0.0, 0.0, 100000.0, 3
        )
        
        if not ok:
            return

        # 4. Gerenciamento do Campo 'vazao'
        # Nota: O nome do campo solicitado é "vazao" (mesmo da ferramenta de setor, ok)
        field_name = "vazao"
        idx = layer.fields().indexOf(field_name)
        
        layer.startEditing()
        
        if idx == -1:
            # Cria campo Double para Vazão
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Double, len=10, prec=3)])
            layer.updateFields()
            idx = layer.fields().indexOf(field_name)

        # 5. Atualização
        count = 0
        features = layer.selectedFeatures()
        
        for feat in features:
            layer.changeAttributeValue(feat.id(), idx, vazao_val)
            count += 1
        
        layer.commitChanges()

        # 6. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            f"Vazão {vazao_val} atribuída com sucesso a {count} linhas.", 
            level=0, 
            duration=3
        )
