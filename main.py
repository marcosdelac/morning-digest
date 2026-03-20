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

# ── Temporada de Carnaval (1 dic → 31 mar) ────────────────────────────────────
def es_temporada_carnaval():
    hoy = date.today()
    return hoy.month == 12 or hoy.month <= 3

# ── Fuentes RSS ────────────────────────────────────────────────────────────────
RSS_FEEDS = {
    'extremadura': [
        'https://news.google.com/rss/search?q=Extremadura&hl=es&gl=ES&ceid=ES:es',
        'https://news.google.com/rss/search?q=Badajoz+OR+Caceres&hl=es&gl=ES&ceid=ES:es',
    ],
    'carnaval': [
        'https://news.google.com/rss/search?q=Carnaval+Badajoz&hl=es&gl=ES&ceid=ES:es',
        'https://news.google.com/rss/search?q=Carnaval+Badajoz+comparsa+chirigota&hl=es&gl=ES&ceid=ES:es',
    ],
    'eurovision': [
        'https://escplus.es/feed/',
        'https://eurovision-spain.com/feed/',
        'https://escxtra.com/feed/',
    ],
    'diseno': [
        'https://www.domestika.org/es/blog/feed',
        'https://www.marketingdirecto.com/feed',
        'https://www.reasonwhy.es/feed',
        'https://www.puromarketing.com/rss.php',
        'https://www.xataka.com/feed',
        'https://hipertextual.com/feed',
    ],
}

# ── Filtros ────────────────────────────────────────────────────────────────────
ENGLISH_WORDS = {'the', 'and', 'for', 'with', 'that', 'this', 'will', 'from',
                 'have', 'been', 'their', 'were', 'said', 'they', 'which'}

PALABRAS_EXCLUIR = {
    'fútbol', 'futbol', 'atletico', 'atlético', 'real madrid', 'barça',
    'barcelona', 'liga', 'champions', 'partido', 'gol', 'jugador',
    'entrenador', 'fichaje', 'baloncesto', 'tenis', 'deporte', 'nba',
    'formula 1', 'motogp', 'ciclismo', 'atletismo'
}

PALABRAS_MULTIMEDIA = {
    'informativo', 'informativos', 'podcast', 'rne audio', 'rtve audio',
    'en directo', 'en vivo', 'retransmisión', 'programa de radio',
    'canal sur radio', 'escúchalo', 'escucha aquí'
}

PALABRAS_DISENO = {
    'diseño', 'marketing', 'branding', 'campaña', 'creatividad',
    'ilustración', 'video', 'vídeo', 'edición', 'audiovisual',
    'redes sociales', 'digital', 'contenido', 'creativo', 'visual',
    'gráfico', 'fotografía', 'tendencia', 'herramienta', 'publicidad',
    'agencia', 'copy', 'estrategia', 'seo', 'social media', 'canva',
    'after effects', 'premiere', 'photoshop', 'illustrator', 'tipografía',
    'inteligencia artificial', 'ia', 'reel', 'stories', 'influencer',
    'marca', 'identidad visual', 'comunicación', 'medios', 'periodismo',
    'imagen', 'color', 'fuente', 'logo', 'animación', 'motion'
}

def es_espanol(texto):
    palabras = set(texto.lower().split())
    return len(palabras & ENGLISH_WORDS) < 2

def es_relevante(texto):
    return not any(p in texto.lower() for p in PALABRAS_EXCLUIR)

def es_legible(texto):
    return not any(p in texto.lower() for p in PALABRAS_MULTIMEDIA)

def es_diseno_relevante(texto):
    if not es_relevante(texto):
        return False
    return any(p in texto.lower() for p in PALABRAS_DISENO)

def limpiar_titulo(texto):
    texto = re.sub(r'\s*-\s*[\w\s\.]+$', '', texto.strip())
    return texto.strip()

def limpiar_summary(texto):
    texto = re.sub(r'<[^>]+>', '', texto)
    texto = re.sub(r'https?://\S+', '', texto)
    texto = re.sub(r'\s{2,}', ' ', texto)
    texto = re.sub(r'\s*-\s*[\w\s\.]+$', '', texto.strip())
    return texto.strip()[:200]


