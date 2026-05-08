from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.PyQt.QtGui import QIcon, QTextDocument, QPageLayout, QPageSize, QColor
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import QgsMapLayerType, QgsProject, QgsVectorLayer, QgsRasterLayer, QgsPalLayerSettings
import os
import pathlib
import json
import datetime

from .ferramenta_base import AqueductTool
from .gerar_layout_mapa import TAMANHOS_PAGINA


class GerarOrcamentoTool(AqueductTool):
    """Ferramenta para gerar o PDF de orçamento do projeto de irrigação."""

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_gerar_orcamento.svg')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf.svg')

        self.action = QAction(QIcon(icon_path), 'Gerar Orçamento', self.iface.mainWindow())
        self.action.triggered.connect(self.run)

        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    # ------------------------------------------------------------------
    def _get_logo_html(self):
        """Retorna o HTML do logo centralizado ou string vazia."""
        img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img')
        logo_path = os.path.join(img_dir, 'logo tocantins agropecuária ltda.png')
        if os.path.exists(logo_path):
            uri = pathlib.Path(logo_path).as_uri()
            return f'<div style="text-align:center; margin:0 0 6px 0;"><img src="{uri}" width="210"></div>'
        return ''

    def _get_termos(self):
        """Lê o arquivo de termos de serviço global e retorna o conteúdo."""
        try:
            from qgis.core import QgsApplication
            termos_path = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_termos.txt')
            if os.path.exists(termos_path):
                with open(termos_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception:
            pass
        return ''

    def _load_materiais(self, project):
        """Lê lista_materiais.json e retorna lista consolidada de itens do orçamento ativo."""
        mat_path = os.path.join(project.homePath(), 'lista_materiais.json')
        if not os.path.exists(mat_path):
            return []
        try:
            with open(mat_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Normalizar para estrutura de budgets
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict) and 'budgets' in data:
                budget_name = data.get('current', 'Orçamento Base')
                budget = data['budgets'].get(budget_name, {})
                # Itens avulsos
                items = list(budget.get('items', []))
                # Expandir blocos do projeto
                from .gerenciar_blocos import BlocoManager
                from .gerenciar_pecas import PecaManager
                bm = BlocoManager()
                pm = PecaManager()
                for pb in budget.get('project_blocos', []):
                    nome_bloco = pb.get('nome', '')
                    mult = pb.get('quantidade', 1)
                    # bm.get() retorna lista de {'nome': ..., 'quantidade': ...}
                    bloco_itens = bm.get(nome_bloco)
                    for bi in bloco_itens:
                        nome_peca = bi.get('nome', '')
                        qtd_bi    = bi.get('quantidade', 0)
                        peca = pm.get(nome_peca)  # {'custo': ..., 'lucro': ...} ou None
                        if peca:
                            preco = peca.get('custo', 0) * (1 + peca.get('lucro', 0) / 100)
                        else:
                            preco = 0.0
                        items.append({
                            'nome': nome_peca,
                            'quantidade': qtd_bi * mult,
                            'preco_unitario': preco
                        })
            else:
                items = []

            # Consolidar itens duplicados
            consolidated = {}
            for item in items:
                nome  = item.get('nome', '')
                qtd   = float(item.get('quantidade', 0))
                preco = float(item.get('preco_unitario', 0))
                if nome in consolidated:
                    consolidated[nome]['qtd'] += qtd
                else:
                    consolidated[nome] = {'qtd': qtd, 'preco': preco}

            return [(n, d['qtd'], d['preco']) for n, d in sorted(consolidated.items())]
        except Exception as e:
            print(f'Erro ao carregar materiais: {e}')
            return []

    def _load_servicos(self, project):
        """Lê lista_servicos.json e retorna lista de (descricao, qtd, valor_unit)."""
        serv_path = os.path.join(project.homePath(), 'lista_servicos.json')
        if not os.path.exists(serv_path):
            return []
        try:
            with open(serv_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return [(i.get('descricao',''), float(i.get('quantidade',0)), float(i.get('valor_unitario',0))) for i in data]
        except Exception as e:
            print(f'Erro ao carregar serviços: {e}')
            return []

    def _build_data_table(self, titulo, colunas, linhas, cor_cabecalho='#1B5E20'):
        """Constrói uma tabela HTML estilizada com cabeçalho verde e linhas alternadas."""
        # Cabeçalho
        th_style = f'background:{cor_cabecalho}; color:#fff; padding:6px 10px; text-align:left; font-weight:normal;'
        th_html = ''.join(f'<th style="{th_style}">{c}</th>' for c in colunas)

        # Linhas
        rows_html = ''
        for i, linha in enumerate(linhas):
            bg = '#f5f5f5' if i % 2 == 0 else '#ffffff'
            tds = ''.join(
                f'<td style="padding:5px 10px; text-align:{"right" if j > 0 else "left"}; background:{bg};">{cel}</td>'
                for j, cel in enumerate(linha)
            )
            rows_html += f'<tr>{tds}</tr>'

        return f"""
        <div style="margin-top:18px;">
            <div style="font-size:12pt; font-weight:bold; color:{cor_cabecalho}; border-bottom:2px solid {cor_cabecalho}; padding-bottom:4px; margin-bottom:4px;">{titulo}</div>
            <table width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">
                <thead><tr>{th_html}</tr></thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        """

    def _load_project_data(self, project):
        """Carrega dados_projeto.json e retorna um dict com todos os campos."""
        info_data = {}
        info_path = os.path.join(project.homePath(), 'dados_projeto.json')
        if os.path.exists(info_path):
            try:
                with open(info_path, 'r', encoding='utf-8') as f:
                    info_data = json.load(f)
            except Exception:
                pass
        return info_data

    def _get_qtd_setores(self, project, layer_name):
        """Conta feições da camada de setores."""
        if layer_name:
            layers = project.mapLayersByName(layer_name)
            if layers:
                return layers[0].featureCount()
        return 0

    def _build_info_table(self, info, qtd_setores):
        """
        Constrói a tabela de informações do projeto usando HTML <table>.
        Duas colunas separadas por uma coluna espaçadora.
        """

        def v(key, sufx='', default='-'):
            """Obtém valor formatado do dicionário."""
            val = info.get(key, None)
            if val is None or str(val).strip() == '':
                return default
            return f"{val}{sufx}"

        # Dados para a coluna esquerda
        col_esq = [
            ('Proprietário',      v('cliente')),
            ('Localidade',        v('local')),
            ('Energia',           v('energia')),
            ('Fonte de Água',     v('fonte_agua')),
            ('Qtd. Fontes',       v('qtd_fontes')),
            ('Data de Emissão',   datetime.datetime.now().strftime('%d/%m/%Y %H:%M')),
        ]

        # Dados para a coluna direita
        col_dir = [
            ('Área Total',            v('area_total', ' ha')),
            ('Total de Setores',      str(qtd_setores) if qtd_setores else '-'),
            ('Setores Simultâneos',   v('simultaneos')),
            ('Tempo por Setor',       v('tempo_setor', ' h')),
            ('Tempo Total Irrigação', v('tempo_total',  ' h')),
            ('Vazão do Projeto',      v('vazao_projeto', ' m³/h')),
            ('Vazão Diária',          v('vazao_diaria',  ' m³')),
        ]

        # Estilo das células label e valor
        lbl = 'color:#1B5E20; font-weight:bold; white-space:nowrap;'
        val = 'color:#111;'
        pad = 'padding:3px 4px 3px 0;'  # padding-right reduzido para aproximar label do valor
        sep = 'width:40px;'  # Coluna separadora invisível

        def par_rows(lista):
            """Gera linhas <tr> para uma lista de (label, valor)."""
            linhas = ''
            for k, vl in lista:
                linhas += (
                    f'<tr>'
                    f'<td style="{lbl}{pad}">{k}:</td>'
                    f'<td style="{val}{pad}">{vl}</td>'
                    f'</tr>'
                )
            return linhas

        html_esq = par_rows(col_esq)
        html_dir = par_rows(col_dir)

        return f"""
        <table width="100%" cellspacing="0" cellpadding="0"
               style="border:1px solid #000; background:#f9f9f9; margin-top:12px;">
          <tr>
            <td style="vertical-align:top; padding:14px 10px 14px 14px; width:45%;">
              <table cellspacing="0" cellpadding="0">
                {html_esq}
              </table>
            </td>
            <td style="{sep}"></td>
            <td style="vertical-align:top; padding:14px 14px 14px 10px; width:45%;
                        border-left:1px solid #ddd;">
              <table cellspacing="0" cellpadding="0">
                {html_dir}
              </table>
            </td>
          </tr>
        </table>
        """

    # ------------------------------------------------------------------
    def run(self):
        project = QgsProject.instance()

        # --- Seleção da camada de setores para o mapa ---
        from qgis.core import QgsWkbTypes
        valid_layers = [
            lyr for lyr in project.mapLayers().values()
            if lyr.type() == QgsMapLayerType.VectorLayer and lyr.geometryType() == QgsWkbTypes.PolygonGeometry
        ]

        area_layer = None
        if valid_layers:
            from qgis.PyQt.QtWidgets import QInputDialog
            layer_names = [l.name() for l in valid_layers]
            item, ok = QInputDialog.getItem(
                self.iface.mainWindow(),
                'Aqueduct - Mapa do Orçamento',
                'Selecione a camada de SETORES para incluir o mapa:',
                layer_names, 0, False
            )
            if ok and item:
                area_layer = next((l for l in valid_layers if l.name() == item), None)

        # --- Seleção do Tamanho da Página do Mapa ---
        map_page_size = 'A4 Paisagem  (297 × 210 mm)' # Default
        sat_layer = None

        if area_layer:
            # Seleção de tamanho de página
            tamanhos_lista = list(TAMANHOS_PAGINA.keys())
            tamanho_sel, ok_p = QInputDialog.getItem(
                self.iface.mainWindow(),
                'Aqueduct - Tamanho do Mapa',
                'Selecione o tamanho da página para o MAPA:',
                tamanhos_lista, 0, False
            )
            if ok_p and tamanho_sel:
                map_page_size = tamanho_sel

            # Seleção de satélite
            rasters = [l for l in project.mapLayers().values() if l.type() == QgsMapLayerType.RasterLayer]
            if rasters:
                raster_names = ["-- Nenhuma --"] + [l.name() for l in rasters]
                item_r, ok_r = QInputDialog.getItem(
                    self.iface.mainWindow(),
                    'Aqueduct - Camada de Fundo',
                    'Selecione a camada de Satélite/Ortomosaico:',
                    raster_names, 0, False
                )
                if ok_r and item_r != "-- Nenhuma --":
                    sat_layer = next((l for l in rasters if l.name() == item_r), None)

        # Diálogo de salvar
        base_name = project.baseName() or 'orcamento'
        default_name = f"{base_name}_orcamento.pdf"
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Salvar Orçamento PDF',
            os.path.join(project.homePath(), default_name),
            'Arquivos PDF (*.pdf)'
        )
        if not pdf_path:
            return
        if not pdf_path.endswith('.pdf'):
            pdf_path += '.pdf'

        try:
            logo_html   = self._get_logo_html()
            info_data   = self._load_project_data(project)
            qtd_setores = self._get_qtd_setores(project, info_data.get('layer_name'))
            info_table  = self._build_info_table(info_data, qtd_setores)

            # --- Termos ---
            termos_txt = self._get_termos()
            if termos_txt:
                termos_html = f"""
                <div style="margin-top:18px; border:1px solid #ddd; background:#f9f9f9; padding:12px 16px;">
                    <div style="font-weight:bold; color:#1B5E20; font-size:13pt; margin-bottom:6px;">
                        Termos e Condições
                    </div>
                    <div style="font-size:8pt; color:#333; line-height:1.2; text-align:justify; white-space:pre-wrap;">{termos_txt.replace(chr(9), '&nbsp;&nbsp;&nbsp;&nbsp;')}</div>
                </div>
                """
            else:
                termos_html = ''

            # --- Tabela de Materiais ---
            materiais = self._load_materiais(project)
            total_mat = 0.0
            linhas_mat = []
            # Formata valor em Real brasileiro: ponto para milhar, vírgula para decimal
            def brl(v): return f'R$ {v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
            for nome, qtd, preco in materiais:
                sub = qtd * preco
                total_mat += sub
                linhas_mat.append((nome, f'{qtd:.2f}', brl(preco), brl(sub)))

            tabela_mat = self._build_data_table(
                'Materiais',
                ['Item', 'Qtd', 'Valor Unit.', 'Total'],
                linhas_mat
            )

            # --- Tabela de Serviços ---
            servicos = self._load_servicos(project)
            total_serv = 0.0
            linhas_serv = []
            for desc, qtd, valor in servicos:
                sub = qtd * valor
                total_serv += sub
                linhas_serv.append((desc, f'{qtd:.2f}', brl(valor), brl(sub)))

            tabela_serv = self._build_data_table(
                'Serviços',
                ['Descrição', 'Qtd', 'Valor Unit.', 'Total'],
                linhas_serv
            )

            total_geral = total_mat + total_serv
            total_html = f"""
            <div style="margin-top:16px; padding-top:10px; border-top:2px solid #1B5E20; text-align:right;">
                <span style="font-size:10pt; color:#333;">
                    Subtotal Materiais: <b>{brl(total_mat)}</b> &nbsp;&nbsp;|&nbsp;&nbsp;
                    Subtotal Serviços: <b>{brl(total_serv)}</b>
                </span>
                <br>
                <span style="font-size:16pt; font-weight:bold; color:#1B5E20;">
                    TOTAL GERAL: {brl(total_geral)}
                </span>
            </div>
            """

            html = f"""
            <html>
            <head>
              <style>
                @page {{ margin: 0; size: A4 portrait; }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-size: 10pt;
                    margin: 0;
                    padding: 0;
                    color: #333;
                }}
                .content {{ padding: 12mm 18mm 18mm 18mm; }}
                .main-title {{
                    text-align: center;
                    color: #1B5E20;
                    font-size: 22pt;
                    font-weight: bold;
                    margin: 8px 0 4px 0;
                }}
                .sub-title {{
                    text-align: center;
                    color: #666;
                    font-size: 12pt;
                    font-weight: normal;
                    margin-bottom: 2px;
                }}
              </style>
            </head>
            <body>
              <div class="content">

                {logo_html}

                <div class="main-title">Orçamento de Projeto</div>
                <div class="sub-title">Materiais e Serviços</div>

                {info_table}

                <hr style="border:none; border-top:1px solid #000; margin:16px 0;">

                {termos_html}

                <div style="page-break-before: always; page-break-inside: auto;">
                  {tabela_mat}

                  {tabela_serv}

                  {total_html}
                </div>

              </div>
            </body>
            </html>
            """

            # === Geração dos PDFs ===
            import tempfile

            # PDF do orçamento em arquivo temporário
            tmp_orc = tempfile.NamedTemporaryFile(suffix='_orcamento.pdf', delete=False)
            tmp_orc_path = tmp_orc.name
            tmp_orc.close()

            doc = QTextDocument()
            doc.setHtml(html)
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(tmp_orc_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setPageOrientation(QPageLayout.Portrait)
            printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)
            doc.print_(printer)

            # === Geração dos PDFs dos Mapas ===
            tmp_map_paths = []
            if area_layer:
                from qgis.core import QgsLayoutExporter
                from .gerar_layout_mapa import MapLayoutGenerator
                generator = MapLayoutGenerator(project)
                
                # Salvar estado original dos rótulos
                original_label_states = {}
                for lyr in project.mapLayers().values():
                    if isinstance(lyr, QgsVectorLayer) and lyr.labelsEnabled():
                        config = lyr.labeling()
                        if config:
                            original_label_states[lyr.id()] = config.settings().format().color()

                def update_labels_color(color):
                    for lid in original_label_states.keys():
                        lyr = project.mapLayer(lid)
                        if lyr:
                            config = lyr.labeling()
                            settings = config.settings()
                            fmt = settings.format()
                            fmt.setColor(color)
                            settings.setFormat(fmt)
                            config.setSettings(settings)
                            lyr.setLabeling(config)
                            lyr.triggerRepaint()

                # Definir camadas visíveis (respeita o que o usuário marcou no painel de camadas)
                visible_layers = project.layerTreeRoot().checkedLayers()
                
                try:
                    # 1. Mapa com Satélite + Rótulos Brancos
                    update_labels_color(QColor("white"))
                    layers_map1 = list(visible_layers) # Cria cópia
                    # Garantir que a camada de satélite selecionada esteja presente no Mapa 1
                    if sat_layer and sat_layer not in layers_map1:
                        layers_map1.append(sat_layer)
                    
                    tmp_m1 = tempfile.NamedTemporaryFile(suffix='_mapa_sat.pdf', delete=False)
                    tmp_m1_path = tmp_m1.name
                    tmp_m1.close()
                    
                    layout1 = generator.create_layout(area_layer, page_size_key=map_page_size, visible_layers=layers_map1)
                    exporter1 = QgsLayoutExporter(layout1)
                    settings = QgsLayoutExporter.PdfExportSettings()
                    settings.dpi = 300
                    exporter1.exportToPdf(tmp_m1_path, settings)
                    tmp_map_paths.append(tmp_m1_path)
                    
                    # 2. Mapa sem Satélite + Rótulos Pretos
                    update_labels_color(QColor("black"))
                    layers_map2 = [l for l in visible_layers if l != sat_layer]
                    
                    tmp_m2 = tempfile.NamedTemporaryFile(suffix='_mapa_tec.pdf', delete=False)
                    tmp_m2_path = tmp_m2.name
                    tmp_m2.close()
                    
                    layout2 = generator.create_layout(area_layer, page_size_key=map_page_size, visible_layers=layers_map2)
                    exporter2 = QgsLayoutExporter(layout2)
                    exporter2.exportToPdf(tmp_m2_path, settings)
                    tmp_map_paths.append(tmp_m2_path)

                finally:
                    # Restaurar estado original de todos os rótulos
                    for lid, color in original_label_states.items():
                        lyr = project.mapLayer(lid)
                        if lyr:
                            config = lyr.labeling()
                            settings = config.settings()
                            fmt = settings.format()
                            fmt.setColor(color)
                            settings.setFormat(fmt)
                            config.setSettings(settings)
                            lyr.setLabeling(config)
                            lyr.triggerRepaint()

            # === Mesclagem dos PDFs ===
            # Tenta usar pypdf ou PyPDF2 (ambos compatíveis com QGIS)
            merged = False
            try:
                try:
                    from pypdf import PdfWriter, PdfReader
                except ImportError:
                    from PyPDF2 import PdfWriter, PdfReader

                writer = PdfWriter()

                # Adiciona páginas do orçamento
                reader_orc = PdfReader(tmp_orc_path)
                for page in reader_orc.pages:
                    writer.add_page(page)

                # Adiciona páginas dos mapas (paisagem, vão ao final)
                for m_path in tmp_map_paths:
                    if m_path and os.path.exists(m_path):
                        reader_map = PdfReader(m_path)
                        for page in reader_map.pages:
                            writer.add_page(page)

                with open(pdf_path, 'wb') as f_out:
                    writer.write(f_out)
                merged = True

            except ImportError:
                # pypdf/PyPDF2 não disponível; entrega só o orçamento sem mapa
                import shutil
                shutil.copy(tmp_orc_path, pdf_path)
                self.iface.messageBar().pushMessage(
                    'Aqueduct',
                    'Aviso: pypdf não instalado. Os mapas não foram incluídos. Instale: pip install pypdf',
                    level=1, duration=10
                )

            # Limpa temporários
            paths_to_clean = [tmp_orc_path] + tmp_map_paths
            for p in paths_to_clean:
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except: pass

            self.iface.messageBar().pushMessage('Aqueduct', f'Orçamento salvo: {pdf_path}', level=0, duration=5)
            if os.name == 'nt':
                os.startfile(pdf_path)

        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), 'Erro', f'Erro ao gerar orçamento:\n{e}')
