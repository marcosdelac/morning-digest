import os
import caldav
import requests
import feedparser
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date
import html as html_lib

# ── Config desde variables de entorno ──────────────────────────────────────────
ICLOUD_EMAIL        = os.environ['ICLOUD_EMAIL']
ICLOUD_APP_PASSWORD = os.environ['ICLOUD_APP_PASSWORD']
OPENWEATHER_API_KEY = os.environ['OPENWEATHER_API_KEY']
GMAIL_ADDRESS       = os.environ['GMAIL_ADDRESS']
GMAIL_APP_PASSWORD  = os.environ['GMAIL_APP_PASSWORD']
RECIPIENT_EMAIL     = os.environ['RECIPIENT_EMAIL']

# ── Fuentes RSS ────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    'extremadura': [
        'https://www.hoy.es/rss/atom.html',
        'https://www.extremadura7dias.com/feed/',
        'https://www.elperiodicoextremadura.com/rss/section/portada.xml',
        'https://www.cope.es/api/rss/extremadura',
    ],
    'eurovision': [
        'https://eurovision-spain.com/feed/',
        'https://escxtra.com/feed/',
        'https://eurovoix.com/feed/',
    ],
      'diseno': [
        'https://www.marketingdirecto.com/feed',
        'https://www.domestika.org/es/blog/feed',
        'https://www.genbeta.com/feed',
        'https://hipertextual.com/feed',
        'https://www.puromarketing.com/rss.php',
    ],
}

# ── Palabras para detectar noticias en inglés ──────────────────────────────────
ENGLISH_WORDS = {'the', 'and', 'for', 'with', 'that', 'this', 'will', 'from',
                 'have', 'been', 'their', 'were', 'said', 'they', 'which'}

def es_espanol(texto):
    palabras = set(texto.lower().split())
    coincidencias = palabras & ENGLISH_WORDS
    return len(coincidencias) < 2


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
                        events_today.append({'hora': hora, 'titulo': summary})
                    except Exception:
                        continue
            except Exception:
                continue

        return events_today if events_today else []
    except Exception as e:
        print(f"Error calendario: {e}")
        return []


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
        print(f"Error tiempo: {e}")
        return None


# ── RSS ────────────────────────────────────────────────────────────────────────
def get_rss_items(feeds, max_per_feed=3, total_max=4, solo_espanol=True):
    items = []
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title   = entry.get('title', '').strip()
                summary = entry.get('summary', '').strip()[:200]
                link    = entry.get('link', '')
                summary = re.sub(r'<[^>]+>', '', summary).strip()

                if not title:
                    continue
                if solo_espanol and not es_espanol(title + ' ' + summary):
                    continue

                items.append({'titulo': title, 'resumen': summary, 'link': link})
                if len(items) >= total_max:
                    return items
        except Exception:
            continue
    return items[:total_max]


# ── Render HTML ────────────────────────────────────────────────────────────────
def render_section(emoji, titulo, contenido_html):
    return f"""
    <div style="margin-bottom: 28px;">
      <h2 style="font-size: 1em; font-weight: 700; color: #1a1a1a; margin: 0 0 12px 0;
                 padding-bottom: 6px; border-bottom: 2px solid #e8a87c;">{emoji} {titulo}</h2>
      {contenido_html}
    </div>"""

def render_news_items(items):
    if not items:
        return '<p style="color:#888;font-size:0.9em;">No hay noticias disponibles.</p>'
    html = ''
    for item in items:
        titulo  = html_lib.escape(item['titulo'])
        resumen = html_lib.escape(item['resumen'])
        link    = item['link']
        html += f"""
        <div style="margin-bottom: 14px; padding-left: 12px; border-left: 3px solid #f0d9c8;">
          <a href="{link}" style="color:#1a1a1a; font-weight:600; text-decoration:none;
             font-size:0.92em; line-height:1.4;">{titulo}</a>
          {'<p style="color:#555;font-size:0.85em;margin:3px 0 0 0;line-height:1.5;">' + resumen + '</p>' if resumen else ''}
        </div>"""
    return html

def render_events(events):
    if not events:
        return '<p style="color:#888;font-size:0.9em;">Sin eventos hoy.</p>'
    html = ''
    for e in events:
        html += f"""
        <div style="display:flex; gap:12px; margin-bottom:8px; align-items:baseline;">
          <span style="font-size:0.85em; color:#e8a87c; font-weight:700;
                min-width:70px;">{html_lib.escape(e['hora'])}</span>
          <span style="font-size:0.92em; color:#1a1a1a;">{html_lib.escape(e['titulo'])}</span>
        </div>"""
    return html

