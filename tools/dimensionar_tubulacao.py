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
class DimensionarTubulacaoDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimensionar Tubulação por Trechos")
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
        f_cam.addRow("Emissores (Pontos):", self.cb_emissores)

        self.cb_mangueiras = QgsMapLayerComboBox()
        self.cb_mangueiras.setFilters(QgsMapLayerProxyModel.LineLayer)
        f_cam.addRow("Mangueiras (Linhas):", self.cb_mangueiras)

        self.cb_tubulacao = QgsMapLayerComboBox()
        self.cb_tubulacao.setFilters(QgsMapLayerProxyModel.LineLayer)
        f_cam.addRow("Tubulação Principal (Linha):", self.cb_tubulacao)

        grp_camadas.setLayout(f_cam)
        lay.addWidget(grp_camadas)

        # Grupo Parâmetros
        grp_hid = QGroupBox("Parâmetros Hidráulicos")
        f_hid = QFormLayout()

        self.spin_vazao_emissor = QDoubleSpinBox()
        self.spin_vazao_emissor.setRange(0.1, 100000.0)
        self.spin_vazao_emissor.setValue(60.0)
        self.spin_vazao_emissor.setDecimals(2)
        self.spin_vazao_emissor.setSuffix(" L/h")
        self.spin_vazao_emissor.setToolTip("Vazão uniforme para todos os emissores.")
        f_hid.addRow("Vazão por Emissor:", self.spin_vazao_emissor)

        self.edit_diametros = QLineEdit("50, 75")
        self.edit_diametros.setToolTip("Diâmetros comerciais permitidos, separados por vírgula (mm).")
        f_hid.addRow("Diâmetros Permitidos (mm):", self.edit_diametros)

        self.spin_hf_max = QDoubleSpinBox()
        self.spin_hf_max.setRange(0.1, 500.0)
        self.spin_hf_max.setValue(2.0)
        self.spin_hf_max.setDecimals(2)
        self.spin_hf_max.setSuffix(" mca")
        f_hid.addRow("Perda de Carga Máxima:", self.spin_hf_max)

        self.spin_tol = QDoubleSpinBox()
        self.spin_tol.setRange(0.01, 20.0)
        self.spin_tol.setValue(0.5)
        self.spin_tol.setDecimals(2)
        self.spin_tol.setSuffix(" m")
        self.spin_tol.setToolTip(
            "Distância máxima para considerar que dois elementos estão conectados.\n"
            "Mangueiras dentro desta distância da tubulação serão detectadas."
        )
        f_hid.addRow("Tolerância de Conexão:", self.spin_tol)

        grp_hid.setLayout(f_hid)
        lay.addWidget(grp_hid)

        lbl_info = QLabel(
            "ℹ️  A <b>ponta final</b> da tubulação é determinada pela orientação do vetor "
            "(último vértice da linha). Use a ferramenta <i>Inverter Linha</i> se necessário."
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

        ma = buscar(['mangueira', 'lateral'], L)
        if ma:
            self.cb_mangueiras.setLayer(ma)

        tu = buscar(['tubu', 'principal', 'adutora'], L)
        if tu:
            self.cb_tubulacao.setLayer(tu)

    def get_inputs(self):
        return {
            'lyr_emissores': self.cb_emissores.currentLayer(),
            'vazao_emissor': self.spin_vazao_emissor.value(),
            'lyr_mangueiras': self.cb_mangueiras.currentLayer(),
            'lyr_tubulacao': self.cb_tubulacao.currentLayer(),
            'diametros': self._parse_diams(self.edit_diametros.text()),
            'hf_max': self.spin_hf_max.value(),
            'tolerancia': self.spin_tol.value(),
        }

    def _parse_diams(self, text):
        try:
            parts = text.replace(';', ',').split(',')
            vals = sorted(set(int(p.strip()) for p in parts if p.strip().isdigit()))
            return vals if vals else [50, 75]
        except:
            return [50, 75]

    def set_log(self, text):
        self.log_output.setPlainText(text)
        self.tabs.setCurrentIndex(1)


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
SETTINGS_KEY = "Aqueduct/DimensionarTubulacao"

class DimensionarTubulacaoTool(AqueductTool):
    """
    Dimensiona uma tubulação selecionada em trechos com base nas mangueiras
    que a tocam, calculando vazões cumulativas e diâmetros por Hazen-Williams.
    A ponta final da tubulação é o ÚLTIMO vértice do vetor (orientação da linha).
    Mangueiras no mesmo ponto de conexão têm suas vazões somadas.

    Dois botões na toolbar:
      ▶  Calcular  – usa os parâmetros salvos e roda sem abrir diálogo.
      ⚙  Configurar – abre o diálogo para ajustar e salvar parâmetros.
    """

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_dimensionar_tubulacao.svg')
        if not os.path.exists(icon_path):
            icon_path = ""

        # Botão ▶ Calcular (execução silenciosa)
        self.action = QAction(QIcon(icon_path), '▶ Calcular Dimensionamento', self.iface.mainWindow())
        self.action.setToolTip(
            "Calcular Dimensionamento\n"
            "Usa os parâmetros salvos e roda diretamente, sem abrir o diálogo.\n"
            "(Use ⚙ Configurar para alterar os parâmetros)"
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

        # Botão ⚙ Configurar (com ícone, sem texto na toolbar)
        icon_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_info.svg')
        if not os.path.exists(icon_config_path):
            icon_config_path = ""

        self.action_config = QAction(QIcon(icon_config_path), 'Configurar Dimensionamento...', self.iface.mainWindow())
        self.action_config.setToolTip("⚙ Configurar Dimensionamento\nAbre o diálogo para ajustar e salvar os parâmetros.")
        self.action_config.triggered.connect(self.run_config)
        self.iface.addPluginToMenu('&Aqueduct', self.action_config)
        if self.toolbar:
            self.toolbar.addAction(self.action_config)

    def unload(self):
        """Remove ambas as actions ao desinstalar o plugin."""
        self.iface.removePluginMenu('&Aqueduct', self.action)
        self.iface.removePluginMenu('&Aqueduct', self.action_config)
        if self.toolbar:
            self.toolbar.removeAction(self.action)
            self.toolbar.removeAction(self.action_config)

    # ------------------------------------------------------------------
    # Persistência de parâmetros com QgsSettings
    # ------------------------------------------------------------------
    def _salvar_params(self, inp):
        """Salva os parâmetros em QgsSettings (persiste entre sessões do QGIS)."""
        s = QgsSettings()
        lyr_em = inp['lyr_emissores']
        lyr_ma = inp['lyr_mangueiras']
        lyr_tu = inp['lyr_tubulacao']
        s.setValue(f"{SETTINGS_KEY}/lyr_emissores", lyr_em.id() if lyr_em else "")
        s.setValue(f"{SETTINGS_KEY}/lyr_mangueiras", lyr_ma.id() if lyr_ma else "")
        s.setValue(f"{SETTINGS_KEY}/lyr_tubulacao",  lyr_tu.id() if lyr_tu else "")
        s.setValue(f"{SETTINGS_KEY}/vazao_emissor",  inp['vazao_emissor'])
        s.setValue(f"{SETTINGS_KEY}/diametros",      ",".join(str(d) for d in inp['diametros']))
        s.setValue(f"{SETTINGS_KEY}/hf_max",         inp['hf_max'])
        s.setValue(f"{SETTINGS_KEY}/tolerancia",     inp['tolerancia'])

    def _carregar_params(self):
        """Carrega parâmetros salvos do QgsSettings. Retorna None se não houver."""
        s = QgsSettings()
        layers = QgsProject.instance().mapLayers()

        def get_layer(key):
            lid = s.value(f"{SETTINGS_KEY}/{key}", "")
            return layers.get(lid)

        lyr_em = get_layer("lyr_emissores")
        lyr_ma = get_layer("lyr_mangueiras")
        lyr_tu = get_layer("lyr_tubulacao")

        if not lyr_em or not lyr_ma or not lyr_tu:
            return None  # forçar abertura do diálogo

        diams_str = s.value(f"{SETTINGS_KEY}/diametros", "50,75")
        try:
            diams = sorted(set(int(x.strip()) for x in diams_str.split(",") if x.strip().isdigit()))
        except:
            diams = [50, 75]

        return {
            'lyr_emissores': lyr_em,
            'lyr_mangueiras': lyr_ma,
            'lyr_tubulacao': lyr_tu,
            'vazao_emissor': float(s.value(f"{SETTINGS_KEY}/vazao_emissor", 60.0)),
            'diametros': diams,
            'hf_max':    float(s.value(f"{SETTINGS_KEY}/hf_max",    2.0)),
            'tolerancia':float(s.value(f"{SETTINGS_KEY}/tolerancia",0.5)),
        }

    # ------------------------------------------------------------------
    # Execução silenciosa (botão ▶)
    # ------------------------------------------------------------------
    def run(self):
        """Roda com os parâmetros salvos. Se não houver configuração prévia, abre o diálogo."""
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
            print(f"Aqueduct DimTub: {msg}")
            log_lines.append(msg)

        try:
            self._executar(inp, log)
        except Exception as e:
            log(f"❌ ERRO: {e}")
            self.iface.messageBar().pushMessage("Aqueduct – Erro", str(e), level=2, duration=8)
            # Exibir log completo no console
            print("\n".join(log_lines))

    # ------------------------------------------------------------------
    # Configurar parâmetros e salvar (botão ⚙)
    # ------------------------------------------------------------------
    def run_config(self):
        """Abre o diálogo de configuração, salva os parâmetros e executa."""
        dlg = DimensionarTubulacaoDialog(self.iface.mainWindow())

        # Pré-popular com valores salvos
        params_salvos = self._carregar_params()
        if params_salvos:
            dlg.cb_emissores.setLayer(params_salvos['lyr_emissores'])
            dlg.cb_mangueiras.setLayer(params_salvos['lyr_mangueiras'])
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
            print(f"Aqueduct DimTub: {msg}")
            log_lines.append(msg)

        try:
            self._executar(inp, log)
        except Exception as e:
            log(f"❌ ERRO CRÍTICO: {e}")
            QMessageBox.critical(self.iface.mainWindow(), "Aqueduct – Erro", str(e))
        finally:
            dlg.set_log("\n".join(log_lines))
            dlg.exec_()


    # ------------------------------------------------------------------
    def _executar(self, inp, log):
        lyr_em  = inp['lyr_emissores']
        lyr_ma  = inp['lyr_mangueiras']
        lyr_tu  = inp['lyr_tubulacao']
        vz_em   = inp['vazao_emissor']   # L/h por emissor (fixo)
        diams   = inp['diametros']
        hf_max  = inp['hf_max']
        tol     = inp['tolerancia']

        # ---- Etapa 1: Validações ----
        erros = []
        if not lyr_em:  erros.append("Camada de emissores não selecionada.")
        if not lyr_ma:  erros.append("Camada de mangueiras não selecionada.")
        if not lyr_tu:  erros.append("Camada de tubulação não selecionada.")
        if not diams:   erros.append("Nenhum diâmetro válido informado.")
        if erros:
            raise Exception("\n".join(erros))

        selecionadas = list(lyr_tu.selectedFeatures())
        if len(selecionadas) != 1:
            raise Exception(
                f"Selecione EXATAMENTE 1 feição na camada de tubulação. "
                f"Atualmente: {len(selecionadas)} selecionadas."
            )

        feat_tu = selecionadas[0]
        geom_tu = feat_tu.geometry()

        # Normalizar: se multipart, pegar a primeira parte
        if geom_tu.isMultipart():
            geom_tu = QgsGeometry.fromPolylineXY(geom_tu.asMultiPolyline()[0])

        comprimento_total = geom_tu.length()
        polyline = geom_tu.asPolyline()

        # Ponta final = ÚLTIMO VÉRTICE (orientação do vetor)
        pt_final_vetor = QgsPointXY(polyline[-1])
        log(f"✅ Tubulação selecionada. Comprimento: {comprimento_total:.2f}m")
        log(f"   Ponta final (último vértice): ({pt_final_vetor.x():.3f}, {pt_final_vetor.y():.3f})")
        log(f"   Diâmetros permitidos: {diams}")
        log(f"   Vazão por emissor: {vz_em} L/h")
        log(f"   HF máxima: {hf_max} mca | Tolerância: {tol}m")

        # ---- Etapa 2: Detectar mangueiras que tocam a tubulação ----
        log("\n📐 Etapa 2 – Identificando mangueiras conectadas...")

        mangueiras_conectadas = []

        for feat_ma in lyr_ma.getFeatures():
            geom_ma = feat_ma.geometry()
            if geom_ma.isMultipart():
                pl_ma = geom_ma.asMultiPolyline()[0]
            else:
                pl_ma = geom_ma.asPolyline()

            # Verificar ponta inicial e final da mangueira
            pontas = [QgsGeometry.fromPointXY(QgsPointXY(pl_ma[0])),
                      QgsGeometry.fromPointXY(QgsPointXY(pl_ma[-1]))]

            ponta_conexao = None
            dist_min = 9999.0

            for ponta in pontas:
                d = ponta.distance(geom_tu)
                if d <= tol and d < dist_min:
                    dist_min = d
                    dist_along = geom_tu.lineLocatePoint(ponta)
                    pt_proj = geom_tu.interpolate(dist_along).asPoint()
                    ponta_conexao = (pt_proj, dist_along)

            if ponta_conexao is not None:
                mangueiras_conectadas.append({
                    'feat_id': feat_ma.id(),
                    'geom': geom_ma,
                    'ponto_conexao': ponta_conexao[0],
                    'dist_along': ponta_conexao[1],
                    'vazao_m3h': 0.0,
                })

        if not mangueiras_conectadas:
            raise Exception(
                "Nenhuma mangueira encontrada conectada à tubulação. "
                "Verifique a tolerância de conexão."
            )

        log(f"   Mangueiras conectadas: {len(mangueiras_conectadas)}")

        # ---- Etapa 3: Somar emissores por mangueira ----
        log("\n💧 Etapa 3 – Somando emissores por mangueira...")

        # Construir índice espacial dos emissores
        em_idx = QgsSpatialIndex()
        em_feats = {}
        for feat_em in lyr_em.getFeatures():
            em_idx.insertFeature(feat_em)
            em_feats[feat_em.id()] = feat_em

        total_emissores = 0
        for ma in mangueiras_conectadas:
            geom_ma = ma['geom']
            bb = geom_ma.boundingBox()
            bb.grow(tol)
            candidatos = em_idx.intersects(bb)

            count = 0
            for fid in candidatos:
                geom_em = em_feats[fid].geometry()
                if geom_em.distance(geom_ma) <= tol:
                    count += 1

            # Vazão em m³/h (fixa para todos os emissores)
            ma['vazao_m3h'] = (count * vz_em) / 1000.0
            total_emissores += count
            log(f"   Mangueira @dist={ma['dist_along']:.2f}m: {count} emissores → {ma['vazao_m3h']:.4f} m³/h")

        log(f"   Total de emissores: {total_emissores}")

        # ---- Etapa 4: Agrupar pontos de conexão e acumular vazões ----
        # Mangueiras no mesmo ponto (mesmo dist_along dentro da tolerância) têm vazões somadas.
        log("\n✂️  Etapa 4 – Agrupando pontos de conexão e acumulando vazões...")

        # Agrupar por dist_along (arredondado a 2 casas para evitar duplicatas por float)
        pontos_conexao = {}  # dist_along_key -> vazao_somada
        for ma in mangueiras_conectadas:
            chave = round(ma['dist_along'], 2)
            pontos_conexao[chave] = pontos_conexao.get(chave, 0.0) + ma['vazao_m3h']

        # A ponta final do vetor (dist = comprimento_total) é a origem do acúmulo
        # Ordenar do final (comprimento_total) para o início (0), ou seja, do maior dist para o menor
        pontos_ord = sorted(pontos_conexao.keys(), reverse=True)

        log(f"   Pontos de conexão únicos: {len(pontos_ord)}")

        # Definir os limites dos trechos incluindo início (0) e fim (comprimento_total) da linha
        limites = sorted(set(list(pontos_conexao.keys()) + [0.0, comprimento_total]))

        # Construir trechos do final para o início com acúmulo de vazão
        # Trecho mais distal (último) = menor vazão; trecho mais proximal (primeiro) = maior vazão
        vazao_acum = 0.0
        trechos = []

        for i in range(len(limites) - 1, 0, -1):
            d_fim = limites[i]
            d_ini = limites[i - 1]

            # Soma a vazão das mangueiras que conectam neste ponto final do trecho
            chave = round(d_fim, 2)
            if chave in pontos_conexao:
                vazao_acum += pontos_conexao[chave]

            comprimento_trecho = d_fim - d_ini
            if comprimento_trecho < 0.01:
                continue

            # Geometria do trecho (interpolação sobre a linha original)
            pt_ini = geom_tu.interpolate(d_ini).asPoint()
            pt_fim = geom_tu.interpolate(d_fim).asPoint()
            geom_trecho = QgsGeometry.fromPolylineXY([QgsPointXY(pt_ini), QgsPointXY(pt_fim)])

            trechos.append({
                'geom': geom_trecho,
                'L': comprimento_trecho,
                'V': vazao_acum,    # m³/h cumulativo
                'DN': diams[0],     # menor diâmetro por padrão
                'HF': 0.0,
                'dist_ini': d_ini,
                'dist_fim': d_fim,
            })

        if not trechos:
            raise Exception("Nenhum trecho gerado. Verifique se há mangueiras conectadas.")

        log(f"   Trechos gerados: {len(trechos)}")
        for i, t in enumerate(trechos):
            log(f"   Trecho {i+1}: dist [{t['dist_fim']:.2f}→{t['dist_ini']:.2f}]m | "
                f"L={t['L']:.2f}m | V={t['V']:.4f} m³/h")

        # ---- Etapa 5: Dimensionamento greedy por Hazen-Williams ----
        log("\n⚙️  Etapa 5 – Dimensionando diâmetros (Hazen-Williams, C=140)...")

        def hf_total_lista(lista):
            return sum(calcular_hf_hw(t['V'], t['DN'], t['L']) for t in lista)

        # Inicializar todos com o menor diâmetro
        for t in trechos:
            t['DN'] = diams[0]

        hf_ini = hf_total_lista(trechos)
        log(f"   HF inicial (todos DN={diams[0]}mm): {hf_ini:.4f} mca")

        if hf_ini <= hf_max:
            log(f"   ✅ HF já dentro do limite com DN{diams[0]}mm. Nenhum upgrade necessário.")
        elif len(diams) == 1:
            log(f"   ⚠️  Apenas um diâmetro disponível. HF excede o limite.")
        else:
            # Ordenar por vazão decrescente: trecho de maior vazão é o mais crítico
            idx_por_vazao = sorted(range(len(trechos)), key=lambda i: trechos[i]['V'], reverse=True)

            concluido = False
            for diam_superior in diams[1:]:
                if concluido:
                    break
                log(f"\n   Tentando upgrade para DN{diam_superior}mm...")
                for t_idx in idx_por_vazao:
                    if trechos[t_idx]['DN'] >= diam_superior:
                        continue  # já neste nível ou superior

                    # Diâmetro maior SEMPRE reduz HF — nunca reverter
                    trechos[t_idx]['DN'] = diam_superior
                    hf_novo = hf_total_lista(trechos)

                    log(f"   ✔ Trecho {t_idx+1} (V={trechos[t_idx]['V']:.4f}m³/h) "
                        f"→ DN{diam_superior}mm | HF acumulado={hf_novo:.4f}mca")

                    if hf_novo <= hf_max:
                        log(f"   ✅ Limite atingido após upgrade do trecho {t_idx+1}.")
                        concluido = True
                        break

            hf_final = hf_total_lista(trechos)
            if hf_final > hf_max:
                log(f"   ⚠️  Mesmo com todos os trechos em DN{diams[-1]}mm, "
                    f"HF={hf_final:.4f}mca ainda excede {hf_max}mca. "
                    f"Considere usar diâmetros maiores.")

        # Calcular HF final por trecho
        hf_sum = 0.0
        for t in trechos:
            t['HF'] = calcular_hf_hw(t['V'], t['DN'], t['L'])
            hf_sum += t['HF']

        log(f"\n   HF total final: {hf_sum:.4f} mca (limite: {hf_max} mca)")
        log("   Configuração final:")
        for i, t in enumerate(trechos):
            log(f"   Trecho {i+1}: DN={t['DN']}mm | V={t['V']:.4f}m³/h | "
                f"L={t['L']:.2f}m | HF={t['HF']:.4f}mca")

        # ---- Etapa 6: Editar a camada de tubulação existente ----
        log("\n📦 Etapa 6 – Inserindo trechos na camada de tubulação existente...")

        pr = lyr_tu.dataProvider()
        campos_existentes = [f.name() for f in lyr_tu.fields()]

        # Adicionar campos necessários se ainda não existirem
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
            log(f"   Campos adicionados à camada: {[c.name() for c in campos_novos]}")

        # Índices dos campos de saída (após possível adição)
        idx_dn = lyr_tu.fields().indexOf("DN")
        idx_v  = lyr_tu.fields().indexOf("V")
        idx_l  = lyr_tu.fields().indexOf("L")
        idx_hf = lyr_tu.fields().indexOf("HF")

        lyr_tu.startEditing()

        # 1. Deletar a feição original selecionada
        lyr_tu.deleteFeature(feat_tu.id())
        log(f"   Feição original (id={feat_tu.id()}) removida.")

        # 2. Inserir os trechos calculados na mesma camada
        feats_novos = []
        for t in trechos:
            f = QgsFeature(lyr_tu.fields())
            f.setGeometry(t['geom'])
            # Copiar atributos da feição original e sobrescrever os calculados
            f.setAttributes(feat_tu.attributes())
            f.setAttribute(idx_dn, t['DN'])
            f.setAttribute(idx_v,  round(t['V'], 4))
            f.setAttribute(idx_l,  round(t['L'], 2))
            f.setAttribute(idx_hf, round(t['HF'], 4))
            feats_novos.append(f)

        lyr_tu.addFeatures(feats_novos)
        lyr_tu.commitChanges()
        lyr_tu.triggerRepaint()
        self.iface.layerTreeView().refreshLayerSymbology(lyr_tu.id())

        log(f"\n✅ Concluído!")
        log(f"   {len(trechos)} trechos inseridos na camada '{lyr_tu.name()}'.")
        log(f"   HF total = {hf_sum:.4f} mca (máx permitido: {hf_max} mca)")

        resumo_dn = {}
        for t in trechos:
            resumo_dn[t['DN']] = resumo_dn.get(t['DN'], 0.0) + t['L']
        for dn, comp in sorted(resumo_dn.items()):
            log(f"   DN{dn}mm → {comp:.2f}m de tubulação")

        self.iface.messageBar().pushMessage(
            "Aqueduct",
            f"Dimensionamento concluído! {len(trechos)} trechos inseridos. HF total = {hf_sum:.4f} mca.",
            level=0, duration=8
        )

