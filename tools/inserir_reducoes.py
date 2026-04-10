import os
from collections import defaultdict

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox,
    QPushButton, QMessageBox, QGroupBox, QLabel, QTableWidget,
    QHeaderView, QHBoxLayout, QWidget, QTableWidgetItem, QTabWidget,
    QScrollArea, QSizePolicy
)
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.core import (
    QgsMapLayerType, QgsProject, QgsWkbTypes, QgsVectorLayer,
    QgsFeature, QgsGeometry, QgsPointXY, QgsField,
    QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsMarkerSymbol,
    QgsSpatialIndex, QgsMapLayerProxyModel
)
from qgis.gui import QgsMapLayerComboBox

from .ferramenta_base import AqueductTool
from .lista_materiais import ProjectBOMManager
from .gerenciar_blocos import BlocoManager, GerenciarBlocosDialog
from .gerenciar_pecas import PecaManager, PecaDialog


# ---------------------------------------------------------------------------
# Tolerância espacial para detecção de proximidade (metros)
TOL = 0.5


def _round_pt(pt):
    return (round(pt.x(), 3), round(pt.y(), 3))


def _build_combo_universal(bloco_manager, peca_manager, match_hint=None):
    """Cria um QComboBox populado com blocos [B] e peças [P]."""
    combo = QComboBox()
    combo.addItem("- Ignorar -", None)
    
    # Adicionar Blocos
    for name in bloco_manager.list_names():
        combo.addItem(f"[B] {name}", ('bloco', name))
        
    # Adicionar Peças
    for name in peca_manager.list_names():
        combo.addItem(f"[P] {name}", ('peca', name))
        
    if match_hint:
        hint = match_hint.lower()
        for i in range(1, combo.count()):
            text = combo.itemText(i).lower()
            # Tenta encontrar correspondência no nome (removendo o prefixo [B] ou [P])
            pure_name = text[4:] if len(text) > 4 else text
            if all(tok in pure_name for tok in hint.split()):
                combo.setCurrentIndex(i)
                break
    return combo


