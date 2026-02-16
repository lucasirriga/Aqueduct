# -*- coding: utf-8 -*-
def classFactory(iface):
    """Load AqueductPlugin class from file main.py."""
    from .main import AqueductPlugin
    return AqueductPlugin(iface)
