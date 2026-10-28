"""Tools pentru agent. registry.py importă tools.anaf și tools.breeam; importul pachetului
înregistrează și tool-urile noi (fără a modifica lista din registry.py)."""

from tools import emisii_vehicul, factor_emisie  # noqa: F401  (înregistrare @tool)
