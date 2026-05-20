# Materialmeldungen: Bündel-Liste mit Click-Strikethrough + Push

**Status:** DONE — 2026-05-19 implementiert
**Erstellt:** 2026-05-19
**Bereich:** Open-Points / Materialmeldungen

## Anforderung

1. **Bündel-View:** alle Materialmeldungen aller Projekte (bzw. pro Projekt — User entscheidet beim Bauen) als einzelne, kompakte Liste ausgeben — nicht mehr getrennt nach Status/Projekt.
2. **Click-Strikethrough:** Beim Anklicken eines Eintrags wird er als „erledigt" markiert und visuell durchgestrichen (statt aus der Liste zu verschwinden).
   - Bisheriger Status-Workflow (`offen`/`bestellt`/`unterwegs`/`angekommen`) bleibt erhalten — Click-Strikethrough setzt vermutlich `procurement_status='angekommen'` (= visuell „done"). Im Edit-Mode noch abstimmen.
3. **Push-Benachrichtigung:** Wenn ein Monteur eine neue Materialmeldung anlegt (oder im Tagesbericht Material als fehlend markiert), bekommen die Lead-Rollen (Bauleitung/Obermonteur/PL) eine Push-Notification.

## Offene Fragen / vor Implementierung klären

- Welche Rollen sehen die Bündel-Liste? (vermutlich Lead-Rollen — Monteur sieht nur seine eigenen?)
- Push-Subscription-Mechanismus existiert bereits (siehe `push-settings`-Component) — nur Trigger einbauen.
- „Strikethrough beim Klick" toggelbar (zurückklicken um zu reaktivieren)?

## Verwandte Bestandteile

- `frontend/src/app/features/open-points/` (bestehende Forms)
- `backend/app/api/reports.py:525` (procurement-Endpoint)
- `backend/app/api/push.py` (Subscription-Mechanismus)
