import os
import json

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QDoubleSpinBox, QListWidget, QListWidgetItem, QPushButton,
    QMessageBox, QGroupBox, QFormLayout, QSplitter, QWidget,
    QDialogButtonBox, QFrame, QTabWidget
)
from qgis.PyQt.QtGui import QIcon, QFont, QColor
from qgis.core import QgsProject

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager
from .lista_materiais import ProjectBOMManager

# ---------------------------------------------------------------------------
# Caminho do banco de dados de bombas
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'motobombas.json')


def _carregar_banco():
    """Carrega o arquivo motobombas.json e adapta a estrutura para o plugin."""
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"Banco de dados não encontrado em: {DB_PATH}")
    with open(DB_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    bombas_originais = data.get('motobombas', [])
    bombas_adaptadas = []
    
    for b in bombas_originais:
        curva_orig = b.get('curva_desempenho', [])
        if not curva_orig:
            continue
            
        curva_nova = []
        vazoes = []
        pressoes = []
        
        for pt in curva_orig:
            q = pt.get('vazao_m3h', 0)
            p = pt.get('altura_manometrica_mca', 0)
            curva_nova.append({'flow_m3_h': q, 'pressure_mca': p})
            vazoes.append(q)
            pressoes.append(p)
            
        if not vazoes:
            continue
            
        bomba_ad = {
            'model': b.get('modelo', 'Desconhecido'),
            'power_cv': str(b.get('potencia_cv', '-')),
            'flow_range_m3_h': {'min': min(vazoes), 'max': max(vazoes)},
            'pressure_range_mca': {'min': min(pressoes), 'max': max(pressoes)},
            'curve': curva_nova,
            '_raw': b # Mantem os dados originais caso precise no futuro
        }
        bombas_adaptadas.append(bomba_ad)
        
    return bombas_adaptadas


def _buscar_bombas_compativeis(todas, vazao_m3h, pressao_mca, margem_vazao=0.15, tolerancia_pressao_mca=2.0):
    """
    Retorna bombas compatíveis realizando interpolação linear direta 
    sobre os pontos da curva coletados para a vazão solicitada.
    """
    compativeis = []
    for b in todas:
        fmin = b['flow_range_m3_h']['min']
        fmax = b['flow_range_m3_h']['max']

        # A vazão do projeto deve estar no range da bomba (com margem)
        if not ((fmin * (1 - margem_vazao)) <= vazao_m3h <= (fmax * (1 + margem_vazao))):
            continue
            
        curve = sorted(b.get('curve', []), key=lambda x: x['flow_m3_h'])
        if len(curve) < 2:
            continue
            
        # Interpolação linear para achar a Altura Manométrica (H) da bomba na vazão solicitada (Q)
        h_interpolado = None
        
        if vazao_m3h <= curve[0]['flow_m3_h']:
            h_interpolado = curve[0]['pressure_mca']
        elif vazao_m3h >= curve[-1]['flow_m3_h']:
            h_interpolado = curve[-1]['pressure_mca']
        else:
            for i in range(len(curve) - 1):
                p1 = curve[i]
                p2 = curve[i+1]
                if p1['flow_m3_h'] <= vazao_m3h <= p2['flow_m3_h']:
                    dq = p2['flow_m3_h'] - p1['flow_m3_h']
                    if dq == 0:
                        h_interpolado = p1['pressure_mca']
                    else:
                        dp = p2['pressure_mca'] - p1['pressure_mca']
                        h_interpolado = p1['pressure_mca'] + (vazao_m3h - p1['flow_m3_h']) * (dp / dq)
                    break
                    
        # Para ser compatível, a bomba deve fornecer no mínimo a pressão exigida 
        # (podendo faltar no máximo uma pequena tolerância)
        if h_interpolado is not None and h_interpolado >= (pressao_mca - tolerancia_pressao_mca):
            # Limitamos para não sugerir bombas absurdamente superdimensionadas
            # (que fornecem mais que o dobro da pressão necessária)
            if h_interpolado <= (pressao_mca * 2.5):
                compativeis.append(b)

    # Ordena por quão perto a pressão interpolada está da desejada, e depois potência
    def _sort_key(b_item):
        try:
            pow_val = float(b_item.get('power_cv', '999').replace(',', '.'))
        except Exception:
            pow_val = 999
        return pow_val
        
    compativeis.sort(key=_sort_key)
    return compativeis


# ---------------------------------------------------------------------------
# Widget de gráfico (sem matplotlib externo — usa QPainter puro)
# ---------------------------------------------------------------------------
class GraficoCurva(QWidget):
    """
    Widget que desenha a curva Q-H de uma bomba usando QPainter.
    Não depende de matplotlib, funcionando em qualquer instalação QGIS.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.bomba = None
        self.vazao_projeto = 0.0
        self.pressao_projeto = 0.0
        self.setMinimumSize(400, 320)
        self.setStyleSheet("background-color: white; border: 1px solid #ccc; border-radius: 4px;")

    def set_bomba(self, bomba, vazao_projeto, pressao_projeto):
        self.bomba = bomba
        self.vazao_projeto = vazao_projeto
        self.pressao_projeto = pressao_projeto
        self.update()

    def limpar(self):
        self.bomba = None
        self.update()

    def paintEvent(self, event):
        from qgis.PyQt.QtGui import QPainter, QPen, QBrush, QPolygonF, QPainterPath, QFont as QF
        from qgis.PyQt.QtCore import QPointF, QRectF

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        # Fundo
        painter.fillRect(0, 0, w, h, QColor('#fafafa'))

        if not self.bomba:
            painter.setPen(QColor('#aaa'))
            painter.setFont(QF('Segoe UI', 11))
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignCenter,
                'Selecione uma bomba\npara ver a curva Q-H'
            )
            painter.end()
            return

        curve = self.bomba.get('curve', [])
        if len(curve) < 2:
            painter.setPen(QColor('#aaa'))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, 'Curva indisponível')
            painter.end()
            return

        # Margens do gráfico
        mL, mR, mT, mB = 60, 24, 28, 52
        gW = w - mL - mR
        gH = h - mT - mB

        # Extrai valores da curva
        flows = [pt['flow_m3_h'] for pt in curve]
        pressures = [pt['pressure_mca'] for pt in curve]

        # Eixos — expande um pouco além dos dados para dar respiro
        fmin_ax = min(flows) * 0.9
        fmax_ax = max(flows) * 1.08
        pmin_ax = 0.0
        pmax_ax = max(pressures) * 1.12

        # Garante que o ponto do projeto aparece no gráfico
        if self.vazao_projeto > 0:
            fmax_ax = max(fmax_ax, self.vazao_projeto * 1.12)
        if self.pressao_projeto > 0:
            pmax_ax = max(pmax_ax, self.pressao_projeto * 1.15)

        def to_px(q, p):
            x = mL + (q - fmin_ax) / (fmax_ax - fmin_ax) * gW
            y = mT + gH - (p - pmin_ax) / (pmax_ax - pmin_ax) * gH
            return QPointF(x, y)

        # ---- Grade ----
        pen_grid = QPen(QColor('#e0e0e0'), 1, Qt.DashLine)
        painter.setPen(pen_grid)
        n_lines = 5
        for i in range(1, n_lines):
            # Horizontal
            yg = mT + gH * i / n_lines
            painter.drawLine(int(mL), int(yg), int(mL + gW), int(yg))
            # Vertical
            xg = mL + gW * i / n_lines
            painter.drawLine(int(xg), int(mT), int(xg), int(mT + gH))

        # ---- Área preenchida abaixo da curva ----
        # Ordena pontos por vazão crescente
        pts_sorted = sorted(zip(flows, pressures), key=lambda x: x[0])
        path_fill = QPainterPath()
        first_px = to_px(pts_sorted[0][0], pts_sorted[0][1])
        path_fill.moveTo(to_px(pts_sorted[0][0], 0))
        path_fill.lineTo(first_px)
        for q, p in pts_sorted[1:]:
            path_fill.lineTo(to_px(q, p))
        path_fill.lineTo(to_px(pts_sorted[-1][0], 0))
        path_fill.closeSubpath()
        painter.fillPath(path_fill, QColor(30, 136, 229, 40))

        # ---- Curva Q-H ----
        pen_curve = QPen(QColor('#1565C0'), 2, Qt.SolidLine)
        pen_curve.setCapStyle(Qt.RoundCap)
        pen_curve.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen_curve)
        poly = QPolygonF([to_px(q, p) for q, p in pts_sorted])
        painter.drawPolyline(poly)

        # Pontos da curva
        painter.setBrush(QBrush(QColor('#1565C0')))
        for q, p in pts_sorted:
            px = to_px(q, p)
            painter.drawEllipse(px, 4, 4)

        # ---- Ponto do Projeto ----
        if self.vazao_projeto > 0 and self.pressao_projeto > 0:
            pp = to_px(self.vazao_projeto, self.pressao_projeto)

            # Linhas de referência (tracejado laranja)
            pen_ref = QPen(QColor('#E65100'), 1, Qt.DashLine)
            painter.setPen(pen_ref)
            painter.drawLine(int(mL), int(pp.y()), int(pp.x()), int(pp.y()))
            painter.drawLine(int(pp.x()), int(mT + gH), int(pp.x()), int(pp.y()))

            # Ponto
            pen_pt = QPen(QColor('#BF360C'), 2)
            painter.setPen(pen_pt)
            painter.setBrush(QBrush(QColor('#FF5722')))
            painter.drawEllipse(pp, 7, 7)

            # Rótulo do ponto
            painter.setPen(QColor('#BF360C'))
            painter.setFont(QF('Segoe UI', 8, QF.Bold))
            painter.drawText(
                QRectF(pp.x() + 9, pp.y() - 18, 120, 36),
                Qt.AlignLeft | Qt.AlignVCenter,
                f'Projeto\n{self.vazao_projeto:.1f} m³/h | {self.pressao_projeto:.1f} mca'
            )

        # ---- Eixos ----
        pen_ax = QPen(QColor('#555'), 1)
        painter.setPen(pen_ax)
        painter.drawLine(mL, mT, mL, mT + gH)       # Y
        painter.drawLine(mL, mT + gH, mL + gW, mT + gH)  # X

        # ---- Rótulos dos eixos ----
        painter.setFont(QF('Segoe UI', 8))
        painter.setPen(QColor('#333'))

        # Eixo Y
        for i in range(n_lines + 1):
            p_val = pmin_ax + (pmax_ax - pmin_ax) * i / n_lines
            yg = mT + gH - gH * i / n_lines
            painter.drawText(QRectF(2, yg - 10, mL - 6, 20), Qt.AlignRight | Qt.AlignVCenter, f'{p_val:.0f}')

        # Eixo X
        for i in range(n_lines + 1):
            q_val = fmin_ax + (fmax_ax - fmin_ax) * i / n_lines
            xg = mL + gW * i / n_lines
            painter.drawText(QRectF(xg - 20, mT + gH + 4, 40, 18), Qt.AlignCenter, f'{q_val:.0f}')

        # Títulos dos eixos
        painter.setFont(QF('Segoe UI', 9, QF.Bold))
        painter.drawText(QRectF(mL, mT + gH + 22, gW, 20), Qt.AlignCenter, 'Vazão (m³/h)')

        painter.save()
        painter.translate(14, mT + gH / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-50, -10, 100, 20), Qt.AlignCenter, 'Pressão (mca)')
        painter.restore()

        # ---- Título da bomba ----
        painter.setPen(QColor('#0D47A1'))
        painter.setFont(QF('Segoe UI', 10, QF.Bold))
        modelo = self.bomba.get('model', '')
        potencia = self.bomba.get('power_cv', '-')
        painter.drawText(QRectF(mL, 4, gW, mT - 4), Qt.AlignCenter,
                         f'Curva Q-H — {modelo}  ({potencia} CV)')

        painter.end()


# ---------------------------------------------------------------------------
# Diálogo principal
# ---------------------------------------------------------------------------
class SelecionarBombaDialog(QDialog):

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle('Aqueduct — Seleção de Motobomba')
        self.resize(960, 600)

        self.peca_manager = PecaManager()
        self.bom_manager = ProjectBOMManager()
        self.todas_bombas = []
        self.bombas_filtradas = []
        self.bomba_selecionada = None

        self.vazao_projeto = self._ler_vazao_projeto()

        self._setup_ui()
        self._carregar_banco()

    # ------------------------------------------------------------------
    def _ler_vazao_projeto(self):
        """Lê vazao_projeto de dados_projeto.json."""
        home = QgsProject.instance().homePath()
        if not home:
            return 0.0
        path = os.path.join(home, 'dados_projeto.json')
        if not os.path.exists(path):
            return 0.0
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            val = data.get('vazao_projeto', 0.0)
            return float(str(val).replace(',', '.')) if val else 0.0
        except Exception:
            return 0.0

    # ------------------------------------------------------------------
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        # ---- Painel de busca ----
        grp_busca = QGroupBox('Parâmetros de Busca')
        form = QFormLayout()

        # Vazão (pré-carregada)
        self.spin_vazao = QDoubleSpinBox()
        self.spin_vazao.setRange(0.1, 10000.0)
        self.spin_vazao.setDecimals(2)
        self.spin_vazao.setSuffix(' m³/h')
        self.spin_vazao.setValue(self.vazao_projeto if self.vazao_projeto > 0 else 1.0)
        if self.vazao_projeto > 0:
            self.spin_vazao.setStyleSheet('color: #1565C0; font-weight: bold;')
        form.addRow('Vazão do Projeto (m³/h):', self.spin_vazao)

        # Pressão pretendida
        self.spin_pressao = QDoubleSpinBox()
        self.spin_pressao.setRange(0.1, 500.0)
        self.spin_pressao.setDecimals(1)
        self.spin_pressao.setSuffix(' mca')
        self.spin_pressao.setValue(30.0)
        form.addRow('Pressão Pretendida (mca):', self.spin_pressao)

        btn_buscar = QPushButton('🔍  Buscar Modelos Compatíveis')
        btn_buscar.setMinimumHeight(34)
        btn_buscar.clicked.connect(self._buscar)
        form.addRow(btn_buscar)

        grp_busca.setLayout(form)
        main_layout.addWidget(grp_busca)

        # ---- Label com nome do arquivo do banco ----
        nome_arquivo = os.path.basename(DB_PATH)
        lbl_banco = QLabel(f'📂 Banco de dados: <b>{nome_arquivo}</b>')
        lbl_banco.setToolTip(DB_PATH)
        lbl_banco.setStyleSheet(
            'color: #555; font-size: 9pt; padding: 2px 4px;'
            'background: #f0f4ff; border: 1px solid #c5cae9; border-radius: 3px;'
        )
        main_layout.addWidget(lbl_banco)

        # ---- Conteúdo principal (splitter) ----
        splitter = QSplitter(Qt.Horizontal)

        # Lado esquerdo: abas de modelos
        left = QWidget()
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        # --- Abas: Resultados / Todas ---
        self.tabs = QTabWidget()
        self.tabs.setMinimumWidth(270)

        # Aba 1 — Resultados da busca
        aba_busca = QWidget()
        lay_busca = QVBoxLayout(aba_busca)
        lay_busca.setContentsMargins(4, 4, 4, 4)

        self.lbl_resultado = QLabel('Aguardando busca...')
        self.lbl_resultado.setStyleSheet('color: #666; font-style: italic;')
        lay_busca.addWidget(self.lbl_resultado)

        self.lista = QListWidget()
        self.lista.currentItemChanged.connect(self._on_item_changed)
        lay_busca.addWidget(self.lista)
        self.tabs.addTab(aba_busca, '🔍 Resultados')

        # Aba 2 — Todas as bombas
        aba_todas = QWidget()
        lay_todas = QVBoxLayout(aba_todas)
        lay_todas.setContentsMargins(4, 4, 4, 4)

        self.lbl_total = QLabel('Carregando...')
        self.lbl_total.setStyleSheet('color: #666; font-style: italic;')
        lay_todas.addWidget(self.lbl_total)

        self.lista_todas = QListWidget()
        self.lista_todas.currentItemChanged.connect(self._on_item_changed)
        lay_todas.addWidget(self.lista_todas)
        self.tabs.addTab(aba_todas, '📋 Todas as Bombas')

        left_lay.addWidget(self.tabs)

        self.btn_selecionar = QPushButton('✅  Selecionar esta Bomba')
        self.btn_selecionar.setEnabled(False)
        self.btn_selecionar.setMinimumHeight(36)
        self.btn_selecionar.setStyleSheet(
            'QPushButton { background: #2E7D32; color: white; border-radius: 4px; font-weight: bold; }'
            'QPushButton:hover { background: #388E3C; }'
            'QPushButton:disabled { background: #ccc; color: #888; }'
        )
        self.btn_selecionar.clicked.connect(self._selecionar)
        left_lay.addWidget(self.btn_selecionar)

        splitter.addWidget(left)

        # Lado direito: gráfico
        self.grafico = GraficoCurva()
        splitter.addWidget(self.grafico)
        splitter.setSizes([280, 680])

        main_layout.addWidget(splitter, 1)

        # Botão fechar
        btn_fechar = QPushButton('Fechar')
        btn_fechar.clicked.connect(self.reject)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_fechar)
        main_layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _carregar_banco(self):
        try:
            self.todas_bombas = _carregar_banco()
        except Exception as e:
            QMessageBox.critical(self, 'Aqueduct — Erro', f'Erro ao carregar banco de bombas:\n{e}')
            self.todas_bombas = []
            return

        # Popula aba "Todas as Bombas"
        self.lista_todas.clear()
        self.lbl_total.setText(f'{len(self.todas_bombas)} modelos disponíveis:')
        self.lbl_total.setStyleSheet('color: #1565C0; font-weight: bold;')

        for b in self.todas_bombas:
            modelo = b.get('model', 'Desconhecido')
            potencia = b.get('power_cv', '-')
            fmin = b['flow_range_m3_h']['min']
            fmax = b['flow_range_m3_h']['max']
            pmin = b['pressure_range_mca']['min']
            pmax = b['pressure_range_mca']['max']
            texto = (
                f'{modelo}  ({potencia} CV)\n'
                f'  Q: {fmin}–{fmax} m³/h   H: {pmin}–{pmax} mca'
            )
            item = QListWidgetItem(texto)
            item.setData(Qt.UserRole, b)
            self.lista_todas.addItem(item)

    # ------------------------------------------------------------------
    def _buscar(self):
        vazao = self.spin_vazao.value()
        pressao = self.spin_pressao.value()

        self.bombas_filtradas = _buscar_bombas_compativeis(self.todas_bombas, vazao, pressao)

        self.lista.clear()
        self.grafico.limpar()
        self.btn_selecionar.setEnabled(False)
        self.bomba_selecionada = None

        if not self.bombas_filtradas:
            self.lbl_resultado.setText('❌ Nenhum modelo compatível encontrado.')
            self.lbl_resultado.setStyleSheet('color: #c62828; font-weight: bold;')
            return

        self.lbl_resultado.setText(f'✅ {len(self.bombas_filtradas)} modelo(s) encontrado(s):')
        self.lbl_resultado.setStyleSheet('color: #2E7D32; font-weight: bold;')

        for b in self.bombas_filtradas:
            modelo = b.get('model', 'Desconhecido')
            potencia = b.get('power_cv', '-')
            fmin = b['flow_range_m3_h']['min']
            fmax = b['flow_range_m3_h']['max']
            pmin = b['pressure_range_mca']['min']
            pmax = b['pressure_range_mca']['max']

            texto = (
                f'{modelo}  ({potencia} CV)\n'
                f'  Q: {fmin}–{fmax} m³/h   H: {pmin}–{pmax} mca'
            )
            item = QListWidgetItem(texto)
            item.setData(Qt.UserRole, b)
            self.lista.addItem(item)

    # ------------------------------------------------------------------
    def _on_item_changed(self, current, _previous):
        if not current:
            self.grafico.limpar()
            self.btn_selecionar.setEnabled(False)
            self.bomba_selecionada = None
            return

        bomba = current.data(Qt.UserRole)
        self.bomba_selecionada = bomba
        self.grafico.set_bomba(
            bomba,
            self.spin_vazao.value(),
            self.spin_pressao.value()
        )
        self.btn_selecionar.setEnabled(True)

    # ------------------------------------------------------------------
    def _selecionar(self):
        if not self.bomba_selecionada:
            return

        modelo = self.bomba_selecionada.get('model', '')
        potencia = self.bomba_selecionada.get('power_cv', '-')
        nome_peca = f'Bomba {modelo}'

        # Verifica se já existe no catálogo de peças
        peca_existente = self.peca_manager.get(nome_peca)

        if peca_existente:
            custo = peca_existente.get('custo', 0.0)
            lucro = peca_existente.get('lucro', 0.0)
            preco = custo * (1 + lucro / 100)
            resp = QMessageBox.question(
                self, 'Bomba já cadastrada',
                f'O modelo "{nome_peca}" já existe no catálogo de peças.\n\n'
                f'Custo: R$ {custo:.2f} | Lucro: {lucro:.0f}% | Preço Final: R$ {preco:.2f}\n\n'
                'Deseja adicioná-la ao orçamento do projeto?',
                QMessageBox.Yes | QMessageBox.No
            )
            if resp == QMessageBox.Yes:
                self._adicionar_ao_orcamento(nome_peca, preco)
        else:
            # Não existe — pede cadastro
            dlg = _CadastrarBombaDialog(nome_peca, potencia, self)
            if dlg.exec_():
                custo = dlg.spin_custo.value()
                lucro = dlg.spin_lucro.value()
                preco = custo * (1 + lucro / 100)

                # Salva na lista de peças globais
                self.peca_manager.add_update(nome_peca, {'custo': custo, 'lucro': lucro})
                QMessageBox.information(
                    self, 'Peça Cadastrada',
                    f'"{nome_peca}" adicionada ao catálogo de peças com sucesso!'
                )
                self._adicionar_ao_orcamento(nome_peca, preco)

    # ------------------------------------------------------------------
    def _adicionar_ao_orcamento(self, nome_peca, preco):
        if not self.bom_manager.filepath:
            QMessageBox.warning(
                self, 'Aviso',
                'Salve o projeto QGIS antes de adicionar itens ao orçamento.'
            )
            return

        self.bom_manager.add_item(nome_peca, preco, 1)
        QMessageBox.information(
            self, 'Sucesso',
            f'"{nome_peca}" adicionada ao orçamento do projeto!\n\n'
            'Acesse a ferramenta Lista de Materiais para revisar.'
        )


# ---------------------------------------------------------------------------
# Diálogo de cadastro de nova bomba como peça
# ---------------------------------------------------------------------------
class _CadastrarBombaDialog(QDialog):

    def __init__(self, nome_peca, potencia, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Cadastrar Bomba como Peça')
        self.resize(360, 240)

        layout = QVBoxLayout(self)

        lbl = QLabel(
            f'O modelo <b>{nome_peca}</b> não está cadastrado no catálogo.\n'
            f'Informe o custo e o percentual de lucro para cadastrá-lo.'
        )
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet('color: #ddd;')
        layout.addWidget(sep)

        form = QFormLayout()

        lbl_nome = QLabel(f'<b>{nome_peca}</b>')
        form.addRow('Modelo:', lbl_nome)

        lbl_pot = QLabel(f'{potencia} CV')
        form.addRow('Potência:', lbl_pot)

        self.spin_custo = QDoubleSpinBox()
        self.spin_custo.setRange(0.0, 999999.0)
        self.spin_custo.setDecimals(2)
        self.spin_custo.setPrefix('R$ ')
        form.addRow('Custo Unitário:', self.spin_custo)

        self.spin_lucro = QDoubleSpinBox()
        self.spin_lucro.setRange(0.0, 1000.0)
        self.spin_lucro.setValue(30.0)
        self.spin_lucro.setSuffix('%')
        form.addRow('Lucro (%):', self.spin_lucro)

        self.lbl_preco_final = QLabel('R$ 0.00')
        self.lbl_preco_final.setStyleSheet('font-weight: bold; color: #2E7D32; font-size: 11pt;')
        form.addRow('Preço Final:', self.lbl_preco_final)

        self.spin_custo.valueChanged.connect(self._atualizar_preco)
        self.spin_lucro.valueChanged.connect(self._atualizar_preco)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText('Cadastrar e Adicionar')
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _atualizar_preco(self):
        preco = self.spin_custo.value() * (1 + self.spin_lucro.value() / 100)
        self.lbl_preco_final.setText(f'R$ {preco:.2f}')


# ---------------------------------------------------------------------------
# Tool wrapper
# ---------------------------------------------------------------------------
class SelecionarBombaTool(AqueductTool):
    """
    Ferramenta de seleção de motobomba por curva Q-H.
    Lê a vazão do projeto em dados_projeto.json, solicita a pressão
    pretendida e exibe os modelos compatíveis com gráfico interativo.
    """

    def initGui(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_selecionar_bomba.svg'
        )
        if not os.path.exists(icon_path):
            icon_path = ''

        self.action = QAction(
            QIcon(icon_path),
            'Selecionar Bomba',
            self.iface.mainWindow()
        )
        self.action.setToolTip(
            'Selecionar Motobomba\n'
            'Busca modelos compatíveis com a vazão e pressão do projeto,\n'
            'exibindo a curva Q-H e permitindo cadastro no orçamento.'
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)

        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        dlg = SelecionarBombaDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
