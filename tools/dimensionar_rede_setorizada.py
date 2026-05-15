import os
import math
import itertools
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QSpinBox, QDialogButtonBox, QMessageBox, QGroupBox,
    QFormLayout, QTabWidget, QWidget, QLineEdit, QPlainTextEdit,
    QScrollArea
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsProject, QgsPointXY,
    QgsWkbTypes, QgsField, QgsSpatialIndex, QgsSettings, QgsFieldProxyModel,
    QgsMapLayerProxyModel
)

from .ferramenta_base import AqueductTool

# ---------------------------------------------------------------------------
# Fórmulas
# ---------------------------------------------------------------------------
def calcular_hf_hw(q_m3h, d_mm, l_m, C=140.0):
    if q_m3h <= 0 or d_mm <= 0 or l_m <= 0: return 0.0
    q_m3s = q_m3h / 3600.0
    D = d_mm / 1000.0
    J = 10.67 * ((q_m3s / C) ** 1.852) / (D ** 4.87)
    return J * l_m

def calcular_velocidade(q_m3h, d_mm):
    if q_m3h <= 0 or d_mm <= 0: return 0.0
    q_m3s = q_m3h / 3600.0
    area = math.pi * ((d_mm / 2000.0) ** 2)
    return q_m3s / area

# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
class DimensionarRedeSetorizadaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimensionar Rede Setorizada (Grafo)")
        self.resize(550, 650)
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Aba Principal
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        conteudo = QWidget()
        lay = QVBoxLayout(conteudo)

        grp_camadas = QGroupBox("Camadas do Sistema")
        f_cam = QFormLayout()
        
        self.cb_tub = QgsMapLayerComboBox()
        self.cb_tub.setFilters(QgsMapLayerProxyModel.LineLayer)
        f_cam.addRow("1. Tubulações (Rede Mista):", self.cb_tub)

        self.cb_em = QgsMapLayerComboBox()
        self.cb_em.setFilters(QgsMapLayerProxyModel.PointLayer)
        f_cam.addRow("2. Emissores (Demanda):", self.cb_em)

        self.spin_vazao = QDoubleSpinBox()
        self.spin_vazao.setRange(0.1, 10000.0)
        self.spin_vazao.setValue(50.0)
        self.spin_vazao.setDecimals(2)
        self.spin_vazao.setSuffix(" L/h")
        f_cam.addRow("↳ Vazão por Emissor:", self.spin_vazao)

        self.cb_valvulas = QgsMapLayerComboBox()
        self.cb_valvulas.setFilters(QgsMapLayerProxyModel.PointLayer)
        f_cam.addRow("3. Válvulas (Setores):", self.cb_valvulas)

        self.cb_fonte = QgsMapLayerComboBox()
        self.cb_fonte.setFilters(QgsMapLayerProxyModel.PointLayer)
        f_cam.addRow("4. Fonte de Água (Raiz):", self.cb_fonte)

        grp_camadas.setLayout(f_cam)
        lay.addWidget(grp_camadas)

        grp_hid = QGroupBox("Parâmetros Hidráulicos e Operacionais")
        f_hid = QFormLayout()

        self.spin_simult = QSpinBox()
        self.spin_simult.setRange(1, 100)
        self.spin_simult.setValue(1)
        self.spin_simult.setToolTip("Quantas válvulas/setores podem operar ao mesmo tempo?")
        f_hid.addRow("Simultaneidade (Nº Setores):", self.spin_simult)

        self.spin_ps = QDoubleSpinBox()
        self.spin_ps.setRange(1.0, 100.0)
        self.spin_ps.setValue(30.0)
        self.spin_ps.setSuffix(" mca")
        f_hid.addRow("Pressão de Serviço (PS):", self.spin_ps)

        self.edit_diams_lat = QLineEdit("16, 20, 25, 32")
        f_hid.addRow("Diâmetros Laterais (mm):", self.edit_diams_lat)

        self.edit_diams_prin = QLineEdit("50, 75, 100, 150")
        f_hid.addRow("Diâmetros Principais/Derivação:", self.edit_diams_prin)

        self.spin_hf_prin = QDoubleSpinBox()
        self.spin_hf_prin.setRange(0.1, 500.0)
        self.spin_hf_prin.setValue(10.0)
        self.spin_hf_prin.setSuffix(" mca")
        f_hid.addRow("HF Máx (Princ/Deriv):", self.spin_hf_prin)

        self.spin_vel_max = QDoubleSpinBox()
        self.spin_vel_max.setRange(0.5, 5.0)
        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setRange(0.01, 10.0)
        self.spin_tol.setValue(0.10)
        self.spin_tol.setSingleStep(0.1)
        self.spin_tol.setSuffix(" m")
        f_hid.addRow("Tolerância de Conexão (Snap):", self.spin_tol)

        grp_hid.setLayout(f_hid)
        lay.addWidget(grp_hid)

        lay.addStretch()
        scroll.setWidget(conteudo)
        self.tabs.addTab(scroll, "Configurações")

        tab_msg = QWidget()
        lay_msg = QVBoxLayout(tab_msg)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        lay_msg.addWidget(self.log_output)
        self.tabs.addTab(tab_msg, "Console de Processamento")

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._auto_selecionar()

    def _auto_selecionar(self):
        L = QgsWkbTypes.LineGeometry
        P = QgsWkbTypes.PointGeometry
        def buscar(kws, geom):
            for l in QgsProject.instance().mapLayers().values():
                if hasattr(l, 'geometryType') and l.geometryType() == geom:
                    if any(k in l.name().lower() for k in kws): return l
            return None

        t = buscar(['tubo', 'cano', 'rede', 'linha'], L)
        if t: self.cb_tub.setLayer(t)
        
        e = buscar(['emissor', 'aspersor', 'gotej', 'micro'], P)
        if e:
            self.cb_em.setLayer(e)
            
        v = buscar(['valv', 'registro', 'setor'], P)
        if v: self.cb_valvulas.setLayer(v)
        
        f = buscar(['fonte', 'bomba', 'reserv', 'poco'], P)
        if f: self.cb_fonte.setLayer(f)

    def get_inputs(self):
        return {
            'tub': self.cb_tub.currentLayer(),
            'em': self.cb_em.currentLayer(),
            'valvulas': self.cb_valvulas.currentLayer(),
            'fonte': self.cb_fonte.currentLayer(),
            'vazao_emissor': self.spin_vazao.value(),
            'simult': self.spin_simult.value(),
            'tolerancia': self.spin_tol.value(),
            'ps': self.spin_ps.value(),
            'd_lat': self._parse_diams(self.edit_diams_lat.text()),
            'd_prin': self._parse_diams(self.edit_diams_prin.text()),
            'hf_prin': self.spin_hf_prin.value(),
            'vel_max': self.spin_vel_max.value(),
        }

    def _parse_diams(self, text):
        try:
            return sorted(set(int(p.strip()) for p in text.replace(';', ',').split(',') if p.strip().isdigit()))
        except:
            return [50]

    def set_log(self, text):
        self.log_output.setPlainText(text)
        self.tabs.setCurrentIndex(1)

