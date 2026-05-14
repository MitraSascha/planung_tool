# n8n Workflow - HEZ-640 Tagesbericht mit Fotos

## Datei

`HEZ-640_Tagesbericht_mit_Fotos_n8n.json`

## Zweck

Der Workflow nimmt Tagesberichte aus der Monteur-HTML-App per Webhook entgegen. Er kann Textfelder und Foto-Dateien verarbeiten, daraus einen strukturierten Tagesbericht bauen und diesen per E-Mail ans Buero senden.

## Webhook

Nach dem Import in n8n lautet der Test-Endpunkt sinngemaess:

```text
https://DEINE-N8N-DOMAIN/webhook-test/hez-640-tagesbericht
```

Nach Aktivierung:

```text
https://DEINE-N8N-DOMAIN/webhook/hez-640-tagesbericht
```

## Erwartete Felder aus der HTML-App

| Feld | Inhalt |
|---|---|
| projekt | Mareschstrasse 1, Berlin-Neukoelln |
| abschnitt | Abschnitt 1 bis 4 |
| datum | Tagesdatum |
| team | Monteur / Team |
| status | Gruen, Gelb oder Rot |
| aufgaben | erledigte Aufgaben |
| materialFehlt | fehlendes Material |
| probleme | Probleme / Behinderungen |
| ausgefuehrteArbeiten | ausgefuehrte Arbeiten |
| offeneArbeiten | offene Arbeiten |
| fotoHinweise | Foto-Hinweise |
| foto / foto1 / foto2 ... | hochgeladene Bilddateien |

## Nach dem Import anpassen

1. Im Node `E-Mail ans Buero senden`:
   - `fromEmail` ersetzen.
   - `toEmail` von `buero@example.de` auf eure echte Buero-Adresse setzen.
   - SMTP-Credentials in n8n verbinden.

2. Optional im Node `Optional - Google Sheet protokollieren`:
   - Node aktivieren.
   - Google-Credentials verbinden.
   - `GOOGLE_SHEET_ID_HIER_EINTRAGEN` ersetzen.
   - Sheet `Tagesberichte` mit passenden Spalten anlegen.

3. Danach Workflow aktivieren und die Produktions-Webhook-URL in die HTML-App eintragen.

## Wichtiger Hinweis zu Fotos

`mailto:` kann Fotos nicht sauber automatisch anhaengen. Fuer automatischen Fotoversand muss die Monteur-App per `fetch()` an diesen n8n-Webhook senden. Dafuer muss in der HTML-App ein Dateifeld eingebaut werden:

```html
<input id="fotos" name="foto" type="file" accept="image/*" multiple>
```

Der Versand erfolgt dann als `FormData` an den Webhook.
