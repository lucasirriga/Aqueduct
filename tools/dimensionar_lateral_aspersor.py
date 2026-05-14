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
from qgis.gui import QgsMapLayerComboBox
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
class DimensionarLateralAspersorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimensionar Lateral de Aspersores")
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
        grp_camadas = QGroupBox("Camadas de Entrada")
        f_cam = QFormLayout()

        self.cb_emissores = QgsMapLayerComboBox()
        self.cb_emissores.setFilters(QgsMapLayerProxyModel.PointLayer)
        f_cam.addRow("Aspersores (Pontos):", self.cb_emissores)

        self.cb_tubulacao = QgsMapLayerComboBox()
        self.cb_tubulacao.setFilters(QgsMapLayerProxyModel.LineLayer)
        f_cam.addRow("Linha Lateral (Linha):", self.cb_tubulacao)

        grp_camadas.setLayout(f_cam)
        lay.addWidget(grp_camadas)

        # Grupo Parâmetros
        grp_hid = QGroupBox("Parâmetros Hidráulicos")
        f_hid = QFormLayout()

        self.spin_vazao_emissor = QDoubleSpinBox()
        self.spin_vazao_emissor.setRange(0.1, 100000.0)
        self.spin_vazao_emissor.setValue(500.0)
        self.spin_vazao_emissor.setDecimals(2)
        self.spin_vazao_emissor.setSuffix(" L/h")
        self.spin_vazao_emissor.setToolTip("Vazão uniforme para todos os aspersores.")
        f_hid.addRow("Vazão por Aspersor:", self.spin_vazao_emissor)

        self.edit_diametros = QLineEdit("50, 75, 100")
        self.edit_diametros.setToolTip("Diâmetros comerciais permitidos, separados por vírgula (mm).")
        f_hid.addRow("Diâmetros Permitidos (mm):", self.edit_diametros)

        self.spin_hf_max = QDoubleSpinBox()
        self.spin_hf_max.setRange(0.1, 500.0)
        self.spin_hf_max.setValue(5.0)
        self.spin_hf_max.setDecimals(2)
        self.spin_hf_max.setSuffix(" mca")
        f_hid.addRow("Perda de Carga Máxima:", self.spin_hf_max)

        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setRange(0.01, 20.0)
        self.spin_tol.setValue(1.0)
        self.spin_tol.setDecimals(2)
        self.spin_tol.setSuffix(" m")
        self.spin_tol.setToolTip(
            "Distância máxima para considerar que um aspersor está conectado à linha."
        )
        f_hid.addRow("Tolerância de Conexão:", self.spin_tol)

        grp_hid.setLayout(f_hid)
        lay.addWidget(grp_hid)

        lbl_info = QLabel(
            "ℹ️  A <b>ponta final</b> da linha lateral é determinada pela orientação do vetor "
            "(último vértice da linha). O fluxo é calculado do início (0) para o fim."
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

        P = QgsWkbTypes.PointGeometry
        L = QgsWkbTypes.LineGeometry

        em = buscar(['emissor', 'gotejador', 'aspersor'], P)
        if em:
            self.cb_emissores.setLayer(em)

        tu = buscar(['lateral', 'linha'], L)
        if tu:
            self.cb_tubulacao.setLayer(tu)

    def get_inputs(self):
        return {
            'lyr_emissores': self.cb_emissores.currentLayer(),
            'vazao_emissor': self.spin_vazao_emissor.value(),
            'lyr_tubulacao': self.cb_tubulacao.currentLayer(),
            'diametros': self._parse_diams(self.edit_diametros.text()),
            'hf_max': self.spin_hf_max.value(),
            'tolerancia': self.spin_tol.value(),
        }

    def _parse_diams(self, text):
        try:
            parts = text.replace(';', ',').split(',')
            vals = sorted(set(int(p.strip()) for p in parts if p.strip().isdigit()))
            return vals if vals else [50, 75, 100]
        except:
            return [50, 75, 100]

    def set_log(self, text):
        self.log_output.setPlainText(text)
        self.tabs.setCurrentIndex(1)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
SETTINGS_KEY = "Aqueduct/DimensionarLateralAspersor"

class DimensionarLateralAspersorTool(AqueductTool):
    """
    Dimensiona uma linha lateral de aspersores selecionada em trechos com base nos
    pontos (aspersores) que a tocam, calculando vazões cumulativas e diâmetros 
    por Hazen-Williams.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_dimensionar_tubulacao.svg')
        if not os.path.exists(icon_path):
            icon_path = ""

        # Botão ▶ Calcular
        self.action = QAction(QIcon(icon_path), '▶ Dimensionar Lateral Aspersores', self.iface.mainWindow())
        self.action.setToolTip(
            "Calcular Dimensionamento de Lateral\n"
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

        self.action_config = QAction(QIcon(icon_config_path), 'Configurar Lateral Aspersores...', self.iface.mainWindow())
        self.action_config.setToolTip("⚙ Configurar Lateral Aspersores\nAbre o diálogo para ajustar e salvar os parâmetros.")
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
        lyr_em = inp['lyr_emissores']
        lyr_tu = inp['lyr_tubulacao']
        s.setValue(f"{SETTINGS_KEY}/lyr_emissores", lyr_em.id() if lyr_em else "")
        s.setValue(f"{SETTINGS_KEY}/lyr_tubulacao",  lyr_tu.id() if lyr_tu else "")
        s.setValue(f"{SETTINGS_KEY}/vazao_emissor",  inp['vazao_emissor'])
        s.setValue(f"{SETTINGS_KEY}/diametros",      ",".join(str(d) for d in inp['diametros']))
        s.setValue(f"{SETTINGS_KEY}/hf_max",         inp['hf_max'])
        s.setValue(f"{SETTINGS_KEY}/tolerancia",     inp['tolerancia'])

    def _carregar_params(self):
        s = QgsSettings()
        layers = QgsProject.instance().mapLayers()

        def get_layer(key):
            lid = s.value(f"{SETTINGS_KEY}/{key}", "")
            return layers.get(lid)

        lyr_em = get_layer("lyr_emissores")
        lyr_tu = get_layer("lyr_tubulacao")

        if not lyr_em or not lyr_tu:
            return None 

        diams_str = s.value(f"{SETTINGS_KEY}/diametros", "50,75,100")
        try:
            diams = sorted(set(int(x.strip()) for x in diams_str.split(",") if x.strip().isdigit()))
        except:
            diams = [50, 75, 100]

        return {
            'lyr_emissores': lyr_em,
            'lyr_tubulacao': lyr_tu,
            'vazao_emissor': float(s.value(f"{SETTINGS_KEY}/vazao_emissor", 500.0)),
            'diametros': diams,
            'hf_max':    float(s.value(f"{SETTINGS_KEY}/hf_max",    5.0)),
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
            print(f"Aqueduct LatAsp: {msg}")
            log_lines.append(msg)

        try:
            self._executar(inp, log)
        except Exception as e:
            log(f"❌ ERRO: {e}")
            self.iface.messageBar().pushMessage("Aqueduct – Erro", str(e), level=2, duration=8)
            print("\n".join(log_lines))

    def run_config(self):
        dlg = DimensionarLateralAspersorDialog(self.iface.mainWindow())

        params_salvos = self._carregar_params()
        if params_salvos:
            dlg.cb_emissores.setLayer(params_salvos['lyr_emissores'])
            dlg.cb_tubulacao.setLayer(params_salvos['lyr_tubulacao'])
            dlg.spin_vazao_emissor.setValue(params_salvos['vazao_emissor'])
            dlg.edit_diametros.setText(", ".join(str(d) for d in params_salvos['diametros']))
            dlg.spin_hf_max.setValue(params_salvos['hf_max'])
            dlg.spin_tol.setValue(params_salvos['tolerancia'])

        if not dlg.exec_():
            return

        inp = dlg.get_inputs()
        self._salvar_params(inp)

        log_lines = []
        def log(msg):
            print(f"Aqueduct LatAsp: {msg}")
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
        lyr_em  = inp['lyr_emissores']
        lyr_tu  = inp['lyr_tubulacao']
        vz_em   = inp['vazao_emissor'] 
        diams   = inp['diametros']
        hf_max  = inp['hf_max']
        tol     = inp['tolerancia']

        erros = []
        if not lyr_em:  erros.append("Camada de aspersores não selecionada.")
        if not lyr_tu:  erros.append("Camada de linha lateral não selecionada.")
        if not diams:   erros.append("Nenhum diâmetro válido informado.")
        if erros:
            raise Exception("\n".join(erros))

        selecionadas = list(lyr_tu.selectedFeatures())
        if not selecionadas:
            raise Exception("Selecione pelo menos 1 feição na camada de linha lateral.")

        log("\n📐 Etapa 2 – Identificando aspersores conectados...")

        # Construir índice espacial e buscar emissores próximos à linha
        em_idx = QgsSpatialIndex()
        em_feats = {}
        for feat_em in lyr_em.getFeatures():
            em_idx.insertFeature(feat_em)
            em_feats[feat_em.id()] = feat_em

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
            log(f"\n--- Linha lateral (ID: {feat_tu.id()}) ---")
            log(f"   Comprimento: {comprimento_total:.2f}m")
            log(f"   Ponta final (último vértice): ({pt_final_vetor.x():.3f}, {pt_final_vetor.y():.3f})")

            bb = geom_tu.boundingBox()
            bb.grow(tol)
            candidatos = em_idx.intersects(bb)

            emissores_conectados = []

            for fid in candidatos:
                feat_em = em_feats[fid]
                geom_em = feat_em.geometry()
                d = geom_em.distance(geom_tu)
                if d <= tol:
                    dist_along = geom_tu.lineLocatePoint(geom_em)
                    emissores_conectados.append({
                        'feat_id': fid,
                        'dist_along': dist_along,
                        'vazao_m3h': vz_em / 1000.0
                    })

            if not emissores_conectados:
                log(f"   ⚠️ Nenhum aspersor conectado. Mantendo a linha inteira sem dimensionamento novo.")
                # Se quiser ignorar, a gente poderia só nao deletar e nao criar novos trechos. 
                # Vamos apenas remover da lista de ids a deletar pra não apagar a linha original.
                ids_para_deletar.remove(feat_tu.id())
                continue

            log(f"   Total de aspersores conectados: {len(emissores_conectados)}")

            pontos_conexao = {}
            for em in emissores_conectados:
                chave = round(em['dist_along'], 2)
                pontos_conexao[chave] = pontos_conexao.get(chave, 0.0) + em['vazao_m3h']

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
                "Nenhum trecho novo gerado. Verifique se os aspersores estão conectados às linhas.",
                level=1, duration=5
            )
            return

        log("\n📦 Etapa 5 – Atualizando a camada...")
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
            f"Dimensionamento concluído! {len(selecionadas)} linhas processadas gerando {len(todos_feats_novos)} trechos. HF Total Somada = {hf_sum_total:.4f} mca.",
            level=0, duration=8
        )
