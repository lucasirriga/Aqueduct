from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.PyQt.QtGui import QIcon, QTextDocument, QPageLayout, QPageSize
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import QgsProject
import os
import pathlib
import json
import datetime

from .ferramenta_base import AqueductTool


class GerarOrcamentoTool(AqueductTool):
    """Ferramenta para gerar o PDF de orçamento do projeto de irrigação."""

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf_orcamento.svg')
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
               style="border:1px solid #ddd; background:#f9f9f9; margin-top:12px;">
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

        # Diálogo de salvar
        base_name = project.baseName() or 'orcamento'
        default_name = f"{base_name}_orcamento.pdf"
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            'Salvar Orçamento PDF',
            os.path.join(os.path.expanduser('~'), default_name),
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

            # Bloco de Termos de Serviço
            termos_txt = self._get_termos()
            if termos_txt:
                # Converte quebras de linha em parágrafos HTML
                termos_linhas = ''.join(
                    f'<p style="margin:2px 0;">{ln}</p>' if ln.strip() else '<br>'
                    for ln in termos_txt.splitlines()
                )
                termos_html = f"""
                <div style="margin-top:18px; border:1px solid #ddd; background:#f9f9f9; padding:12px 16px;">
                    <div style="font-weight:bold; color:#1B5E20; font-size:11pt; margin-bottom:6px;">
                        Termos e Condições
                    </div>
                    <div style="font-size:9pt; color:#333; line-height:1.5; text-align:justify;">
                        {termos_linhas}
                    </div>
                </div>
                """
            else:
                termos_html = ''

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

                {termos_html}

              </div>
            </body>
            </html>
            """

            # Geração do PDF
            doc = QTextDocument()
            doc.setHtml(html)

            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setPageOrientation(QPageLayout.Portrait)
            printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)

            doc.print_(printer)

            self.iface.messageBar().pushMessage('Aqueduct', f'Orçamento salvo: {pdf_path}', level=0, duration=5)
            if os.name == 'nt':
                os.startfile(pdf_path)

        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), 'Erro', f'Erro ao gerar orçamento:\n{e}')