# ---------------------------------------------------------------------------
class InserirReducoesDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.bloco_manager = BlocoManager()
        self.peca_manager = PecaManager()
        self.project_bom = ProjectBOMManager()

        # Dicionários de resultado após detecção
        # Cada categoria é: {chave: {'label': str, 'count': int, 'pts': list[tuple]}}
        self.reducoes_lateral = {}     # variações DN na própria lateral
        self.juncoes_derivacao = {}    # junção lateral → derivação
        self.juncoes_emissor = {}      # junção lateral → emissor
        self.finais_linha = {}         # extremidades finais de lateral

        # Combos de seleção de bloco por chave
        self.combos_lateral = {}
        self.combos_derivacao = {}
        self.combos_emissor = {}
        self.combos_finais = {}

        self.setWindowTitle("Aqueduct - Conexões e Reduções")
        self.resize(700, 600)
        self._setup_ui()

    # ------------------------------------------------------------------
    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Seleção de camadas ---
        grp_layers = QGroupBox("1. Camadas de Entrada")
        form_l = QFormLayout()

        self.cb_topologia = QgsMapLayerComboBox()
        self.cb_topologia.setFilters(QgsMapLayerProxyModel.LineLayer)
        self._auto_set_layer(self.cb_topologia, ['topologia', 'acumulo', 'vazão', 'vazao', 'rede'])
        form_l.addRow("Camada de Topologia (linhas):", self.cb_topologia)

        self.cb_emissores = QgsMapLayerComboBox()
        self.cb_emissores.setFilters(QgsMapLayerProxyModel.PointLayer)
        self._auto_set_layer(self.cb_emissores, ['emissor', 'gotejador', 'aspersor', 'microaspersor'])
        form_l.addRow("Camada de Emissores (pontos):", self.cb_emissores)

        grp_layers.setLayout(form_l)
        layout.addWidget(grp_layers)

        # --- Gerenciamento de Materiais ---
        grp_materiais = QGroupBox("Gerenciamento de Materiais")
        lay_mat = QHBoxLayout()
        
        btn_pecas = QPushButton("📦  Gerenciar Peças")
        btn_pecas.clicked.connect(self._on_manage_pecas)
        lay_mat.addWidget(btn_pecas)
        
        btn_blocos = QPushButton("🏗️  Gerenciar Blocos")
        btn_blocos.clicked.connect(self._on_manage_blocos)
        lay_mat.addWidget(btn_blocos)
        
        grp_materiais.setLayout(lay_mat)
        layout.addWidget(grp_materiais)

        # --- Botão detectar ---
        btn_detectar = QPushButton("🔍  Detectar Conexões e Reduções")
        btn_detectar.setMinimumHeight(36)
        btn_detectar.clicked.connect(self._detectar)
        layout.addWidget(btn_detectar)

        # --- Abas de resultado ---
        tabs = QTabWidget()
        
        # Aba 1 – Reduções em Laterais
        self.tab_lat = QWidget()
        self.lay_lat = QVBoxLayout(self.tab_lat)
        self.lay_lat.addWidget(QLabel(
            "Pontos onde a mesma linha lateral muda de DN (redução telescópica).\n"
            "Atribua uma peça de redução ou um bloco para cada par de diâmetros."
        ))
        self.table_lat = self._make_table(["Transição DN", "Ocorrências", "Item de Redução (Peça ou Bloco)"])
        self.lay_lat.addWidget(self.table_lat)
        tabs.addTab(self.tab_lat, "Reduções em Laterais")

        # Aba 2 – Junturas Lateral → Derivação
        self.tab_deriv = QWidget()
        self.lay_deriv = QVBoxLayout(self.tab_deriv)
        self.lay_deriv.addWidget(QLabel(
            "Pontos onde o início de uma lateral toca em uma derivação.\n"
            "Atribua uma peça ou bloco para cada combinação de diâmetros lateral × derivação."
        ))
        self.table_deriv = self._make_table(["Transição (Lat→Deriv)", "Ocorrências", "Item de Conexão (Peça ou Bloco)"])
        self.lay_deriv.addWidget(self.table_deriv)
        tabs.addTab(self.tab_deriv, "Junturas Lat→Derivação")

        # Aba 3 – Junturas Lateral → Emissor
        self.tab_emiss = QWidget()
        self.lay_emiss = QVBoxLayout(self.tab_emiss)
        self.lay_emiss.addWidget(QLabel(
            "Pontos onde o final de uma lateral alcança um emissor.\n"
            "Atribua uma peça ou bloco para cada DN de lateral que alimenta um emissor."
        ))
        self.table_emiss = self._make_table(["Conexão", "Qtd", "Peça / Bloco"])
        self.lay_emiss.addWidget(self.table_emiss)
        tabs.addTab(self.tab_emiss, "Laterais → Emissores")

        # Aba 4 – Finais de Linha (Pontas Cegas ou Com aspersor)
        self.tab_finais = QWidget()
        self.lay_finais = QVBoxLayout(self.tab_finais)
        self.lay_finais.addWidget(QLabel(
            "Pontos onde a linha lateral termina (inclusive se houver aspersor).\n"
            "Atribua uma peça de final de linha (ex: Plug, Válvula de limpeza)."
        ))
        self.table_finais = self._make_table(["DN do Cano", "Qtd", "Peça / Bloco"])
        self.lay_finais.addWidget(self.table_finais)
        tabs.addTab(self.tab_finais, "Finais de Linha")

        layout.addWidget(tabs)

        # --- Botões de ação ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_plotar = QPushButton("📍  Plotar Pontos")
        self.btn_plotar.setEnabled(False)
        self.btn_plotar.clicked.connect(self._plotar)
        btn_row.addWidget(self.btn_plotar)

        self.btn_orcar = QPushButton("📄  Adicionar ao Orçamento")
        self.btn_orcar.setEnabled(False)
        self.btn_orcar.clicked.connect(self._orcar)
        btn_row.addWidget(self.btn_orcar)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    @staticmethod
    def _make_table(headers):
        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(headers)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        return tbl

    def _auto_set_layer(self, combo, palavras):
        """Tenta pré-selecionar a camada pelo nome."""
        for layer in QgsProject.instance().mapLayers().values():
            if not hasattr(layer, 'geometryType'):
                continue
            nome = layer.name().lower()
            for kw in palavras:
                if kw in nome:
                    combo.setLayer(layer)
                    return

    # ------------------------------------------------------------------
    def _detectar(self):
        lyr_topo = self.cb_topologia.currentLayer()
        lyr_emiss = self.cb_emissores.currentLayer()

        if not lyr_topo:
            QMessageBox.warning(self, "Aviso", "Selecione a camada de topologia.")
            return

        idx_tipo = lyr_topo.fields().indexOf("tipo")
        idx_dn   = lyr_topo.fields().indexOf("DN")
        if idx_tipo == -1 or idx_dn == -1:
            QMessageBox.warning(self, "Aviso",
                "A camada de topologia precisa ter os campos 'tipo' e 'DN'.\n"
                "Execute primeiro a ferramenta de Acúmulo de Vazão.")
            return

        # ----------------------------------------------------------------
        # Passo 1 – indexar todas as feições por ponto extremo
        # ----------------------------------------------------------------
        # endpoint_map: (x,y) -> list of {'tipo', 'dn', 'fid', 'extremo': 'inicio'|'fim'}
        endpoint_map = defaultdict(list)
        # segmentos por LID para buscas posteriores
        segmentos = []  # {'geom', 'tipo', 'dn'}

        for feat in lyr_topo.getFeatures():
            tipo_val = feat[idx_tipo]
            dn_val   = feat[idx_dn]
            if not tipo_val or dn_val is None:
                continue
            try:
                dn_val = int(dn_val)
            except (ValueError, TypeError):
                continue

            geom = feat.geometry()
            if geom.isMultipart():
                partes = geom.asMultiPolyline()
            else:
                partes = [geom.asPolyline()]

            for parte in partes:
                if len(parte) < 2:
                    continue
                pt_ini = _round_pt(parte[0])
                pt_fim = _round_pt(parte[-1])
                info = {'tipo': tipo_val, 'dn': dn_val}
                endpoint_map[pt_ini].append({**info, 'extremo': 'inicio'})
                endpoint_map[pt_fim].append({**info, 'extremo': 'fim'})
                segmentos.append({'geom': geom, 'tipo': tipo_val, 'dn': dn_val})

        # ----------------------------------------------------------------
        # Caso 1 – Reduções telescópicas dentro da própria lateral
        # ----------------------------------------------------------------
        reducoes_lat = defaultdict(lambda: {'count': 0, 'pts': []})

        for pt, conns in endpoint_map.items():
            # Só laterais
            laterais = [c for c in conns if c['tipo'] == 'lateral']
            if len(laterais) != 2:
                continue
            dn_a, dn_b = laterais[0]['dn'], laterais[1]['dn']
            if dn_a == dn_b:
                continue
            maior, menor = max(dn_a, dn_b), min(dn_a, dn_b)
            chave = f"DN {maior}→{menor} mm"
            reducoes_lat[chave]['count'] += 1
            reducoes_lat[chave]['pts'].append(pt)
            reducoes_lat[chave]['dn_maior'] = maior
            reducoes_lat[chave]['dn_menor'] = menor

        self.reducoes_lateral = dict(reducoes_lat)

        # ----------------------------------------------------------------
        # Caso 2 – Juntura lateral → derivação
        # A lateral inicia (extremo 'inicio') em um ponto que pertence
        # ao corpo (não extremo) de uma derivação, OU compartilha extremo.
        # ----------------------------------------------------------------
        # Índice espacial das feições de derivação
        deriv_idx = QgsSpatialIndex()
        deriv_feats = {}  # fid → {'geom', 'dn'}
        for feat in lyr_topo.getFeatures():
            if feat[idx_tipo] != 'derivacao':
                continue
            try:
                dn_d = int(feat[idx_dn])
            except (ValueError, TypeError):
                continue
            deriv_feats[feat.id()] = {'geom': feat.geometry(), 'dn': dn_d}
            tmp = QgsFeature(feat.id())
            tmp.setGeometry(feat.geometry())
            deriv_idx.insertFeature(tmp)

        juncoes_d = defaultdict(lambda: {'count': 0, 'pts': []})

        for pt, conns in endpoint_map.items():
            # O ponto deve ter pelo menos um início de lateral
            inicios_lat = [c for c in conns if c['tipo'] == 'lateral' and c['extremo'] == 'inicio']
            if not inicios_lat:
                continue

            # Verificar se o ponto pertence a alguma derivação (extremo ou interior)
            pt_xy = QgsPointXY(pt[0], pt[1])
            pt_geom = QgsGeometry.fromPointXY(pt_xy)
            candidatos = deriv_idx.nearestNeighbor(pt_geom, 5)

            for fid in candidatos:
                d_info = deriv_feats.get(fid)
                if not d_info:
                    continue
                dist = pt_geom.distance(d_info['geom'])
                if dist > TOL:
                    continue
                # Conexão confirmada
                dn_deriv = d_info['dn']
                for lat_info in inicios_lat:
                    dn_lat = lat_info['dn']
                    chave = f"Lat {dn_lat}mm → Deriv {dn_deriv}mm"
                    juncoes_d[chave]['count'] += 1
                    juncoes_d[chave]['pts'].append(pt)
                    juncoes_d[chave]['dn_lat'] = dn_lat
                    juncoes_d[chave]['dn_deriv'] = dn_deriv
                break  # basta a derivação mais próxima

        self.juncoes_derivacao = dict(juncoes_d)

        # ----------------------------------------------------------------
        # Caso 3 – Juntura lateral → emissor
        # O ponto final de uma lateral está próximo a um emissor.
        # ----------------------------------------------------------------
        juncoes_e = defaultdict(lambda: {'count': 0, 'pts': []})

        if lyr_emiss:
            emiss_pts = []
            for feat in lyr_emiss.getFeatures():
                geom = feat.geometry()
                if geom.isEmpty():
                    continue
                emiss_pts.append(_round_pt(geom.asPoint()))

            emiss_set = set(emiss_pts)

            # Índice espacial dos emissores para busca por proximidade
            emiss_idx = QgsSpatialIndex()
            emiss_feat_list = {}
            for feat in lyr_emiss.getFeatures():
                geom = feat.geometry()
                if geom.isEmpty():
                    continue
                tmp = QgsFeature(feat.id())
                tmp.setGeometry(geom)
                emiss_idx.insertFeature(tmp)
                emiss_feat_list[feat.id()] = geom

            for pt, conns in endpoint_map.items():
                # Extremo de lateral (pode ser início ou fim)
                fins_lat = [c for c in conns if c['tipo'] == 'lateral']
                if not fins_lat:
                    continue

                pt_xy = QgsPointXY(pt[0], pt[1])
                pt_geom = QgsGeometry.fromPointXY(pt_xy)
                candidatos = emiss_idx.nearestNeighbor(pt_geom, 3)

                for fid in candidatos:
                    e_geom = emiss_feat_list.get(fid)
                    if not e_geom:
                        continue
                    dist = pt_geom.distance(e_geom)
                    if dist > TOL:
                        continue
                    # Conexão confirmada
                    for lat_info in fins_lat:
                        dn_lat = lat_info['dn']
                        chave = f"Emissor ← Lat {dn_lat}mm"
                        juncoes_e[chave]['count'] += 1
                        juncoes_e[chave]['pts'].append(pt)
                        juncoes_e[chave]['dn_lat'] = dn_lat
                    break

        self.juncoes_emissor = dict(juncoes_e)

        # ----------------------------------------------------------------
        # Caso 4 – Finais de Linha Lateral
        # Um ponto onde uma lateral termina ('fim') e nada começa ('inicio')
        # ----------------------------------------------------------------
        finais_l = defaultdict(lambda: {'count': 0, 'pts': []})
        for pt, conns in endpoint_map.items():
            lats_fim = [c for c in conns if c['tipo'] == 'lateral' and c['extremo'] == 'fim']
            lats_ini = [c for c in conns if c['tipo'] == 'lateral' and c['extremo'] == 'inicio']
            
            # Se termina uma lateral e não começa nenhuma outra lateral (ponta da linha)
            if lats_fim and not lats_ini:
                dn_final = lats_fim[0]['dn']
                chave = f"Final de Linha {dn_final}mm"
                finais_l[chave]['count'] += 1
                finais_l[chave]['pts'].append(pt)
                finais_l[chave]['dn'] = dn_final
        
        self.finais_linha = dict(finais_l)

        # ----------------------------------------------------------------
        # Preencher as tabelas
        # ----------------------------------------------------------------
        # Preencher as tabelas usando o combo universal
        self._preencher_tabela(
            self.table_lat, self.reducoes_lateral, self.combos_lateral,
            hint_fn=lambda k, d: f"reduc {d.get('dn_maior','')} {d.get('dn_menor','')}"
        )
        self._preencher_tabela(
            self.table_deriv, self.juncoes_derivacao, self.combos_derivacao,
            hint_fn=lambda k, d: f"deriv {d.get('dn_lat','')} {d.get('dn_deriv','')}"
        )
        self._preencher_tabela(
            self.table_emiss, self.juncoes_emissor, self.combos_emissor,
            hint_fn=lambda k, d: f"emissor {d.get('dn_lat','')}"
        )
        self._preencher_tabela(
            self.table_finais, self.finais_linha, self.combos_finais,
            hint_fn=lambda k, d: f"fim {d.get('dn','')}"
        )

        total = (len(self.reducoes_lateral) + len(self.juncoes_derivacao) +
                 len(self.juncoes_emissor) + len(self.finais_linha))

        if total == 0:
            QMessageBox.information(self, "Resultado",
                "Nenhuma conexão ou redução detectada.\n"
                "Verifique se as camadas de topologia e emissores estão corretas.")
        else:
            self.btn_plotar.setEnabled(True)
            self.btn_orcar.setEnabled(True)
            QMessageBox.information(self, "Detecção Concluída",
                f"Encontrado:\n"
                f"  • {len(self.reducoes_lateral)} tipo(s) de redução em laterais\n"
                f"  • {len(self.juncoes_derivacao)} tipo(s) de juntura lateral→derivação\n"
                f"  • {len(self.juncoes_emissor)} tipo(s) de juntura lateral→emissor")

    # ------------------------------------------------------------------
    def _preencher_tabela(self, table, dados, combos_dict, hint_fn=None):
        table.setRowCount(0)
        combos_dict.clear()

        for i, (chave, data) in enumerate(dados.items()):
            table.insertRow(i)
            table.setItem(i, 0, QTableWidgetItem(chave))
            table.setItem(i, 1, QTableWidgetItem(f"{data['count']} ocorr."))
            hint = hint_fn(chave, data) if hint_fn else None
            
            combo = _build_combo_universal(self.bloco_manager, self.peca_manager, match_hint=hint)
            
            table.setCellWidget(i, 2, combo)
            combos_dict[chave] = combo

    # ------------------------------------------------------------------
    def _on_manage_pecas(self):
        dlg = PecaDialog(self.peca_manager, self)
        dlg.exec_()
        self.peca_manager.load()
        self._refresh_all_combos()

    def _on_manage_blocos(self):
        dlg = GerenciarBlocosDialog(self)
        dlg.exec_()
        self.bloco_manager.load()
        self._refresh_all_combos()

    def _refresh_all_combos(self):
        """Atualiza todos os QComboBoxes nas tabelas com os dados carregados."""
        def _update_table_combos(table, combos_dict):
            for row in range(table.rowCount()):
                chave = table.item(row, 0).text()
                combo_antigo = combos_dict.get(chave)
                if not combo_antigo: continue
                
                # Salva a seleção atual
                sel_data = combo_antigo.currentData()
                
                # Cria novo combo com dados atualizados
                novo_combo = _build_combo_universal(self.bloco_manager, self.peca_manager)
                
                # Tenta restaurar a seleção
                if sel_data:
                    idx = novo_combo.findData(sel_data)
                    if idx >= 0:
                        novo_combo.setCurrentIndex(idx)
                
                table.setCellWidget(row, 2, novo_combo)
                combos_dict[chave] = novo_combo

        _update_table_combos(self.table_lat,  self.combos_lateral)
        _update_table_combos(self.table_deriv, self.combos_derivacao)
        _update_table_combos(self.table_emiss, self.combos_emissor)
        _update_table_combos(self.table_finais, self.combos_finais)

    # ------------------------------------------------------------------
    def _coletar_resultados(self):
        """Retorna lista de {label, tipo, nome, pts} para plotagem e orçamento.
        tipo pode ser 'peca' (peça unitária) ou 'bloco'."""
        resultados = []

        def _coleta(dados_dict, combos_dict, categoria):
            for chave, data in dados_dict.items():
                combo = combos_dict.get(chave)
                sel = combo.currentData() if combo else None  # (tipo_str, nome) ou None
                tipo_sel, nome_sel = sel if sel else (None, None)
                resultados.append({
                    'label': f"[{categoria}] {chave}",
                    'tipo_sel': tipo_sel,   # 'peca' ou 'bloco'
                    'nome_sel': nome_sel,
                    'pts': data['pts']
                })

        _coleta(self.reducoes_lateral,  self.combos_lateral,  "Redução Lateral")
        _coleta(self.juncoes_derivacao, self.combos_derivacao, "Juntura→Derivação")
        _coleta(self.juncoes_emissor,   self.combos_emissor,   "Juntura→Emissor")
        _coleta(self.finais_linha,      self.combos_finais,    "Final de Linha")
        return resultados

    # ------------------------------------------------------------------
    def _plotar(self):
        resultados = self._coletar_resultados()
        if not resultados:
            QMessageBox.warning(self, "Aviso", "Nenhum dado para plotar.")
            return

        crs = (self.cb_topologia.currentLayer().crs().authid()
               if self.cb_topologia.currentLayer()
               else QgsProject.instance().crs().authid())

        out = QgsVectorLayer(f"Point?crs={crs}", "Conexões e Reduções", "memory")
        pr = out.dataProvider()
        pr.addAttributes([
            QgsField("Categoria", QVariant.String),
            QgsField("Transicao", QVariant.String),
            QgsField("Bloco", QVariant.String),
        ])
        out.updateFields()

        feats = []
        for r in resultados:
            nome_exib = r['nome_sel'] or "Não definido"
            categoria = r['label'].split("]")[0].lstrip("[")
            for pt in r['pts']:
                f = QgsFeature()
                f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(pt[0], pt[1])))
                f.setAttributes([categoria, r['label'], nome_exib])
                feats.append(f)

        if not feats:
            QMessageBox.information(self, "Aviso", "Nenhum ponto gerado.")
            return

        pr.addFeatures(feats)

        # Simbologia categorizada por Categoria
        categorias_unicas = list({r['label'].split("]")[0].lstrip("[") for r in resultados})
        cat_renders = []
        for i, cat in enumerate(categorias_unicas):
            hue = int((i * 120) % 360)
            sym = QgsMarkerSymbol.createSimple({
                'name': 'circle', 'size': '4',
                'outline_style': 'solid', 'outline_width': '0.5'
            })
            sym.setColor(QColor.fromHsv(hue, 200, 220))
            cat_renders.append(QgsRendererCategory(cat, sym, cat))

        out.setRenderer(QgsCategorizedSymbolRenderer("Categoria", cat_renders))
        QgsProject.instance().addMapLayer(out)

        QMessageBox.information(self, "Sucesso",
            f"Camada 'Conexões e Reduções' criada com {len(feats)} pontos.")

    # ------------------------------------------------------------------
    def _orcar(self):
        resultados = self._coletar_resultados()
        if not resultados:
            QMessageBox.warning(self, "Aviso", "Nenhum dado para orçar.")
            return

        if not self.project_bom.filepath:
            QMessageBox.warning(self, "Aviso", "Salve o projeto do QGIS primeiro.")
            return

        adicionados = 0
        ignorados = 0
        for r in resultados:
            qtd = len(r['pts'])
            if r['tipo_sel'] == 'peca' and r['nome_sel']:
                # Peça unitária: busca preço no catálogo e lança como item avulso
                peca_data = self.peca_manager.get(r['nome_sel'])
                custo  = peca_data.get('custo', 0) if peca_data else 0
                lucro  = peca_data.get('lucro', 0) if peca_data else 0
                preco  = custo * (1 + lucro / 100)
                self.project_bom.add_item(r['nome_sel'], preco, qtd, save=False)
                adicionados += qtd
            elif r['tipo_sel'] == 'bloco' and r['nome_sel']:
                self.project_bom.add_bloco_project(r['nome_sel'], qtd, save=False)
                adicionados += qtd
            else:
                ignorados += qtd

        if adicionados > 0:
            self.project_bom.save()
            msg = f"{adicionados} ocorrências adicionadas ao orçamento."
            if ignorados:
                msg += f"\n({ignorados} sem item definido foram ignoradas.)"
            QMessageBox.information(self, "Sucesso", msg)
        else:
            QMessageBox.warning(self, "Aviso",
                "Nenhuma peça adicionada. Defina ao menos um bloco nas tabelas acima.")


# ---------------------------------------------------------------------------
class InserirReducoesTool(AqueductTool):

    def initGui(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_contabilizar.svg')
        if not os.path.exists(icon_path):
            icon_path = ""

        self.action = QAction(
            QIcon(icon_path),
            'Conexões e Reduções',
            self.iface.mainWindow()
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)

        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = InserirReducoesDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