# ---------------------------------------------------------------------------
# Tool Principal
# ---------------------------------------------------------------------------
SETTINGS_KEY = "Aqueduct/RedeSetorizada"

class DimensionarRedeSetorizadaTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_acumulo_vazao.svg')
        self.action = QAction(QIcon(icon_path), '▶ Dimensionar Rede Completa (Grafos)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar: self.toolbar.addAction(self.action)
        else: self.iface.addToolBarIcon(self.action)

        icon_config = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_info.svg')
        self.action_cfg = QAction(QIcon(icon_config), 'Configurar Rede Completa...', self.iface.mainWindow())
        self.action_cfg.triggered.connect(self.run_config)
        self.iface.addPluginToMenu('&Aqueduct', self.action_cfg)
        if self.toolbar: self.toolbar.addAction(self.action_cfg)

    def unload(self):
        self.iface.removePluginMenu('&Aqueduct', self.action)
        self.iface.removePluginMenu('&Aqueduct', self.action_cfg)
        if self.toolbar:
            self.toolbar.removeAction(self.action)
            self.toolbar.removeAction(self.action_cfg)

    def run(self):
        inp = self._carregar_params()
        if not inp:
            self.run_config()
            return
        self._wrap_executar(inp)

    def run_config(self):
        dlg = DimensionarRedeSetorizadaDialog(self.iface.mainWindow())
        inp = self._carregar_params()
        if inp:
            if inp['tub']: dlg.cb_tub.setLayer(inp['tub'])
            if inp['em']: dlg.cb_em.setLayer(inp['em'])
            dlg.spin_vazao.setValue(inp['vazao_emissor'])
            if inp['valvulas']: dlg.cb_valvulas.setLayer(inp['valvulas'])
            if inp['fonte']: dlg.cb_fonte.setLayer(inp['fonte'])
            dlg.spin_simult.setValue(inp['simult'])
            dlg.spin_tol.setValue(inp['tolerancia'])
            dlg.spin_ps.setValue(inp['ps'])
            dlg.edit_diams_lat.setText(", ".join(map(str, inp['d_lat'])))
            dlg.edit_diams_prin.setText(", ".join(map(str, inp['d_prin'])))
            dlg.spin_hf_prin.setValue(inp['hf_prin'])
            dlg.spin_vel_max.setValue(inp['vel_max'])

        if dlg.exec_():
            novo_inp = dlg.get_inputs()
            self._salvar_params(novo_inp)
            self._wrap_executar(novo_inp, dlg)

    def _wrap_executar(self, inp, dlg=None):
        log_lines = []
        def log(msg):
            print(f"RedeSetorizada: {msg}")
            log_lines.append(str(msg))

        try:
            self._executar(inp, log)
        except Exception as e:
            import traceback
            log(f"❌ ERRO CRÍTICO: {e}")
            log(traceback.format_exc())
            QMessageBox.critical(self.iface.mainWindow(), "Erro", str(e))
        finally:
            if dlg:
                dlg.set_log("\n".join(log_lines))
                dlg.exec_()
            else:
                print("\n".join(log_lines))

    def _salvar_params(self, inp):
        s = QgsSettings()
        for k in ['tub', 'em', 'valvulas', 'fonte']:
            s.setValue(f"{SETTINGS_KEY}/{k}", inp[k].id() if inp[k] else "")
        s.setValue(f"{SETTINGS_KEY}/vazao_emissor", inp['vazao_emissor'])
        s.setValue(f"{SETTINGS_KEY}/simult", inp['simult'])
        s.setValue(f"{SETTINGS_KEY}/tolerancia", inp['tolerancia'])
        s.setValue(f"{SETTINGS_KEY}/ps", inp['ps'])
        s.setValue(f"{SETTINGS_KEY}/d_lat", ",".join(map(str, inp['d_lat'])))
        s.setValue(f"{SETTINGS_KEY}/d_prin", ",".join(map(str, inp['d_prin'])))
        s.setValue(f"{SETTINGS_KEY}/hf_prin", inp['hf_prin'])
        s.setValue(f"{SETTINGS_KEY}/vel_max", inp['vel_max'])

    def _carregar_params(self):
        s = QgsSettings()
        l = QgsProject.instance().mapLayers()
        tub = l.get(s.value(f"{SETTINGS_KEY}/tub", ""))
        em = l.get(s.value(f"{SETTINGS_KEY}/em", ""))
        valv = l.get(s.value(f"{SETTINGS_KEY}/valvulas", ""))
        fonte = l.get(s.value(f"{SETTINGS_KEY}/fonte", ""))
        if not tub or not em or not fonte: return None

        return {
            'tub': tub, 'em': em, 'valvulas': valv, 'fonte': fonte,
            'vazao_emissor': float(s.value(f"{SETTINGS_KEY}/vazao_emissor", 50.0)),
            'simult': int(s.value(f"{SETTINGS_KEY}/simult", 1)),
            'tolerancia': float(s.value(f"{SETTINGS_KEY}/tolerancia", 0.10)),
            'ps': float(s.value(f"{SETTINGS_KEY}/ps", 30.0)),
            'd_lat': [int(x) for x in s.value(f"{SETTINGS_KEY}/d_lat", "16,20").split(",") if x.strip()],
            'd_prin': [int(x) for x in s.value(f"{SETTINGS_KEY}/d_prin", "50,75").split(",") if x.strip()],
            'hf_prin': float(s.value(f"{SETTINGS_KEY}/hf_prin", 10.0)),
            'vel_max': float(s.value(f"{SETTINGS_KEY}/vel_max", 2.0)),
        }

    # =========================================================================
    # CORE ALGORITHM
    # =========================================================================
    def _executar(self, inp, log):
        log("🚀 Iniciando Dimensionamento Setorizado...")
        
        # 1. Verificar inputs
        lyr_t = inp['tub']; lyr_e = inp['em']; lyr_v = inp['valvulas']; lyr_f = inp['fonte']
        if not lyr_t or not lyr_e or not lyr_f: raise Exception("Camadas essenciais faltando!")

        vazao_m3h = inp['vazao_emissor'] / 1000.0

        # 2. Ler geometria da fonte, válvulas e emissores
        feat_fonte = next(lyr_f.getFeatures(), None)
        if not feat_fonte: raise Exception("Camada de fonte está vazia!")
        pt_fonte = feat_fonte.geometry().asPoint()

        valv_pts = []
        if lyr_v:
            for f in lyr_v.getFeatures():
                valv_pts.append(f.geometry().asPoint())
                
        em_pts_list = []
        em_pts = {}
        em_idx = QgsSpatialIndex()
        for f in lyr_e.getFeatures():
            pt = f.geometry().asPoint()
            em_pts_list.append(pt)
            em_pts[f.id()] = {'geom': f.geometry(), 'vazao': vazao_m3h}
            em_idx.insertFeature(f)

        tol = inp['tolerancia']
        
        # 3. Planarizar a Rede (Snap/Split nas interseções em T, Válvulas e Emissores)
        log(f"✂️ Planarizando a rede para garantir conexões de setores (Tolerância: {tol}m)...")
        import processing
        
        vl_blade = QgsVectorLayer("LineString?crs=" + lyr_t.crs().authid(), "blade", "memory")
        pr_blade = vl_blade.dataProvider()
        feats_blade = []
        
        # A própria rede corta a si mesma nas interseções
        for f in lyr_t.getFeatures():
            new_f = QgsFeature()
            new_f.setGeometry(f.geometry())
            feats_blade.append(new_f)
            
        # Adicionar cruzes para forçar quebra exatamente nas válvulas e emissores
        cross_size = tol * 2.0
        for pt in valv_pts + em_pts_list:
            g1 = QgsGeometry.fromPolylineXY([QgsPointXY(pt.x() - cross_size, pt.y()), QgsPointXY(pt.x() + cross_size, pt.y())])
            g2 = QgsGeometry.fromPolylineXY([QgsPointXY(pt.x(), pt.y() - cross_size), QgsPointXY(pt.x(), pt.y() + cross_size)])
            f1 = QgsFeature(); f1.setGeometry(g1); feats_blade.append(f1)
            f2 = QgsFeature(); f2.setGeometry(g2); feats_blade.append(f2)
            
        pr_blade.addFeatures(feats_blade)
        
        res = processing.run("native:splitwithlines", {
            'INPUT': lyr_t,
            'LINES': vl_blade,
            'OUTPUT': 'memory:'
        })
        lyr_split = res['OUTPUT']
        feats_tub = list(lyr_split.getFeatures())
        ids_para_deletar = [f.id() for f in lyr_t.getFeatures()] # Deletar da camada original!

        # 4. Montar Grafo Não-Direcionado de Tubos
        log(f"🌐 Construindo Grafo de Tubulações...")
        
        node_idx = QgsSpatialIndex()
        nodes = {} # id -> pt
        next_node_id = 0
        
        def get_node_id(pt):
            nonlocal next_node_id
            nearest = node_idx.nearestNeighbor(pt, 1)
            if nearest:
                nid = nearest[0]
                if pt.distance(nodes[nid]) <= tol:
                    return nid
            
            nid = next_node_id
            next_node_id += 1
            nodes[nid] = pt
            f = QgsFeature()
            f.setGeometry(QgsGeometry.fromPointXY(pt))
            f.setId(nid)
            node_idx.insertFeature(f)
            return nid
            
        edges = {}       # edge_id -> { geom, L, n1, n2, tipologia, V, DN, HF }
        adj = {}         # node -> list of (neighbor_node, edge_id)
        edge_id_counter = 0

        for f in feats_tub:
            g = f.geometry()
            if not g or g.isEmpty() or g.isNull():
                continue
                
            polylines = []
            if g.isMultipart(): 
                mp = g.asMultiPolyline()
                if mp:
                    polylines.extend(mp)
            else:
                pl = g.asPolyline()
                if pl:
                    polylines.append(pl)
                    
            for part_idx, pl in enumerate(polylines):
                if not pl: 
                    continue
                
                n1 = get_node_id(QgsPointXY(pl[0]))
                n2 = get_node_id(QgsPointXY(pl[-1]))
                
                # Criar geometria temporaria da parte para calculos
                g_part = QgsGeometry.fromPolylineXY(pl)
                L = g_part.length()
                
                # Verificar se eh lateral (toca emissor)
                bb = g_part.boundingBox()
                bb.grow(0.1)
                intersecting_ems = em_idx.intersects(bb)
                has_em = False
                for eid in intersecting_ems:
                    if g_part.distance(em_pts[eid]['geom']) < 0.1:
                        has_em = True
                        break
                        
                # Usar um ID unico para arestas multiparte
                edge_uid = f"{f.id()}_{part_idx}"
                
                edges[edge_uid] = {
                    'geom': g_part, 'L': L, 'n1': n1, 'n2': n2, 
                    'has_em': has_em, 'V': 0.0, 'DN': 0, 'HF': 0.0, 'tipologia': 'Pendente', 'f_orig': f
                }
                adj.setdefault(n1, []).append((n2, edge_uid))
                adj.setdefault(n2, []).append((n1, edge_uid))

        log(f"   Foram mapeados {len(edges)} segmentos de tubo e {len(nodes)} nós.")

        # Achar nó da fonte
        nearest_fonte = node_idx.nearestNeighbor(pt_fonte, 1)
        if not nearest_fonte: raise Exception("Nenhuma tubulação encontrada perto da fonte!")
        root_node = nearest_fonte[0]
        log(f"   Fonte conectada ao nó: {root_node}")

        # 4. BFS para direcionar o grafo (Fonte -> Folhas)
        log("🧭 Direcionando fluxo da Fonte para as Extremidades...")
        parent = {root_node: None}
        edge_to_parent = {} # node -> edge_id que liga ao parent
        children = {root_node: []} # node -> list of (child_node, edge_id)
        
        queue = [root_node]
        while queue:
            u = queue.pop(0)
            if u not in children: children[u] = []
            for v, eid in adj.get(u, []):
                if v not in parent:
                    parent[v] = u
                    edge_to_parent[v] = eid
                    children[u].append((v, eid))
                    queue.append(v)

        # 5. Mapear Válvulas e Emissores para os nós do Grafo
        log("📌 Mapeando Válvulas e Emissores nos nós da rede...")
        node_valves = set()
        for vp in valv_pts:
            nearest = node_idx.nearestNeighbor(vp, 1)
            if nearest:
                vn = nearest[0]
                if vp.distance(nodes[vn]) < 5.0: # Tolerancia larga para mapeamento (5m)
                    node_valves.add(vn)
        
        log(f"   Foram encontradas {len(node_valves)} válvulas conectadas.")

        node_emissores = {}
        for eid, edata in em_pts.items():
            ep = edata['geom'].asPoint()
            nearest = node_idx.nearestNeighbor(ep, 1)
            if nearest:
                en = nearest[0]
                if ep.distance(nodes[en]) < 5.0:
                    node_emissores[en] = node_emissores.get(en, 0.0) + edata['vazao']

        # 6. Categorização Explícita (Tipologia)
        log("🔄 Categorizando Tubulações (Fonte -> Válvulas -> Emissores)...")
        
        # A. PRINCIPAIS (Caminho das Válvulas até a Fonte)
        for vn in node_valves:
            curr = vn
            while curr != root_node:
                p = parent.get(curr)
                if p is None: break
                eid = edge_to_parent[curr]
                edges[eid]['tipologia'] = 'Principal'
                curr = p
                
        # B. LATERAIS (Tocam emissores)
        for eid, e in edges.items():
            if e['tipologia'] == 'Principal': continue
            
            # Se a geometria toca um emissor fisicamente, ou um dos nós tem emissor
            if e['has_em'] or node_emissores.get(e['n1'], 0.0) > 0 or node_emissores.get(e['n2'], 0.0) > 0:
                e['tipologia'] = 'Lateral'

        # Obter ordem inversa da BFS para propagação de baixo pra cima
        post_order = []
        def dfs(u):
            for v, eid in children.get(u, []): dfs(v)
            post_order.append(u)
        dfs(root_node)

        # C. DERIVAÇÕES (Restantes)
        # Se não é Principal, e não tocou em emissor (Lateral), é Derivação.
        # Fazer isso varrendo todos os edges garante que até linhas desconectadas da fonte
        # (por erros de desenho) não fiquem como "Pendente" na tabela.
        for eid, e in edges.items():
            if e['tipologia'] == 'Pendente':
                e['tipologia'] = 'Derivacao'

        # 7. Acúmulo de Vazões (Post-Order)
        log("🔄 Calculando Acúmulo de Vazão...")
        node_flow = {}         # node -> vazao total vindo dos filhos (intra-setor)
        node_sectors = {}      # node -> list of flows representing downstream sectors
        
        for u in post_order:
            flow_here = node_emissores.get(u, 0.0)
            sectors_here = []
            
            for v, eid in children.get(u, []):
                flow_here += node_flow.get(v, 0.0)
                sectors_here.extend(node_sectors.get(v, []))
                
            if u in node_valves:
                # Este nó fecha um setor!
                if flow_here > 0:
                    sectors_here.append(flow_here) # Adiciona o setor recem fechado
                flow_here = 0.0 # Zera o fluxo "solto" pra cima, pois agora é setor empacotado
                
            node_flow[u] = flow_here
            node_sectors[u] = sectors_here
            
            # Definir tipologia do edge que sobe pro parent
            p = parent.get(u)
            if p is not None:
                eid = edge_to_parent[u]
                
                # Calcular a Vazao do Edge (V)
                if edges[eid]['tipologia'] in ['Lateral', 'Derivacao']:
                    edges[eid]['V'] = flow_here
                elif edges[eid]['tipologia'] == 'Principal':
                    # Principal: Combinação Máxima de Simultaneidade
                    simult = inp['simult']
                    secs = sorted(node_sectors[u], reverse=True)
                    edges[eid]['V'] = sum(secs[:simult]) + flow_here

        # 8. Dimensionamento (Regras de HF e Velocidade)
        log("⚙️ Dimensionando Diâmetros (Hazen-Williams)...")
        diams_lat = inp['d_lat']
        diams_prin = inp['d_prin']
        
        # A. Dimensionar Principais e Derivações (Garantir Velocidade 1º)
        for eid, e in edges.items():
            if e['tipologia'] == 'Lateral':
                e['DN'] = diams_lat[0]
            else:
                e['DN'] = diams_prin[-1] # fallback maximo
                for d in diams_prin:
                    vel = calcular_velocidade(e['V'], d)
                    if vel <= inp['vel_max']:
                        e['DN'] = d
                        break
                e['HF'] = calcular_hf_hw(e['V'], e['DN'], e['L'])
                
        # Otimizar HF do caminho Principal/Derivacao
        concluido_prin = False
        while not concluido_prin:
            max_path_hf = 0.0
            worst_path_nodes = []
            
            def find_worst_main_path(curr, current_hf, path):
                nonlocal max_path_hf, worst_path_nodes
                is_leaf = True
                for v, eid in children.get(curr, []):
                    if edges[eid]['tipologia'] != 'Lateral':
                        is_leaf = False
                        edges[eid]['HF'] = calcular_hf_hw(edges[eid]['V'], edges[eid]['DN'], edges[eid]['L'])
                        find_worst_main_path(v, current_hf + edges[eid]['HF'], path + [eid])
                if is_leaf:
                    if current_hf > max_path_hf:
                        max_path_hf = current_hf
                        worst_path_nodes = list(path)
            
            # Iniciar a partir do root_node
            is_root_leaf = True
            for v, eid in children.get(root_node, []):
                if edges[eid]['tipologia'] != 'Lateral':
                    is_root_leaf = False
                    edges[eid]['HF'] = calcular_hf_hw(edges[eid]['V'], edges[eid]['DN'], edges[eid]['L'])
                    find_worst_main_path(v, edges[eid]['HF'], [eid])
                    
            if max_path_hf <= inp['hf_prin'] or is_root_leaf:
                concluido_prin = True
            else:
                aumentou = False
                for eid in worst_path_nodes:
                    curr_dn = edges[eid]['DN']
                    if curr_dn < diams_prin[-1]:
                        idx = diams_prin.index(curr_dn)
                        edges[eid]['DN'] = diams_prin[idx + 1]
                        aumentou = True
                        break
                if not aumentou:
                    concluido_prin = True
                    log(f"   ⚠️ Caminho principal estourou {inp['hf_prin']}mca (Chegou a {max_path_hf:.2f}mca) mesmo no diâmetro máximo.")
                        
        # B. Dimensionar Laterais (Regra dos 20% PS)
        # O encadeamento de laterais vai da derivação até o ultimo emissor.
        # Precisamos de um DFS a partir das Derivacoes para baixo nas Laterais.
        
        limite_hf_lat = 0.20 * inp['ps']
        log(f"   Limite 20% PS para Laterais: {limite_hf_lat:.2f} mca")
        
        # Identificar nós que sao inicio de laterais
        inicios_laterais = []
        for u in [root_node] + post_order:
            is_u_lateral = False
            if u != root_node:
                eid_up = edge_to_parent[u]
                if edges[eid_up]['tipologia'] == 'Lateral':
                    is_u_lateral = True
            
            if not is_u_lateral:
                for v, eid_down in children.get(u, []):
                    if edges[eid_down]['tipologia'] == 'Lateral':
                        inicios_laterais.append(v)
                            
        # Para cada inicio de lateral, iterar aumento de diametro se houver caminho estourando
        for start_node in inicios_laterais:
            concluido = False
            while not concluido:
                # Achar o pior caminho (maior HF acumulado)
                max_path_hf = 0.0
                worst_path_nodes = []
                
                def find_worst_path(curr, current_hf, path):
                    nonlocal max_path_hf, worst_path_nodes
                    is_leaf = True
                    for v, eid in children.get(curr, []):
                        if edges[eid]['tipologia'] == 'Lateral':
                            is_leaf = False
                            edges[eid]['HF'] = calcular_hf_hw(edges[eid]['V'], edges[eid]['DN'], edges[eid]['L'])
                            find_worst_path(v, current_hf + edges[eid]['HF'], path + [eid])
                    if is_leaf:
                        if current_hf > max_path_hf:
                            max_path_hf = current_hf
                            worst_path_nodes = list(path)
                            
                eid_start = edge_to_parent[start_node]
                edges[eid_start]['HF'] = calcular_hf_hw(edges[eid_start]['V'], edges[eid_start]['DN'], edges[eid_start]['L'])
                find_worst_path(start_node, edges[eid_start]['HF'], [eid_start])
                
                if max_path_hf <= limite_hf_lat:
                    concluido = True # Passou!
                else:
                    # Falhou. Precisamos aumentar o diâmetro.
                    # A regra de ouro é aumentar o diâmetro do trecho de montante (com maior vazão)
                    # Vamos varrer o pior caminho de cima pra baixo e aumentar o 1º que não está no maximo
                    aumentou = False
                    for eid in worst_path_nodes:
                        curr_dn = edges[eid]['DN']
                        if curr_dn < diams_lat[-1]:
                            # Acha o proximo diametro
                            idx = diams_lat.index(curr_dn)
                            edges[eid]['DN'] = diams_lat[idx + 1]
                            aumentou = True
                            break # Só aumenta 1 por iteração e recalcula
                            
                    if not aumentou:
                        # Todos os canos ja estao no diametro maximo! Nao tem como resolver.
                        concluido = True
                        log(f"   ⚠️ Lateral estourou {limite_hf_lat}mca (Chegou a {max_path_hf:.2f}mca) mesmo no diâmetro máximo.")

        # Recalcular HFs finais para salvar
        for eid, e in edges.items():
            e['HF'] = calcular_hf_hw(e['V'], e['DN'], e['L'])

        # 8. Atualizar Camada
        log("\n📦 Salvando resultados no QGIS...")
        pr = lyr_t.dataProvider()
        campos_existentes = [f.name() for f in lyr_t.fields()]

        campos_novos = []
        if "Tipo" not in campos_existentes: campos_novos.append(QgsField("Tipo", QVariant.String))
        if "DN" not in campos_existentes: campos_novos.append(QgsField("DN", QVariant.Int))
        if "V" not in campos_existentes: campos_novos.append(QgsField("V", QVariant.Double, len=10, prec=4))
        if "L" not in campos_existentes: campos_novos.append(QgsField("L", QVariant.Double, len=10, prec=2))
        if "HF" not in campos_existentes: campos_novos.append(QgsField("HF", QVariant.Double, len=10, prec=4))
        
        if campos_novos:
            pr.addAttributes(campos_novos)
            lyr_t.updateFields()

        idx_tipo = lyr_t.fields().indexOf("Tipo")
        idx_dn = lyr_t.fields().indexOf("DN")
        idx_v  = lyr_t.fields().indexOf("V")
        idx_l  = lyr_t.fields().indexOf("L")
        idx_hf = lyr_t.fields().indexOf("HF")

        feats_novos = []
        for eid, e in edges.items():
            f = QgsFeature(lyr_t.fields())
            f.setGeometry(e['geom'])
            f.setAttributes(e['f_orig'].attributes())
            f.setAttribute(idx_tipo, e['tipologia'])
            f.setAttribute(idx_dn, e['DN'])
            f.setAttribute(idx_v, round(e['V'], 4))
            f.setAttribute(idx_l, round(e['L'], 2))
            f.setAttribute(idx_hf, round(e['HF'], 4))
            feats_novos.append(f)

        lyr_t.startEditing()
        lyr_t.deleteFeatures(ids_para_deletar)
        lyr_t.addFeatures(feats_novos)
        lyr_t.commitChanges()
        lyr_t.triggerRepaint()

        log(f"\n✅ SUCESSO! Rede Dimensionada.")
        log(f"   {len(feats_novos)} trechos processados.")
        
        self.iface.messageBar().pushMessage(
            "Aqueduct",
            f"Dimensionamento Concluído! {len(feats_novos)} trechos avaliados.",
            level=0, duration=8
        )
