import os
import math
from qgis.PyQt.QtWidgets import (QAction, QDialog, QVBoxLayout, QHBoxLayout, 
                               QLabel, QDoubleSpinBox, QSpinBox, QDialogButtonBox, 
                               QMessageBox, QProgressDialog, QGroupBox, QFormLayout,
                               QTabWidget, QWidget, QCheckBox)
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
        self.resize(520, 520)
        
        layout = QVBoxLayout(self)
        
        # === Abas Principal / Avançado ===
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # ---------- ABA PRINCIPAL ----------
        tab_principal = QWidget()
        lay_tab = QVBoxLayout(tab_principal)
        
        # --- Etapa 1: Rede Parcelar ---
        group_etapa1 = QGroupBox("Etapa 1: Rede Parcelar")
        lay_etapa1 = QFormLayout()
        
        self.cb_emissores = QgsMapLayerComboBox()
        self.cb_emissores.setFilters(QgsMapLayerProxyModel.PointLayer)
        lay_etapa1.addRow("Emissores (Pontos):", self.cb_emissores)
        
        self.cb_laterais = QgsMapLayerComboBox()
        self.cb_laterais.setFilters(QgsMapLayerProxyModel.LineLayer)
        lay_etapa1.addRow("Linhas Laterais:", self.cb_laterais)
        
        self.cb_derivacao = QgsMapLayerComboBox()
        self.cb_derivacao.setFilters(QgsMapLayerProxyModel.LineLayer)
        lay_etapa1.addRow("Linhas de Derivação:", self.cb_derivacao)
        
        self.cb_cavaletes = QgsMapLayerComboBox()
        self.cb_cavaletes.setFilters(QgsMapLayerProxyModel.PointLayer)
        lay_etapa1.addRow("Cavaletes:", self.cb_cavaletes)
        
        self.spin_vazao = QDoubleSpinBox()
        self.spin_vazao.setRange(0.01, 10000.0)
        self.spin_vazao.setValue(2.0)
        self.spin_vazao.setDecimals(2)
        lay_etapa1.addRow("Vazão por Emissor (L/h):", self.spin_vazao)
        
        group_etapa1.setLayout(lay_etapa1)
        lay_tab.addWidget(group_etapa1)
        
        # --- Etapa 2: Linha Principal ---
        group_etapa2 = QGroupBox("Etapa 2: Linha Principal e Simulação")
        lay_etapa2 = QFormLayout()
        
        self.cb_linha_principal = QgsMapLayerComboBox()
        self.cb_linha_principal.setFilters(QgsMapLayerProxyModel.LineLayer)
        lay_etapa2.addRow("Linha Principal:", self.cb_linha_principal)
        
        self.cb_fontes = QgsMapLayerComboBox()
        self.cb_fontes.setFilters(QgsMapLayerProxyModel.PointLayer)
        lay_etapa2.addRow("Fontes (Bombas):", self.cb_fontes)
        
        self.spin_cap_fonte = QDoubleSpinBox()
        self.spin_cap_fonte.setRange(0.1, 999999.0)
        self.spin_cap_fonte.setValue(50.0)
        self.spin_cap_fonte.setDecimals(2)
        lay_etapa2.addRow("Capacidade Max por Fonte (m³/h):", self.spin_cap_fonte)
        
        self.spin_simultaneos = QSpinBox()
        self.spin_simultaneos.setRange(1, 999)
        self.spin_simultaneos.setValue(2)
        lay_etapa2.addRow("Cavaletes Simultâneos:", self.spin_simultaneos)
        
        group_etapa2.setLayout(lay_etapa2)
        lay_tab.addWidget(group_etapa2)
        
        # --- Etapa 3: Dimensionamento ---
        group_etapa3 = QGroupBox("Etapa 3: Dimensionamento Hidráulico")
        lay_etapa3 = QFormLayout()
        
        self.spin_pressao_servico = QDoubleSpinBox()
        self.spin_pressao_servico.setRange(1.0, 1000.0)
        self.spin_pressao_servico.setValue(30.0)
        self.spin_pressao_servico.setDecimals(1)
        lay_etapa3.addRow("Pressão de Serviço (mca):", self.spin_pressao_servico)
        
        self.spin_var_lateral = QDoubleSpinBox()
        self.spin_var_lateral.setRange(1.0, 100.0)
        self.spin_var_lateral.setValue(10.0)
        self.spin_var_lateral.setDecimals(1)
        lay_etapa3.addRow("Variação Máx. Pressão Lateral (%):", self.spin_var_lateral)
        
        self.spin_hf_outros = QDoubleSpinBox()
        self.spin_hf_outros.setRange(0.01, 500.0)
        self.spin_hf_outros.setValue(2.0)
        self.spin_hf_outros.setDecimals(2)
        lay_etapa3.addRow("Perda de Carga Máx. Outros (mca):", self.spin_hf_outros)
        
        self.spin_diam_lateral = QDoubleSpinBox()
        self.spin_diam_lateral.setRange(0.0, 500.0)
        self.spin_diam_lateral.setValue(0.0)
        self.spin_diam_lateral.setDecimals(1)
        self.spin_diam_lateral.setSpecialValueText("Auto")
        self.spin_diam_lateral.setToolTip("Deixe em 'Auto' (0.0) para descobrir sozinho ou fixe um tamanho de mangueira!")
        lay_etapa3.addRow("Diâmetro Fixo Lateral (mm):", self.spin_diam_lateral)
        
        self.chk_is_mangueira = QCheckBox("Laterais são Mangueiras (Rolo)")
        self.chk_is_mangueira.setToolTip("Se marcado, as laterais terão diâmetro fixo por toda extensão e serão contabilizadas em Rolos na lista de materiais.")
        lay_etapa3.addRow(self.chk_is_mangueira)
        
        group_etapa3.setLayout(lay_etapa3)
        lay_tab.addWidget(group_etapa3)
        lay_tab.addStretch()
        
        self.tabs.addTab(tab_principal, "Principal")
        
        # ---------- ABA AVANÇADO ----------
        tab_avancado = QWidget()
        lay_av = QVBoxLayout(tab_avancado)
        
        group_simp = QGroupBox("Simplificação de Geometria (Douglas-Peuker)")
        lay_simp = QFormLayout()
        lay_simp.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        
        lbl_info = QLabel(
            "Usa o algoritmo Douglas-Peuker para remover nós intermediários desnecessários em "
            "linhas contínuas, evitando que um trecho seja dividido em múltiplos segmentos.\n"
            "A tolerância é em metros (unidades do mapa). Padrão recomendado: 1.0 m.\n"
            "Desative para processar as geometrias sem nenhuma alteração."
        )
        lbl_info.setWordWrap(True)
        lay_av.addWidget(lbl_info)
        
        # Laterais
        self.chk_simp_lateral = QCheckBox("Simplificar Laterais")
        self.chk_simp_lateral.setChecked(True)
        self.chk_simp_lateral.toggled.connect(self._toggle_simp_lateral)
        lay_simp.addRow(self.chk_simp_lateral)
        
        self.spin_simp_lateral = QDoubleSpinBox()
        self.spin_simp_lateral.setRange(0.01, 100.0)
        self.spin_simp_lateral.setValue(1.0)
        self.spin_simp_lateral.setDecimals(2)
        self.spin_simp_lateral.setSuffix(" m")
        self.spin_simp_lateral.setToolTip("Tolerância em metros para o algoritmo Douglas-Peuker nas linhas laterais")
        lay_simp.addRow("   Tolerância lateral:", self.spin_simp_lateral)
        
        # Separador visual
        lay_simp.addRow(QLabel(""))
        
        # Derivações
        self.chk_simp_derivacao = QCheckBox("Simplificar Derivações")
        self.chk_simp_derivacao.setChecked(False)
        self.chk_simp_derivacao.toggled.connect(self._toggle_simp_derivacao)
        lay_simp.addRow(self.chk_simp_derivacao)
        
        self.spin_simp_derivacao = QDoubleSpinBox()
        self.spin_simp_derivacao.setRange(0.01, 100.0)
        self.spin_simp_derivacao.setValue(1.0)
        self.spin_simp_derivacao.setDecimals(2)
        self.spin_simp_derivacao.setSuffix(" m")
        self.spin_simp_derivacao.setEnabled(False)
        self.spin_simp_derivacao.setToolTip("Tolerância em metros para o algoritmo Douglas-Peuker nas linhas de derivação")
        lay_simp.addRow("   Tolerância derivação:", self.spin_simp_derivacao)
        
        group_simp.setLayout(lay_simp)
        lay_av.addWidget(group_simp)
        lay_av.addStretch()
        
        self.tabs.addTab(tab_avancado, "Avançado")
        
        # Botões
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        
        # Auto-seleção de camadas ao abrir o diálogo
        self._auto_selecionar_camadas()

    def _auto_selecionar_camadas(self):
        """Tenta pré-selecionar camadas do projeto com base em palavras-chave nos nomes."""
        
        def buscar_camada(palavras_chave, tipo_geometria):
            """Retorna a primeira camada encontrada cujo nome contenha alguma palavra-chave."""
            for layer in QgsProject.instance().mapLayers().values():
                if not hasattr(layer, 'geometryType'):
                    continue
                if layer.geometryType() != tipo_geometria:
                    continue
                nome = layer.name().lower()
                for kw in palavras_chave:
                    if kw in nome:
                        return layer
            return None
        
        PONTO = QgsWkbTypes.PointGeometry
        LINHA = QgsWkbTypes.LineGeometry
        
        # Mapeamento: (combo_box, [palavras-chave], tipo_geometria)
        mapeamentos = [
            (self.cb_emissores,       ['emissor', 'gotejador', 'aspersor', 'microaspersor', 'emitter'], PONTO),
            (self.cb_laterais,        ['lateral', 'mangueira'],                                          LINHA),
            (self.cb_derivacao,       ['deriv', 'derivação', 'derivacao', 'subprincipal'],              LINHA),
            (self.cb_cavaletes,       ['cavalete', 'hidrante', 'tomada'],                                PONTO),
            (self.cb_linha_principal, ['principal', 'adutora', 'tronco', 'main'],                        LINHA),
            (self.cb_fontes,          ['fonte', 'bomba', 'pump', 'motor'],                               PONTO),
        ]
        
        for combo, palavras, tipo in mapeamentos:
            camada = buscar_camada(palavras, tipo)
            if camada:
                combo.setLayer(camada)

    def _toggle_simp_lateral(self, checked):
        self.spin_simp_lateral.setEnabled(checked)

    def _toggle_simp_derivacao(self, checked):
        self.spin_simp_derivacao.setEnabled(checked)

    def get_inputs(self):
        # Tolerância em metros (None = não simplificar)
        simp_lateral = self.spin_simp_lateral.value() if self.chk_simp_lateral.isChecked() else None
        simp_derivacao = self.spin_simp_derivacao.value() if self.chk_simp_derivacao.isChecked() else None
        return {
            'emissores': self.cb_emissores.currentLayer(),
            'laterais': self.cb_laterais.currentLayer(),
            'derivacao': self.cb_derivacao.currentLayer(),
            'cavaletes': self.cb_cavaletes.currentLayer(),
            'vazao': self.spin_vazao.value(),
            'linha_principal': self.cb_linha_principal.currentLayer(),
            'fontes': self.cb_fontes.currentLayer(),
            'cap_fonte': self.spin_cap_fonte.value(),
            'simultaneos': self.spin_simultaneos.value(),
            'pressao_servico': self.spin_pressao_servico.value(),
            'var_lateral': self.spin_var_lateral.value(),
            'hf_outros': self.spin_hf_outros.value(),
            'diam_lateral': self.spin_diam_lateral.value(),
            'simp_lateral': simp_lateral,
            'simp_derivacao': simp_derivacao,
            'is_mangueira': self.chk_is_mangueira.isChecked()
        }

    @staticmethod
    def get_auto_inputs():
        """Tenta encontrar as camadas automaticamente no projeto atual."""
        def buscar(keywords, geom):
            for l in QgsProject.instance().mapLayers().values():
                if hasattr(l, 'geometryType') and l.geometryType() == geom:
                    name = l.name().lower()
                    if any(kw in name for kw in keywords): return l
            return None

        from qgis.core import QgsWkbTypes
        P = QgsWkbTypes.PointGeometry
        L = QgsWkbTypes.LineGeometry
        
        return {
            'emissores': buscar(['emissor', 'gotejador', 'aspersor'], P),
            'laterais': buscar(['lateral', 'mangueira'], L),
            'derivacao': buscar(['deriv', 'subprincipal'], L),
            'cavaletes': buscar(['cavalete', 'hidrante'], P),
            'linha_principal': buscar(['principal', 'adutora', 'main'], L),
            'fontes': buscar(['fonte', 'bomba'], P),
            'vazao': 2.0,
            'cap_fonte': 50.0,
            'simultaneos': 2,
            'pressao_servico': 30.0,
            'var_lateral': 10.0,
            'hf_outros': 2.0,
            'diam_lateral': 0.0,
            'simp_lateral': 1.0,
            'simp_derivacao': None,
            'is_mangueira': False
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
        self.run_with_inputs(inputs)

    def run_automated(self, params=None):
        """Executa automaticamente tentando detectar camadas."""
        inputs = AcumuloVazaoDialog.get_auto_inputs()
        if params:
            inputs.update(params)
        
        # Validação básica
        req = ['emissores', 'laterais', 'derivacao', 'cavaletes', 'linha_principal', 'fontes']
        missing = [r for r in req if not inputs.get(r)]
        if missing:
            raise Exception(f"Não encontrei estas camadas automaticamente: {', '.join(missing)}")
            
        self.run_with_inputs(inputs)

    def run_with_inputs(self, inputs):
        # Validação: Se for mangueira, diâmetro deve ser informado
        if inputs['is_mangueira'] and inputs['diam_lateral'] <= 0:
            self.iface.messageBar().pushMessage("Aqueduct", "Se as laterais são mangueiras, informe um diâmetro fixo!", level=2, duration=5)
            return
            
        self.execute_routing(inputs)
        
    def round_point(self, pt):
        """Arredonda a coordenada para evitar problemas de precisao float"""
        return (round(pt.x(), 3), round(pt.y(), 3))
        
    def dimensionar_tubo(self, line_edges_info, hf_limit, fixed_diam=0.0):
        catalogo = [20, 25, 32, 50, 75, 100, 125, 150]
        if fixed_diam > 0:
            result = {}
            for e in line_edges_info:
                d = int(fixed_diam)
                hf_trecho = 0.0
                if e['q'] > 0 and e['l'] > 0:
                    D = d / 1000.0
                    q_m3s = e['q'] / 3600.0
                    j = 10.67 * ((q_m3s / 140.0)**1.852) / (D**4.87)
                    hf_trecho = j * e['l']
                result[e['e_idx']] = (d, hf_trecho)
            return result
            
        C = 140.0
        def calc_hf_array(diams_array):
            hf_total = 0.0
            for i, d_mm in enumerate(diams_array):
                if line_edges_info[i]['q'] <= 0 or line_edges_info[i]['l'] <= 0: continue
                D = d_mm / 1000.0
                q_m3s = line_edges_info[i]['q'] / 3600.0
                j = 10.67 * ((q_m3s / C)**1.852) / (D**4.87)
                hf_total += j * line_edges_info[i]['l']
            return hf_total
            
        best_d = catalogo[-1]
        for d in catalogo:
            test_diams = [d] * len(line_edges_info)
            if calc_hf_array(test_diams) <= hf_limit:
                best_d = d
                break
                
        current_diams = [best_d] * len(line_edges_info)
        indices_sorted_by_q = sorted(range(len(line_edges_info)), key=lambda i: line_edges_info[i]['q'])
        
        # Algoritmo de redução multi-passo para garantir continuidade (telescopagem suave)
        # Processamos de ponta a ponta tentando reduzir um nível por vez
        changed = True
        while changed:
            changed = False
            for i in range(len(indices_sorted_by_q)): # Do Final para o Início
                idx = indices_sorted_by_q[i]
                d = current_diams[idx]
                
                if d > catalogo[0]:
                    c_idx = catalogo.index(d)
                    lower_d = catalogo[c_idx - 1]
                    
                    # Regra de Continuidade: O diâmetro atual não pode ser mais do que 1 nível 
                    # menor que o diâmetro do trecho de montante (vazão imediatamente superior).
                    if i < len(indices_sorted_by_q) - 1:
                        upstream_d = current_diams[indices_sorted_by_q[i+1]]
                        u_idx = catalogo.index(upstream_d)
                        # O menor diâmetro permitido aqui é o nível imediatamente abaixo do montante
                        min_permitido = catalogo[max(0, u_idx - 1)]
                        if lower_d < min_permitido:
                            continue # Pularia etapa do catálogo, ignora esta redução por hora
                    
                    # Tenta aplicar a redução e verifica Perda de Carga Total
                    current_diams[idx] = lower_d
                    if calc_hf_array(current_diams) <= hf_limit:
                        changed = True
                    else:
                        current_diams[idx] = d # Reverte
                    
        result = {}
        for i, d in enumerate(current_diams):
            e = line_edges_info[i]
            hf_trecho = 0.0
            if e['q'] > 0 and e['l'] > 0:
                D = d / 1000.0
                q_m3s = e['q'] / 3600.0
                j = 10.67 * ((q_m3s / 140.0)**1.852) / (D**4.87)
                hf_trecho = j * e['l']
            result[e['e_idx']] = (d, hf_trecho)
            
        return result

    def execute_routing(self, inputs):
        lyr_emissores = inputs['emissores']
        lyr_laterais = inputs['laterais']
        lyr_derivacao = inputs['derivacao']
        lyr_cavaletes = inputs['cavaletes']
        vazao_emissor = inputs['vazao']
        lyr_linha_principal = inputs['linha_principal']
        lyr_fontes = inputs['fontes']
        cap_fonte = inputs['cap_fonte']
        simultaneos = inputs['simultaneos']
        
        self.iface.messageBar().pushMessage("Aqueduct", "Construindo topologia rígida de rede...", level=0, duration=3)
        
        progress = QProgressDialog("Indexando geometria...", "Cancelar", 0, 100, self.iface.mainWindow())
        progress.setWindowTitle("Roteamento de Vazão")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        # 1. Index Line Features
        all_lines = {} # id -> {'geom': geom, 'tipo': tipo, 'fid': fid_original}
        line_idx = QgsSpatialIndex()
        global_lid = 0
        
        def load_lines(layer, tipo):
            nonlocal global_lid
            for f in layer.getFeatures():
                geom = f.geometry()
                
                if geom.isMultipart():
                    lines = geom.asMultiPolyline()
                else:
                    lines = [geom.asPolyline()]
                for line_coords in lines:
                    line_geom = QgsGeometry.fromPolylineXY(line_coords)
                    
                    # Simplificação Douglas-Peuker com tolerância fixa em metros (igual à ferramenta nativa do QGIS)
                    # QgsMapToPixelSimplifier.SimplifyAlgorithm: 0 = Douglas-Peuker
                    if tipo == 'lateral' and inputs.get('simp_lateral') is not None:
                        simplificada = line_geom.simplify(inputs['simp_lateral'])
                        if not simplificada.isEmpty() and simplificada.length() > 0:
                            line_geom = simplificada
                    elif tipo == 'derivacao' and inputs.get('simp_derivacao') is not None:
                        simplificada = line_geom.simplify(inputs['simp_derivacao'])
                        if not simplificada.isEmpty() and simplificada.length() > 0:
                            line_geom = simplificada
                        
                    all_lines[global_lid] = {'geom': line_geom, 'tipo': tipo, 'fid': f.id()}
                    f_temp = QgsFeature(global_lid)
                    f_temp.setGeometry(line_geom)
                    line_idx.insertFeature(f_temp)
                    global_lid += 1

        load_lines(lyr_laterais, 'lateral')
        load_lines(lyr_derivacao, 'derivacao')

        progress.setValue(15)
        progress.setLabelText("Mapeando Emissores e Cavaletes para tubulações únicas...")

        # 2. Atribuir Emissores e Cavaletes para UMA ÚNICA LINHA mais próxima
        # Isso evita cortar duas linhas próximas por engano
        points_assigned = {lid: [] for lid in all_lines}
        
        emitter_nodes_to_route = []
        for f in lyr_emissores.getFeatures():
            geom = f.geometry()
            nearest = line_idx.nearestNeighbor(geom, 1)
            if nearest:
                lid = nearest[0]
                points_assigned[lid].append(geom)
                emitter_nodes_to_route.append((geom, lid))
                
        cavalete_nodes_starts = []
        for f in lyr_cavaletes.getFeatures():
            geom = f.geometry()
            nearest = line_idx.nearestNeighbor(geom, 1)
            if nearest:
                lid = nearest[0]
                points_assigned[lid].append(geom)
                cavalete_nodes_starts.append((geom, lid))

        # 2b. Projetar os pontos iniciais de laterais nas derivações
        # Essencial quando a derivação é simplificada e perde vértices intermediários onde as laterais tocam.
        # Para cada lateral, o seu ponto inicial (e final) é projetado na derivação mais próxima.
        tolerancia_conexao = 0.5  # metros - distância máxima para considerar uma junção lateral-derivação
        
        # Separar IDs por tipo para facilitar busca
        lids_derivacao = {lid for lid, d in all_lines.items() if d['tipo'] == 'derivacao'}
        
        # Índice espacial só das derivações
        deriv_idx = QgsSpatialIndex()
        for lid in lids_derivacao:
            f_temp = QgsFeature(lid)
            f_temp.setGeometry(all_lines[lid]['geom'])
            deriv_idx.insertFeature(f_temp)
        
        for lid, line_data in all_lines.items():
            if line_data['tipo'] != 'lateral':
                continue
            polyline = line_data['geom'].asPolyline()
            if not polyline:
                continue
            # Verifica apenas o ponto inicial da lateral (onde ela nasce na derivação)
            pt_inicio = QgsGeometry.fromPointXY(QgsPointXY(polyline[0].x(), polyline[0].y()))
            candidatos = deriv_idx.nearestNeighbor(pt_inicio, 3)
            for deriv_lid in candidatos:
                deriv_geom = all_lines[deriv_lid]['geom']
                dist = pt_inicio.distance(deriv_geom)
                if dist <= tolerancia_conexao:
                    # Projetar o ponto inicial da lateral na derivação
                    points_assigned[deriv_lid].append(pt_inicio)
                    break  # basta a derivação mais próxima dentro da tolerância

        progress.setValue(30)
        progress.setLabelText("Gerando malha topológica rígida...")


        # 3. Quebrar as linhas e construir arestas preservando o ID
        nodes = set() # Agora node é: (x, y, lid)
        edges = []
        
        coord_map = {} # (x, y) -> set(lids que dividem essa coordenada)
        
        for lid, line_data in all_lines.items():
            line_geom = line_data['geom']
            tipo = line_data['tipo']
            notable_geoms = points_assigned[lid]
            
            vertices_on_line = []
            
            # Vértices da própria linha
            for pt in line_geom.asPolyline():
                dist_along = float(line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pt)))
                vertices_on_line.append((dist_along, pt))
                
            # Projeta apenas os notáveis atrelados a ela
            for target_geom in notable_geoms:
                dist_along = float(line_geom.lineLocatePoint(target_geom))
                pt_proj = line_geom.interpolate(dist_along).asPoint()
                vertices_on_line.append((dist_along, pt_proj))
                
            vertices_on_line.sort(key=lambda x: x[0])
            
            # Filtrar muito agrupados
            filtered = []
            last_dist = -999.0
            for d, pt in vertices_on_line:
                if (d - last_dist) > 0.05: # 5cm tolerância
                    filtered.append(pt)
                    last_dist = d
                    
            # Arestas físicas do tubo
            for i in range(len(filtered) - 1):
                pt_a = self.round_point(filtered[i])
                pt_b = self.round_point(filtered[i+1])
                
                n_a = (pt_a[0], pt_a[1], lid)
                n_b = (pt_b[0], pt_b[1], lid)
                nodes.add(n_a)
                nodes.add(n_b)
                
                if pt_a not in coord_map: coord_map[pt_a] = set()
                coord_map[pt_a].add(lid)
                if pt_b not in coord_map: coord_map[pt_b] = set()
                coord_map[pt_b].add(lid)
                
                seg_geom = QgsGeometry.fromPolylineXY([QgsPointXY(*pt_a), QgsPointXY(*pt_b)])
                edges.append({
                    'u': n_a, 'v': n_b, 'length': seg_geom.length(),
                    'geom': seg_geom, 'flow': 0.0, 'tipo': tipo, 'is_transfer': False
                })

        progress.setValue(45)
        progress.setLabelText("Ligando cruzamentos entre setores (Bloqueando Laterais)...")

        # 4. Criar links condicionais entre linhas que se cruzam
        for pt_xy, lids in coord_map.items():
            lids_list = list(lids)
            for i in range(len(lids_list)):
                for j in range(i+1, len(lids_list)):
                    lid1 = lids_list[i]
                    lid2 = lids_list[j]
                    t1 = all_lines[lid1]['tipo']
                    t2 = all_lines[lid2]['tipo']
                    
                    # REGRA DE OURO: Não transfere água de uma lateral para outra lateral
                    # Isso resolve o problema das laterais cortadas que eram unidas
                    if t1 == 'lateral' and t2 == 'lateral':
                        continue
                        
                    n1 = (pt_xy[0], pt_xy[1], lid1)
                    n2 = (pt_xy[0], pt_xy[1], lid2)
                    nodes.add(n1)
                    nodes.add(n2)
                    
                    # Conexao instantanea (0 custo)
                    edges.append({
                        'u': n1, 'v': n2, 'length': 0.0,
                        'geom': None, 'flow': 0.0, 'tipo': 'transfer', 'is_transfer': True
                    })

        progress.setValue(60)
        progress.setLabelText("Executando roteamento otimizado...")

        # 5. Montar grafo rápido
        graph = {n: {} for n in nodes}
        for idx, edge in enumerate(edges):
            u, v, cost = edge['u'], edge['v'], edge['length']
            graph[u][v] = (cost, idx)
            graph[v][u] = (cost, idx)

        # 6. Alvos exatos dos Cavaletes
        cavalete_targets = set()
        for geom, lid in cavalete_nodes_starts:
            dist_along = float(all_lines[lid]['geom'].lineLocatePoint(geom))
            pt_proj = all_lines[lid]['geom'].interpolate(dist_along).asPoint()
            rounded = self.round_point(pt_proj)
            cavalete_targets.add((rounded[0], rounded[1], lid))

        # 7. Algoritmo de Dijkstra reverso
        import heapq
        distances = {n: float('inf') for n in nodes}
        next_edge = {n: None for n in nodes}
        pq = []
        for cv in cavalete_targets:
            if cv in distances:
                distances[cv] = 0.0
                heapq.heappush(pq, (0.0, cv))
                
        while pq:
            d, curr = heapq.heappop(pq)
            if d > distances[curr]: continue
            for neighbor, (cost, e_idx) in graph[curr].items():
                new_d = d + cost
                if new_d < distances[neighbor]:
                    distances[neighbor] = new_d
                    next_edge[neighbor] = e_idx
                    heapq.heappush(pq, (new_d, neighbor))
                    
        progress.setValue(80)
        progress.setLabelText("Somando escoamento nos trechos...")

        # 8. Acumular fluxo partindo das fontes (Emissores)
        flow_at_cavalete = {cv: 0.0 for cv in cavalete_targets}
        
        for geom, lid in emitter_nodes_to_route:
            dist_along = float(all_lines[lid]['geom'].lineLocatePoint(geom))
            pt_proj = all_lines[lid]['geom'].interpolate(dist_along).asPoint()
            rounded = self.round_point(pt_proj)
            start_node = (rounded[0], rounded[1], lid)
            
            if start_node in distances and distances[start_node] < float('inf'):
                curr = start_node
                while True:
                    e_idx = next_edge.get(curr)
                    if e_idx is None:
                        # Chegou no alvo final (cavalete)
                        if curr in flow_at_cavalete:
                            flow_at_cavalete[curr] += vazao_emissor
                        break
                        
                    edges[e_idx]['flow'] += vazao_emissor
                    u, v = edges[e_idx]['u'], edges[e_idx]['v']
                    curr = u if u != curr else v

        progress.setValue(90)
        progress.setLabelText("Renderizando camada final...")

        # --- DIMENSIONAMENTO OTIMIZADO (ETAPA 1) ---
        edges_by_lid = {}
        for e_idx, edge in enumerate(edges):
            if not edge['is_transfer'] and edge['flow'] > 0:
                lid = edge['orig_lid'] if 'orig_lid' in edge else edge['u'][2]
                if lid not in edges_by_lid: edges_by_lid[lid] = []
                l_tubo = edge.get('length', edge.get('len', 0.0))
                edges_by_lid[lid].append({
                    'e_idx': e_idx,
                    'l': l_tubo,
                    'q': edge['flow'] / 1000.0
                })
                
        diams = {}
        limit_lateral = inputs['pressao_servico'] * (inputs['var_lateral'] / 100.0)
        limit_outros = inputs['hf_outros']
        is_mangueira = inputs.get('is_mangueira', False)
        
        for k_lid, info in all_lines.items():
            if k_lid not in edges_by_lid: continue
            
            fix_d = 0.0
            if info['tipo'] == 'lateral' and is_mangueira:
                fix_d = inputs['diam_lateral']
                
            if info['tipo'] == 'lateral':
                d_dict = self.dimensionar_tubo(edges_by_lid[k_lid], limit_lateral, fix_d)
            else:
                d_dict = self.dimensionar_tubo(edges_by_lid[k_lid], limit_outros, 0.0)
            diams.update(d_dict)

        # 9. Gerar camada de Saída omitindo as arestas virtuais ('transfer')
        crs = lyr_laterais.crs().authid()
        out_layer = QgsVectorLayer(f"LineString?crs={crs}", "Topologia e Acúmulo de Vazão", "memory")
        pr = out_layer.dataProvider()
        pr.addAttributes([
            QgsField("tipo", QVariant.String),
            QgsField("V", QVariant.Double, len=10, prec=2),
            QgsField("DN", QVariant.Int),
            QgsField("HF", QVariant.Double, len=10, prec=2),
            QgsField("L", QVariant.Double, len=10, prec=2),
            QgsField("formato", QVariant.String)
        ])
        out_layer.updateFields()
        
        out_features = []
        for e_idx, edge in enumerate(edges):
            if not edge['is_transfer'] and edge['flow'] > 0:
                feat = QgsFeature()
                feat.setGeometry(edge['geom'])
                vazao_m3 = round(edge['flow'] / 1000.0, 2)
                d_val, hf_val = diams.get(e_idx, (0, 0.0))
                l_tubo = edge.get('length', edge.get('len', 0.0))
                
                formato = "Barra"
                if edge['tipo'] == 'lateral' and is_mangueira:
                    formato = "Rolo"
                    
                feat.setAttributes([edge['tipo'], vazao_m3, d_val, round(hf_val, 2), round(l_tubo, 2), formato])
                out_features.append(feat)
                
        pr.addFeatures(out_features)
        QgsProject.instance().addMapLayer(out_layer)
        
        progress.setValue(100)
        
        max_flow = max((e['flow'] for e in edges), default=0.0) / 1000.0
        
        # 10. Gerar camada de Saída dos Cavaletes 
        out_layer_pts = QgsVectorLayer(f"Point?crs={crs}", "Cavaletes - Acúmulo de Vazão", "memory")
        pr_pts = out_layer_pts.dataProvider()
        pr_pts.addAttributes([
            QgsField("V", QVariant.Double, len=10, prec=2)
        ])
        out_layer_pts.updateFields()
        
        out_features_pts = []
        for cv, flow_sum in flow_at_cavalete.items():
            if flow_sum > 0:
                feat = QgsFeature()
                feat.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(cv[0], cv[1])))
                feat.setAttributes([round(flow_sum / 1000.0, 2)])
                out_features_pts.append(feat)
                
        pr_pts.addFeatures(out_features_pts)
        QgsProject.instance().addMapLayer(out_layer_pts)
        
        msg = f"Grafo Rígido Concluído! Fluxos parcelares processados com sucesso. Vazão Max: {max_flow:.2f} m³/h"
        self.iface.messageBar().pushMessage("Aqueduct", msg, level=0, duration=10)
        
        # --- ETAPA 2: Algoritmo Genético / Linha Principal ---
        if lyr_linha_principal and lyr_fontes and lyr_linha_principal.featureCount() > 0 and lyr_fontes.featureCount() > 0:
            self.execute_main_line(lyr_linha_principal, lyr_fontes, flow_at_cavalete, inputs, out_layer_pts, out_layer)

    def execute_main_line(self, lyr_lp, lyr_fontes, flow_at_cavalete, inputs, out_layer_pts=None, out_layer_lines=None):
        cap_fonte = inputs['cap_fonte']
        simultaneos = inputs['simultaneos']
        progress = QProgressDialog("Construindo Linha Principal...", "Cancelar", 0, 100, self.iface.mainWindow())
        progress.setWindowTitle("Simulação de Turnos (AG)")
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        all_lines = {}
        line_idx = QgsSpatialIndex()
        global_lid = 0
        
        for f in lyr_lp.getFeatures():
            geom = f.geometry()
            lines = geom.asMultiPolyline() if geom.isMultipart() else [geom.asPolyline()]
            for line_coords in lines:
                line_geom = QgsGeometry.fromPolylineXY(line_coords)
                all_lines[global_lid] = {'geom': line_geom, 'fid': f.id(), 'tipo': 'principal'}
                f_temp = QgsFeature(global_lid)
                f_temp.setGeometry(line_geom)
                line_idx.insertFeature(f_temp)
                global_lid += 1
                
        if not all_lines: return
            
        progress.setValue(10)
        
        points_assigned = {lid: [] for lid in all_lines}
        cv_nodes = []
        cv_keys_ordered = []
        for cv_coords, flow in flow_at_cavalete.items():
            if flow <= 0: continue
            geom = QgsGeometry.fromPointXY(QgsPointXY(cv_coords[0], cv_coords[1]))
            nearest = line_idx.nearestNeighbor(geom, 1)
            if nearest:
                lid = nearest[0]
                points_assigned[lid].append(geom)
                cv_nodes.append((geom, lid, flow))
                cv_keys_ordered.append(cv_coords)
                
        fontes_nodes = []
        for f in lyr_fontes.getFeatures():
            geom = f.geometry()
            nearest = line_idx.nearestNeighbor(geom, 1)
            if nearest:
                lid = nearest[0]
                points_assigned[lid].append(geom)
                fontes_nodes.append((geom, lid))
                
        progress.setValue(20)
        progress.setLabelText("Mapeando interseções em 'T' das tubulações principais...")
        
        # 2b. Injetar todas as geometrias de interseção natural (linhas cruzadas em T)
        # para que o roteador não pule tubos conectados mas mal-recortados.
        lids_list = list(all_lines.keys())
        for i in range(len(lids_list)):
            for j in range(i+1, len(lids_list)):
                g1 = all_lines[lids_list[i]]['geom']
                g2 = all_lines[lids_list[j]]['geom']
                
                # Permite até 20cm de erro no desenho do usuário ao emendar um tubo com o outro
                if g1.distance(g2) < 0.20:
                    try:
                        # Pega a menor distância ligando as duas geometrias
                        sl = g1.shortestLine(g2)
                        if sl and not sl.isEmpty():
                            cl_len = sl.length()
                            # Extrai o ponto médio (ou exatamente o ponto de interseção se tocar)
                            pt = sl.interpolate(cl_len / 2.0).asPoint()
                            pg = QgsGeometry.fromPointXY(pt)
                            points_assigned[lids_list[i]].append(pg)
                            points_assigned[lids_list[j]].append(pg)
                    except Exception:
                        pass
        
        nodes = set()
        edges = []
        coord_map = {}
        
        for lid, line_data in all_lines.items():
            line_geom = line_data['geom']
            notable = points_assigned[lid]
            vs = [(float(line_geom.lineLocatePoint(QgsGeometry.fromPointXY(pt))), pt) for pt in line_geom.asPolyline()]
            for tg in notable:
                da = float(line_geom.lineLocatePoint(tg))
                vs.append((da, line_geom.interpolate(da).asPoint()))
            vs.sort(key=lambda x: x[0])
            
            filtered = []
            last_d = -999.0
            for d, pt in vs:
                if (d - last_d) > 0.05:
                    filtered.append(pt)
                    last_d = d
            
            for i in range(len(filtered) - 1):
                pa = self.round_point(filtered[i])
                pb = self.round_point(filtered[i+1])
                na, nb = (pa[0], pa[1], lid), (pb[0], pb[1], lid)
                nodes.add(na)
                nodes.add(nb)
                if pa not in coord_map: coord_map[pa] = set()
                if pb not in coord_map: coord_map[pb] = set()
                coord_map[pa].add(lid)
                coord_map[pb].add(lid)
                sg = QgsGeometry.fromPolylineXY([QgsPointXY(*pa), QgsPointXY(*pb)])
                edges.append({'u': na, 'v': nb, 'len': sg.length(), 'geom': sg})

        for pt_xy, lids in coord_map.items():
            l_list = list(lids)
            for i in range(len(l_list)):
                for j in range(i+1, len(lids_list)):
                    if j >= len(l_list): break
                    n1, n2 = (pt_xy[0], pt_xy[1], l_list[i]), (pt_xy[0], pt_xy[1], l_list[j])
                    nodes.add(n1)
                    nodes.add(n2)
                    edges.append({'u': n1, 'v': n2, 'len': 0.0, 'geom': None})

        # 3. AMARRAÇÃO FINAL E INFALÍVEL DA TOPOLOGIA CAD
        # Se os nós de tubulações diferentes estiverem a menos de 25 centímetros garantimos sua fusão.
        # Isso varre micro-imperfeições que o QGIS não agrupa automaticamente no LineLocatePoint.
        nodes_list = list(nodes)
        for i in range(len(nodes_list)):
            n1 = nodes_list[i]
            for j in range(i+1, len(nodes_list)):
                n2 = nodes_list[j]
                if n1[2] == n2[2]: continue
                
                dx = n1[0] - n2[0]
                dy = n1[1] - n2[1]
                if dx*dx + dy*dy <= 0.0625:  # Tolera até 25cm (0.25^2 = 0.0625)
                    edges.append({'u': n1, 'v': n2, 'len': 0.0, 'geom': None})

        graph = {n: {} for n in nodes}
        for idx, edge in enumerate(edges):
            u, v, cost = edge['u'], edge['v'], edge['len']
            graph[u][v] = (cost, idx)
            graph[v][u] = (cost, idx)
            
        progress.setValue(30)
        
        cv_exact = []
        for idx, (g, lid, flow) in enumerate(cv_nodes):
            da = float(all_lines[lid]['geom'].lineLocatePoint(g))
            pt = all_lines[lid]['geom'].interpolate(da).asPoint()
            rx, ry = self.round_point(pt)
            best_n, best_d = None, float('inf')
            for (nx, ny, nlid) in nodes:
                if nlid == lid:
                    d = (nx - rx)**2 + (ny - ry)**2
                    if d < best_d:
                        best_d = d
                        best_n = (nx, ny, lid)
            if best_n:
                bx, by = cv_keys_ordered[idx][:2]
                cv_exact.append((best_n[0], best_n[1], lid, flow / 1000.0, bx, by))
            
        ft_exact = []
        for g, lid in fontes_nodes:
            da = float(all_lines[lid]['geom'].lineLocatePoint(g))
            pt = all_lines[lid]['geom'].interpolate(da).asPoint()
            rx, ry = self.round_point(pt)
            best_n, best_d = None, float('inf')
            for (nx, ny, nlid) in nodes:
                if nlid == lid:
                    d = (nx - rx)**2 + (ny - ry)**2
                    if d < best_d:
                        best_d = d
                        best_n = (nx, ny, lid)
            if best_n:
                ft_exact.append(best_n)
            
        if not cv_exact or not ft_exact:
            self.iface.messageBar().pushMessage("Aqueduct AG", "Fontes ou Cavaletes vazios ou não mapeados na LP.", level=1, duration=5)
            return
            
        progress.setValue(40)
        progress.setLabelText("Mapeando distância às Fontes (Dijkstra)...")
        
        import heapq
        ft_paths = {}
        for start_ft in ft_exact:
            src_node = (start_ft[0], start_ft[1], start_ft[2])
            dist = {n: float('inf') for n in nodes}
            prev_edge = {n: None for n in nodes}
            prev_node = {n: None for n in nodes}
            
            if src_node not in dist: continue
            
            dist[src_node] = 0.0
            pq = [(0.0, src_node)]
            while pq:
                d, curr = heapq.heappop(pq)
                if d > dist[curr]: continue
                for nxt, (cost, e_idx) in graph[curr].items():
                    nd = d + cost
                    if nd < dist[nxt]:
                        dist[nxt] = nd
                        prev_edge[nxt] = e_idx
                        prev_node[nxt] = curr
                        heapq.heappush(pq, (nd, nxt))
                        
            ft_paths[src_node] = {}
            for cv in cv_exact:
                cv_n = (cv[0], cv[1], cv[2])
                if dist.get(cv_n, float('inf')) < float('inf'):
                    path = []
                    c = cv_n
                    while prev_edge[c] is not None:
                        path.append(prev_edge[c])
                        c = prev_node[c]
                    ft_paths[src_node][cv_n] = (dist[cv_n], path)
                    
        progress.setValue(50)
        progress.setLabelText("Executando Algoritmo Genético (Turnos)...")
        
        import random
        pop_size = 50
        generations = 50
        
        if simultaneos > len(cv_exact): simultaneos = len(cv_exact)
        
        def evaluate(perm):
            shifts = [perm[i:i+simultaneos] for i in range(0, len(perm), simultaneos)]
            max_edges = {i: 0.0 for i in range(len(edges))}
            
            for shift in shifts:
                shift_edges = {i: 0.0 for i in range(len(edges))}
                avail = {ft: cap_fonte for ft in ft_exact}
                
                shift_cvs = []
                for idx in shift:
                    cv = cv_exact[idx]
                    cv_n = (cv[0], cv[1], cv[2])
                    md = min((ft_paths[(f[0], f[1], f[2])].get(cv_n, (float('inf'), []))[0] for f in ft_exact), default=float('inf'))
                    shift_cvs.append((md, cv_n, cv[3]))
                shift_cvs.sort(key=lambda x: x[0])
                
                for _, cv_n, cv_demand in shift_cvs:
                    demand = cv_demand
                    srcs = []
                    for ft in ft_exact:
                        ft_n = (ft[0], ft[1], ft[2])
                        d, p = ft_paths[ft_n].get(cv_n, (float('inf'), []))
                        if d < float('inf'): srcs.append((d, ft, p))
                    srcs.sort(key=lambda x: x[0])
                    
                    for i, (_, ft, path) in enumerate(srcs):
                        if demand <= 0: break
                        
                        # Se for a ÚLTIMA fonte conectada (ou a única da rede), ela precisa suprir a água remanescente 
                        # independentemente da sua capacidade limite, pois o objetivo do AG é dimensionar a tubulação, 
                        # então o tubo DEVE conhecer essa vazão real do projeto.
                        if i == len(srcs) - 1:
                            take = demand
                        else:
                            take = min(demand, avail[ft])
                            
                        if take > 0:
                            avail[ft] -= take
                            demand -= take
                            for e_idx in path:
                                shift_edges[e_idx] += take
                                
                for k, v in shift_edges.items():
                    if v > max_edges[k]: max_edges[k] = v
                    
            return max_edges, sum(max_edges.values())

        if len(cv_exact) <= simultaneos:
            best_perm = list(range(len(cv_exact)))
            best_max_edges, best_fit = evaluate(best_perm)
        else:
            pop = [random.sample(range(len(cv_exact)), len(cv_exact)) for _ in range(pop_size)]
            best_perm = None
            best_fit = float('inf')
            best_max_edges = None
            
            for gen in range(generations):
                if progress.wasCanceled(): return
                progress.setValue(50 + int(40 * gen / generations))
                
                scored = []
                for p in pop:
                    me, fit = evaluate(p)
                    scored.append((fit, p, me))
                    if fit < best_fit:
                        best_fit = fit
                        best_perm = p
                        best_max_edges = me
                
                scored.sort(key=lambda x: x[0])
                survivors = [x[1] for x in scored[:pop_size//2]]
                
                new_pop = list(survivors)
                while len(new_pop) < pop_size:
                    p1, p2 = random.sample(survivors, 2)
                    size = len(p1)
                    a, b = sorted([random.randint(0, size-1), random.randint(0, size-1)])
                    child = [-1] * size
                    child[a:b+1] = p1[a:b+1]
                    p2_filt = [x for x in p2 if x not in child[a:b+1]]
                    idx = 0
                    for i in range(size):
                        if child[i] == -1:
                            child[i] = p2_filt[idx]
                            idx += 1
                            
                    if random.random() < 0.1:
                        m1, m2 = random.sample(range(size), 2)
                        child[m1], child[m2] = child[m2], child[m1]
                        
                    new_pop.append(child)
                pop = new_pop

        progress.setValue(90)
        progress.setLabelText("Gerando camada da Linha Principal...")
        
        # --- DIMENSIONAMENTO (ETAPA 2) ---
        edges_by_lid = {}
        for e_idx, edge in enumerate(edges):
            if edge['geom'] is not None:
                lid = edge['orig_lid'] if 'orig_lid' in edge else edge['u'][2]
                if lid not in edges_by_lid: edges_by_lid[lid] = []
                l_tubo = edge.get('length', edge.get('len', 0.0))
                edges_by_lid[lid].append({
                    'e_idx': e_idx,
                    'l': l_tubo,
                    'q': best_max_edges[e_idx]
                })
                
        diams = {}
        for k_lid in edges_by_lid:
            d_dict = self.dimensionar_tubo(edges_by_lid[k_lid], inputs['hf_outros'], 0.0)
            diams.update(d_dict)

        # 8.2 Preparar features da Linha Principal
        feats = []
        for e_idx, edge in enumerate(edges):
            if edge['geom'] is not None:
                feat = QgsFeature()
                feat.setGeometry(edge['geom'])
                d_val, hf_val = diams.get(e_idx, (0, 0.0))
                l_tubo = edge.get('length', edge.get('len', 0.0))
                # Adicionando o tipo 'principal' no início para combinar com a camada unificada
                feat.setAttributes(["principal", round(best_max_edges[e_idx], 2), d_val, round(hf_val, 2), round(l_tubo, 2)])
                feats.append(feat)
                
        # Adiciona os trechos diretamente à camada unificada passada como argumento
        if out_layer_lines:
            out_layer_lines.dataProvider().addFeatures(feats)
            out_layer_lines.updateExtents()
            out_layer_lines.triggerRepaint()
        else:
            # Fallback caso seja rodada isoladamente
            crs = lyr_lp.crs().authid()
            out_lp = QgsVectorLayer(f"LineString?crs={crs}", "Linha Principal", "memory")
            pr_lp = out_lp.dataProvider()
            pr_lp.addAttributes([QgsField("tipo", QVariant.String), QgsField("V", QVariant.Double, len=10, prec=2), QgsField("DN", QVariant.Int), QgsField("HF", QVariant.Double, len=10, prec=2), QgsField("L", QVariant.Double, len=10, prec=2)])
            out_lp.updateFields()
            pr_lp.addFeatures(feats)
            QgsProject.instance().addMapLayer(out_lp)
        
        # 7. Adicionar o Turno selecionado na Tabela de Atributos dos Cavaletes
        if out_layer_pts and best_perm:
            idx_turno = out_layer_pts.fields().lookupField("turno")
            if idx_turno == -1:
                out_layer_pts.dataProvider().addAttributes([QgsField("turno", QVariant.Int)])
                out_layer_pts.updateFields()
                idx_turno = out_layer_pts.fields().lookupField("turno")
                
            mapa_turnos = {}
            shifts_finais = [best_perm[i:i+simultaneos] for i in range(0, len(best_perm), simultaneos)]
            for t_idx, shift in enumerate(shifts_finais):
                for cv_idx in shift:
                    cv_data = cv_exact[cv_idx]
                    mapa_turnos[(cv_data[4], cv_data[5])] = t_idx + 1
                    
            out_layer_pts.startEditing()
            for feat in out_layer_pts.getFeatures():
                pt = feat.geometry().asPoint()
                bx, by = self.round_point(pt)
                for (cx, cy), numero_turno in mapa_turnos.items():
                    if (cx-bx)**2 + (cy-by)**2 < 0.0001:
                        out_layer_pts.changeAttributeValue(feat.id(), idx_turno, numero_turno)
                        break
            out_layer_pts.commitChanges()
            
        progress.setValue(100)
        self.iface.messageBar().pushMessage("Aqueduct AG", f"Simulação concluída! Pior cenário minimizado para vazão de {max(best_max_edges.values(), default=0):.2f} m³/h", level=0, duration=10)