# ── Calendario iCloud ──────────────────────────────────────────────────────────
def get_calendar_events():
    eventos = []
    hoy     = date.today()
    try:
        client = caldav.DAVClient(
            url='https://caldav.icloud.com/',
            username=ICLOUD_EMAIL,
            password=ICLOUD_APP_PASSWORD
        )
        principal      = client.principal()
        calendars      = principal.calendars()
        today_start    = datetime.combine(hoy, datetime.min.time())
        today_end      = datetime.combine(hoy, datetime.max.time())

        for calendar in list(calendars):
            try:
                events = calendar.date_search(start=today_start, end=today_end, expand=True)
                for event in events:
                    try:
                        comp    = event.vobject_instance.vevent
                        summary = str(comp.summary.value) if hasattr(comp, 'summary') else 'Sin título'
                        dtstart = comp.dtstart.value if hasattr(comp, 'dtstart') else None
                        hora    = dtstart.strftime('%H:%M') if isinstance(dtstart, datetime) else 'Todo el día'
                        eventos.append({'hora': hora, 'titulo': summary})
                    except Exception:
                        continue
            except Exception:
                continue

        eventos.sort(key=lambda x: (x['hora'] == 'Todo el día', x['hora']))
    except Exception as e:
        print(f"Error calendario: {e}")

    return eventos


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
def get_rss_items(feeds, max_per_feed=5, total_max=4,
                  solo_espanol=True, filtro_diseno=False, filtro_legible=False):
    items = []
    seen  = set()
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:max_per_feed]:
                title   = limpiar_titulo(entry.get('title', ''))
                summary = limpiar_summary(entry.get('summary', ''))
                link    = entry.get('link', '')

                if not title or title in seen:
                    continue
                if solo_espanol and not es_espanol(title + ' ' + summary):
                    continue
                if not es_relevante(title + ' ' + summary):
                    continue
                if filtro_legible and not es_legible(title + ' ' + summary):
                    continue
                if filtro_diseno and not es_diseno_relevante(title + ' ' + summary):
                    continue

                seen.add(title)
                items.append({'titulo': title, 'resumen': summary, 'link': link})
                if len(items) >= total_max:
                    return items
        except Exception:
            continue
    return items[:total_max]


# ── Efemérides (Wikipedia API) ─────────────────────────────────────────────────
def get_efemeride():
    try:
        hoy   = date.today()
        url   = f"https://es.wikipedia.org/api/rest_v1/feed/onthisday/events/{hoy.month}/{hoy.day}"
        data  = requests.get(url, timeout=10, headers={'User-Agent': 'morning-digest/1.0'}).json()
        items = data.get('events', [])
        if not items:
            return None
        # Buscar uno relacionado con comunicación, arte, música o cultura
        palabras_clave = {'radio', 'televisión', 'television', 'cine', 'música', 'musica',
                          'periodismo', 'prensa', 'arte', 'cultura', 'españa', 'extremadura',
                          'diseño', 'fotografía', 'teatro', 'festival', 'publicación'}
        for item in items:
            texto = item.get('text', '').lower()
            if any(p in texto for p in palabras_clave):
                return {'año': item.get('year', ''), 'texto': item.get('text', '')}
        # Si no hay uno temático, devolver el más reciente
        items_sorted = sorted(items, key=lambda x: abs(x.get('year', 0)), reverse=True)
        best = items_sorted[0]
        return {'año': best.get('year', ''), 'texto': best.get('text', '')}
    except Exception as e:
        print(f"Error efemérides: {e}")
        return None


