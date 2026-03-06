import os
import math
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QDoubleSpinBox, QDialogButtonBox, QMessageBox, QProgressDialog)
from qgis.PyQt.QtCore import Qt, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsProject, QgsPointXY,
    QgsWkbTypes, QgsField, QgsSpatialIndex, QgsMapLayerProxyModel
)

from .ferramenta_base import AqueductTool

class AcumuloVazaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Roteamento e Acúmulo de Vazão')
        self.resize(400, 300)
        
        layout = QVBoxLayout(self)
        
        # Camada de Emissores (Pontos)
        layout.addWidget(QLabel("Camada de Emissores (Pontos):"))
        self.cb_emissores = QgsMapLayerComboBox()
        self.cb_emissores.setFilters(QgsMapLayerProxyModel.PointLayer)
        layout.addWidget(self.cb_emissores)
        
        # Camada de Linhas Laterais (Linhas)
        layout.addWidget(QLabel("Camada de Linhas Laterais:"))
        self.cb_laterais = QgsMapLayerComboBox()
        self.cb_laterais.setFilters(QgsMapLayerProxyModel.LineLayer)
        layout.addWidget(self.cb_laterais)
        
        # Camada de Linhas de Derivação (Linhas)
        layout.addWidget(QLabel("Camada de Linhas de Derivação:"))
        self.cb_derivacao = QgsMapLayerComboBox()
        self.cb_derivacao.setFilters(QgsMapLayerProxyModel.LineLayer)
        layout.addWidget(self.cb_derivacao)
        
        # Camada de Cavaletes (Pontos)
        layout.addWidget(QLabel("Camada de Cavaletes (Destino):"))
        self.cb_cavaletes = QgsMapLayerComboBox()
        self.cb_cavaletes.setFilters(QgsMapLayerProxyModel.PointLayer)
        layout.addWidget(self.cb_cavaletes)
        
        # Vazão por Emissor
        layout.addWidget(QLabel("Vazão por Emissor (L/h):"))
        self.spin_vazao = QDoubleSpinBox()
        self.spin_vazao.setRange(0.01, 10000.0)
        self.spin_vazao.setValue(2.0)
        self.spin_vazao.setDecimals(2)
        layout.addWidget(self.spin_vazao)
        
        layout.addStretch()
        
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

    def get_inputs(self):
        return {
            'emissores': self.cb_emissores.currentLayer(),
            'laterais': self.cb_laterais.currentLayer(),
            'derivacao': self.cb_derivacao.currentLayer(),
            'cavaletes': self.cb_cavaletes.currentLayer(),
            'vazao': self.spin_vazao.value()
        }


