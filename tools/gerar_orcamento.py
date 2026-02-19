from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox
from qgis.PyQt.QtGui import QIcon, QTextDocument, QPageLayout, QPageSize
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import QgsProject
import os
import pathlib

from .ferramenta_base import AqueductTool

class GerarOrcamentoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf_orcamento.svg')
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf.svg')
            
        self.action = QAction(QIcon(icon_path), 'Gerar Orçamento (Novo)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        project = QgsProject.instance()
        
        # 1. Dialog para Salvar Arquivo
        base_name = project.baseName() or "orcamento"
        default_name = f"{base_name}_novo.pdf"
        
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Salvar Orçamento PDF",
            os.path.join(os.path.expanduser("~"), default_name),
            "Arquivos PDF (*.pdf)"
        )
        
        if not pdf_path: return
        if not pdf_path.endswith('.pdf'): pdf_path += '.pdf'

        try:
            # 2. Caminho do Logo
            img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img')
            logo_path = os.path.join(img_dir, 'logo tocantins agropecuária ltda.png')
            
            logo_html = ""
            if os.path.exists(logo_path):
                logo_uri = pathlib.Path(logo_path).as_uri()
                # Centralizado e fixo (no fluxo normal da página por enquanto, pois é header único)
                logo_html = f'<div style="text-align: center; margin-top: 0px;"><img src="{logo_uri}" width="210"></div>'
            else:
                logo_html = f'<div style="text-align: center; color: red;">Logo não encontrado: {logo_path}</div>'

            # 3. HTML Estrutura Básica
            html = f"""
            <html>
            <head>
                <style>
                    @page {{ margin: 0; size: A4 portrait; }}
                    body {{ 
                        font-family: 'Times New Roman', Times, serif; 
                        margin: 0; 
                        padding: 0; 
                    }}
                    .content {{
                        padding: 12mm 20mm 20mm 20mm; /* Top padding reduced */
                    }}
                </style>
            </head>
            <body>
                <div class="content">
                    {logo_html}
                </div>
            </body>
            </html>
            """
            
            # 4. Geração PDF
            doc = QTextDocument()
            doc.setHtml(html)
            
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setPageOrientation(QPageLayout.Portrait)
            printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)
            
            doc.print_(printer)
            
            self.iface.messageBar().pushMessage("Aqueduct", f"Orçamento gerado: {pdf_path}", level=0)
            if os.name == 'nt':
                os.startfile(pdf_path)

        except Exception as e:
            QMessageBox.critical(self.iface.mainWindow(), "Erro", f"Erro ao gerar orçamento: {str(e)}")