def render_weather(w):
    if not w:
        return '<p style="color:#888;font-size:0.9em;">No disponible.</p>'
    iconos = {
        'cielo claro': '☀️', 'algo de nubes': '⛅', 'nubes': '☁️',
        'nublado': '☁️', 'lluvia': '🌧️', 'llovizna': '🌦️',
        'tormenta': '⛈️', 'nieve': '❄️', 'niebla': '🌫️',
    }
    icono = '🌤️'
    for k, v in iconos.items():
        if k in w['description'].lower():
            icono = v
            break

    return f"""
    <div style="background:#fdf6f0; border-radius:8px; padding:14px 18px; display:inline-block;">
      <span style="font-size:2em;">{icono}</span>
      <span style="font-size:1.4em; font-weight:700; margin-left:8px;">{w['temp']}°C</span>
      <span style="color:#555; margin-left:8px;">{w['description']}</span>
      <div style="font-size:0.82em; color:#777; margin-top:6px;">
        Sensación {w['feels_like']}°C &nbsp;·&nbsp;
        Mín {w['temp_min']}° / Máx {w['temp_max']}° &nbsp;·&nbsp;
        Humedad {w['humidity']}% &nbsp;·&nbsp;
        Viento {w['wind']} km/h
      </div>
    </div>"""

def render_lectura(items):
    if not items:
        return '<p style="color:#888;font-size:0.9em;">No hay lectura disponible hoy.</p>'
    item    = items[0]
    titulo  = html_lib.escape(item['titulo'])
    resumen = html_lib.escape(item['resumen'])
    link    = item['link']
    return f"""
    <div style="background:#fdf6f0; border-radius:8px; padding:14px 18px;">
      <a href="{link}" style="color:#1a1a1a; font-weight:700; font-size:0.95em;
         text-decoration:none; line-height:1.4;">{titulo}</a>
      {'<p style="color:#555;font-size:0.85em;margin:6px 0 0 0;line-height:1.5;">' + resumen + '</p>' if resumen else ''}
      <a href="{link}" style="display:inline-block; margin-top:10px; font-size:0.8em;
         color:#e8a87c; text-decoration:none;">Leer artículo →</a>
    </div>"""


def build_email_html(events, weather, news_ext, news_eurov, news_diseno, fecha_str):
    now  = datetime.now()
    body = f"""
    {render_section('🌤️', 'El tiempo en Badajoz', render_weather(weather))}
    {render_section('📅', 'Tus eventos de hoy', render_events(events))}
    {render_section('📰', 'Extremadura hoy', render_news_items(news_ext))}
    {render_section('🎤', 'Eurovisión', render_news_items(news_eurov))}
    {render_section('💡', 'Lectura del día', render_lectura(news_diseno))}
    """

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f5f5f0;font-family:Georgia,'Times New Roman',serif;">
  <div style="max-width:600px;margin:24px auto;background:#ffffff;border-radius:12px;
              overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">

    <div style="background:#1a1a1a;padding:24px 32px;">
      <p style="margin:0;font-size:0.72em;letter-spacing:3px;color:#e8a87c;
                text-transform:uppercase;font-family:sans-serif;">Resumen del día · Marcos</p>
      <p style="margin:6px 0 0 0;font-size:1.1em;color:#ffffff;">{fecha_str}</p>
    </div>

    <div style="padding:28px 32px;line-height:1.7;color:#1a1a1a;">
      {body}
    </div>

    <div style="padding:16px 32px;background:#f9f9f7;border-top:1px solid #eee;">
      <p style="margin:0;font-size:0.75em;color:#aaa;font-family:sans-serif;">
        Generado automáticamente · {now.strftime('%d/%m/%Y %H:%M')}
      </p>
    </div>

  </div>
</body>
</html>"""


# ── Envío de email ─────────────────────────────────────────────────────────────
def send_email(subject, body_html):
    msg            = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = f"Resumen del día <{GMAIL_ADDRESS}>"
    msg['To']      = RECIPIENT_EMAIL
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, RECIPIENT_EMAIL, msg.as_string())


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    now   = datetime.now()
    dias  = {'Monday':'Lunes','Tuesday':'Martes','Wednesday':'Miércoles',
             'Thursday':'Jueves','Friday':'Viernes','Saturday':'Sábado','Sunday':'Domingo'}
    meses = {'January':'enero','February':'febrero','March':'marzo','April':'abril',
             'May':'mayo','June':'junio','July':'julio','August':'agosto',
             'September':'septiembre','October':'octubre','November':'noviembre','December':'diciembre'}
    dia_es    = dias.get(now.strftime('%A'), now.strftime('%A'))
    mes_es    = meses.get(now.strftime('%B'), now.strftime('%B'))
    fecha_str = f"{dia_es}, {now.day} de {mes_es} de {now.year}"

    print(f"🚀 Iniciando resumen para {fecha_str}...")

    print("📅 Leyendo calendario iCloud...")
    events = get_calendar_events()

    print("🌤️  Consultando el tiempo...")
    weather = get_weather()

    print("📰 Cargando RSS...")
    news_ext    = get_rss_items(RSS_FEEDS['extremadura'], solo_espanol=True)
    news_eurov  = get_rss_items(RSS_FEEDS['eurovision'], solo_espanol=False)
    news_diseno = get_rss_items(RSS_FEEDS['diseno'], solo_espanol=True)

    print("✉️  Generando email...")
    body_html = build_email_html(events, weather, news_ext, news_eurov, news_diseno, fecha_str)
    subject   = f"📋 Resumen del {dia_es} · {now.day} de {mes_es}"

    print(f"📧 Enviando: {subject}")
    send_email(subject, body_html)
    print("✅ Resumen enviado correctamente.")


if __name__ == '__main__':
    main()