# ── Palabra del día ────────────────────────────────────────────────────────────
PALABRAS = [
    ("Briefing", "Documento que define los objetivos, el público y los requisitos de un proyecto creativo antes de empezar."),
    ("Moodboard", "Collage visual de referencias de estilo, colores y texturas que sirve para alinear la dirección creativa."),
    ("Copywriting", "Redacción persuasiva orientada a captar la atención del usuario y llevarle a una acción concreta."),
    ("Kerning", "Ajuste del espacio entre caracteres individuales en tipografía para mejorar la legibilidad visual."),
    ("Call to action", "Elemento visual o textual que invita al usuario a realizar una acción específica, como 'Comprar' o 'Suscribirse'."),
    ("Storyboard", "Secuencia de ilustraciones que representa la narrativa visual de un vídeo o animación antes de producirse."),
    ("Paleta cromática", "Conjunto de colores seleccionados que definen la identidad visual de una marca o proyecto."),
    ("Engagement", "Nivel de interacción activa del público con el contenido: likes, comentarios, compartidos y tiempo de lectura."),
    ("Retícula", "Sistema de líneas y columnas invisibles que organiza los elementos visuales en un diseño para crear orden."),
    ("Identidad visual", "Conjunto de elementos gráficos —logo, tipografía, colores— que representan de forma coherente una marca."),
    ("Motion graphics", "Técnica audiovisual que combina diseño gráfico y animación para comunicar conceptos de forma dinámica."),
    ("Jerarquía visual", "Organización de los elementos de un diseño por orden de importancia para guiar la mirada del espectador."),
    ("Benchmark", "Análisis comparativo de la competencia para identificar buenas prácticas y oportunidades de mejora."),
    ("Storytelling", "Técnica narrativa que usa historias para conectar emocionalmente con el público y transmitir un mensaje."),
    ("Espacio negativo", "Zona vacía alrededor de los elementos de un diseño que ayuda a destacarlos y aporta equilibrio visual."),
    ("Audiencia objetivo", "Perfil concreto del público al que se dirige una campaña, definido por edad, intereses y comportamiento."),
    ("Tipografía display", "Fuente tipográfica diseñada para usarse a gran tamaño, priorizando el impacto visual sobre la legibilidad."),
    ("User journey", "Recorrido completo que sigue un usuario desde que descubre un producto hasta que completa una acción."),
    ("Tono de voz", "Personalidad y estilo con que una marca se comunica con su audiencia en todos sus mensajes."),
    ("Above the fold", "Parte de una página web visible sin hacer scroll; zona de mayor atención e impacto para el usuario."),
    ("Flat design", "Estilo visual que usa formas simples, colores planos y ausencia de sombras para lograr interfaces limpias."),
    ("Branding emocional", "Estrategia que conecta una marca con sentimientos y valores personales del consumidor para generar fidelidad."),
    ("Prototipo", "Versión preliminar de un diseño o producto usada para testear ideas antes del desarrollo definitivo."),
    ("Píxel perfecto", "Estándar de precisión en diseño digital donde cada elemento ocupa exactamente los píxeles necesarios."),
    ("Palimpsesto", "En comunicación, mensaje que reescribe o actualiza uno anterior manteniendo trazas del original."),
    ("Color primario de marca", "Color principal asociado a una empresa, tan reconocible que identifica la marca sin necesidad del logo."),
    ("Rough cut", "Primera versión de edición de vídeo sin pulir, usada para revisar la estructura narrativa antes del montaje final."),
    ("Brief creativo", "Resumen conciso que define el qué, para quién, por qué y cómo de un proyecto de comunicación."),
    ("Logotipo vs isologo", "El logotipo es solo texto; el isologo combina símbolo e icono inseparablemente en una misma unidad visual."),
    ("Pantone", "Sistema estandarizado de colores usado en diseño e impresión para garantizar la consistencia del color exacto."),
    ("Wireframe", "Esquema básico de una interfaz digital que muestra la estructura sin colores ni estilos definitivos."),
    ("Cross-posting", "Publicar el mismo contenido en varias redes sociales adaptando formato y tono a cada plataforma."),
    ("Legibilidad", "Facilidad con que un texto puede ser leído, determinada por tamaño, interlineado, contraste y tipografía."),
    ("Insight", "Verdad profunda y no obvia sobre el comportamiento del consumidor que inspira una idea creativa relevante."),
    ("Composición áurea", "Principio de diseño basado en la proporción 1:1,618, presente en la naturaleza y considerada visualmente perfecta."),
    ("Guión técnico", "Documento de producción audiovisual que detalla cada plano, encuadre, movimiento de cámara y diálogo."),
    ("Rebranding", "Proceso de renovación total o parcial de la identidad visual y comunicativa de una marca existente."),
    ("Espacio de color", "Rango de colores representables en un sistema: RGB para pantallas, CMYK para impresión."),
    ("Clickbait", "Título sensacionalista diseñado para atraer clics aunque el contenido no justifique la promesa del titular."),
    ("Fuente serif", "Tipografía con remates o patines en los extremos de las letras, asociada a tradición y formalidad."),
    ("Diseño responsive", "Adaptación automática de un diseño web a distintos tamaños de pantalla sin perder usabilidad."),
    ("Claim", "Frase breve y memorable que acompaña al logo de una marca y resume su propuesta de valor."),
    ("Convergencia mediática", "Fusión de distintos medios de comunicación en plataformas digitales únicas que integran texto, imagen y vídeo."),
    ("Render", "Proceso de generar la imagen final de un diseño 3D o animación a partir de los datos del proyecto."),
    ("Curva de aprendizaje", "En diseño de interfaces, facilidad o dificultad con que un nuevo usuario comprende cómo usar el producto."),
    ("Infografía", "Representación visual de información compleja que combina texto, iconos y gráficos para facilitar su comprensión."),
    ("Agencia 360°", "Agencia que ofrece servicios integrados de comunicación: publicidad, digital, relaciones públicas y estrategia."),
    ("Narrative arc", "Estructura narrativa de un contenido con planteamiento, nudo y desenlace para mantener la atención del espectador."),
    ("Hipervínculo semántico", "Enlace cuyo texto describe con precisión el destino, mejorando SEO y experiencia de usuario simultáneamente."),
    ("Edición multicámara", "Técnica de montaje que alterna planos grabados con varias cámaras simultáneas para dinamizar la narración."),
    ("Posicionamiento de marca", "Lugar que ocupa una marca en la mente del consumidor respecto a sus competidores."),
    ("Sistema de diseño", "Conjunto de componentes visuales y normas reutilizables que garantizan coherencia en todos los productos de una marca."),
]

