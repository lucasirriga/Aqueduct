import os
import math
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QDialogButtonBox, QMessageBox, QGroupBox,
    QFormLayout, QTabWidget, QWidget, QLineEdit, QPlainTextEdit,
    QScrollArea
)
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsProject, QgsPointXY,
    QgsWkbTypes, QgsField, QgsSpatialIndex, QgsMapLayerProxyModel,
    QgsSettings
)

from .ferramenta_base import AqueductTool

# ---------------------------------------------------------------------------
# Fórmula Hazen-Williams
# ---------------------------------------------------------------------------
def calcular_hf_hw(q_m3h, d_mm, l_m, C=140.0):
    """Retorna a perda de carga (mca) por Hazen-Williams."""
    if q_m3h <= 0 or d_mm <= 0 or l_m <= 0:
        return 0.0
    q_m3s = q_m3h / 3600.0
    D = d_mm / 1000.0
    J = 10.67 * ((q_m3s / C) ** 1.852) / (D ** 4.87)
    return J * l_m

# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------
class DimensionarLinhaPrincipalDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimensionar Linha Principal")
        self.resize(520, 500)

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ---- Aba Principal ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        conteudo = QWidget()
        lay = QVBoxLayout(conteudo)

        # Grupo Camadas
        grp_camadas = QGroupBox("Camadas e Atributos")
        f_cam = QFormLayout()

        self.cb_tubulacao = QgsMapLayerComboBox()
        self.cb_tubulacao.setFilters(QgsMapLayerProxyModel.LineLayer)
        f_cam.addRow("Camada de Linhas:", self.cb_tubulacao)

        self.cb_campo_vazao = QgsFieldComboBox()
        self.cb_campo_vazao.setFilters(QgsFieldProxyModel.Numeric)
        f_cam.addRow("Campo de Vazão (m³/h):", self.cb_campo_vazao)
        
        # Conecta a mudança da camada para atualizar os campos
        self.cb_tubulacao.layerChanged.connect(self.cb_campo_vazao.setLayer)
        if self.cb_tubulacao.currentLayer():
            self.cb_campo_vazao.setLayer(self.cb_tubulacao.currentLayer())

        grp_camadas.setLayout(f_cam)
        lay.addWidget(grp_camadas)

        # Grupo Parâmetros
        grp_hid = QGroupBox("Parâmetros Hidráulicos")
        f_hid = QFormLayout()

        self.edit_diametros = QLineEdit("50, 75, 100, 150")
        self.edit_diametros.setToolTip("Diâmetros comerciais permitidos, separados por vírgula (mm).")
        f_hid.addRow("Diâmetros Permitidos (mm):", self.edit_diametros)

        self.spin_hf_max = QDoubleSpinBox()
        self.spin_hf_max.setRange(0.1, 500.0)
        self.spin_hf_max.setValue(10.0)
        self.spin_hf_max.setDecimals(2)
        self.spin_hf_max.setSuffix(" mca")
        f_hid.addRow("Perda de Carga Máxima:", self.spin_hf_max)

        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setRange(0.01, 20.0)
        self.spin_tol.setValue(1.0)
        self.spin_tol.setDecimals(2)
        self.spin_tol.setSuffix(" m")
        self.spin_tol.setToolTip(
            "Distância máxima para considerar que uma linha secundária está conectada à principal."
        )
        f_hid.addRow("Tolerância de Conexão:", self.spin_tol)

        grp_hid.setLayout(f_hid)
        lay.addWidget(grp_hid)

        lbl_info = QLabel(
            "ℹ️  Apenas linhas secundárias que tocam com seu <b>ponto inicial</b> serão "
            "contabilizadas. A ponta final da linha principal é determinada pelo último vértice."
        )
        lbl_info.setWordWrap(True)
        lbl_info.setStyleSheet("color: #555; font-size: 8pt; padding: 4px;")
        lay.addWidget(lbl_info)

        lay.addStretch()
        scroll.setWidget(conteudo)
        self.tabs.addTab(scroll, "Principal")

        # ---- Aba Mensagens ----
        tab_msg = QWidget()
        lay_msg = QVBoxLayout(tab_msg)
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Resultados e detalhes do cálculo aparecerão aqui...")
        lay_msg.addWidget(self.log_output)
        self.tabs.addTab(tab_msg, "Mensagens")

        # Botões
        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._auto_selecionar()

    def _auto_selecionar(self):
        def buscar(kws, geom):
            for l in QgsProject.instance().mapLayers().values():
                if hasattr(l, 'geometryType') and l.geometryType() == geom:
                    nome = l.name().lower()
                    if any(k in nome for k in kws):
                        return l
            return None

        L = QgsWkbTypes.LineGeometry

        tu = buscar(['principal', 'adutora', 'mestra', 'tubulacao', 'linha'], L)
        if tu:
            self.cb_tubulacao.setLayer(tu)
            self.cb_campo_vazao.setLayer(tu)
            idx = tu.fields().indexOf("V")
            if idx >= 0:
                self.cb_campo_vazao.setField("V")

    def get_inputs(self):
        return {
            'lyr_tubulacao': self.cb_tubulacao.currentLayer(),
            'campo_vazao': self.cb_campo_vazao.currentField(),
            'diametros': self._parse_diams(self.edit_diametros.text()),
            'hf_max': self.spin_hf_max.value(),
            'tolerancia': self.spin_tol.value(),
        }

    def _parse_diams(self, text):
        try:
            parts = text.replace(';', ',').split(',')
            vals = sorted(set(int(p.strip()) for p in parts if p.strip().isdigit()))
            return vals if vals else [50, 75, 100, 150]
        except:
            return [50, 75, 100, 150]

    def set_log(self, text):
        self.log_output.setPlainText(text)
        self.tabs.setCurrentIndex(1)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
