from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsWkbTypes, QgsField
from qgis.PyQt.QtCore import QVariant
import os
import math

from .ferramenta_base import AqueductTool

class CalculoHfTool(AqueductTool):
    """
    Ferramenta para calcular Perda de Carga (Hf) em tubulações.
    Fórmula: Hazen-Williams
    Parâmetros esperados nos campos:
    - Comprimento (m)
    - DN (mm)
    - vazao (m³/h)
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_hf.svg')
        
        self.action = QAction(QIcon(icon_path), 'Calcular Perda de Carga (Hf)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações
        if not layer or layer.type() != layer.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3)
            return

        # Verifica campos necessários
        fields = layer.fields()
        idx_len = fields.indexOf("Comprimento")
        idx_dn = fields.indexOf("DN")
        idx_flow = fields.indexOf("vazao")
        
        missing = []
        if idx_len == -1: missing.append("Comprimento")
        if idx_dn == -1: missing.append("DN")
        if idx_flow == -1: missing.append("vazao")
        
        if missing:
             self.iface.messageBar().pushMessage(
                 "Aqueduct", 
                 f"Campos obrigatórios ausentes: {', '.join(missing)}. Execute as ferramentas anteriores primeiro.", 
                 level=3
             )
             return

        # 2. Prepara Campo Hf
        field_name = "Hf"
        idx_hf = fields.indexOf(field_name)
        
        layer.startEditing()
        
        if idx_hf == -1:
            layer.dataProvider().addAttributes([QgsField(field_name, QVariant.Double, len=10, prec=4)])
            layer.updateFields()
            idx_hf = layer.fields().indexOf(field_name)

        # 3. Definição do Escopo
        selected_count = layer.selectedFeatureCount()
        if selected_count > 0:
            features = layer.selectedFeatures()
            mode_msg = "apenas nas feições selecionadas"
        else:
            features = layer.getFeatures()
            mode_msg = "em todas as feições"

        count = 0
        errors = 0
        
        # Coeficiente de Hazen-Williams
        C = 130.0
        
        for feat in features:
            try:
                L = feat.attributes()[idx_len] # Metros
                DN = feat.attributes()[idx_dn] # Milímetros
                Q_m3h = feat.attributes()[idx_flow] # m³/h
                
                # Validação de valores nulos ou zero
                if L is None or DN is None or Q_m3h is None or DN <= 0:
                    continue
                    
                # Conversões para Sistema Internacional (SI) para fórmula padrão
                # Q em m³/s
                Q_si = float(Q_m3h) / 3600.0
                # D em metros
                D_si = float(DN) / 1000.0
                
                # Fórmula Hazen-Williams (SI Metric)
                # J (m/m) = 10.67 * (Q / C)^1.852 * D^-4.87
                
                # Q/C
                term1 = (Q_si / C) ** 1.852
                
                # D^-4.87
                term2 = D_si ** -4.87
                
                # J (Perda unitária)
                J = 10.67 * term1 * term2
                
                # Hf Total = J * L
                Hf = J * float(L)
                
                layer.changeAttributeValue(feat.id(), idx_hf, Hf)
                count += 1
                
            except Exception as e:
                errors += 1
                print(f"Erro calculando Hf feature {feat.id()}: {e}")

        layer.commitChanges()

        # 4. Relatório
        msg = f"Cálculo Hf concluído {mode_msg}. Processados: {count}. Erros/Ignorados: {errors}."
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=5)
