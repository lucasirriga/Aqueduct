from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import (
    QgsWkbTypes, QgsField, QgsProject, QgsFeature, 
    QgsSpatialIndex, QgsGeometry, QgsCoordinateTransform
)
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class VazaoLinhaTool(AqueductTool):
    """
    Ferramenta para contar emissores (pontos) que tocam linhas
    e calcular a vazão total da linha.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_vazao_linha.svg')
        
        self.action = QAction(QIcon(icon_path), 'Calcular Vazão por Emissores (Linha)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        line_layer = self.iface.activeLayer()
        
        # 1. Validação da Camada de Linhas (Alvo)
        if not line_layer or line_layer.type() != line_layer.VectorLayer or line_layer.geometryType() != QgsWkbTypes.LineGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada de LINHAS ativa primeiro.", level=3)
            return

        # 2. Seleção da Camada de Pontos (Emissores)
        point_layers = []
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.type() == layer.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry:
                point_layers.append(layer)
        
        if not point_layers:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada de pontos encontrada no projeto.", level=3)
            return
            
        point_layer_names = [l.name() for l in point_layers]
        
        item, ok = QInputDialog.getItem(
            self.iface.mainWindow(), 
            "Aqueduct - Seleção de Emissores", 
            "Selecione a camada de pontos (emissores):", 
            point_layer_names, 
            0, 
            False
        )
        
        if not ok or not item:
            return
            
        selected_point_layer = None
        for layer in point_layers:
            if layer.name() == item:
                selected_point_layer = layer
                break
        
        if not selected_point_layer:
            return

        # 3. Input da Vazão (L/h)
        vazao_lph, ok_vazao = QInputDialog.getDouble(
            self.iface.mainWindow(),
            "Aqueduct - Vazão do Emissor",
            "Vazão de UM emissor (L/h):",
            1.0, 0.001, 10000.0, 2
        )
        
        if not ok_vazao:
            return

        # 4. Preparação dos Campos
        line_layer.startEditing()
        data_provider = line_layer.dataProvider()
        
        # Campos: 'emissores' (int) e 'vazao' (double)
        fields_to_add = []
        idx_emissores = line_layer.fields().indexOf("emissores")
        idx_vazao = line_layer.fields().indexOf("vazao")
        
        if idx_emissores == -1:
            fields_to_add.append(QgsField("emissores", QVariant.Int))
        if idx_vazao == -1:
            fields_to_add.append(QgsField("vazao", QVariant.Double, len=10, prec=3))
            
        if fields_to_add:
            data_provider.addAttributes(fields_to_add)
            line_layer.updateFields()
            idx_emissores = line_layer.fields().indexOf("emissores")
            idx_vazao = line_layer.fields().indexOf("vazao")

        # 5. Processamento (Spatial Index)
        self.iface.messageBar().pushMessage("Aqueduct", "Calculando emissores nas linhas...", level=0)
        
        point_provider = selected_point_layer.dataProvider()
        point_index = QgsSpatialIndex(point_provider.getFeatures())
        
        # Setup de Transformação de Coordenadas (CRS)
        source_crs = line_layer.crs()
        target_crs = selected_point_layer.crs()
        transform = None
        
        if source_crs != target_crs:
            self.iface.messageBar().pushMessage("Aqueduct", "Transformando coordenadas...", level=0)
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())

        # Define quais linhas processar
        if line_layer.selectedFeatureCount() > 0:
            features_lines = line_layer.selectedFeatures()
            mode_msg = "apenas nas linhas selecionadas"
        else:
            features_lines = line_layer.getFeatures()
            mode_msg = "em todas as linhas"

        count_features = 0
        total_emissores = 0
        
        # Buffer de tolerância para "toque" (em unidades do mapa da linha)
        # Se for métrico (UTM), 0.05 metro (5cm) é razoável para pegar pontos "em cima".
        # Se for grau (WGS84), seria muito menor. Assumindo projeção métrica para irrigação.
        tolerance = 0.05 
        if source_crs.isGeographic():
            tolerance = 0.0000005 # Aprox 5cm no equador
            
        for line_feat in features_lines:
            line_geom = line_feat.geometry()
            if not line_geom:
                continue
                
            # Prepara geometria para busca (transforma se necessário)
            geom_for_check = line_geom
            if transform:
                try:
                    # Clone e transformação
                    geom_copy = QgsGeometry(line_geom) # Copy constructor
                    geom_copy.transform(transform)
                    geom_for_check = geom_copy
                except Exception as e:
                    print(f"Erro transform: {e}")
                    continue

            # Bounding Box Bufferizado para garantir que pegamos pontos na borda
            bbox = geom_for_check.boundingBox()
            # Precisamos expandir o bbox um pouco pois o ponto pode estar "quase" tocando
            # e o index ignoraria. Mas o spatial index é estrito. 
            # O ideal é usar o buffer da geometria para interseção.
            
            # Estratégia: Buffer na linha para pegar pontos próximos
            # Bufferizando a linha de check (que está no CRS dos pontos)
            if transform:
                 # Se transformamos a linha para o CRS dos pontos, o buffer deve ser em unidades do CRS dos pontos
                 buffer_geom = geom_for_check.buffer(tolerance, 5)
            else:
                 # Buffer normal
                 buffer_geom = line_geom.buffer(tolerance, 5)
            
            candidate_ids = point_index.intersects(buffer_geom.boundingBox())
            
            points_inside = 0
            for pid in candidate_ids:
                pt_feat = selected_point_layer.getFeature(pid)
                if pt_feat.hasGeometry():
                    if buffer_geom.intersects(pt_feat.geometry()):
                         points_inside += 1
            
            # Cálculo de vazão da Linha (m³/h)
            # (Qtd * L_h) / 1000
            vazao_calc = (points_inside * vazao_lph) / 1000.0
            
            line_layer.changeAttributeValue(line_feat.id(), idx_emissores, points_inside)
            line_layer.changeAttributeValue(line_feat.id(), idx_vazao, vazao_calc)
            
            total_emissores += points_inside
            count_features += 1

        line_layer.commitChanges()

        # 6. Relatório
        msg = (f"Cálculo finalizado {mode_msg}. Linhas: {count_features}. "
               f"Emissores: {total_emissores}.")
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=5)
