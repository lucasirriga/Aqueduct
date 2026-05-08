from qgis.PyQt.QtWidgets import QAction, QInputDialog
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsWkbTypes, QgsField, QgsProject, QgsFeature, QgsSpatialIndex
from qgis.PyQt.QtCore import QVariant
import os

from .ferramenta_base import AqueductTool

class VazaoSetorTool(AqueductTool):
    """
    Ferramenta para contar emissores (pontos) dentro de setores (polígonos)
    e calcular a vazão total.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_vazao_setor.svg')
        
        self.action = QAction(QIcon(icon_path), 'Calcular Vazão e Emissores', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        poly_layer = self.iface.activeLayer()
        
        # 1. Validação da Camada de Polígonos (Alvo)
        if not poly_layer or poly_layer.type() != QgsMapLayerType.VectorLayer or poly_layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada de POLÍGONOS ativa primeiro.", level=3, duration=5)
            return

        # 2. Seleção da Camada de Pontos (Emissores)
        # Lista apenas camadas de ponto do projeto
        point_layers = []
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.type() == QgsMapLayerType.VectorLayer and layer.geometryType() == QgsWkbTypes.PointGeometry:
                point_layers.append(layer)
        
        if not point_layers:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma camada de pontos encontrada no projeto.", level=3, duration=5)
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
            
        # Pega a camada selecionada pelo nome
        selected_point_layer = None
        for layer in point_layers:
            if layer.name() == item:
                selected_point_layer = layer
                break
        
        if not selected_point_layer:
            return

        # 3. Input da Vazão
        vazao_litros, ok_vazao = QInputDialog.getDouble(
            self.iface.mainWindow(),
            "Aqueduct - Vazão",
            "Vazão do emissor (Litros):",
            1.0, 0.001, 10000.0, 2
        )
        
        if not ok_vazao:
            return

        # 4. Preparação dos Campos
        poly_layer.startEditing()
        data_provider = poly_layer.dataProvider()
        
        fields_to_add = []
        idx_emissores = poly_layer.fields().indexOf("emissores")
        idx_vazao = poly_layer.fields().indexOf("V")
        
        if idx_emissores == -1:
            fields_to_add.append(QgsField("emissores", QVariant.Int))
        if idx_vazao == -1:
            fields_to_add.append(QgsField("V", QVariant.Double, len=10, prec=2))
            
        if fields_to_add:
            data_provider.addAttributes(fields_to_add)
            poly_layer.updateFields()
            # Recalcula índices
            idx_emissores = poly_layer.fields().indexOf("emissores")
            idx_vazao = poly_layer.fields().indexOf("V")

        # 5. Processamento (Spatial Index)
        # Cria índice espacial dos pontos para performance
        self.iface.messageBar().pushMessage("Aqueduct", "Indexando pontos...", level=0, duration=5)
        point_provider = selected_point_layer.dataProvider()
        point_index = QgsSpatialIndex(point_provider.getFeatures())
        
        # Validação e Setup de CRS
        source_crs = poly_layer.crs()
        target_crs = selected_point_layer.crs()
        transform = None
        
        from qgis.core import QgsCoordinateTransform
        
        if source_crs != target_crs:
            self.iface.messageBar().pushMessage("Aqueduct Info", f"Transformando geometria de {source_crs.authid()} para {target_crs.authid()}", level=0, duration=5)
            transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())

        # Define quais polígonos processar
        if poly_layer.selectedFeatureCount() > 0:
            features_poly = poly_layer.selectedFeatures()
            mode_msg = "apenas nas feições selecionadas"
        else:
            features_poly = poly_layer.getFeatures()
            mode_msg = "em todas as feições"

        count_features = 0
        total_emissores = 0
        
        for poly_feat in features_poly:
            poly_geom = poly_feat.geometry()
            if not poly_geom:
                continue
                
            # Transforma geometria do polígono para o CRS dos pontos se necessário
            # para garantir que a busca espacial funcione corretamente
            geom_for_spatial_check = poly_geom
            if transform:
                try:
                    # Clone para não alterar a geometria original na camada (embora geometry() retorne copia)
                    geom_copy = QgsFeature(poly_feat).geometry() 
                    geom_copy.transform(transform)
                    geom_for_spatial_check = geom_copy
                except Exception as e:
                    print(f"Erro de transformação: {e}")
                    continue

            # Otimização: Primeiro pega candidatos pelo Bounding Box
            candidate_ids = point_index.intersects(geom_for_spatial_check.boundingBox())
            
            # Refinamento: Verifica contêm
            points_inside = 0
            for pid in candidate_ids:
                # É preciso buscar a feature do ponto para ter a geometria exata
                pt_feat = selected_point_layer.getFeature(pid)
                if pt_feat.hasGeometry() and geom_for_spatial_check.contains(pt_feat.geometry()):
                    points_inside += 1
            
            # Cálculo de vazão
            # (Qtd * Litros) / 1000
            vazao_calc = (points_inside * vazao_litros) / 1000.0
            
            # Atualiza atributos
            poly_layer.changeAttributeValue(poly_feat.id(), idx_emissores, points_inside)
            poly_layer.changeAttributeValue(poly_feat.id(), idx_vazao, round(vazao_calc, 2))
            
            total_emissores += points_inside
            count_features += 1

        poly_layer.commitChanges()

        # 6. Relatório
        msg = (f"Cálculo finalizado {mode_msg}.\n"
               f"Setores processados: {count_features}\n"
               f"Total de Emissores encontrados: {total_emissores}")
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=5)