SETTINGS_KEY = "Aqueduct/DimensionarLinhaPrincipal"

# O import realçado acima não funciona no escopo de módulo de algumas versões
# QgsFieldProxyModel é necessário apenas para filtros avançados, usaremos de forma mais simples
from qgis.core import QgsFieldProxyModel

class DimensionarLinhaPrincipalTool(AqueductTool):
    """
    Dimensiona uma linha principal considerando as linhas secundárias que saem dela
    (tocando a linha principal com o vértice 0).
    Extrai a vazão das linhas secundárias de um campo especificado.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_dimensionar_tubulacao.svg')
        if not os.path.exists(icon_path):
            icon_path = ""

        # Botão ▶ Calcular
        self.action = QAction(QIcon(icon_path), '▶ Dimensionar Linha Principal', self.iface.mainWindow())
        self.action.setToolTip(
            "Calcular Dimensionamento de Linha Principal\n"
            "Usa os parâmetros salvos e roda diretamente, sem abrir o diálogo.\n"
            "(Use ⚙ Configurar para alterar os parâmetros)"
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

        # Botão ⚙ Configurar
        icon_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_info.svg')
        if not os.path.exists(icon_config_path):
            icon_config_path = ""

        self.action_config = QAction(QIcon(icon_config_path), 'Configurar Linha Principal...', self.iface.mainWindow())
        self.action_config.setToolTip("⚙ Configurar Linha Principal\nAbre o diálogo para ajustar e salvar os parâmetros.")
        self.action_config.triggered.connect(self.run_config)
        self.iface.addPluginToMenu('&Aqueduct', self.action_config)
        if self.toolbar:
            self.toolbar.addAction(self.action_config)

    def unload(self):
        self.iface.removePluginMenu('&Aqueduct', self.action)
        self.iface.removePluginMenu('&Aqueduct', self.action_config)
        if self.toolbar:
            self.toolbar.removeAction(self.action)
            self.toolbar.removeAction(self.action_config)

    def _salvar_params(self, inp):
        s = QgsSettings()
        lyr_tu = inp['lyr_tubulacao']
        s.setValue(f"{SETTINGS_KEY}/lyr_tubulacao",  lyr_tu.id() if lyr_tu else "")
        s.setValue(f"{SETTINGS_KEY}/campo_vazao",    inp['campo_vazao'])
        s.setValue(f"{SETTINGS_KEY}/diametros",      ",".join(str(d) for d in inp['diametros']))
        s.setValue(f"{SETTINGS_KEY}/hf_max",         inp['hf_max'])
        s.setValue(f"{SETTINGS_KEY}/tolerancia",     inp['tolerancia'])

    def _carregar_params(self):
        s = QgsSettings()
        layers = QgsProject.instance().mapLayers()

        def get_layer(key):
            lid = s.value(f"{SETTINGS_KEY}/{key}", "")
            return layers.get(lid)

        lyr_tu = get_layer("lyr_tubulacao")

        if not lyr_tu:
            return None 

        diams_str = s.value(f"{SETTINGS_KEY}/diametros", "50,75,100,150")
        try:
            diams = sorted(set(int(x.strip()) for x in diams_str.split(",") if x.strip().isdigit()))
        except:
            diams = [50, 75, 100, 150]

        return {
            'lyr_tubulacao': lyr_tu,
            'campo_vazao': s.value(f"{SETTINGS_KEY}/campo_vazao", "V"),
            'diametros': diams,
            'hf_max':    float(s.value(f"{SETTINGS_KEY}/hf_max",    10.0)),
            'tolerancia':float(s.value(f"{SETTINGS_KEY}/tolerancia",1.0)),
        }

    def run(self):
        inp = self._carregar_params()
        if inp is None:
            self.iface.messageBar().pushMessage(
                "Aqueduct",
                "Nenhuma configuração salva. Abrindo diálogo de configuração...",
                level=1, duration=3
            )
            self.run_config()
            return

        log_lines = []
        def log(msg):
            print(f"Aqueduct LinhaPrin: {msg}")
            log_lines.append(msg)

        try:
            self._executar(inp, log)
        except Exception as e:
            log(f"❌ ERRO: {e}")
            self.iface.messageBar().pushMessage("Aqueduct – Erro", str(e), level=2, duration=8)
            print("\n".join(log_lines))

    def run_config(self):
        dlg = DimensionarLinhaPrincipalDialog(self.iface.mainWindow())

        params_salvos = self._carregar_params()
        if params_salvos:
            dlg.cb_tubulacao.setLayer(params_salvos['lyr_tubulacao'])
            if params_salvos['lyr_tubulacao']:
                dlg.cb_campo_vazao.setLayer(params_salvos['lyr_tubulacao'])
            dlg.cb_campo_vazao.setField(params_salvos['campo_vazao'])
            dlg.edit_diametros.setText(", ".join(str(d) for d in params_salvos['diametros']))
            dlg.spin_hf_max.setValue(params_salvos['hf_max'])
            dlg.spin_tol.setValue(params_salvos['tolerancia'])

        if not dlg.exec_():
            return

        inp = dlg.get_inputs()
        self._salvar_params(inp)

        log_lines = []
        def log(msg):
            print(f"Aqueduct LinhaPrin: {msg}")
            log_lines.append(msg)

        try:
            self._executar(inp, log)
        except Exception as e:
            log(f"❌ ERRO CRÍTICO: {e}")
            QMessageBox.critical(self.iface.mainWindow(), "Aqueduct – Erro", str(e))
        finally:
            dlg.set_log("\n".join(log_lines))
            dlg.exec_()

    def _executar(self, inp, log):
        lyr_tu   = inp['lyr_tubulacao']
        campo_v  = inp['campo_vazao'] 
        diams    = inp['diametros']
        hf_max   = inp['hf_max']
        tol      = inp['tolerancia']

        erros = []
        if not lyr_tu:   erros.append("Camada de linhas não selecionada.")
        if not campo_v:  erros.append("Campo de vazão não selecionado.")
        if not diams:    erros.append("Nenhum diâmetro válido informado.")
        if erros:
            raise Exception("\n".join(erros))

        idx_vazao = lyr_tu.fields().indexOf(campo_v)
        if idx_vazao < 0:
            raise Exception(f"Campo '{campo_v}' não encontrado na camada de linhas.")

        selecionadas = list(lyr_tu.selectedFeatures())
        if not selecionadas:
            raise Exception("Selecione pelo menos 1 feição para ser a linha principal dimensionada.")
        ids_selecionados = [f.id() for f in selecionadas]

        log("\n📐 Etapa 1 – Identificando inícios de linhas conectadas...")

        # Coletar pontos iniciais de todas as linhas (exceto as que estão selecionadas para serem a principal neste loop)
        sec_pontos_iniciais = []
        for feat_sec in lyr_tu.getFeatures():
            if feat_sec.id() in ids_selecionados:
                continue

            geom_sec = feat_sec.geometry()
            if not geom_sec or geom_sec.isEmpty():
                continue
            
            # Garantir que obtemos o primeiro vértice da linha
            if geom_sec.isMultipart():
                pl = geom_sec.asMultiPolyline()[0]
            else:
                pl = geom_sec.asPolyline()
                
            pt_ini = QgsPointXY(pl[0])
            geom_pt = QgsGeometry.fromPointXY(pt_ini)
            
            vazao = feat_sec.attribute(idx_vazao)
            try:
                vazao = float(vazao) if vazao is not None else 0.0
            except:
                vazao = 0.0
                
            if vazao <= 0:
                continue

            sec_pontos_iniciais.append({
                'fid': feat_sec.id(),
                'geom': geom_pt,
                'vazao_m3h': vazao
            })

        log(f"   Foram encontrados {len(sec_pontos_iniciais)} inícios de linhas secundárias válidos com vazão > 0.")

        pr = lyr_tu.dataProvider()
        campos_existentes = [f.name() for f in lyr_tu.fields()]

        campos_novos = []
        if "DN" not in campos_existentes:
            campos_novos.append(QgsField("DN", QVariant.Int))
        if "V" not in campos_existentes:
            campos_novos.append(QgsField("V", QVariant.Double, len=10, prec=4))
        if "L" not in campos_existentes:
            campos_novos.append(QgsField("L", QVariant.Double, len=10, prec=2))
        if "HF" not in campos_existentes:
            campos_novos.append(QgsField("HF", QVariant.Double, len=10, prec=4))

        if campos_novos:
            pr.addAttributes(campos_novos)
            lyr_tu.updateFields()

        idx_dn = lyr_tu.fields().indexOf("DN")
        idx_v  = lyr_tu.fields().indexOf("V")
        idx_l  = lyr_tu.fields().indexOf("L")
        idx_hf = lyr_tu.fields().indexOf("HF")

        todos_feats_novos = []
        ids_para_deletar = []
        hf_sum_total = 0.0

        for feat_tu in selecionadas:
            ids_para_deletar.append(feat_tu.id())
            geom_tu = feat_tu.geometry()

            if geom_tu.isMultipart():
                geom_tu = QgsGeometry.fromPolylineXY(geom_tu.asMultiPolyline()[0])

            comprimento_total = geom_tu.length()
            polyline = geom_tu.asPolyline()

            pt_final_vetor = QgsPointXY(polyline[-1])
            log(f"\n--- Linha principal (ID: {feat_tu.id()}) ---")
            log(f"   Comprimento: {comprimento_total:.2f}m")
            
            # Encontrar secundárias que conectam a esta linha
            ramais_conectados = []
            
            for sec in sec_pontos_iniciais:
                d = sec['geom'].distance(geom_tu)
                if d <= tol:
                    dist_along = geom_tu.lineLocatePoint(sec['geom'])
                    ramais_conectados.append({
                        'fid': sec['fid'],
                        'dist_along': dist_along,
                        'vazao_m3h': sec['vazao_m3h']
                    })

            if not ramais_conectados:
                log(f"   ⚠️ Nenhuma linha secundária conecta-se a esta linha principal. Ignorando.")
                ids_para_deletar.remove(feat_tu.id())
                continue

            log(f"   Ramificações conectadas: {len(ramais_conectados)}")

            # Agrupar vazões por nó (dist_along)
            pontos_conexao = {}
            for ramal in ramais_conectados:
                chave = round(ramal['dist_along'], 2)
                pontos_conexao[chave] = pontos_conexao.get(chave, 0.0) + ramal['vazao_m3h']

            limites = sorted(set(list(pontos_conexao.keys()) + [0.0, comprimento_total]))

            vazao_acum = 0.0
            trechos = []

            for i in range(len(limites) - 1, 0, -1):
                d_fim = limites[i]
                d_ini = limites[i - 1]

                chave = round(d_fim, 2)
                if chave in pontos_conexao:
                    vazao_acum += pontos_conexao[chave]

                comprimento_trecho = d_fim - d_ini
                if comprimento_trecho < 0.01:
                    continue

                pt_ini = geom_tu.interpolate(d_ini).asPoint()
                pt_fim = geom_tu.interpolate(d_fim).asPoint()
                geom_trecho = QgsGeometry.fromPolylineXY([QgsPointXY(pt_ini), QgsPointXY(pt_fim)])

                trechos.append({
                    'geom': geom_trecho,
                    'L': comprimento_trecho,
                    'V': vazao_acum,
                    'DN': diams[0],
                    'HF': 0.0,
                })

            if not trechos:
                ids_para_deletar.remove(feat_tu.id())
                continue

            # Dimensionamento (Hazen-Williams)
            def hf_total_lista(lista):
                return sum(calcular_hf_hw(t['V'], t['DN'], t['L']) for t in lista)

            hf_ini = hf_total_lista(trechos)

            if hf_ini > hf_max and len(diams) > 1:
                idx_por_vazao = sorted(range(len(trechos)), key=lambda i: trechos[i]['V'], reverse=True)
                concluido = False
                for diam_superior in diams[1:]:
                    if concluido:
                        break
                    for t_idx in idx_por_vazao:
                        if trechos[t_idx]['DN'] >= diam_superior:
                            continue
                        trechos[t_idx]['DN'] = diam_superior
                        if hf_total_lista(trechos) <= hf_max:
                            concluido = True
                            break

            hf_sum = 0.0
            for t in trechos:
                t['HF'] = calcular_hf_hw(t['V'], t['DN'], t['L'])
                hf_sum += t['HF']
                
                f = QgsFeature(lyr_tu.fields())
                f.setGeometry(t['geom'])
                f.setAttributes(feat_tu.attributes())
                f.setAttribute(idx_dn, t['DN'])
                f.setAttribute(idx_v,  round(t['V'], 4))
                f.setAttribute(idx_l,  round(t['L'], 2))
                f.setAttribute(idx_hf, round(t['HF'], 4))
                todos_feats_novos.append(f)
                
            hf_sum_total += hf_sum
            log(f"   ✅ Linha processada. {len(trechos)} trechos. HF: {hf_sum:.4f} mca")

        if not todos_feats_novos:
            log("\nNenhum trecho novo gerado para as linhas selecionadas.")
            self.iface.messageBar().pushMessage(
                "Aqueduct",
                "Nenhum trecho novo gerado. Verifique as conexões das linhas.",
                level=1, duration=5
            )
            return

        log("\n📦 Etapa final – Atualizando a camada principal...")
        lyr_tu.startEditing()
        lyr_tu.deleteFeatures(ids_para_deletar)
        lyr_tu.addFeatures(todos_feats_novos)
        lyr_tu.commitChanges()
        lyr_tu.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(lyr_tu.id())

        log(f"\n✅ Concluído!")
        log(f"   Foram criados {len(todos_feats_novos)} novos trechos no total.")

        self.iface.messageBar().pushMessage(
            "Aqueduct",
            f"Dimensionamento concluído! {len(selecionadas)} linhas principais processadas gerando {len(todos_feats_novos)} trechos. HF Total Somada = {hf_sum_total:.4f} mca.",
            level=0, duration=8
        )
