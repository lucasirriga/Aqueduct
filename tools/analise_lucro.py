from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QLabel, QPushButton, QMessageBox, QWidget, 
    QHeaderView, QFrame, QAbstractItemView, QFileDialog
)
from qgis.PyQt.QtGui import QIcon, QColor, QFont
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import QgsProject
import os
import json
import pathlib
import datetime

from .ferramenta_base import AqueductTool
from .gerenciar_pecas import PecaManager
from .gerenciar_servicos import ServicoManager
from .gerenciar_blocos import BlocoManager
from .lista_materiais import ProjectBOMManager
from .lista_servicos import ProjectServiceListManager

class AnaliseLucroDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Análise de Lucro e Rentabilidade")
        self.resize(1100, 700)
        
        # Managers
        self.peca_mgr = PecaManager()
        self.serv_mgr = ServicoManager()
        self.bloco_mgr = BlocoManager()
        self.bom_project = ProjectBOMManager()
        self.serv_project = ProjectServiceListManager()
        
        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Cabeçalho
        header = QLabel("Resumo de Rentabilidade do Projeto")
        header.setStyleSheet("font-size: 16pt; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(header)
        
        # Tabela Principal
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Item", "Categoria", "Qtd", "Custo Unit.", 
            "Margem %", "Venda Unit.", "Lucro Unit.", "Lucro Total", 
            "Impacto Lucro %", "Impacto Orç. %"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        # Conectar sinal de edição
        self.table.itemChanged.connect(self._on_cell_changed)
        layout.addWidget(self.table)
        
        # Painel de Resumo (Cards)
        summary_panel = QHBoxLayout()
        summary_panel.setSpacing(15)
        
        self.card_custo = self._create_card(
            "Custo Total", "R$ 0,00", "#e74c3c", 
            "Total investido em peças e serviços."
        )
        self.card_venda = self._create_card(
            "Venda Total", "R$ 0,00", "#3498db", 
            "Valor bruto a ser pago pelo cliente."
        )
        self.card_lucro = self._create_card(
            "Lucro Total", "R$ 0,00", "#2ecc71", 
            "Saldo líquido estimado do projeto."
        )
        self.card_margem = self._create_card(
            "Margem Global", "0,0%", "#f1c40f", 
            "Sua rentabilidade média final."
        )
        
        summary_panel.addWidget(self.card_custo)
        summary_panel.addWidget(self.card_venda)
        summary_panel.addWidget(self.card_lucro)
        summary_panel.addWidget(self.card_margem)
        
        layout.addLayout(summary_panel)
        
        # Botões
        btn_layout = QHBoxLayout()
        btn_refresh = QPushButton("Atualizar Dados")
        btn_refresh.clicked.connect(self.load_data)
        
        self.btn_apply = QPushButton("Aplicar ao Orçamento")
        self.btn_apply.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 5px;")
        self.btn_apply.clicked.connect(self.on_apply_to_budget)
        
        self.btn_pdf = QPushButton(" Gerar Relatório PDF")
        self.btn_pdf.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 5px;")
        self.btn_pdf.clicked.connect(self.on_generate_pdf)
        
        btn_close = QPushButton("Fechar")
        btn_close.clicked.connect(self.close)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_refresh)
        btn_layout.addWidget(self.btn_apply)
        btn_layout.addWidget(self.btn_pdf)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def _create_card(self, title, value, color, description):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        # Efeito de card moderno com borda colorida e fundo escuro
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: #1e272e;
                border-radius: 12px;
                border: 1px solid #34495e;
                border-left: 5px solid {color};
                padding: 12px;
            }}
        """)
        
        vbox = QVBoxLayout()
        vbox.setSpacing(2)
        
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet(f"color: {color}; font-size: 8pt; font-weight: bold; text-transform: uppercase; border: none;")
        
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(f"color: white; font-size: 16pt; font-weight: bold; border: none; margin-top: 5px;")
        lbl_value.setAlignment(Qt.AlignLeft)
        
        lbl_desc = QLabel(description)
        lbl_desc.setStyleSheet("color: #95a5a6; font-size: 8pt; border: none; margin-top: 5px;")
        lbl_desc.setWordWrap(True)
        
        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)
        vbox.addStretch()
        vbox.addWidget(lbl_desc)
        frame.setLayout(vbox)
        
        # Guardar referência para atualizar valor depois
        if not hasattr(self, 'cards'): self.cards = {}
        self.cards[title] = lbl_value
        
        return frame

    def load_data(self):
        # 1. Consolidar itens
        # Estrutura: { item_id: {nome, cat, qtd, custo, venda, lucro_unit, lucro_total} }
        consolidated = {}

        # --- A. Peças Avulsas ---
        for item in self.bom_project.items:
            nome = item['nome']
            qty = item['quantidade']
            venda = item['preco_unitario']
            
            # Buscar custo no catálogo
            peca_data = self.peca_mgr.get(nome)
            custo = peca_data.get('custo', 0.0) if peca_data else 0.0
            
            self._add_to_consolidated(consolidated, nome, "Peça", qty, custo, venda)

        # --- B. Blocos (Explodir) ---
        for pb in self.bom_project.project_blocos:
            b_nome = pb['nome']
            b_qtd = pb['quantidade']
            
            itens_bloco = self.bloco_mgr.get(b_nome)
            if itens_bloco:
                for ib in itens_bloco:
                    p_nome = ib['nome']
                    p_qtd = ib['quantidade'] * b_qtd
                    
                    # Buscar dados no catálogo
                    peca_data = self.peca_mgr.get(p_nome)
                    if peca_data:
                        custo = peca_data.get('custo', 0.0)
                        lucro_perc = peca_data.get('lucro', 0.0)
                        venda = custo * (1+lucro_perc/100)
                    else:
                        custo = 0.0
                        venda = 0.0
                        
                    self._add_to_consolidated(consolidated, p_nome, "Peça (Kit)", p_qtd, custo, venda)

        # --- C. Serviços ---
        for serv in self.serv_project.items:
            desc = serv['descricao']
            qty = serv['quantidade']
            venda = serv['valor_unitario']
            
            # Buscar custo no catálogo
            serv_data = self.serv_mgr.get(desc)
            # Se o catálogo tiver custo, usamos. Caso contrário, custo = venda (lucro 0) ou custo = 0 (lucro total)?
            # Para serviços sem custo definido, assumimos que 80% é lucro se não houver campo custo (legado)
            if serv_data and 'custo' in serv_data:
                custo = serv_data['custo']
            else:
                custo = venda * 0.5 # Fallback conservador para serviços antigos: 50% de custo
            
            self._add_to_consolidated(consolidated, desc, "Serviço", qty, custo, venda)

        # 2. Calcular totais globais
        total_custo_proj = 0.0
        total_venda_proj = 0.0
        total_lucro_proj = 0.0
        
        for item in consolidated.values():
            total_custo_proj += item['custo'] * item['qtd']
            total_venda_proj += item['venda'] * item['qtd']
            total_lucro_proj += item['lucro_total']

        # 3. Preencher tabela
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        row = 0
        for item_nome, data in sorted(consolidated.items(), key=lambda x: x[1]['lucro_total'], reverse=True):
            self.table.insertRow(row)
            
            # Impactos
            impacto_lucro = (data['lucro_total'] / total_lucro_proj * 100) if total_lucro_proj > 0 else 0
            impacto_venda = (data['venda'] * data['qtd'] / total_venda_proj * 100) if total_venda_proj > 0 else 0
            
            # Margem
            margem = ((data['venda'] / data['custo']) - 1) * 100 if data['custo'] > 0 else 0
            
            # Itens da linha (ReadOnly por padrão, Margem editável)
            def create_readonly(text):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                return it

            self.table.setItem(row, 0, create_readonly(item_nome))
            self.table.setItem(row, 1, create_readonly(data['cat']))
            self.table.setItem(row, 2, create_readonly(f"{data['qtd']:.2f}"))
            self.table.setItem(row, 3, create_readonly(f"R$ {data['custo']:.2f}"))
            
            # Margem (EDITÁVEL)
            item_margem = QTableWidgetItem(f"{margem:.1f}")
            item_margem.setBackground(QColor("#34495e")) # Destaque para edição
            self.table.setItem(row, 4, item_margem)
            
            self.table.setItem(row, 5, create_readonly(f"R$ {data['venda']:.2f}"))
            
            # Lucro Unit
            lucro_unit = data['venda'] - data['custo']
            item_lucro_unit = create_readonly(f"R$ {lucro_unit:.2f}")
            if lucro_unit < 0: item_lucro_unit.setForeground(QColor("red"))
            self.table.setItem(row, 6, item_lucro_unit)
            
            # Lucro Total
            item_lucro_tot = create_readonly(f"R$ {data['lucro_total']:.2f}")
            item_lucro_tot.setFont(QFont("", -1, QFont.Bold))
            if data['lucro_total'] < 0: item_lucro_tot.setForeground(QColor("red"))
            else: item_lucro_tot.setForeground(QColor("#2ecc71"))
            self.table.setItem(row, 7, item_lucro_tot)
            
            # Impacto Lucro
            self.table.setItem(row, 8, create_readonly(f"{impacto_lucro:.1f}%"))
            
            # Impacto Orçamento
            self.table.setItem(row, 9, create_readonly(f"{impacto_venda:.1f}%"))
            
            row += 1
        self.table.blockSignals(False)

        # 4. Atualizar cards
        self.cards["Custo Total"].setText(f"R$ {total_custo_proj:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.cards["Venda Total"].setText(f"R$ {total_venda_proj:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.cards["Lucro Total"].setText(f"R$ {total_lucro_proj:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        margem_global = (total_lucro_proj / total_venda_proj * 100) if total_venda_proj > 0 else 0
        self.cards["Margem Global"].setText(f"{margem_global:.1f}%")
    def _add_to_consolidated(self, consolidated, nome, cat, qty, custo, venda):
        if nome in consolidated:
            consolidated[nome]['qtd'] += qty
        else:
            consolidated[nome] = {
                'nome': nome,
                'cat': cat,
                'qtd': qty,
                'custo': custo,
                'venda': venda,
                'lucro_total': (venda - custo) * qty
            }

    def _on_cell_changed(self, item):
        if item.column() != 4: return # Apenas margem
        
        try:
            row = item.row()
            nova_margem = float(item.text().replace(',', '.'))
            
            # Pegar custo (está na coluna 3 mas formatado)
            # Para evitar erros de string, vamos forçar um reload síncrono ou recalcular
            # Melhor: Usar um cache da linha
            self._recalcular_linha(row, nova_margem)
            self._recalcular_cards()
        except Exception as e:
            print(f"Erro ao editar margem: {e}")

    def _recalcular_linha(self, row, margem_perc):
        self.table.blockSignals(True)
        try:
            custo_str = self.table.item(row, 3).text().replace('R$ ', '').replace(',', '.')
            custo = float(custo_str)
            qty = float(self.table.item(row, 2).text())
            
            nova_venda = custo * (1 + margem_perc / 100)
            novo_lucro_unit = nova_venda - custo
            novo_lucro_tot = novo_lucro_unit * qty
            
            self.table.item(row, 5).setText(f"R$ {nova_venda:.2f}")
            self.table.item(row, 6).setText(f"R$ {novo_lucro_unit:.2f}")
            self.table.item(row, 7).setText(f"R$ {novo_lucro_tot:.2f}")
            
            # Cor
            if novo_lucro_unit < 0: self.table.item(row, 6).setForeground(QColor("red"))
            else: self.table.item(row, 6).setForeground(QColor("white"))
            
            if novo_lucro_tot < 0: self.table.item(row, 7).setForeground(QColor("red"))
            else: self.table.item(row, 7).setForeground(QColor("#2ecc71"))
            
        finally:
            self.table.blockSignals(False)

    def _recalcular_cards(self):
        total_custo = 0.0
        total_venda = 0.0
        total_lucro = 0.0
        
        for r in range(self.table.rowCount()):
            qty = float(self.table.item(r, 2).text())
            custo = float(self.table.item(r, 3).text().replace('R$ ', '').replace(',', '.'))
            venda = float(self.table.item(r, 5).text().replace('R$ ', '').replace(',', '.'))
            
            total_custo += custo * qty
            total_venda += venda * qty
            total_lucro += (venda - custo) * qty

        self.cards["Custo Total"].setText(f"R$ {total_custo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.cards["Venda Total"].setText(f"R$ {total_venda:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        self.cards["Lucro Total"].setText(f"R$ {total_lucro:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        margem_global = (total_lucro / total_venda * 100) if total_venda > 0 else 0
        self.cards["Margem Global"].setText(f"{margem_global:.1f}%")

    def on_apply_to_budget(self):
        reply = QMessageBox.question(self, "Confirmar", 
            "Deseja aplicar estas novas margens ao orçamento do projeto?\n\nStandalone items (Peças/Serviços) serão atualizados. Itens dentro de Kits precisam ser atualizados no Catálogo Global.",
            QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.No: return
        
        sync_global = QMessageBox.question(self, "Catálogo Global", 
            "Deseja salvar as novas margens também no Catálogo Global (para futuros projetos)?",
            QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

        updated_standalone = 0
        updated_global = 0
        
        for r in range(self.table.rowCount()):
            nome = self.table.item(r, 0).text()
            cat = self.table.item(r, 1).text()
            margem = float(self.table.item(r, 4).text().replace(',', '.'))
            venda = float(self.table.item(r, 5).text().replace('R$ ', '').replace(',', '.'))
            custo = float(self.table.item(r, 3).text().replace('R$ ', '').replace(',', '.'))

            # 1. Update Project Lists (BOM / Services)
            if "Peça" in cat: # Peça or Peça (Kit)
                # Standalone (Project-only update)
                if cat == "Peça":
                    for idx, item in enumerate(self.bom_project.items):
                        if item['nome'] == nome:
                            self.bom_project.update_item(idx, item['quantidade'], venda, save=False)
                            updated_standalone += 1
                
                # Global Catalog Sync
                if sync_global:
                    peca_data = self.peca_mgr.get(nome)
                    if peca_data:
                        peca_data['lucro'] = margem
                        self.peca_mgr.add_update(nome, peca_data)
                        updated_global += 1

            elif cat == "Serviço":
                # Project update
                for idx, serv in enumerate(self.serv_project.items):
                    if serv['descricao'] == nome:
                        self.serv_project.update_item(idx, serv['quantidade'], venda)
                        updated_standalone += 1
                
                # Global Catalog Sync
                if sync_global:
                    serv_data = self.serv_mgr.get(nome)
                    if serv_data:
                        serv_data['lucro'] = margem
                        serv_data['custo'] = custo
                        serv_data['valor'] = venda
                        self.serv_mgr.add_update(nome, serv_data)
                        updated_global += 1

        self.bom_project.save()
        QMessageBox.information(self, "Sucesso", 
            f"Alterações aplicadas!\n\nItens atualizados no projeto: {updated_standalone}\nItens atualizados no catálogo: {updated_global}")
        self.load_data()

    def on_generate_pdf(self):
        project = QgsProject.instance()
        base_name = project.baseName() or 'analise_lucro'
        default_name = f"{base_name}_rentabilidade.pdf"
        
        pdf_path, _ = QFileDialog.getSaveFileName(
            self, 'Salvar Relatório de Lucro',
            os.path.join(project.homePath(), default_name),
            'Arquivos PDF (*.pdf)'
        )
        if not pdf_path: return
        if not pdf_path.endswith('.pdf'): pdf_path += '.pdf'

        try:
            # 1. Carregar Dados de Cabeçalho (Padrão Aqueduct)
            info_path = os.path.join(project.homePath(), 'dados_projeto.json')
            info = {}
            if os.path.exists(info_path):
                with open(info_path, 'r', encoding='utf-8') as f:
                    info = json.load(f)

            # 2. Logo
            img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'img')
            logo_path = os.path.join(img_dir, 'logo tocantins agropecuária ltda.png')
            logo_html = ""
            if os.path.exists(logo_path):
                uri = pathlib.Path(logo_path).as_uri()
                logo_html = f'<div style="text-align:center;"><img src="{uri}" width="200"></div>'

            # 3. Resumo (Cards)
            custo_tot = self.cards["Custo Total"].text()
            venda_tot = self.cards["Venda Total"].text()
            lucro_tot = self.cards["Lucro Total"].text()
            margem_glob = self.cards["Margem Global"].text()

            # 4. Tabela
            rows_html = ""
            for r in range(self.table.rowCount()):
                row_data = [self.table.item(r, c).text() for c in range(10)]
                bg = "#f9f9f9" if r % 2 == 0 else "#ffffff"
                
                # Formatação de cores para lucro
                lucro_color = "#2ecc71" if "R$ -" not in row_data[7] else "#e74c3c"
                
                rows_html += f"""
                <tr style="background-color: {bg};">
                    <td style="padding: 5px;">{row_data[0]}</td>
                    <td style="padding: 5px; text-align: center;">{row_data[2]}</td>
                    <td style="padding: 5px; text-align: right;">{row_data[3]}</td>
                    <td style="padding: 5px; text-align: center; font-weight: bold;">{row_data[4]}%</td>
                    <td style="padding: 5px; text-align: right;">{row_data[5]}</td>
                    <td style="padding: 5px; text-align: right; font-weight: bold; color: {lucro_color};">{row_data[7]}</td>
                </tr>
                """

            # 5. Assemble HTML
            html = f"""
            <html>
            <head>
                <style>
                    @page {{ margin: 15mm; }}
                    body {{ 
                        font-family: 'Helvetica', 'Arial', sans-serif; 
                        color: #2d3436; 
                        line-height: 1.4;
                        margin: 0;
                        padding: 0;
                    }}
                    .header {{ 
                        border-bottom: 3px solid #27ae60; 
                        padding-bottom: 15px; 
                        margin-bottom: 25px; 
                    }}
                    .title {{ 
                        text-align: center; 
                        color: #27ae60; 
                        font-size: 24pt; 
                        font-weight: bold; 
                        margin-top: 10px;
                    }}
                    .info-table {{ 
                        width: 100%; 
                        margin-bottom: 25px; 
                        font-size: 10pt; 
                        background: #f8f9fa;
                        padding: 10px;
                        border-radius: 5px;
                    }}
                    
                    /* Cards de Resumo */
                    .summary-container {{
                        width: 100%;
                        margin-bottom: 30px;
                        display: table;
                        border-spacing: 10px 0;
                    }}
                    .card {{
                        display: table-cell;
                        width: 25%;
                        padding: 15px;
                        border-radius: 10px;
                        color: white;
                        text-align: left;
                        vertical-align: top;
                    }}
                    .card-title {{ font-size: 8pt; font-weight: bold; text-transform: uppercase; opacity: 0.9; }}
                    .card-value {{ font-size: 15pt; font-weight: bold; margin: 5px 0; }}
                    .card-desc {{ font-size: 7pt; opacity: 0.8; line-height: 1.1; }}
                    
                    /* Cores dos Cards */
                    .custo {{ background-color: #c0392b; border-bottom: 4px solid #962d22; }}
                    .venda {{ background-color: #2980b9; border-bottom: 4px solid #1f618d; }}
                    .lucro {{ background-color: #27ae60; border-bottom: 4px solid #1e8449; }}
                    .margem {{ background-color: #d35400; border-bottom: 4px solid #a04000; }}

                    /* Tabela de Dados */
                    .data-table {{ 
                        width: 100%; 
                        border-collapse: collapse; 
                        font-size: 9pt; 
                        margin-top: 10px;
                    }}
                    .data-table th {{ 
                        background: #27ae60; 
                        color: white; 
                        padding: 10px; 
                        text-align: left;
                        border-bottom: 2px solid #1e8449;
                    }}
                    .data-table td {{ 
                        padding: 8px; 
                        border-bottom: 1px solid #dfe6e9; 
                    }}
                    .footer {{ 
                        text-align: center; 
                        font-size: 8pt; 
                        color: #636e72; 
                        margin-top: 40px; 
                        border-top: 1px solid #dfe6e9;
                        padding-top: 15px;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    {logo_html}
                    <div class="title">Relatório de Rentabilidade Financeira</div>
                </div>

                <table class="info-table">
                    <tr>
                        <td width="15%"><b>Cliente:</b></td>
                        <td width="35%">{info.get('cliente', '-')}</td>
                        <td width="15%"><b>Localidade:</b></td>
                        <td width="35%">{info.get('local', '-')}</td>
                    </tr>
                    <tr>
                        <td><b>Projeto:</b></td>
                        <td>{base_name}</td>
                        <td><b>Emissão:</b></td>
                        <td>{datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}</td>
                    </tr>
                </table>

                <table width="100%" cellspacing="10" cellpadding="0" style="margin-bottom: 20px;">
                    <tr>
                        <td class="card custo" width="25%">
                            <div class="card-title">Custo Total</div>
                            <div class="card-value">{custo_tot}</div>
                            <div class="card-desc">Total investido em materiais e serviços.</div>
                        </td>
                        <td class="card venda" width="25%">
                            <div class="card-title">Venda Total</div>
                            <div class="card-value">{venda_tot}</div>
                            <div class="card-desc">Valor bruto orçado para o cliente.</div>
                        </td>
                        <td class="card lucro" width="25%">
                            <div class="card-title">Lucro Total</div>
                            <div class="card-value">{lucro_tot}</div>
                            <div class="card-desc">Saldo líquido estimado do projeto.</div>
                        </td>
                        <td class="card margem" width="25%">
                            <div class="card-title">Margem Global</div>
                            <div class="card-value">{margem_glob}</div>
                            <div class="card-desc">Rentabilidade média real do orçamento.</div>
                        </td>
                    </tr>
                </table>

                <table class="data-table">
                    <thead>
                        <tr>
                            <th width="40%">Item / Componente</th>
                            <th style="text-align: center;">Qtd</th>
                            <th style="text-align: right;">Custo Unit.</th>
                            <th style="text-align: center;">Margem</th>
                            <th style="text-align: right;">Venda Unit.</th>
                            <th style="text-align: right;">Lucro Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>

                <div class="footer">
                    <b>Tocantins Agropecuária Ltda.</b><br>
                    <i>Este relatório é uma ferramenta de simulação financeira e deve ser validado com o Catálogo Global.</i><br>
                    Gerado automaticamente pelo Módulo Aqueduct Strategy.
                </div>
            </body>
            </html>
            """

            # 6. Gerar PDF
            from qgis.PyQt.QtGui import QTextDocument, QPageLayout, QPageSize
            from qgis.PyQt.QtPrintSupport import QPrinter

            doc = QTextDocument()
            doc.setHtml(html)
            
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(pdf_path)
            printer.setPageSize(QPageSize(QPageSize.A4))
            # O usuário pediu RETRATO
            printer.setPageOrientation(QPageLayout.Portrait)
            # Zerar margens no printer (o HTML já cuida se necessário ou usamos default)
            doc.print_(printer)

            QMessageBox.information(self, "Sucesso", f"Relatório salvo com sucesso em:\n{pdf_path}")
            if os.name == 'nt':
                os.startfile(pdf_path)

        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao gerar relatório PDF: {e}")

class AnaliseLucroTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_lucro.svg')
        # Se icone não existir, usar um padrão do QGIS ou deixar sem
        self.action = QAction(QIcon(icon_path), 'Análise de Lucro', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        if not QgsProject.instance().homePath():
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto QGIS antes de realizar a análise.")
            return
            
        self.dlg = AnaliseLucroDialog(self.iface.mainWindow())
        self.dlg.show()
