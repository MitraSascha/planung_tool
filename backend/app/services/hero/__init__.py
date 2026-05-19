"""HERO-Software-Integration für das Planung-Tool.

Übernommen aus MitraApp (``apps/hero/``) und an FastAPI/Pydantic-Settings
angepasst. Bietet:

  * ``client.HeroClient`` — synchrones GraphQL mit Retry
  * ``service.*`` — High-Level-Funktionen (Partner-Sync, Tracking-Time-Push)
  * ``queries`` — GraphQL-Strings

Token + URL kommen aus ``settings.hero_api_token`` / ``settings.hero_graphql_url``.
Wenn Token leer ist, deaktiviert sich die Integration automatisch — der Server
läuft weiter.
"""
