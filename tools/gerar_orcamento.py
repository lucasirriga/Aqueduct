from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox, QProgressDialog
from qgis.PyQt.QtGui import QIcon, QTextDocument, QPageLayout, QPageSize
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import (
    QgsProject, QgsApplication, QgsPrintLayout, QgsLayoutItemMap, 
    QgsLayoutItemMapGrid, QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes,
    QgsLayoutExporter, QgsLayoutItemShape, QgsFillSymbol, QgsLayoutItemScaleBar,
    QgsWkbTypes, QgsRectangle, QgsLayoutItemLegend
)
import os
import json
import datetime

from .ferramenta_base import AqueductTool
from .lista_materiais import ProjectBOMManager
from .lista_servicos import ProjectServiceListManager
from .gerenciar_pecas import PecaManager
from .gerenciar_blocos import BlocoManager

class GerarOrcamentoTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf_orcamento.svg')
        # Se icone nao existir, usa o de pdf generico
        if not os.path.exists(icon_path):
            icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_pdf.svg')
            
        self.action = QAction(QIcon(icon_path), 'Gerar Orçamento Completo', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        project = QgsProject.instance()
        if not project.fileName():
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "O projeto deve ser salvo antes de gerar o orçamento.")
            return

        # 1. Dialog para Salvar Arquivo
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        base_name = project.baseName() or "orcamento_aqueduct"
        default_name = f"Orcamento_{base_name}_{timestamp}.pdf"
        
        pdf_path, _ = QFileDialog.getSaveFileName(
            self.iface.mainWindow(),
            "Salvar Orçamento PDF",
            os.path.join(os.path.expanduser("~"), default_name),
            "Arquivos PDF (*.pdf)"
        )
        
        if not pdf_path: return
        if not pdf_path.endswith('.pdf'): pdf_path += '.pdf'

        # Progress Dialog (Operação demorada)
        progress = QProgressDialog("Gerando Orçamento...", "Cancelar", 0, 100, self.iface.mainWindow())
        progress.setWindowModality(2) # WindowModal
        progress.show()

        try:
            # 2. Coleta de Dados
            progress.setLabelText("Coletando Dados...")
            progress.setValue(10)
            
            # --- Gerenciadores ---
            bom_mgr = ProjectBOMManager()
            serv_mgr = ProjectServiceListManager()
            bloc_mgr = BlocoManager()
            peca_mgr = PecaManager()
            
            # --- Info Projeto ---
            info_data = {}
            info_path = os.path.join(project.homePath(), 'dados_projeto.json')
            if os.path.exists(info_path):
                with open(info_path, 'r', encoding='utf-8') as f:
                    info_data = json.load(f)
            
            # --- Termos ---
            termos_content = ""
            termos_path = os.path.join(QgsApplication.qgisSettingsDirPath(), 'aqueduct_termos.txt')
            if os.path.exists(termos_path):
                with open(termos_path, 'r', encoding='utf-8') as f:
                    termos_content = f.read().replace('\n', '<br>')
            else:
                termos_content = "Termos de serviço não definidos."
                
            # 3. Consolidação de Materiais (Mesma lógica da ListaMateriaisDialog)
            progress.setLabelText("Calculando Materiais...")
            progress.setValue(20)
            
            consolidated = {} # {nome: {'qtd': 0, 'preco': 0}}
            
            # Avulsas
            for item in bom_mgr.items:
                nome = item['nome']
                if nome not in consolidated:
                    consolidated[nome] = {'qtd': 0.0, 'preco': item['preco_unitario']}
                consolidated[nome]['qtd'] += item['quantidade']
                
            # Blocos
            for pb in bom_mgr.project_blocos:
                b_nome = pb['nome']
                b_qtd = pb['quantidade']
                itens_bloco = bloc_mgr.get(b_nome)
                if itens_bloco:
                    for ib in itens_bloco:
                        p_nome = ib['nome']
                        p_qtd = ib['quantidade']
                        total_p_qtd = p_qtd * b_qtd
                        
                        if p_nome not in consolidated:
                            # Preço do catalogo
                            pd = peca_mgr.get(p_nome)
                            custo = pd.get('custo', 0) if pd else 0
                            lucro = pd.get('lucro', 0) if pd else 0
                            preco = custo * (1+lucro/100)
                            consolidated[p_nome] = {'qtd': 0.0, 'preco': preco}
                        
                        consolidated[p_nome]['qtd'] += total_p_qtd

            # 4. Geração da Imagem do Mapa
            progress.setLabelText("Renderizando Mapa...")
            progress.setValue(40)
            map_image_path = self.generate_map_image(project)
            
            # 5. Montagem do HTML
            progress.setLabelText("Gerando Relatório...")
            progress.setValue(70)
            
            logo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img', 'logo tocantins agropecuária ltda.png')
            logo_html = ""
            if os.path.exists(logo_path):
                # Usar file:/// path para QPrinter achar
                logo_uri = QIcon(logo_path).pixmap(200,100) # Check validity? 
                # Better: just path
                import pathlib
                logo_uri = pathlib.Path(logo_path).as_uri()
                logo_html = f'<img src="{logo_uri}" width="200" style="display: block; margin: 0 auto;">'
            
            # Formatando Valores
            total_materiais = sum(d['qtd']*d['preco'] for d in consolidated.values())
            total_servicos = sum(i['quantidade']*i['valor_unitario'] for i in serv_mgr.items)
            total_geral = total_materiais + total_servicos
            
            # Tabela Materiais HTML
            rows_mat = ""
            for nome, d in sorted(consolidated.items()):
                sub = d['qtd'] * d['preco']
                rows_mat += f"""
                <tr>
                    <td style="text-align: left; padding: 4px;">{nome}</td>
                    <td style="text-align: center; padding: 4px;">{d['qtd']:.2f}</td>
                    <td style="text-align: right; padding: 4px;">R$ {d['preco']:.2f}</td>
                    <td style="text-align: right; padding: 4px;">R$ {sub:.2f}</td>
                </tr>
                """
            
            # Tabela Serviços HTML
            rows_serv = ""
            for i in serv_mgr.items:
                sub = i['quantidade']*i['valor_unitario']
                rows_serv += f"""
                <tr>
                    <td style="text-align: left; padding: 4px;">{i['descricao']}</td>
                    <td style="text-align: center; padding: 4px;">{i['quantidade']:.2f}</td>
                    <td style="text-align: right; padding: 4px;">R$ {i['valor_unitario']:.2f}</td>
                    <td style="text-align: right; padding: 4px;">R$ {sub:.2f}</td>
                </tr>
                """

            html = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; font-size: 10pt; }}
                    h1 {{ text-align: center; font-size: 18pt; margin-bottom: 5px; }}
                    h2 {{ font-size: 14pt; border-bottom: 2px solid #333; margin-top: 20px; padding-bottom: 5px; }}
                    .info-box {{ border: 1px solid #ccc; padding: 10px; background-color: #f9f9f9; margin: 10px 0; }}
                    table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 9pt; }}
                    th {{ background-color: #eee; border: 1px solid #ddd; padding: 5px; }}
                    td {{ border: 1px solid #ddd; }}
                    .total {{ text-align: right; font-weight: bold; font-size: 12pt; margin-top: 10px; }}
                    .page-break {{ page-break-before: always; }}
                    .termos {{ font-size: 9pt; text-align: justify; line-height: 1.4; }}
                </style>
            </head>
            <body>
                <!-- Header -->
                <div style="text-align: center;">
                    {logo_html}
                </div>
                
                <!-- Info -->
                <div class="info-box">
                    <b>CLIENTE:</b> {info_data.get('cliente', '')}<br>
                    <b>LOCAL:</b> {info_data.get('local', '')}<br>
                    <b>ÁREA TOTAL:</b> {info_data.get('area_total', '-')} ha<br>
                    <b>DATA:</b> {datetime.datetime.now().strftime("%d/%m/%Y")}
                </div>
                
                <!-- Termos -->
                <h2>TERMOS DE SERVIÇO</h2>
                <div class="termos">
                    {termos_content}
                </div>
                
                <div class="page-break"></div>
                
                <!-- Orçamento -->
                <h1>ORÇAMENTO</h1>
                
                <h2>MATERIAIS</h2>
                <table>
                    <thead>
                        <tr>
                            <th width="50%">Item</th>
                            <th width="15%">Qtd</th>
                            <th width="15%">Unit.</th>
                            <th width="20%">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_mat}
                    </tbody>
                </table>
                <div class="total">Subtotal Materiais: R$ {total_materiais:.2f}</div>
                
                <h2>SERVIÇOS</h2>
                <table>
                    <thead>
                        <tr>
                            <th width="50%">Descrição</th>
                            <th width="15%">Qtd</th>
                            <th width="15%">Unit.</th>
                            <th width="20%">Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_serv}
                    </tbody>
                </table>
                <div class="total">Subtotal Serviços: R$ {total_servicos:.2f}</div>
                
                <div style="text-align: right; font-size: 16pt; font-weight: bold; margin-top: 30px; border-top: 2px solid black; padding-top: 10px;">
                    TOTAL GERAL: R$ {total_geral:.2f}
                </div>
                
                <!-- Mapa (Rotacionado) -->
                <div class="page-break"></div>
                <div style="text-align: center; width: 100%;">
                    <!-- Width fixo para ajustar layout (A4 @ 96dpi approx 700-800px) -->
                    <img src="PLACEHOLDER_MAP_PATH" width="700">
                </div>
            </body>
            </html>
            """
            
            # Substituir URI do mapa
            import pathlib
            map_uri = pathlib.Path(map_image_path).as_uri()
            html = html.replace("PLACEHOLDER_MAP_PATH", map_uri)
            
            # 6. Exportação PDF
            doc = QTextDocument()
            doc.setHtml(html)
            
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            printer.setPageOrientation(QPageLayout.Portrait)
            # Margens (mm)
            printer.setPageMargins(10, 10, 10, 10, QPrinter.Millimeter)
            
            doc.print_(printer)
            
            # Cleanup
            if os.path.exists(map_image_path):
                os.remove(map_image_path)
                
            progress.setValue(100)
            self.iface.messageBar().pushMessage("Aqueduct", f"Orçamento salvo: {pdf_path}", level=0)
            
            if os.name == 'nt':
                os.startfile(pdf_path)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self.iface.mainWindow(), "Erro", f"Falha ao gerar orçamento: {e}")
        finally:
            progress.close()

    def generate_map_image(self, project):
        """Gera uma imagem temporária do layout do mapa usando a classe padronizada MapLayoutGenerator"""
        import tempfile
        from .gerar_layout_mapa import MapLayoutGenerator
        
        temp_path = os.path.join(tempfile.gettempdir(), "temp_map_aqueduct.png")
        
        # Gerar Layout Padronizado
        generator = MapLayoutGenerator(project)
        # standalone=False remove as margens internas da imagem, 
        # confiando que o documento PDF final terá as margens de 10mm.
        layout = generator.create_layout(area_layer=None, standalone=False) # Deixa auto-detectar
        
        # Exportar como Imagem
        exporter = QgsLayoutExporter(layout)
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 300
        exporter.exportToImage(temp_path, settings)
        
        # Rotacionar imagem para Portrait (90 graus)
        from qgis.PyQt.QtGui import QImage, QTransform
        img = QImage(temp_path)
        if not img.isNull():
            # Rotate 90 degrees clockwise
            transform = QTransform().rotate(90)
            img = img.transformed(transform)
            img.save(temp_path)
        
        return temp_path