def get_palabra_del_dia():
    idx = date.today().timetuple().tm_yday % len(PALABRAS)
    termino, definicion = PALABRAS[idx]
    return {'termino': termino, 'definicion': definicion}


# ── Resumen semanal (solo lunes) ───────────────────────────────────────────────
def get_resumen_semanal():
    """Devuelve noticias de los últimos 7 días para el resumen del lunes"""
    try:
        feeds = [
            'https://news.google.com/rss/search?q=Extremadura+semana&hl=es&gl=ES&ceid=ES:es',
            'https://escplus.es/feed/',
            'https://www.marketingdirecto.com/feed',
        ]
        return get_rss_items(feeds, max_per_feed=3, total_max=3, solo_espanol=True)
    except Exception:
        return []


# ── Render HTML ────────────────────────────────────────────────────────────────
def render_section(emoji, titulo, contenido_html):
    return f"""
    <div style="margin-bottom: 28px;">
      <h2 style="font-size: 1em; font-weight: 700; color: #1a1a1a; margin: 0 0 12px 0;
                 padding-bottom: 6px; border-bottom: 2px solid #e8a87c;">{emoji} {titulo}</h2>
      {contenido_html}
    </div>"""

def render_eventos(eventos):
    if not eventos:
        return '<p style="color:#888;font-size:0.9em;">Sin eventos hoy.</p>'
    html = ''
    for e in eventos:
        html += f"""
        <div style="display:flex; gap:12px; margin-bottom:8px; align-items:baseline;">
          <span style="font-size:0.85em; color:#e8a87c; font-weight:700;
                min-width:80px;">{html_lib.escape(e['hora'])}</span>
          <span style="font-size:0.85em;">📌</span>
          <span style="font-size:0.92em; color:#1a1a1a;">{html_lib.escape(e['titulo'])}</span>
        </div>"""
    return html

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

def render_efemeride(efem):
    if not efem:
        return '<p style="color:#888;font-size:0.9em;">No disponible hoy.</p>'
    return f"""
    <div style="background:#fdf6f0; border-radius:8px; padding:14px 18px;">
      <span style="font-size:0.8em; color:#e8a87c; font-weight:700;">
        {html_lib.escape(str(efem['año']))}
      </span>
      <p style="margin:4px 0 0 0; font-size:0.92em; color:#1a1a1a; line-height:1.6;">
        {html_lib.escape(efem['texto'])}
      </p>
    </div>"""

def render_palabra(palabra):
    return f"""
    <div style="background:#fdf6f0; border-radius:8px; padding:14px 18px;">
      <p style="margin:0; font-size:1em; font-weight:700; color:#1a1a1a;">
        {html_lib.escape(palabra['termino'])}
      </p>
      <p style="margin:6px 0 0 0; font-size:0.88em; color:#555; line-height:1.6;">
        {html_lib.escape(palabra['definicion'])}
      </p>
    </div>"""

