import os
import random
import json
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QSpinBox, QDoubleSpinBox, QDialogButtonBox, QMessageBox, QProgressDialog, QTabWidget, QWidget)
from qgis.PyQt.QtCore import Qt, QCoreApplication, QSettings
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsProject,
    QgsWkbTypes, QgsField, QgsSpatialIndex, QgsMapLayerProxyModel
)
from qgis.PyQt.QtCore import QVariant

from .ferramenta_base import AqueductTool

class AgruparDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Setores Inteligentes: Treinamento e Predição')
        self.resize(450, 400)
        
        main_layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # ABA 1: Treinamento (Aprender)
        self.tab_train = QWidget()
        train_layout = QVBoxLayout(self.tab_train)
        
        lbl_info = QLabel("<b>Aprender Padrões de Geometria a partir de um Gabarito</b><br><br>Selecione a malha não agrupada (Base) e o mapa onde você já uniu os setores (Gabarito). A ferramenta analisará seu estilo de agrupamento e usará como inteligência.")
        lbl_info.setWordWrap(True)
        train_layout.addWidget(lbl_info)
        
        train_layout.addWidget(QLabel("Camada Base (Células Soltas):"))
        self.combo_base = QgsMapLayerComboBox()
        self.combo_base.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        train_layout.addWidget(self.combo_base)
        
        train_layout.addWidget(QLabel("Camada Gabarito (Setores Unidos Manualmente):"))
        self.combo_target = QgsMapLayerComboBox()
        self.combo_target.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        train_layout.addWidget(self.combo_target)
        
        train_layout.addStretch()
        
        # ABA 2: Aplicação (Otimização)
        self.tab_apply = QWidget()
        apply_layout = QVBoxLayout(self.tab_apply)
        
        # Recupera peso salvo, se houver, para mostrar status
        settings = QSettings()
        saved_weights = settings.value("Aqueduct/AgruparML", "")
        status_txt = "<b>Status do Aprendizado:</b> "
        if not saved_weights:
            status_txt += "🔴 Sem modelo treinado. Usando padrão fixo."
        else:
            try:
                prof = json.loads(saved_weights)
                ex_count = prof.get('total_examples', 1)
                status_txt += f"🟢 Modelo Treinado! (Experiência: {ex_count} projeto{'s' if ex_count>1 else ''})"
            except:
                status_txt += "🟢 Modelo Treinado!"
        self.lbl_status = QLabel(status_txt)
        apply_layout.addWidget(self.lbl_status)
        
        self.lbl_target = QLabel('Quantidade Alvo de Emissores por Setor:')
        self.spin_target = QSpinBox()
        self.spin_target.setMaximum(1000000)
        self.spin_target.setValue(1000)
        
        self.lbl_tol = QLabel('Tolerância de Erro Admissível (%):')
        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setMaximum(100)
        self.spin_tol.setValue(10.0)
        
        self.lbl_gen = QLabel('Número de Gerações Iniciais:')
        self.spin_gen = QSpinBox()
        self.spin_gen.setMaximum(5000)
        self.spin_gen.setValue(10)
        
        self.lbl_passo = QLabel('Pausar a cada (gerações):')
        self.spin_passo = QSpinBox()
        self.spin_passo.setMaximum(100)
        self.spin_passo.setValue(5)
        
        apply_layout.addWidget(self.lbl_target)
        apply_layout.addWidget(self.spin_target)
        apply_layout.addWidget(self.lbl_tol)
        apply_layout.addWidget(self.spin_tol)
        apply_layout.addWidget(self.lbl_gen)
        apply_layout.addWidget(self.spin_gen)
        apply_layout.addWidget(self.lbl_passo)
        apply_layout.addWidget(self.spin_passo)
        apply_layout.addStretch()
        
        self.tabs.addTab(self.tab_apply, "1. Gerar Automático")
        self.tabs.addTab(self.tab_train, "2. Treinar Novo Padrão")
        
        # Botões
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        
        main_layout.addWidget(self.buttons)
        
    def is_training_mode(self):
        return self.tabs.currentIndex() == 1
        
    def get_training_layers(self):
        return self.combo_base.currentLayer(), self.combo_target.currentLayer()

    def get_values(self):
        return self.spin_target.value(), self.spin_tol.value(), self.spin_gen.value(), self.spin_passo.value()

