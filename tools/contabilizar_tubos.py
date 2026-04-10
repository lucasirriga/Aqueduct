import os
import math
import re
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QMessageBox, QLabel, 
    QDoubleSpinBox, QComboBox, QHeaderView
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsProject, QgsWkbTypes

from .ferramenta_base import AqueductTool
from .lista_materiais import ProjectBOMManager
from .gerenciar_pecas import PecaManager

class ContabilizarTubosDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle("Aqueduct - Contabilizar Tubulações")
        self.resize(900, 500)
        
        self.peca_manager = PecaManager()
        self.bom_manager = ProjectBOMManager()
        
        if not self.bom_manager.filepath:
             QMessageBox.warning(self, "Aviso", "Salve o projeto antes de continuar para que a lista de materiais seja vinculada.")
        
        self.layer = self.iface.activeLayer()
        self.data_rows = [] # Armazena os dados processados: {dn: {length: x, widget_reserva: w, widget_combo: c, label_barras: l}}
        
        self.setup_ui()
        self.process_layer()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Header info
        if self.layer and self.layer.type() == QgsMapLayerType.VectorLayer and self.layer.geometryType() == QgsWkbTypes.LineGeometry:
            lbl_layer = QLabel(f"<b>Camada Ativa:</b> {self.layer.name()}")
        else:
            lbl_layer = QLabel("<b style='color: red;'>Nenhuma camada de linha selecionada!</b> Selecione uma camada de tubulação no painel de camadas.")
        layout.addWidget(lbl_layer)

        # Tabela
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "Diâmetro (Layer)", "Comp. Total (m)", "Reserva (%)", "Qtd Barras (6m)", "Peça no Catálogo"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        
        layout.addWidget(self.table)
        
        # Botões
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_add = QPushButton("Adicionar ao Orçamento")
        self.btn_add.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 5px;")
        self.btn_add.clicked.connect(self.adicionar_ao_orcamento)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_add)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def process_layer(self):
        if not self.layer or self.layer.type() != QgsMapLayerType.VectorLayer or self.layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        # Busca campo de diâmetro
        fields = [f.name() for f in self.layer.fields()]
        dn_field = next((f for f in fields if f.lower() in ['dn', 'diametro', 'diameter', 'diâm']), None)
        
        if not dn_field:
            QMessageBox.critical(self, "Erro", "Campo de diâmetro (DN/Diâmetro) não encontrado na camada selecionada.")
            return

        totais_dn = {} # {valor_dn: soma_comprimento}
        
        for feat in self.layer.getFeatures():
            dn = feat[dn_field]
            if dn is None: continue
            
            # Tentar normalizar DN
            try:
                dn_val = str(dn)
                # Se for número, tenta tirar o .0 (ex: 20.0 -> 20)
                if dn_val.endswith('.0'): dn_val = dn_val[:-2]
            except:
                dn_val = str(dn)
                
            length = feat.geometry().length()
            totais_dn[dn_val] = totais_dn.get(dn_val, 0) + length
            
        # Povoar Tabela
        self.table.setRowCount(len(totais_dn))
        pecas_disponiveis = self.peca_manager.list_names()
        
        for i, (dn, comprimento) in enumerate(sorted(totais_dn.items())):
            # 0. Diâmetro
            self.table.setItem(i, 0, QTableWidgetItem(dn))
            self.table.item(i, 0).setFlags(Qt.ItemIsEnabled)
            
            # 1. Comprimento
            self.table.setItem(i, 1, QTableWidgetItem(f"{comprimento:.2f}"))
            self.table.item(i, 1).setFlags(Qt.ItemIsEnabled)
            
            # 2. Reserva Técnica
            spin_reserva = QDoubleSpinBox()
            spin_reserva.setRange(0, 100)
            spin_reserva.setSuffix(" %")
            spin_reserva.setValue(5.0) # Padrão 5%
            spin_reserva.valueChanged.connect(lambda: self.update_row_calc(i))
            self.table.setCellWidget(i, 2, spin_reserva)
            
            # 3. Qtd Barras (Label/Item)
            label_barras = QLabel("0")
            label_barras.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(i, 3, label_barras)
            
            # 4. Combobox Peça (Filtro Inteligente)
            combo_pecas = QComboBox()
            combo_pecas.setEditable(True)
            combo_pecas.setInsertPolicy(QComboBox.NoInsert)
            
            # Logica de filtro inteligente
            pecas_filtradas = self.filtro_inteligente(dn, pecas_disponiveis)
            combo_pecas.addItems(pecas_filtradas)
            # Se não achou nada filtrado, mostra todas
            if not pecas_filtradas:
                combo_pecas.addItems(pecas_disponiveis)
            
            self.table.setCellWidget(i, 4, combo_pecas)
            
            # Guardar referências para cálculo e salvamento
            self.data_rows.append({
                'dn': dn,
                'length': comprimento,
                'spin_reserva': spin_reserva,
                'label_barras': label_barras,
                'combo_pecas': combo_pecas
            })
            
            # Calcular inicial
            self.update_row_calc(i)

    def filtro_inteligente(self, dn, lista_completa):
        """
        Filtra a lista de peças baseada no valor do DN (ex: '20').
        Busca '20mm', '20 mm', '20' no nome.
        """
        dn_str = str(dn).lower()
        # Regex p/ pegar variações: 20mm, 20 mm, 20.0, etc
        pattern = re.compile(rf"\b{re.escape(dn_str)}(\s?mm)?\b", re.IGNORECASE)
        
        match_pri = [] # Partidas fortes (ex: Tubo 20mm)
        match_sec = [] # Contém o número mas talvez não seja o principal (ex: Adaptador 20x25)
        
        for p in lista_completa:
            p_lower = p.lower()
            if pattern.search(p_lower):
                # Se contém 'tubo' ou 'tubulação' é prioridade máxima
                if 'tubo' in p_lower or 'tubula' in p_lower:
                    match_pri.insert(0, p)
                else:
                    match_pri.append(p)
            elif dn_str in p_lower: 
                match_sec.append(p)
                
        return match_pri + match_sec

    def update_row_calc(self, row_index):
        if row_index >= len(self.data_rows): return
        
        data = self.data_rows[row_index]
        reserva = data['spin_reserva'].value()
        comprimento_total = data['length']
        
        comp_com_reserva = comprimento_total * (1 + (reserva / 100.0))
        qtd_barras = math.ceil(comp_com_reserva / 6.0)
        
        data['label_barras'].setText(str(qtd_barras))

    def adicionar_ao_orcamento(self):
        if not self.bom_manager.filepath:
            QMessageBox.critical(self, "Erro", "Caminho do projeto não definido. Salve o projeto primeiro.")
            return

        confirm = QMessageBox.question(self, "Confirmar", "Deseja adicionar estes itens à lista de materiais?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        added_count = 0
        for data in self.data_rows:
            nome_peca = data['combo_pecas'].currentText()
            if not nome_peca or nome_peca == "":
                continue
                
            qtd = int(data['label_barras'].text())
            if qtd <= 0:
                continue

            # Buscar dados da peça para preço
            dados_peca = self.peca_manager.get(nome_peca)
            if dados_peca:
                custo = dados_peca.get('custo', 0)
                lucro = dados_peca.get('lucro', 0)
                preco = custo * (1 + (lucro / 100.0))
                
                self.bom_manager.add_item(nome_peca, preco, qtd)
                added_count += 1
            else:
                # Caso o usuário tenha digitado um nome que não está no catálogo
                # (O combo é editável mas com QComboBox.NoInsert, mas ainda pode ter texto manual)
                QMessageBox.warning(self, "Aviso", f"Peça '{nome_peca}' não encontrada no catálogo. Ignorada.")

        if added_count > 0:
            QMessageBox.information(self, "Sucesso", f"{added_count} tipos de tubulação adicionados ao orçamento!")
            self.accept()
        else:
            QMessageBox.warning(self, "Aviso", "Nenhum item válido foi adicionado.")

class ContabilizarTubosTool(AqueductTool):
    def initGui(self):
        # Usar um ícone de tubulação se existir, ou o mesmo de contabilizar
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_tubos.svg')
        if not os.path.exists(icon_path):
             icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_contabilizar.svg')
             
        self.action = QAction(QIcon(icon_path), 'Contabilizar Tubulações (Barras 6m)', self.iface.mainWindow())
        self.action.setToolTip("Calcula quantidade de barras de 6m por diâmetro com reserva técnica")
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsMapLayerType.VectorLayer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Selecione uma camada de linhas (tubulação) antes de abrir esta ferramenta.")
            return

        dlg = ContabilizarTubosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
