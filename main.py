import os
import caldav
import requests
import feedparser
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
import json

# ── Config desde variables de entorno ──────────────────────────────────────────
ICLOUD_EMAIL        = os.environ['ICLOUD_EMAIL']
ICLOUD_APP_PASSWORD = os.environ['ICLOUD_APP_PASSWORD']
OPENWEATHER_API_KEY = os.environ['OPENWEATHER_API_KEY']
GEMINI_API_KEY      = os.environ['GEMINI_API_KEY']
GMAIL_ADDRESS       = os.environ['GMAIL_ADDRESS']
GMAIL_APP_PASSWORD  = os.environ['GMAIL_APP_PASSWORD']
RECIPIENT_EMAIL     = os.environ['RECIPIENT_EMAIL']

# ── Fuentes RSS ────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    'extremadura': [
        'https://www.hoy.es/rss/atom.html',
        'https://www.elperiodicoextremadura.com/rss/section/portada.xml',
        'https://www.extremadura7dias.com/feed/',
    ],
    'eurovision': [
        'https://escxtra.com/feed/',
        'https://eurovoix.com/feed/',
        'https://eurovision-spain.com/feed/',
    ],
    'marketing': [
        'https://www.marketingdirecto.com/feed',
        'https://www.puromarketing.com/rss.php',
        'https://www.creativebloq.com/rss',
        'https://muycanal.com/feed',
    ],
}

# ── Calendario iCloud ──────────────────────────────────────────────────────────
def get_calendar_events():
    try:
        client = caldav.DAVClient(
            url='https://caldav.icloud.com/',
            username=ICLOUD_EMAIL,
            password=ICLOUD_APP_PASSWORD
        )
        principal = client.principal()
        calendars = principal.calendars()

        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end   = datetime.combine(date.today(), datetime.max.time())
        events_today = []

        for calendar in calendars:
            try:
                events = calendar.date_search(start=today_start, end=today_end, expand=True)
                for event in events:
                    try:
                        comp    = event.vobject_instance.vevent
                        summary = str(comp.summary.value) if hasattr(comp, 'summary') else 'Sin título'
                        dtstart = comp.dtstart.value if hasattr(comp, 'dtstart') else None
                        hora    = dtstart.strftime('%H:%M') if isinstance(dtstart, datetime) else 'Todo el día'
                        events_today.append(f"- {hora}: {summary}")
                    except Exception:
                        continue
            except Exception:
                continue

        return events_today if events_today else ["Sin eventos en el calendario para hoy."]
    except Exception as e:
        return [f"No se pudo conectar al calendario: {str(e)}"]


# ── Tiempo ─────────────────────────────────────────────────────────────────────
def get_weather():
    try:
        url  = (f"https://api.openweathermap.org/data/2.5/weather"
                f"?q=Badajoz,ES&appid={OPENWEATHER_API_KEY}&units=metric&lang=es")
        data = requests.get(url, timeout=10).json()
        return {
            'temp':        round(data['main']['temp']),
            'feels_like':  round(data['main']['feels_like']),
            'description': data['weather'][0]['description'].capitalize(),
            'humidity':    data['main']['humidity'],
            'wind':        round(data['wind']['speed'] * 3.6),
            'temp_min':    round(data['main']['temp_min']),
            'temp_max':    round(data['main']['temp_max']),
        }
    except Exception as e:
        return {'error': str(e)}


# ── RSS ────────────────────────────────────────────────────────────────────────
def get_rss_items(feeds, max_per_feed=2, total_max=5):
    items = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title   = entry.get('title', '').strip()
                summary = entry.get('summary', '').strip()[:400]
                link    = entry.get('link', '')
                if title:
                    items.append(f"• {title}\n  {summary}\n  🔗 {link}")
                if len(items) >= total_max:
                    return items
        except Exception:
            continue
    return items[:total_max]


