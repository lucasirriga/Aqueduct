import os
import math
import heapq
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QMessageBox, QLabel, 
    QDoubleSpinBox, QDialogButtonBox, QComboBox
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
    QgsPointXY, QgsWkbTypes, QgsSpatialIndex, QgsField,
    QgsMapLayerProxyModel, QgsMapLayerType
)

from .ferramenta_base import AqueductTool
from .lista_materiais import ProjectBOMManager
from .gerenciar_pecas import PecaManager

class MicrotuboComandoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Roteamento de Microtubo de Comando")
        self.resize(450, 350)
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # Seleção de Camadas
        self.cb_comando = QgsMapLayerComboBox()
        self.cb_comando.setFilters(QgsMapLayerProxyModel.PointLayer)
        form.addRow("Centro de Comando (Ponto):", self.cb_comando)
        
        self.cb_cavaletes = QgsMapLayerComboBox()
        self.cb_cavaletes.setFilters(QgsMapLayerProxyModel.PointLayer)
        form.addRow("Cavaletes (Alvos):", self.cb_cavaletes)
        
        self.cb_linha_principal = QgsMapLayerComboBox()
        self.cb_linha_principal.setFilters(QgsMapLayerProxyModel.LineLayer)
        self.cb_linha_principal.layerChanged.connect(self._on_layer_lp_changed)
        form.addRow("Camada de Tubulações:", self.cb_linha_principal)
        
        self.cb_campo_tipo = QComboBox()
        self.cb_campo_tipo.currentIndexChanged.connect(self._on_field_changed)
        form.addRow("Campo de Tipo:", self.cb_campo_tipo)
        
        self.cb_valor_tipo = QComboBox()
        form.addRow("Valor para Linha Principal:", self.cb_valor_tipo)
        
        # Seleção de Material
        self.peca_manager = PecaManager()
        self.cb_material = QComboBox()
        self.cb_material.addItems(self.peca_manager.list_names())
        # Tentar pré-selecionar algo com "microtubo" ou "comando"
        for i in range(self.cb_material.count()):
            txt = self.cb_material.itemText(i).lower()
            if "micro" in txt or "comando" in txt:
                self.cb_material.setCurrentIndex(i)
                break
        form.addRow("Peça (Microtubo):", self.cb_material)
        
        # Configuração do Rolo
        self.spin_rolo = QDoubleSpinBox()
        self.spin_rolo.setRange(1.0, 10000.0)
        self.spin_rolo.setValue(600.0) # Conforme sugerido pelo usuário
        self.spin_rolo.setSuffix(" m")
        form.addRow("Comprimento do Rolo/Barra:", self.spin_rolo)
        
        layout.addLayout(form)
        
        # Botões
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        self._auto_selecionar()

    def _on_layer_lp_changed(self, layer):
        self.cb_campo_tipo.clear()
        if not layer: return
        fields = [f.name() for f in layer.fields()]
        self.cb_campo_tipo.addItems(fields)
        
        # Tenta pré-selecionar 'tipo'
        for i in range(self.cb_campo_tipo.count()):
            if self.cb_campo_tipo.itemText(i).lower() == 'tipo':
                self.cb_campo_tipo.setCurrentIndex(i)
                break

    def _on_field_changed(self):
        self.cb_valor_tipo.clear()
        layer = self.cb_linha_principal.currentLayer()
        field = self.cb_campo_tipo.currentText()
        if not layer or not field: return
        
        # Pega valores únicos do campo selecionado
        idx = layer.fields().indexOf(field)
        values = layer.uniqueValues(idx)
        self.cb_valor_tipo.addItems([str(v) for v in values])
        
        # Tenta pré-selecionar 'Principal'
        for i in range(self.cb_valor_tipo.count()):
            if 'principal' in self.cb_valor_tipo.itemText(i).lower():
                self.cb_valor_tipo.setCurrentIndex(i)
                break

    def _auto_selecionar(self):
        """Tenta encontrar as camadas automaticamente."""
        layers = QgsProject.instance().mapLayers().values()
        for lyr in layers:
            if lyr.type() != QgsMapLayerType.VectorLayer:
                continue
            name = lyr.name().lower()
            if lyr.geometryType() == QgsWkbTypes.PointGeometry:
                if "comando" in name or "estat" in name:
                    self.cb_comando.setLayer(lyr)
                if "cavalete" in name or "hidrante" in name:
                    self.cb_cavaletes.setLayer(lyr)
            elif lyr.geometryType() == QgsWkbTypes.LineGeometry:
                if "principal" in name or "adutora" in name or "tronco" in name or "tubulacao" in name:
                    self.cb_linha_principal.setLayer(lyr)

    def get_inputs(self):
        return {
            'comando': self.cb_comando.currentLayer(),
            'cavaletes': self.cb_cavaletes.currentLayer(),
            'linha_principal': self.cb_linha_principal.currentLayer(),
            'filter_field': self.cb_campo_tipo.currentText(),
            'filter_value': self.cb_valor_tipo.currentText(),
            'material': self.cb_material.currentText(),
            'comp_rolo': self.spin_rolo.value()
        }

class MicrotuboComandoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_microtubo_comando.svg')
        if not os.path.exists(icon_path):
             icon_path = "" # Fallback
             
        self.action = QAction(QIcon(icon_path), 'Gerar Microtubo de Comando', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = MicrotuboComandoDialog(self.iface.mainWindow())
        if not dlg.exec_():
            return
            
        inputs = dlg.get_inputs()
        if not all([inputs['comando'], inputs['cavaletes'], inputs['linha_principal']]):
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Selecione as três camadas necessárias.")
            return
            
        self.executor_roteamento(inputs)

    def round_pt(self, pt):
        return (round(pt.x(), 3), round(pt.y(), 3))

    def executor_roteamento(self, inputs):
        lyr_cmd = inputs['comando']
        lyr_cv  = inputs['cavaletes']
        lyr_lp  = inputs['linha_principal']
        filter_field = inputs['filter_field']
        filter_value = inputs['filter_value']
        
        nome_material = inputs['material']
        comp_rolo = inputs['comp_rolo']
        
        # 1. Construir Grafo da Linha Principal
        all_lines = []
        line_idx = QgsSpatialIndex()
        
        nodes = set()
        edges = []
        coord_map = {} # (x,y) -> set(edge_indices)
        
        # Indexar geometrias e pontos notáveis (cruzamentos)
        # Para simplificar, assumimos que a linha principal é conectada
        for f in lyr_lp.getFeatures():
            # FILTRO: Considerar apenas a Linha Principal baseada no campo/valor selecionado
            if filter_field and str(f[filter_field]) != filter_value:
                continue
                
            geom = f.geometry()
            all_lines.append(geom)
            line_idx.insertFeature(f)
            
        # 2. Identificar Ponto de Comando e Cavaletes
        # Pegamos o primeiro ponto do comando (geralmente é só um)
        feat_cmd = next(lyr_cmd.getFeatures(), None)
        if not feat_cmd:
            QMessageBox.critical(None, "Erro", "Nenhum ponto encontrado na camada de Comando.")
            return
        pt_comando = feat_cmd.geometry().asPoint()
        
        # 3. Mapear todos os pontos para a malha do grafo
        # Vamos criar um grafo de vértices + pontos projetados
        raw_edges = []
        nodes_dict = {} # (x,y) -> set(neighbor_nodes)
        
        def add_edge(p1, p2):
            p1_r = self.round_pt(QgsPointXY(*p1))
            p2_r = self.round_pt(QgsPointXY(*p2))
            if p1_r == p2_r: return
            dist = QgsPointXY(*p1_r).distance(QgsPointXY(*p2_r))
            raw_edges.append((p1_r, p2_r, dist))
            
        # Quebrar as linhas em arestas simples, suportando MultiLineString
        for geom in all_lines:
            if geom.isMultipart():
                lines = geom.asMultiPolyline()
            else:
                lines = [geom.asPolyline()]
                
            for polyline in lines:
                for i in range(len(polyline)-1):
                    add_edge(polyline[i], polyline[i+1])
                
        # Construir Adjacency List
        graph = {}
        for u, v, d in raw_edges:
            if u not in graph: graph[u] = []
            if v not in graph: graph[v] = []
            graph[u].append((v, d))
            graph[v].append((u, d))
            
        # Encontrar nós mais próximos para Comando e cada Cavalete
        def find_nearest_node(pt):
            pt_xy = self.round_pt(pt)
            if pt_xy in graph: return pt_xy
            # Busca o nó mais próximo no grafo
            best_node = None
            min_dist = float('inf')
            for node in graph:
                d = QgsPointXY(*pt_xy).distance(QgsPointXY(*node))
                if d < min_dist:
                    min_dist = d
                    best_node = node
            return best_node

        node_comando = find_nearest_node(pt_comando)
        if not node_comando:
            QMessageBox.critical(None, "Erro", "Não foi possível conectar o comando à linha principal.")
            return

        # 4. Roteamento Dijkstra Reverso (do Comando para todos)
        # Isso é mais eficiente: uma única execução encontra o caminho para todos os cavaletes
        distances = {node_comando: 0.0}
        predecessors = {node_comando: None}
        pq = [(0.0, node_comando)]
        
        while pq:
            d, curr = heapq.heappop(pq)
            if d > distances.get(curr, float('inf')): continue
            
            for neighbor, weight in graph.get(curr, []):
                new_dist = d + weight
                if new_dist < distances.get(neighbor, float('inf')):
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = curr
                    heapq.heappush(pq, (new_dist, neighbor))
                    
        # 5. Gerar Linhas e Somar Comprimento
        total_length = 0.0
        out_features = []
        
        crs = lyr_lp.crs().authid()
        mem_layer = QgsVectorLayer(f"LineString?crs={crs}", "Microtubo de Comando", "memory")
        pr = mem_layer.dataProvider()
        pr.addAttributes([QgsField("ID_Cav", QVariant.Int), QgsField("Comp", QVariant.Double)])
        mem_layer.updateFields()
        
        for f_cv in lyr_cv.getFeatures():
            pt_cv = f_cv.geometry().asPoint()
            node_cv = find_nearest_node(pt_cv)
            
            if node_cv in predecessors:
                path_pts = []
                curr = node_cv
                path_len = 0.0
                while curr:
                    path_pts.append(QgsPointXY(*curr))
                    prev = predecessors[curr]
                    if prev:
                        path_len += QgsPointXY(*curr).distance(QgsPointXY(*prev))
                    curr = prev
                
                if len(path_pts) > 1:
                    feat = QgsFeature()
                    feat.setGeometry(QgsGeometry.fromPolylineXY(path_pts))
                    feat.setAttributes([f_cv.id(), round(path_len, 2)])
                    out_features.append(feat)
                    total_length += path_len
                    
        if not out_features:
            QMessageBox.warning(None, "Aviso", "Nenhum caminho encontrado entre o comando e os cavaletes.")
            return
            
        pr.addFeatures(out_features)
        QgsProject.instance().addMapLayer(mem_layer)
        
        # 6. Orçamento
        qtd_rolos = math.ceil(total_length / comp_rolo)
        
        bom = ProjectBOMManager()
        if not bom.filepath:
            QMessageBox.warning(None, "Orçamento", f"Linhas geradas ({total_length:.2f}m), mas o projeto não está salvo. Quantidade estimada: {qtd_rolos} rolos.")
            return
            
        # Pegar preço do catálogo
        peca_data = PecaManager().get(nome_material)
        if peca_data:
            custo = peca_data.get('custo', 0)
            lucro = peca_data.get('lucro', 0)
            preco = custo * (1 + lucro/100)
            bom.add_item(nome_material, preco, qtd_rolos)
            QMessageBox.information(None, "Sucesso", 
                f"Roteamento concluído!\n"
                f"Total de Microtubo: {total_length:.2f} m\n"
                f"Quantidade: {qtd_rolos} rolos adicionados ao orçamento.")
        else:
            QMessageBox.warning(None, "Catálogo", f"Material '{nome_material}' não encontrado no catálogo de preços. Verifique a escrita.")
