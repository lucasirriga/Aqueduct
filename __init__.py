# -*- coding: utf-8 -*-
def classFactory(iface):
    """Carrega a classe AqueductPlugin do arquivo main.py."""
    from .main import AqueductPlugin
    return AqueductPlugin(iface)
