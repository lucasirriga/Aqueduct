from qgis.PyQt.QtWidgets import QAction, QInputDialog, QDialog, QVBoxLayout, QLabel, QDoubleSpinBox, QSpinBox, QDialogButtonBox
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsWkbTypes, QgsFeature, QgsGeometry, QgsField
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class TaperingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Tapering (Divisão)")
        
        layout = QVBoxLayout()
        
        # Distância do Fim
        layout.addWidget(QLabel("Distância de Corte (a partir do FIM) em metros:"))
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.01, 10000.0)
        self.spin_dist.setValue(20.0)
        self.spin_dist.setDecimals(2)
        layout.addWidget(self.spin_dist)
        
        # DN do Primeiro Trecho (Inicio -> Corte)
        layout.addWidget(QLabel("DN do Trecho INICIAL (Restante):"))
        self.spin_dn1 = QSpinBox()
        self.spin_dn1.setRange(0, 5000)
        self.spin_dn1.setValue(75)
        layout.addWidget(self.spin_dn1)
        
        # DN do Segundo Trecho (Corte -> Fim)
        layout.addWidget(QLabel("DN do Trecho FINAL (Cortado):"))
        self.spin_dn2 = QSpinBox()
        self.spin_dn2.setRange(0, 5000)
        self.spin_dn2.setValue(50)
        layout.addWidget(self.spin_dn2)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)

class DividirDnTool(AqueductTool):
    """
    Ferramenta para dividir (cortar) linhas a uma distância fixa do final.
    Atualiza DNs dos dois segmentos resultantes.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_dividir_dn.svg')
        
        self.action = QAction(QIcon(icon_path), 'Dividir Linha por Tapering (DN)', self.iface.mainWindow())
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
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de LINHAS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de LINHA.", level=3, duration=5)
            return

        selected_count = layer.selectedFeatureCount()
        if selected_count == 0:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma linha selecionada. Selecione as linhas para dividir.", level=2, duration=5)
            return
            
        # 2. Input do Usuário (Dialog Customizado)
        dlg = TaperingDialog(self.iface.mainWindow())
        if not dlg.exec_():
            return
            
        cut_dist = dlg.spin_dist.value()
        dn1_val = dlg.spin_dn1.value()
        dn2_val = dlg.spin_dn2.value()

        # 3. Preparação Campos
        field_dn = "DN"
        idx_dn = layer.fields().indexOf(field_dn)
        
        layer.startEditing()
        
        if idx_dn == -1:
            layer.dataProvider().addAttributes([QgsField(field_dn, QVariant.Int)])
            layer.updateFields()
            idx_dn = layer.fields().indexOf(field_dn)

        # 4. Processamento
        layer.beginEditCommand("Dividir Linha (Tapering)")
        
        count_split = 0
        features = layer.selectedFeatures()
        
        for feat in features:
            geom = feat.geometry()
            length = geom.length()
            
            # Validações de comprimento
            if length <= cut_dist:
                # Se a linha for menor que o corte, o que fazer?
                # Opção A: Ignorar.
                # Opção B: Atribuir tudo ao DN2?
                # Vamos ignorar e avisar no log/console.
                print(f"Linha {feat.id()} ignorada (comprimento {length:.2f} < corte {cut_dist})")
                continue
                
            # Calcular ponto de corte
            # Distancia do inicio = Total - Distancia do Fim
            split_point_dist = length - cut_dist
            
            # Divide a geometria
            # Fix: QgsGeometry não tem curveSubstring direto. Acessar AbstractGeometry.
            
            if geom.isMultipart():
                # Simplificação: Se for multipart, tenta pegar a primeira parte ou avisa
                # Para redes hídricas conectadas, geralmente é single part.
                # Vamos converter para single se for apenas 1 parte, senão pular.
                if geom.wkbType() == QgsWkbTypes.MultiLineString and len(geom.asMultiPolyline()) == 1:
                     abstract_geom = geom.constGet().geometryN(0) # Pega a primeira parte
                else:
                     print(f"Feature {feat.id()} é multipart complexo. Pulando divisão exata.")
                     continue
            else:
                abstract_geom = geom.constGet()

            try:
                # curveSubstring retorna um novo QgsCurve* (QgsAbstractGeometry*)
                # Args: startDistance, endDistance
                seg_start = abstract_geom.curveSubstring(0, split_point_dist)
                seg_end = abstract_geom.curveSubstring(split_point_dist, length)
                
                # Encapsula de volta em QgsGeometry
                geom_start = QgsGeometry(seg_start)
                geom_end = QgsGeometry(seg_end)
            except Exception as e:
                print(f"Erro ao dividir geometria {feat.id()}: {e}")
                continue
            
            if not geom_start or not geom_end:
                continue
                
            # Atualiza a feature original para ser o Trecho 1 (Inicio)
            layer.changeGeometry(feat.id(), geom_start)
            layer.changeAttributeValue(feat.id(), idx_dn, dn1_val)
            
            # Cria nova feature para o Trecho 2 (Fim)
            new_feat = QgsFeature(feat) # Copia atributos
            new_feat.setGeometry(geom_end)
            new_feat.setAttribute(idx_dn, dn2_val)
            
            # Adiciona nova feature
            layer.addFeature(new_feat)
            
            count_split += 1

        layer.endEditCommand()
        layer.triggerRepaint()

        # 5. Relatório
        self.iface.messageBar().pushMessage(
            "Aqueduct", 
            f"Divisão concluída! {count_split} linhas divididas.", 
            level=0, 
            duration=4
        )