class AcumuloVazaoTool(AqueductTool):
    """
    Ferramenta para acumular vazão na rede hidráulica.
    Roteia o fluxo dos emissores pelas laterais e derivações até o cavalete.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_hf.svg') 
        if not os.path.exists(icon_path):
             icon_path = ""
             
        self.action = QAction(QIcon(icon_path), 'Acúmulo de Vazão (Roteamento)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = AcumuloVazaoDialog(self.iface.mainWindow())
        if not dlg.exec_():
            return
            
        inputs = dlg.get_inputs()
        
        if not all([inputs['emissores'], inputs['laterais'], inputs['derivacao'], inputs['cavaletes']]):
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione todas as 4 camadas.", level=2, duration=5)
            return
            
        self.execute_routing(
            inputs['emissores'], 
            inputs['laterais'], 
            inputs['derivacao'], 
            inputs['cavaletes'], 
            inputs['vazao']
        )
        
    def round_point(self, pt):
        """Arredonda a coordenada para evitar problemas de precisao float"""
        return (round(pt.x(), 3), round(pt.y(), 3))

    def execute_routing(self, lyr_emissores, lyr_laterais, lyr_derivacao, lyr_cavaletes, vazao_emissor):
        self.iface.messageBar().pushMessage("Aqueduct", "Construindo topologia de rede e quebrando linhas...", level=0, duration=3)
        
        progress = QProgressDialog("Construindo rede (Split nas conexões)...", "Cancelar", 0, 100, self.iface.mainWindow())
        progress.setWindowTitle("Roteamento de Vazão")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        # 1. Coletar todos os pontos notáveis para "snapping" (Emissores + Cavaletes)
        notable_points = []
        for f in lyr_emissores.getFeatures():
            notable_points.append(f.geometry())
        for f in lyr_cavaletes.getFeatures():
            notable_points.append(f.geometry())
            
        # Também podemos adicionar nós de intersecção entre derivações para garantir
        index_notable = QgsSpatialIndex()
        for i, geom in enumerate(notable_points):
            f = QgsFeature()
            f.setId(i)
            f.setGeometry(geom)
            index_notable.insertFeature(f)
            
        nodes = set()
        edges = [] # edge: (node_a, node_b, length, geom, flow, tipo)
        
        def process_layer(layer, tipo):
            for f in layer.getFeatures():
                geom = f.geometry()
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                else:
                    lines = [geom.asPolyline()]
                    
                for line in lines:
                    line_geom = QgsGeometry.fromPolylineXY(line)
                    
                    # Coleta vértices originais e pontos notáveis próximos
                    vertices_on_line = []
                    
                    # 1. Adiciona Vértices Originais
                    for pt in line:
                        dist_along = float(line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pt)))
                        vertices_on_line.append((dist_along, pt))
                        
                    # 2. Busca Pontos Notáveis próximos (BoundingBox expandida)
                    bbox = line_geom.boundingBox()
                    bbox.grow(1.0) # 1 metro tolerância
                    candidate_ids = index_notable.intersects(bbox)
                    
                    for cid in candidate_ids:
                        target_geom = notable_points[cid]
                        # Mede distancia exata
                        if line_geom.distance(target_geom) < 0.5: # 50cm de tolerância para "tocar" a linha
                            # Encontra o ponto projetado e a distancia ao longo da linha
                            dist_along = float(line_geom.lineLocatePoint(target_geom))
                            pt_proj = line_geom.interpolate(dist_along).asPoint()
                            vertices_on_line.append((dist_along, pt_proj))
                            
                    # Ordena todos os vértices pela distância ao longo da linha
                    vertices_on_line.sort(key=lambda x: x[0])
                    
                    # Remove duplicatas (pontos muito próximos)
                    filtered_vertices = []
                    last_dist = -999.0
                    for dist_along, pt in vertices_on_line:
                        if (dist_along - last_dist) > 0.05: # 5cm minimos para ser trecho válido
                            filtered_vertices.append(pt)
                            last_dist = dist_along
                            
                    # Agora cria as arestas
                    for i in range(len(filtered_vertices) - 1):
                        pt_a = self.round_point(filtered_vertices[i])
                        pt_b = self.round_point(filtered_vertices[i+1])
                        nodes.add(pt_a)
                        nodes.add(pt_b)
                        
                        seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(*pt_a), QgsPointXY(*pt_b)])
                        edges.append({
                            'u': pt_a,
                            'v': pt_b,
                            'length': seg_geom.length(),
                            'geom': seg_geom,
                            'flow': 0.0,
                            'tipo': tipo
                        })

        progress.setValue(10)
        process_layer(lyr_laterais, 'lateral')
        progress.setValue(20)
        process_layer(lyr_derivacao, 'derivacao')
        
        progress.setValue(20)
        progress.setLabelText("Mapeando Cavaletes e Emissores...")
        
        # 2. Mapear Cavaletes (Targets) para os nós mais próximos da rede
        cavalete_nodes = set()
        for f in lyr_cavaletes.getFeatures():
            geom = f.geometry()
            pt = self.round_point(geom.asPoint())
            # O cavalete pode já bater num node exato, ou precisarmos pegar o mais proximo.
            # Para simplificar na Etapa 1, assumimos que ele "Toca" a rede e o vértice existe.
            # Se não tocar exatamente, achamos o node mais proximo.
            closest_node = None
            min_dist = float('inf')
            pt_xy = QgsPointXY(*pt)
            for n in nodes:
                n_xy = QgsPointXY(*n)
                d = pt_xy.distance(n_xy)
                if d < min_dist:
                    min_dist = d
                    closest_node = n
            if closest_node and min_dist < 2.0: # tolerância de 2m
                cavalete_nodes.add(closest_node)

        # 3. Montar grafo para busca (Dijkstra)
        # Como a tubulação pode ter fluxo em qualquer direção, o grafo é não-direcionado num primeiro momento.
        graph = {n: {} for n in nodes}
        for idx, edge in enumerate(edges):
            u, v, cost = edge['u'], edge['v'], edge['length']
            graph[u][v] = (cost, idx) # node_dst -> (distancia, id_da_aresta)
            graph[v][u] = (cost, idx)

        progress.setValue(40)
        progress.setLabelText("Roteando emissores...")
        
        # 4. Roteamento: Para cada emissor, achar o menor caminho até QUALQUER cavalete.
        # Ao invés de rodar Dijkstra de cada emissor (q sao muitos), 
        # invertemos: rodamos Dijkstra a partir DOS CAVALETES p/ todos os nós.
        # Assim achamos os prev_nodes e shortest_paths de qualquer nó da rede ate o cavalete.
        
        import heapq
        
        distances = {n: float('inf') for n in nodes}
        # next_hop diz qual é a aresta que me leva em direção ao cavalete
        next_edge = {n: None for n in nodes} 
        
        pq = []
        for cv_node in cavalete_nodes:
            distances[cv_node] = 0
            heapq.heappush(pq, (0, cv_node))
            
        while pq:
            d, curr = heapq.heappop(pq)
            if d > distances[curr]:
                continue
                
            for neighbor, (cost, edge_idx) in graph[curr].items():
                new_d = d + cost
                if new_d < distances[neighbor]:
                    distances[neighbor] = new_d
                    next_edge[neighbor] = edge_idx  # Aresta que liga neighbor a curr
                    heapq.heappush(pq, (new_d, neighbor))
                    
        progress.setValue(60)
        progress.setLabelText("Acumulando fluxos...")

        # 5. Acumular fluxo
        emissores_feats = list(lyr_emissores.getFeatures())
        total_e = len(emissores_feats)
        for i, f in enumerate(emissores_feats):
            if i % 100 == 0:
                QCoreApplication.processEvents()
                if progress.wasCanceled():
                    return
            
            geom = f.geometry()
            pt = self.round_point(geom.asPoint())
            pt_xy = QgsPointXY(*pt)
            
            # Encontra nó da rede mais proximo
            closest_node = None
            min_dist = float('inf')
            for n in nodes:
                d = pt_xy.distance(QgsPointXY(*n))
                if d < min_dist:
                    min_dist = d
                    closest_node = n
                    
            if closest_node is not None and distances.get(closest_node, float('inf')) < float('inf'):
                # Injeta a vazao e percorre o caminho gravado pelo next_edge
                curr_node = closest_node
                while True:
                    e_idx = next_edge.get(curr_node)
                    if e_idx is None:
                        break
                        
                    edges[e_idx]['flow'] += vazao_emissor
                    
                    # Vai para o próximo nó em direção ao cavalete
                    # A aresta 'e_idx' liga u e v. Um deles é curr_node. 
                    u, v = edges[e_idx]['u'], edges[e_idx]['v']
                    curr_node = u if u != curr_node else v

        progress.setValue(80)
        progress.setLabelText("Gerando camadas de saída...")

        # 6. Criar camada de saída
        crs = lyr_laterais.crs().authid()
        out_layer = QgsVectorLayer(f"LineString?crs={crs}", "Topologia e Acúmulo de Vazão", "memory")
        pr = out_layer.dataProvider()
        pr.addAttributes([
            QgsField("tipo", QVariant.String),
            QgsField("vazao_acumulada", QVariant.Double)
        ])
        out_layer.updateFields()
        
        out_features = []
        for edge in edges:
            # Pula arestas por onde não passa água, se desejável (opcional)
            if edge['flow'] > 0:
                feat = QgsFeature()
                feat.setGeometry(edge['geom'])
                feat.setAttributes([edge['tipo'], edge['flow']])
                out_features.append(feat)
                
        pr.addFeatures(out_features)
        QgsProject.instance().addMapLayer(out_layer)
        
        progress.setValue(100)
        self.iface.messageBar().pushMessage("Aqueduct", f"Roteamento concluído com sucesso. Vazão máxima num tubo: {max((e['flow'] for e in edges), default=0):.2f} L/h", level=0, duration=10)