class AgruparSetoresTool(AqueductTool):
    """
    Ferramenta para treinar padrões de agrupamento ou aplicar a 
    predição espacial usando Algoritmo Genético + Aprendizado Global.
    """

    def initGui(self):
        # Aqui, como não temos icone de agrupamento, criaremos um ícone genérico ou usamos default
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_hf.svg') 
        # Idealmente um icone específico de cluster seria melhor, mas usando isso para evitar crash
        if not os.path.exists(icon_path):
             icon_path = ""
             
        self.action = QAction(QIcon(icon_path), 'Agrupar Setores por Emissores', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        
        # 1. Validações Iniciais
        if not layer or layer.type() != layer.VectorLayer:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione uma camada vetorial de POLÍGONOS.", level=3, duration=5)
            return

        if layer.geometryType() != QgsWkbTypes.PolygonGeometry:
            self.iface.messageBar().pushMessage("Aqueduct", "Operação permitida apenas em camadas de POLÍGONO.", level=3, duration=5)
            return

        fields = layer.fields()
        idx_emissores = fields.indexOf("emissores")
        if idx_emissores == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "A camada deve ter um campo 'emissores'.", level=3, duration=5)
             return

        # 2. Pede dados na UI
        dlg = AgruparDialog(self.iface.mainWindow())
        
        # Se usuário já tem a camada ativa como target, pre-selecionar nas combos é automático do QGIS
        if not dlg.exec_():
            return
            
        is_training = dlg.is_training_mode()
        
        if is_training:
            layer_base, layer_target = dlg.get_training_layers()
            self.execute_training(layer_base, layer_target)
            return

        # ---- MODO APLICAÇÃO (AUTOMÁTICA/PREDIÇÃO) ----
        target, tol_percent, gens_iniciais, passo = dlg.get_values()
        
        # Carrega conhecimento aprendido global, se houver
        settings = QSettings()
        learned_data_str = settings.value("Aqueduct/AgruparML", "")
        learned_profile = None
        if learned_data_str:
            try:
                learned_profile = json.loads(learned_data_str)
            except:
                pass
        
        # 3. Extrair feições, geometria e pesos
        self.iface.messageBar().pushMessage("Aqueduct", "Preparando dados...", level=0, duration=3)
        
        features = {}
        weights = {}
        idx = QgsSpatialIndex()
        
        has_selection = layer.selectedFeatureCount() > 0
        feats_to_process = layer.selectedFeatures() if has_selection else layer.getFeatures()
        
        for feat in feats_to_process:
            feat_id = feat.id()
            features[feat_id] = feat
            idx.insertFeature(feat)
            
            val = feat.attribute("emissores")
            try:
                weights[feat_id] = float(val) if val else 0.0
            except ValueError:
                weights[feat_id] = 0.0

        if not features:
             self.iface.messageBar().pushMessage("Aqueduct", "Nenhuma feição encontrada.", level=3, duration=5)
             return
             
        # 4. Criar Grafo de Adjacências
        self.iface.messageBar().pushMessage("Aqueduct", "Montando grafo de conexões (bordas)...", level=0, duration=3)
        graph = {feat_id: [] for feat_id in features}
        
        for feat_id, feat in features.items():
            geom = feat.geometry()
            bbox = geom.boundingBox()
            candidates = idx.intersects(bbox)
            for cand_id in candidates:
                if cand_id != feat_id and cand_id in features:
                    cand_geom = features[cand_id].geometry()
                    
                    # Usa verificação exata de toque ou intersecção
                    if geom.touches(cand_geom) or geom.intersects(cand_geom):
                        # Pega a geometria da intersecção
                        intersection = geom.intersection(cand_geom)
                        # Só consideramos vizinhos reais aqueles cuja intersecção 
                        # produza um comprimento maior que zero (ou seja, compartilham linha, não só ponto)
                        # QgsGeometry.length() retornará 0 para pontos, mas >0 para linhas adjacentes.
                        if not intersection.isEmpty() and intersection.length() > 0.01:
                            graph[feat_id].append(cand_id)

        # 5. Encontrar Componentes Conexos
        components = []
        visited = set()
        for node in graph:
            if node not in visited:
                comp = []
                queue = [node]
                visited.add(node)
                while queue:
                    curr = queue.pop(0)
                    comp.append(curr)
                    for neighbor in graph[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(comp)

        # 6. Rodar Algoritmo Genético
        self.iface.messageBar().pushMessage("Aqueduct", "Rodando Algoritmo Genético (aguarde)...", level=0, duration=3)
        
        global_assignment = {}
        sector_counter = 1
        
        # Ajustando a barra de progresso para exibir o número total de componentes
        progress = QProgressDialog("Inicializando otimização...", "Cancelar", 0, len(components), self.iface.mainWindow())
        progress.setWindowTitle("Agrupando Setores")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        for i, comp in enumerate(components):
            QCoreApplication.processEvents()
            if progress.wasCanceled():
                self.iface.messageBar().pushMessage("Aqueduct", "Operação cancelada pelo usuário.", level=2, duration=4)
                return
                
            total_weight = sum(weights[n] for n in comp)
            K = max(1, int(round(total_weight / target)))
            
            progress.setLabelText(f"Processando grupo {i+1} de {len(components)} (Polígonos: {len(comp)}, Setores Esperados: {K})")
            progress.setValue(i)
            
            if K <= 1:
                for n in comp:
                    global_assignment[n] = sector_counter
                sector_counter += 1
            else:
                local_graph = {n: [nb for nb in graph[n] if nb in comp] for n in comp}
                
                assignment = self.run_ga(comp, local_graph, weights, target, tol_percent, gens_iniciais, passo, K, progress, features, layer.crs().authid(), global_assignment, sector_counter, learned_profile)
                
                if not assignment: # Cancelado
                    self.iface.messageBar().pushMessage("Aqueduct", "Operação cancelada na iteração escolhida.", level=0, duration=4)
                    return
                    
                for feat_id, local_idx in assignment.items():
                    global_assignment[feat_id] = sector_counter + local_idx
                sector_counter += K

        progress.setValue(len(components))

        # 7. Criar Camada de Saída fazendo o Dissolve (Uniões geométricas)
        self.iface.messageBar().pushMessage("Aqueduct", "Unindo geometrias (Dissolve)...", level=0, duration=3)
        
        dissolved_geometries = {}
        dissolved_emissores = {}
        
        for feat_id, s_id in global_assignment.items():
            geom = features[feat_id].geometry()
            em_val = weights[feat_id]
            
            if s_id not in dissolved_geometries:
                dissolved_geometries[s_id] = QgsGeometry(geom)
                dissolved_emissores[s_id] = em_val
            else:
                # Merge geometry
                dissolved_geometries[s_id] = dissolved_geometries[s_id].combine(geom)
                dissolved_emissores[s_id] += em_val

        # Create output layer in memory
        crs = layer.crs().authid()
        out_layer = QgsVectorLayer(f"Polygon?crs={crs}", "Setores Agrupados", "memory")
        pr = out_layer.dataProvider()
        pr.addAttributes([
            QgsField("setor_id", QVariant.Int),
            QgsField("emissores", QVariant.Double)
        ])
        out_layer.updateFields()
        
        out_features = []
        for s_id in dissolved_geometries:
            out_feat = QgsFeature()
            out_feat.setGeometry(dissolved_geometries[s_id])
            out_feat.setAttributes([s_id, dissolved_emissores[s_id]])
            out_features.append(out_feat)
            
        pr.addFeatures(out_features)
        QgsProject.instance().addMapLayer(out_layer)

        msg = f"Agrupamento concluído! Criados {len(dissolved_geometries)} setores."
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=10)


    def decode(self, seeds, graph, weights):
        assignment = {}
        sector_sums = {i: 0.0 for i in range(len(seeds))}
        boundaries = {i: [] for i in range(len(seeds))}
        
        for i, seed in enumerate(seeds):
            assignment[seed] = i
            sector_sums[i] += weights[seed]
            boundaries[i] = [n for n in graph[seed]]
                
        unassigned = set(graph.keys()) - set(assignment.keys())
        
        while unassigned:
            progress = False
            # sort by amount so far
            sector_order = sorted(boundaries.keys(), key=lambda x: sector_sums[x])
            
            for i in sector_order:
                # refresh valid boundaries
                valid_neighbors = [n for n in boundaries[i] if n in unassigned]
                boundaries[i] = valid_neighbors
                
                if valid_neighbors:
                    n = valid_neighbors[0]
                    assignment[n] = i
                    sector_sums[i] += weights[n]
                    unassigned.remove(n)
                    
                    new_neighbors = [nn for nn in graph[n] if nn in unassigned]
                    boundaries[i].extend(new_neighbors)
                    progress = True
                    break
                    
            if not progress and unassigned:
                # Force assign remaining based on proximity or just dump to closest logical neighbor
                # meaning they are trapped
                for n in list(unassigned):
                    assigned_neighbors = [nn for nn in graph[n] if nn in assignment]
                    if assigned_neighbors:
                        s_id = assignment[assigned_neighbors[0]]
                        assignment[n] = s_id
                        sector_sums[s_id] += weights[n]
                        unassigned.remove(n)
                        progress = True
                if not progress:
                    # just assign to sector 0 to clear loop
                    for n in list(unassigned):
                        assignment[n] = 0
                        sector_sums[0] += weights[n]
                    unassigned.clear()
                    
        return assignment, sector_sums
        
    def execute_training(self, layer_base, layer_target):
        if not layer_base or not layer_target:
            self.iface.messageBar().pushMessage("Aqueduct", "Selecione as duas camadas para treinar.", level=3, duration=5)
            return
            
        idx_emissores = layer_base.fields().indexOf("emissores")
        if idx_emissores == -1:
             self.iface.messageBar().pushMessage("Aqueduct", "A camada Base deve ter o campo 'emissores'.", level=3, duration=5)
             return
             
        self.iface.messageBar().pushMessage("Aqueduct", "Iniciando Aprendizado de Máquina Espacial...", level=0, duration=4)
        
        # 1. Indexar geometria dos setores de gabarito (target)
        target_features = {f.id(): f for f in layer_target.getFeatures()}
        target_idx = QgsSpatialIndex(layer_target.getFeatures())
        
        # 2. Iterar pela base (células) e encontrar qual gabarito elas pertencem (Spatial Join)
        base_features = {f.id(): f for f in layer_base.getFeatures()}
        base_graph = {fid: [] for fid in base_features}
        base_idx = QgsSpatialIndex(layer_base.getFeatures())
        
        # Extrai vizinhança da base para medir pontas internamente no gabarito
        for fid, f in base_features.items():
            candidates = base_idx.intersects(f.geometry().boundingBox())
            for cid in candidates:
                if cid != fid:
                    intersection = f.geometry().intersection(base_features[cid].geometry())
                    if not intersection.isEmpty() and intersection.length() > 0.01:
                        base_graph[fid].append(cid)
        
        # Faz a correspondência de cada base para o target final
        assignment = {}
        for fid, f in base_features.items():
            candidates = target_idx.intersects(f.geometry().boundingBox())
            best_target = -1
            max_area = -1
            for cid in candidates:
                inter = f.geometry().intersection(target_features[cid].geometry())
                if inter.area() > max_area:
                    max_area = inter.area()
                    best_target = cid
            if best_target != -1:
                assignment[fid] = best_target
                
        # 3. Calcular métricas dos setores ideais
        stats = {
            'sector_count': 0,
            'cells_per_sector': [],
            'compacity_ratios': [],
            'exposed_edges_ratio': []
        }
        
        sectors = set(assignment.values())
        stats['sector_count'] = len(sectors)
        
        for s_id in sectors:
            nodes_in_sector = [n for n, s in assignment.items() if s == s_id]
            stats['cells_per_sector'].append(len(nodes_in_sector))
            
            # Conta pontas / arestas expostas
            total_edges = 0
            exposed_edges = 0
            for node in nodes_in_sector:
                neighbors = base_graph[node]
                total_edges += len(neighbors)
                same_sector_count = sum(1 for nb in neighbors if assignment.get(nb, -1) == s_id)
                exposed_edges += (len(neighbors) - same_sector_count)
            
            if total_edges > 0:
                stats['exposed_edges_ratio'].append(exposed_edges / total_edges)
                
            # Compacidade bruta (Área vs Perímetro)
            geom_combined = QgsGeometry()
            for node in nodes_in_sector:
                geom_combined = geom_combined.combine(base_features[node].geometry())
            
            area = geom_combined.area()
            perim = geom_combined.length()
            if perim > 0:
                # Círculo seria ~0.079, quadrado ~0.062 (Area/Perimetro^2)
                compacity = area / (perim * perim)
                stats['compacity_ratios'].append(compacity)
                
        # Prepara o perfil deste projeto específico
        def avg(lst): return sum(lst) / len(lst) if lst else 0.0
        
        current_profile = {
            'avg_cells': avg(stats['cells_per_sector']),
            'avg_compacity': avg(stats['compacity_ratios']),
            'avg_exposed_edges_ratio': avg(stats['exposed_edges_ratio']),
            'trained_on': layer_target.name()
        }
        
        # Salva em QSettings Global de forma Cumulativa
        settings = QSettings()
        history_str = settings.value("Aqueduct/AgruparML_History", "")
        history = []
        if history_str:
            try:
                history = json.loads(history_str)
            except:
                pass
                
        history.append(current_profile)
        settings.setValue("Aqueduct/AgruparML_History", json.dumps(history))
        
        # Calcula a média acumulada global
        global_avg_cells = sum(p.get('avg_cells', 0) for p in history) / len(history)
        global_avg_compacity = sum(p.get('avg_compacity', 0) for p in history) / len(history)
        global_avg_exposed = sum(p.get('avg_exposed_edges_ratio', 0) for p in history) / len(history)
        
        global_profile = {
            'avg_cells': global_avg_cells,
            'avg_compacity': global_avg_compacity,
            'avg_exposed_edges_ratio': global_avg_exposed,
            'total_examples': len(history)
        }
        
        settings.setValue("Aqueduct/AgruparML", json.dumps(global_profile))
        
        msg = f"Aprendizado Adicionado à Base Coletiva!\nTotal de Experiência: {len(history)} projeto(s).\n\nNovo Perfil Global:\n- Média de Células: {global_profile['avg_cells']:.1f}\n- Arestas Serrilhadas: {global_profile['avg_exposed_edges_ratio']*100:.1f}%\n- Compacidade: {global_profile['avg_compacity']:.4f}\n\nO QGIS ficou mais inteligente!"
        QMessageBox.information(self.iface.mainWindow(), "Inteligência Abastecida", msg)


    def fitness(self, assignment, sector_sums, target, tolerance_percent, graph, learned_profile=None):
        tol_ratio = tolerance_percent / 100.0
        score = 0.0
        
        # 1. Ponto pela proximidade do Target (Maior peso, escala de 1000)
        for s_id, total in sector_sums.items():
            diff = abs(total - target)
            max_allowed_diff = target * tol_ratio
            if diff <= max_allowed_diff:
                if max_allowed_diff == 0:
                    score += 1000.0
                else:
                    score += 1000.0 - (diff / max_allowed_diff) * 500.0
            else:
                score -= (diff - max_allowed_diff) / target * 2000.0

        # 2. Penalidade por Formato (Polígonos "Engolidos", "Pontas" e "Serrilhados")
        # Analisa cada polígono em relação aos seus vizinhos imediatos
        for node, s_id in assignment.items():
            neighbors = graph.get(node, [])
            if not neighbors:
                continue
                
            same_sector_count = 0
            neighbor_sectors = {}
            for nb in neighbors:
                nb_s_id = assignment.get(nb, -1)
                if nb_s_id == s_id:
                    same_sector_count += 1
                elif nb_s_id != -1:
                    neighbor_sectors[nb_s_id] = neighbor_sectors.get(nb_s_id, 0) + 1
            
            # A. Penalidade de "Dente Engolido"
            # Se esse polígono tem 3 ou mais vizinhos de UM MESMO setor diferente
            for diff_s_id, count in neighbor_sectors.items():
                if count >= 3:
                     score -= 300.0
                     
            # B. Penalidade de "Ponta" (Extremidades expostas em 90 graus)
            # Se o polígono tem apenas 1 vizinho do seu próprio setor, mas tem múltiplos vizinhos no total,
            # significa que ele está projetado/espetado para fora.
            if same_sector_count == 1 and len(neighbors) > 1:
                score -= 150.0
                
            # C. Penalidade de Perímetro (Evitar áreas cerrilhadas) adaptada ao Machine Learning
            diff_sector_edges = len(neighbors) - same_sector_count
            
            if learned_profile:
                # Se treinou, tentamos penalizar desvios na proporção de pontas para mimetizar o usuário em vez do valor fixo 10
                current_ratio = diff_sector_edges / max(1, len(neighbors))
                target_ratio = learned_profile.get('avg_exposed_edges_ratio', 0.2)
                ratio_diff = abs(current_ratio - target_ratio)
                score -= ratio_diff * 100.0  # Penaliza desvios do gosto de "serrilhado" do autor
            else:
                score -= diff_sector_edges * 10.0
                
        return score

    def run_ga(self, nodes, graph, weights, target, tolerance_percent, initial_generations, step_generations, K, progress_dialog, features_dict, crs_authid, global_assignment_so_far, current_sector_counter, learned_profile):
        pop_size = 15
        
        def random_individual():
            return random.sample(nodes, K)
            
        population = [random_individual() for _ in range(pop_size)]
        
        best_ind = None
        best_fitness = -float('inf')
        best_assignment = None
        
        current_gen = 0
        total_gens_target = initial_generations
        
        while True: # Avançaremos até o usuário aprovar ou cancelar
            
            for _ in range(total_gens_target - current_gen):
                QCoreApplication.processEvents()
                if progress_dialog and progress_dialog.wasCanceled():
                    return None
                    
                scored_pop = []
                for ind in population:
                    assignment, sector_sums = self.decode(ind, graph, weights)
                    fit = self.fitness(assignment, sector_sums, target, tolerance_percent, graph, learned_profile)
                    scored_pop.append((fit, ind, assignment))
                    
                    if fit > best_fitness:
                        best_fitness = fit
                        best_ind = ind
                        best_assignment = assignment
                        
                scored_pop.sort(key=lambda x: x[0], reverse=True)
                parents = [x[1] for x in scored_pop[:max(2, pop_size//2)]]
                
                next_pop = [best_ind]
                while len(next_pop) < pop_size:
                    p1 = random.choice(parents)
                    p2 = random.choice(parents)
                    pool = list(set(p1 + p2))
                    random.shuffle(pool)
                    child = pool[:K]
                    while len(child) < K:
                        cand = random.choice(nodes)
                        if cand not in child:
                            child.append(cand)
                    
                    # Mutação (agora com 40% de chance para aumentar diversidade)
                    if random.random() < 0.4:
                        idx_to_mutate = random.randint(0, K-1)
                        new_seed = random.choice(nodes)
                        if new_seed not in child:
                            child[idx_to_mutate] = new_seed
                            
                    next_pop.append(child)
                    
                # Injeta "imigrantes aleatórios" no fim da população para forçar exploração
                # Substitui os piores 10% da nova população por indivíduos aleatórios
                num_immigrants = max(1, pop_size // 10)
                for i in range(1, num_immigrants + 1):
                    next_pop[-i] = random_individual()
                    
                population = next_pop
                current_gen += 1

            # Momento de gerar prévia para exibir
            dissolved = {}
            # Como podemos ter resolvido alguns componentes já, mesclamos o que já foi guardado em global_assignment_so_far
            temp_assignment_combo = global_assignment_so_far.copy()
            for feat_id, local_idx in best_assignment.items():
                temp_assignment_combo[feat_id] = current_sector_counter + local_idx
                
            for feat_id, s_id in temp_assignment_combo.items():
                geom = features_dict[feat_id].geometry()
                if s_id not in dissolved:
                    dissolved[s_id] = QgsGeometry(geom)
                else:
                    dissolved[s_id] = dissolved[s_id].combine(geom)
            
            temp_layer = QgsVectorLayer(f"Polygon?crs={crs_authid}", f"Prévia Geração {current_gen}", "memory")
            pr = temp_layer.dataProvider()
            out_features = []
            for s_id, dgeom in dissolved.items():
                out_feat = QgsFeature()
                out_feat.setGeometry(dgeom)
                out_features.append(out_feat)
            pr.addFeatures(out_features)
            
            QgsProject.instance().addMapLayer(temp_layer)
            temp_layer.setOpacity(0.5)
            self.iface.mapCanvas().refresh()
            
            answer = QMessageBox.question(
                self.iface.mainWindow(),
                "Iteração de Agrupamento",
                f"Atingiu {current_gen} gerações.\n"
                f"A camada 'Prévia Geração {current_gen}' está no mapa para visualização transparente.\n\n"
                f"O resultado está satisfatório?\n"
                f" - SIM: Encerra o AG para este conjunto de polígonos.\n"
                f" - NÃO: Continua rodando mais {step_generations} gerações.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            QgsProject.instance().removeMapLayer(temp_layer)
            self.iface.mapCanvas().refresh()
            
            if answer == QMessageBox.Yes:
                break
            else:
                total_gens_target += step_generations
                
        return best_assignment
