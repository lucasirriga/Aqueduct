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
        self.setWindowTitle("Aqueduct - Contabilizar Tubulacoes")
        self.resize(1100, 500)
        
        self.peca_manager = PecaManager()
        self.bom_manager = ProjectBOMManager()
        
        if not self.bom_manager.filepath:
             QMessageBox.warning(self, "Aviso", "Salve o projeto antes de continuar para que a lista de materiais seja vinculada.")
        
        self.layer = self.iface.activeLayer()
        self.data_rows = [] 
        
        self.setup_ui()
        self.process_layer()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Header info
        if self.layer and self.layer.type() == QgsMapLayerType.VectorLayer and self.layer.geometryType() == QgsWkbTypes.LineGeometry:
            lbl_layer = QLabel(f"<b>Camada Ativa:</b> {self.layer.name()}")
        else:
            lbl_layer = QLabel("<b style='color: red;'>Nenhuma camada de linha selecionada!</b> Selecione uma camada de tubulacao no painel de camadas.")
        layout.addWidget(lbl_layer)

        # Tabela
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Formato", "Diametro", "Comp. Total (m)", "Reserva (%)", 
            "Comp. Unidade (m)", "Qtd (Barras/Rolos)", "Peca no Catalogo"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.Stretch)
        
        layout.addWidget(self.table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        
        self.btn_add = QPushButton("Adicionar ao Orcamento")
        self.btn_add.clicked.connect(self.adicionar_ao_orcamento)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_add)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)

    def process_layer(self):
        if not self.layer or self.layer.type() != QgsMapLayerType.VectorLayer or self.layer.geometryType() != QgsWkbTypes.LineGeometry:
            return

        # Busca campo de diametro
        fields = [f.name() for f in self.layer.fields()]
        dn_field = next((f for f in fields if f.lower() in ['dn', 'diametro', 'diameter', 'diam']), None)
        
        if not dn_field:
            QMessageBox.critical(self, "Erro", "Campo de diametro (DN/Diametro) nao encontrado na camada selecionada.")
            return

        # Busca campo formato (opcional)
        format_field = next((f for f in fields if f.lower() == 'formato'), None)
        
        totais = {} # {(dn, formato): soma_comprimento}
        
        for feat in self.layer.getFeatures():
            dn = feat[dn_field]
            if dn is None: continue
            
            formato = "Barra"
            if format_field:
                val_f = feat[format_field]
                if val_f and str(val_f).strip().lower() == 'rolo':
                    formato = "Rolo"
            
            try:
                dn_val = str(dn)
                if dn_val.endswith('.0'): dn_val = dn_val[:-2]
            except:
                dn_val = str(dn)
                
            length = feat.geometry().length()
            key = (dn_val, formato)
            totais[key] = totais.get(key, 0) + length
            
        # Povoar Tabela
        self.table.setRowCount(len(totais))
        pecas_disponiveis = self.peca_manager.list_names()
        
        for i, ((dn, formato), comprimento) in enumerate(sorted(totais.items())):
            # 0. Formato
            self.table.setItem(i, 0, QTableWidgetItem(formato))
            self.table.item(i, 0).setFlags(Qt.ItemIsEnabled)
            
            # 1. Diametro
            self.table.setItem(i, 1, QTableWidgetItem(dn))
            self.table.item(i, 1).setFlags(Qt.ItemIsEnabled)
            
            # 2. Comprimento
            self.table.setItem(i, 2, QTableWidgetItem(f"{comprimento:.2f}"))
            self.table.item(i, 2).setFlags(Qt.ItemIsEnabled)
            
            # 3. Reserva Tecnica
            spin_reserva = QDoubleSpinBox()
            spin_reserva.setRange(0, 100)
            spin_reserva.setSuffix(" %")
            spin_reserva.setValue(5.0)
            spin_reserva.valueChanged.connect(lambda: self.update_row_calc(i))
            self.table.setCellWidget(i, 3, spin_reserva)

            # 4. Comp. Unidade (6m para Barra, variavel para Rolo)
            spin_unidade = QDoubleSpinBox()
            spin_unidade.setRange(0.1, 5000.0)
            spin_unidade.setSuffix(" m")
            if formato == "Barra":
                spin_unidade.setValue(6.0)
                spin_unidade.setEnabled(False)
            else:
                spin_unidade.setValue(100.0) # Padrao rolo 100m
            
            spin_unidade.valueChanged.connect(lambda: self.update_row_calc(i))
            self.table.setCellWidget(i, 4, spin_unidade)
            
            # 5. Quantidade (Label)
            label_qtd = QLabel("0")
            label_qtd.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(i, 5, label_qtd)
            
            # 6. Combobox Peca
            combo_pecas = QComboBox()
            combo_pecas.setEditable(True)
            combo_pecas.setInsertPolicy(QComboBox.NoInsert)
            
            pecas_filtradas = self.filtro_inteligente(dn, pecas_disponiveis)
            combo_pecas.addItems(pecas_filtradas)
            if not pecas_filtradas:
                combo_pecas.addItems(pecas_disponiveis)
            
            self.table.setCellWidget(i, 6, combo_pecas)
            
            # Guardar referencias
            self.data_rows.append({
                'dn': dn,
                'formato': formato,
                'length': comprimento,
                'spin_reserva': spin_reserva,
                'spin_unidade': spin_unidade,
                'label_qtd': label_qtd,
                'combo_pecas': combo_pecas
            })
            
            self.update_row_calc(i)

    def filtro_inteligente(self, dn, lista_completa):
        """
        Filtra a lista de pecas baseada no valor do DN (ex: '20').
        Busca '20mm', '20 mm', '20' no nome.
        """
        dn_str = str(dn).lower()
        # Regex p/ pegar variacoes: 20mm, 20 mm, 20.0, etc
        pattern = re.compile(rf"\b{re.escape(dn_str)}(\s?mm)?\b", re.IGNORECASE)
        
        match_pri = [] # Partidas fortes (ex: Tubo 20mm)
        match_sec = [] # Contem o numero mas talvez nao seja o principal (ex: Adaptador 20x25)
        
        for p in lista_completa:
            p_lower = p.lower()
            if pattern.search(p_lower):
                # Se contem 'tubo' ou 'tubulacao' e prioridade maxima
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
        unidade_m = data['spin_unidade'].value()
        
        comp_com_reserva = comprimento_total * (1 + (reserva / 100.0))
        qtd = math.ceil(comp_com_reserva / unidade_m)
        
        data['label_qtd'].setText(str(qtd))

    def adicionar_ao_orcamento(self):
        if not self.bom_manager.filepath:
            QMessageBox.critical(self, "Erro", "Caminho do projeto nao definido. Salve o projeto primeiro.")
            return

        confirm = QMessageBox.question(self, "Confirmar", "Deseja adicionar estes itens a lista de materiais?", QMessageBox.Yes | QMessageBox.No)
        if confirm != QMessageBox.Yes:
            return

        added_count = 0
        for data in self.data_rows:
            nome_peca = data['combo_pecas'].currentText()
            if not nome_peca or nome_peca == "":
                continue
                
            qtd = int(data['label_qtd'].text())
            if qtd <= 0:
                continue

            # Buscar dados da peca para preco
            dados_peca = self.peca_manager.get(nome_peca)
            if dados_peca:
                custo = dados_peca.get('custo', 0)
                lucro = dados_peca.get('lucro', 0)
                preco = custo * (1 + (lucro / 100.0))
                
                self.bom_manager.add_item(nome_peca, preco, qtd)
                added_count += 1
            else:
                # Caso o usuario tenha digitado um nome que nao esta no catalogo
                QMessageBox.warning(self, "Aviso", f"Peca '{nome_peca}' nao encontrada no catalogo. Ignorada.")

        if added_count > 0:
            QMessageBox.information(self, "Sucesso", f"{added_count} tipos de tubulacao adicionados ao orcamento!")
            self.accept()
        else:
            QMessageBox.warning(self, "Aviso", "Nenhum item valido foi adicionado.")

class ContabilizarTubosTool(AqueductTool):
    def initGui(self):
        # Usar um icone de tubulacao se existir, ou o mesmo de contabilizar
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_contabilizar_tubos.svg')
        if not os.path.exists(icon_path):
             icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_contabilizar.svg')
             
        self.action = QAction(QIcon(icon_path), 'Contabilizar Tubulacoes', self.iface.mainWindow())
        self.action.setToolTip("Calcula quantidade de barras ou rolos por diametro com reserva tecnica")
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)

    def run(self):
        layer = self.iface.activeLayer()
        if not layer or layer.type() != QgsMapLayerType.VectorLayer or layer.geometryType() != QgsWkbTypes.LineGeometry:
            QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Selecione uma camada de linhas (tubulacao) antes de abrir esta ferramenta.")
            return

        dlg = ContabilizarTubosDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()
