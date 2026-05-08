import os
import math
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, 
    QPushButton, QMessageBox, QCheckBox, QGroupBox, QLabel,
    QListWidget, QAbstractItemView, QLineEdit, QHBoxLayout
)
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsMapLayerType, QgsProject, QgsWkbTypes, QgsVectorLayer

from .ferramenta_base import AqueductTool
from .lista_materiais import ProjectBOMManager
from .gerenciar_pecas import PecaManager

class SelecaoMaterialDialog(QDialog):
    """
    Diálogo auxiliar para selecionar um material do catálogo global
    que corresponde a um item detectado (ex: Tubo DN 50).
    """
    def __init__(self, manager, termo_sugerido, titulo, descricao, qtd, unidade, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle(titulo)
        self.resize(500, 400)
        
        self.selected_material_name = None
        
        layout = QVBoxLayout()
        
        # Info
        lbl_info = QLabel(f"<b>Item Detectado:</b> {descricao}<br>"
                          f"<b>Quantidade Calculada:</b> {qtd} {unidade}")
        layout.addWidget(lbl_info)
        
        layout.addWidget(QLabel("Selecione o material correspondente no catálogo:"))
        
        # Filtro
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filtrar:"))
        self.edit_filter = QLineEdit()
        self.edit_filter.setText(termo_sugerido)
        self.edit_filter.textChanged.connect(self.refresh_list)
        filter_layout.addWidget(self.edit_filter)
        layout.addLayout(filter_layout)
        
        # Lista
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        layout.addWidget(self.list_widget)
        
        # Botões
        btn_layout = QHBoxLayout()
        self.btn_ok = QPushButton("Confirmar e Adicionar")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_skip = QPushButton("Ignorar este Item")
        self.btn_skip.clicked.connect(self.reject)
        
        btn_layout.addWidget(self.btn_skip)
        btn_layout.addWidget(self.btn_ok)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
        
        self.refresh_list()
        
    def refresh_list(self):
        self.list_widget.clear()
        termo = self.edit_filter.text().lower()
        all_names = self.manager.list_names()
        
        for name in all_names:
            if termo in name.lower():
                self.list_widget.addItem(name)

    def accept(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Aviso", "Selecione um material ou clique em Ignorar.")
            return
        
        self.selected_material_name = selected[0].text()
        super().accept()


class ContabilizarMateriaisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Aqueduct - Contabilizar Materiais")
        self.resize(450, 250)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        group = QGroupBox("Seleção de Camadas")
        form = QFormLayout()
        
        self.combo_tubos = QComboBox()
        self.combo_mangueiras = QComboBox()
        self.combo_emissores = QComboBox()
        
        self.populate_layers()
        
        form.addRow("Camada de Tubulação (Linha):", self.combo_tubos)
        form.addRow("Camada de Mangueiras (Linha):", self.combo_mangueiras)
        form.addRow("Camada de Emissores (Ponto):", self.combo_emissores)
        
        group.setLayout(form)
        layout.addWidget(group)
        
        self.btn_run = QPushButton("Processar e Contabilizar")
        self.btn_run.clicked.connect(self.accept)
        layout.addWidget(self.btn_run)
        
        self.setLayout(layout)
        
    def populate_layers(self):
        layers = list(QgsProject.instance().mapLayers().values())
        
        # Adicionar opção vazia
        self.combo_tubos.addItem("- Selecionar -", None)
        self.combo_mangueiras.addItem("- Selecionar -", None)
        self.combo_emissores.addItem("- Selecionar -", None)
        
        for layer in layers:
            if layer.type() != QgsMapLayerType.VectorLayer:
                continue
                
            geo_type = layer.geometryType()
            
            # Linhas (Tubos e Mangueiras)
            if geo_type == QgsWkbTypes.LineGeometry:
                self.combo_tubos.addItem(layer.name(), layer)
                self.combo_mangueiras.addItem(layer.name(), layer)
                
            # Pontos (Emissores)
            elif geo_type == QgsWkbTypes.PointGeometry:
                self.combo_emissores.addItem(layer.name(), layer)

    def get_layers(self):
        return {
            'tubos': self.combo_tubos.currentData(),
            'mangueiras': self.combo_mangueiras.currentData(),
            'emissores': self.combo_emissores.currentData()
        }

class ContabilizarMateriaisTool(AqueductTool):
    def initGui(self):
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'icons', 'icone_contabilizar_materiais.svg')
        self.action = QAction(QIcon(icon_path), 'Contabilizar Materiais Auto', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        
        self.iface.addPluginToMenu('&Aqueduct', self.action)
        if self.toolbar:
            self.toolbar.addAction(self.action)
        else:
            self.iface.addToolBarIcon(self.action)
            
    def run(self):
        dlg = ContabilizarMateriaisDialog(self.iface.mainWindow())
        if not dlg.exec_():
            return
            
        layers = dlg.get_layers()
        
        peca_manager = PecaManager()
        project_bom = ProjectBOMManager()
        
        if not project_bom.filepath:
             QMessageBox.warning(self.iface.mainWindow(), "Aviso", "Salve o projeto antes de continuar.")
             return
             
        items_added = 0
        
        # 1. Processar Tubos
        layer_tubos = layers['tubos']
        if layer_tubos:
            # Agrupar por DN ou Diametro
            # Tentar achar campo DN
            fields = [f.name() for f in layer_tubos.fields()]
            dn_field = next((f for f in fields if f.lower() in ['dn', 'diametro', 'diameter']), None)
            
            if dn_field:
                totais_dn = {} # {50: comprimento, 75: comprimento}
                
                for feat in layer_tubos.getFeatures():
                    try:
                        dn = feat[dn_field]
                        # Tentar converter para int p/ agrupar '50' e 50
                        try: dn_int = int(float(dn))
                        except: dn_int = dn
                        
                        geom = feat.geometry()
                        length = geom.length()
                        
                        totais_dn[dn_int] = totais_dn.get(dn_int, 0) + length
                    except: pass
                    
                # Iterar totais e pedir seleção
                for dn, comprimento in totais_dn.items():
                    qtd_barras = math.ceil(comprimento / 6.0)
                    
                    sel_dlg = SelecaoMaterialDialog(
                        peca_manager, 
                        str(dn), 
                        f"Tubulação DN {dn}", 
                        f"Tubos DN {dn} (Total: {comprimento:.2f}m)", 
                        qtd_barras, 
                        "barras (6m)",
                        self.iface.mainWindow()
                    )
                    
                    if sel_dlg.exec_():
                         nome_peca = sel_dlg.selected_material_name
                         dados_peca = peca_manager.get(nome_peca)
                         # Calc preço
                         custo = dados_peca.get('custo', 0)
                         lucro = dados_peca.get('lucro', 0)
                         preco = custo * (1 + lucro/100)
                         
                         project_bom.add_item(nome_peca, preco, qtd_barras)
                         items_added += 1
            else:
                self.iface.messageBar().pushMessage("Aqueduct", "Campo DN/Diâmetro não encontrado na camada de tubos.", level=1, duration=5)

        # 2. Processar Mangueiras
        layer_mangueiras = layers['mangueiras']
        if layer_mangueiras:
            total_len = 0
            for feat in layer_mangueiras.getFeatures():
                total_len += feat.geometry().length()
            
            if total_len > 0:
                qtd_rolos = math.ceil(total_len / 500.0)
                
                sel_dlg = SelecaoMaterialDialog(
                    peca_manager, 
                    "Mangueira", 
                    "Mangueiras de Gotejamento", 
                    f"Mangueiras (Total: {total_len:.2f}m)", 
                    qtd_rolos, 
                    "rolos (500m)",
                    self.iface.mainWindow()
                )
                
                if sel_dlg.exec_():
                     nome_peca = sel_dlg.selected_material_name
                     dados_peca = peca_manager.get(nome_peca)
                     custo = dados_peca.get('custo', 0)
                     lucro = dados_peca.get('lucro', 0)
                     preco = custo * (1 + lucro/100)
                     
                     project_bom.add_item(nome_peca, preco, qtd_rolos)
                     items_added += 1

        # 3. Processar Emissores
        layer_emissores = layers['emissores']
        if layer_emissores:
            count = layer_emissores.featureCount()
            if count > 0:
                sel_dlg = SelecaoMaterialDialog(
                    peca_manager, 
                    "Emissor", 
                    "Emissores / Aspersores", 
                    "Pontos de Emissão", 
                    count, 
                    "unidades",
                    self.iface.mainWindow()
                )
                
                if sel_dlg.exec_():
                     nome_peca = sel_dlg.selected_material_name
                     dados_peca = peca_manager.get(nome_peca)
                     custo = dados_peca.get('custo', 0)
                     lucro = dados_peca.get('lucro', 0)
                     preco = custo * (1 + lucro/100)
                     
                     project_bom.add_item(nome_peca, preco, count)
                     items_added += 1

        if items_added > 0:
            QMessageBox.information(self.iface.mainWindow(), "Sucesso", f"{items_added} itens adicionados à Lista de Materiais!")
        else:
            self.iface.messageBar().pushMessage("Aqueduct", "Nenhum item adicionado.", level=0, duration=5)