# ── Prompt ─────────────────────────────────────────────────────────────────────
def build_prompt(events, weather, news_ext, news_eurov, news_marketing, today_str):
    weather_str = (
        f"{weather.get('description', '')}, {weather.get('temp', '?')}°C "
        f"(sensación {weather.get('feels_like', '?')}°C). "
        f"Mín {weather.get('temp_min', '?')}°C / Máx {weather.get('temp_max', '?')}°C. "
        f"Humedad {weather.get('humidity', '?')}%. Viento {weather.get('wind', '?')} km/h."
        if 'error' not in weather
        else f"No disponible ({weather.get('error')})"
    )

    events_str     = '\n'.join(events) if events else "Sin eventos hoy."
    news_ext_str   = '\n\n'.join(news_ext) if news_ext else "No se encontraron noticias."
    news_eurov_str = '\n\n'.join(news_eurov) if news_eurov else "No se encontraron noticias."
    news_mkt_str   = '\n\n'.join(news_marketing) if news_marketing else "No se encontraron artículos."

    return f"""Eres el asistente personal de Marcos, un estudiante de Periodismo y Comunicación Audiovisual en su último año, que además hace prácticas en una agencia de marketing digital en Badajoz. Le apasionan el Carnaval de Badajoz, Eurovisión, el diseño, los vinilos y las plantas. Habla con él de forma cercana, directa y sin rollos innecesarios.

Hoy es {today_str}. Prepárale su digest matutino con los datos que te doy abajo.

Instrucciones de estilo:
- Tono: cercano, directo, con algo de gracia pero sin pasarte. Nada de frases corporativas ni de motivación barata.
- Emojis: úsalos, pero con criterio. Uno por sección es suficiente.
- Longitud: conciso. Cada sección en 3-5 líneas máximo.
- El asunto tiene que ser atractivo y con algo del día. Empiézalo con: ASUNTO: [asunto aquí]

Estructura del email:
1. Saludo breve (una frase, que tenga algo que ver con el día o el tiempo)
2. 🌤️ El tiempo en Badajoz hoy
3. 📅 Tus eventos de hoy
4. 📰 Extremadura hoy (máx. 3 noticias, una línea por noticia con el titular y contexto mínimo)
5. 🎤 Eurovisión (máx. 3 noticias, mismo formato)
6. 💡 Lectura del día (1 artículo de marketing o diseño, con 2-3 líneas de por qué merece la pena leerlo)
7. Cierre breve (algo corto, nada de "¡que tengas un gran día!")

=== TIEMPO ===
{weather_str}

=== CALENDARIO ===
{events_str}

=== NOTICIAS EXTREMADURA ===
{news_ext_str}

=== NOTICIAS EUROVISIÓN ===
{news_eurov_str}

=== MARKETING / DISEÑO ===
{news_mkt_str}
"""


# ── Gemini API ─────────────────────────────────────────────────────────────────
def generate_with_gemini(prompt):
    import time
    url  = (f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    for intento in range(3):
        r = requests.post(url, json=body, timeout=60)
        if r.status_code == 429:
            espera = 60 * (intento + 1)
            print(f"⏳ Límite de Gemini, esperando {espera}s...")
            time.sleep(espera)
            continue
        r.raise_for_status()
        return r.json()['candidates'][0]['content']['parts'][0]['text']
    raise Exception("Gemini no respondió tras 3 intentos")

# ── Envío de email ─────────────────────────────────────────────────────────────
def send_email(subject, body_text):
    paragraphs = body_text.replace('\r\n', '\n').split('\n')
    html_lines = []
    for line in paragraphs:
        if line.strip() == '':
            html_lines.append('<br>')
        elif any(line.startswith(e) for e in ['🌤️', '📅', '📰', '🎤', '💡']):
            html_lines.append(f'<h3 style="margin-top:24px;margin-bottom:6px;color:#1a1a1a;">{line}</h3>')
        elif line.startswith('•'):
            html_lines.append(f'<p style="margin:4px 0 4px 12px;">{line}</p>')
        elif line.startswith('  🔗'):
            html_lines.append(f'<p style="margin:0 0 10px 12px;font-size:0.85em;color:#666;">{line}</p>')
        else:
            html_lines.append(f'<p style="margin:6px 0;">{line}</p>')

    body_html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"></head>
<body style="font-family: Georgia, 'Times New Roman', serif; max-width: 620px; margin: 0 auto;
             padding: 32px 24px; color: #1a1a1a; line-height: 1.75; background: #ffffff;">
  <div style="border-left: 4px solid #e8a87c; padding-left: 16px; margin-bottom: 28px;">
    <p style="font-size: 0.8em; color: #888; margin: 0;">MORNING DIGEST · MARCOS</p>
  </div>
  {''.join(html_lines)}
  <div style="margin-top: 40px; padding-top: 16px; border-top: 1px solid #eee;
              font-size: 0.78em; color: #aaa;">
    Generado automáticamente · {datetime.now().strftime('%d/%m/%Y %H:%M')}
  </div>
</body>
</html>"""

    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"Morning Digest <{GMAIL_ADDRESS}>"
    msg['To']      = RECIPIENT_EMAIL

    msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html, 'html',  'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    today_str = datetime.now().strftime('%A, %d de %B de %Y')
    print(f"🚀 Iniciando digest para {today_str}...")

    print("📅 Leyendo calendario iCloud...")
    events = get_calendar_events()

    print("🌤️  Consultando el tiempo...")
    weather = get_weather()

    print("📰 Cargando RSS...")
    news_ext       = get_rss_items(RSS_FEEDS['extremadura'])
    news_eurov     = get_rss_items(RSS_FEEDS['eurovision'])
    news_marketing = get_rss_items(RSS_FEEDS['marketing'])

    print("🤖 Generando digest con Gemini...")
    prompt   = build_prompt(events, weather, news_ext, news_eurov, news_marketing, today_str)
    response = generate_with_gemini(prompt)

    # Separar asunto del cuerpo
    lines      = response.strip().split('\n')
    subject    = "☀️ Tu digest del día"
    body_start = 0

    for i, line in enumerate(lines):
        if line.upper().startswith('ASUNTO:'):
            subject    = line.split(':', 1)[1].strip()
            body_start = i + 1
            break

    body_text = '\n'.join(lines[body_start:]).strip()

    print(f"📧 Enviando email: {subject}")
    send_email(subject, body_text)
    print("✅ Digest enviado correctamente.")


if __name__ == '__main__':
    main()