def render_resumen_semanal(items):
    if not items:
        return '<p style="color:#888;font-size:0.9em;">No hay resumen disponible.</p>'
    html = '<p style="font-size:0.85em;color:#555;margin:0 0 12px 0;">Lo más destacado de los últimos 7 días:</p>'
    html += render_news_items(items)
    return html


def build_email_html(eventos, weather, news_ext, news_carnaval,
                     news_eurov, news_diseno, efemeride, palabra,
                     resumen_semanal, fecha_str, es_lunes):
    now  = datetime.now()

    secciones = f"""
    {render_section('🌤️', 'El tiempo en Badajoz', render_weather(weather))}
    {render_section('📅', 'Eventos de hoy', render_eventos(eventos))}
    """

    if es_lunes and resumen_semanal:
        secciones += render_section('📋', 'Resumen de la semana', render_resumen_semanal(resumen_semanal))

    secciones += render_section('📰', 'Extremadura hoy', render_news_items(news_ext))

    if es_temporada_carnaval() and news_carnaval:
        secciones += render_section('🎭', 'Carnaval de Badajoz', render_news_items(news_carnaval))

    secciones += f"""
    {render_section('🎤', 'Eurovisión', render_news_items(news_eurov))}
    {render_section('💡', 'Lectura del día', render_lectura(news_diseno))}
    {render_section('📖', 'Palabra del día', render_palabra(palabra))}
    {render_section('🗓️', 'Efeméride', render_efemeride(efemeride))}
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
      {secciones}
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
    now      = datetime.now()
    dias_cap = {
        'Monday':'Lunes', 'Tuesday':'Martes', 'Wednesday':'Miércoles',
        'Thursday':'Jueves', 'Friday':'Viernes', 'Saturday':'Sábado', 'Sunday':'Domingo'
    }
    dias_min = {
        'Monday':'lunes', 'Tuesday':'martes', 'Wednesday':'miércoles',
        'Thursday':'jueves', 'Friday':'viernes', 'Saturday':'sábado', 'Sunday':'domingo'
    }
    meses = {
        'January':'enero', 'February':'febrero', 'March':'marzo', 'April':'abril',
        'May':'mayo', 'June':'junio', 'July':'julio', 'August':'agosto',
        'September':'septiembre', 'October':'octubre', 'November':'noviembre', 'December':'diciembre'
    }
    dia_en    = now.strftime('%A')
    dia_es    = dias_cap.get(dia_en, dia_en)
    dia_min   = dias_min.get(dia_en, dia_en)
    mes_es    = meses.get(now.strftime('%B'), now.strftime('%B'))
    fecha_str = f"{dia_es}, {now.day} de {mes_es} de {now.year}"
    es_lunes  = dia_en == 'Monday'

    print(f"🚀 Iniciando resumen para {fecha_str}...")

    print("📅 Leyendo calendario iCloud...")
    eventos = get_calendar_events()

    print("🌤️  Consultando el tiempo...")
    weather = get_weather()

    print("📰 Cargando RSS...")
    news_ext     = get_rss_items(RSS_FEEDS['extremadura'], solo_espanol=True, filtro_legible=True)
    news_carnaval = get_rss_items(RSS_FEEDS['carnaval'], solo_espanol=True, total_max=3) if es_temporada_carnaval() else []
    news_eurov   = get_rss_items(RSS_FEEDS['eurovision'], solo_espanol=True, max_per_feed=5)
    news_diseno  = get_rss_items(RSS_FEEDS['diseno'], solo_espanol=True, filtro_diseno=True, max_per_feed=6, total_max=1)

    print("📖 Cargando efeméride y palabra del día...")
    efemeride       = get_efemeride()
    palabra         = get_palabra_del_dia()
    resumen_semanal = get_resumen_semanal() if es_lunes else []

    print("✉️  Generando email...")
    body_html = build_email_html(
        eventos, weather, news_ext, news_carnaval,
        news_eurov, news_diseno, efemeride, palabra,
        resumen_semanal, fecha_str, es_lunes
    )

    subject = f"🫡 ¡A por el {dia_min}!"
    if es_lunes:
        subject = f"🫡 ¡A por el {dia_min}! Nueva semana 💪"

    print(f"📧 Enviando: {subject}")
    send_email(subject, body_html)
    print("✅ Resumen enviado correctamente.")


if __name__ == '__main__':
    main()
