"""
carta_pro.py · CMA Financial Letter, versión Pro (PDF con gráficas).

Capa aditiva (Norma 3): app.py la usa solo en Modo Pro; si falla, app.py entrega la carta base.
Recibe la carta base (ctx) más los datos de pro_ui.contexto_carta_pro (xp). Solo ReportLab (sin matplotlib).
Lenguaje informativo y condicional (Norma 2).
"""
import html as _html
import io
from datetime import datetime

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Flowable, PageBreak)

C_TX, C_MUTED, C_SOFT = colors.HexColor("#1f2937"), colors.HexColor("#6b7280"), colors.HexColor("#4b5563")
C_ORO, C_ORO_OSC, C_ORO_TXT = colors.HexColor("#b8962e"), colors.HexColor("#8a6d1f"), colors.HexColor("#8a7a4a")
C_LINEA, C_PAPEL, C_SELLO, C_SELLO_BORDE = colors.HexColor("#eee6d3"), colors.HexColor("#fffdf8"), colors.HexColor("#f7f3e8"), colors.HexColor("#e3d7b5")
C_POS, C_NEG, C_ACERO, C_MARFIL = colors.HexColor("#047857"), colors.HexColor("#6b7280"), colors.HexColor("#4f7aa6"), colors.HexColor("#c9bfa6")
COL_CLASE = {"ETF": "#b8962e", "Acciones": "#7a5f22", "Cripto": "#e2c575", "Otros": "#9ca3af", "Efectivo": "#4f7aa6"}

e = lambda x: _html.escape(str(x if x is not None else ""))
m = lambda v, d=2: f"{'-' if float(v or 0) < 0 else ''}${abs(float(v or 0)):,.{d}f}"
ms = lambda v, d=2: f"{'+' if float(v or 0) >= 0 else '-'}${abs(float(v or 0)):,.{d}f}"
pc = lambda v, d=2: "—" if v is None else f"{float(v):+.{d}f}%"
col = lambda v: "#047857" if float(v or 0) >= 0 else "#6b7280"
tit = lambda v: (f"{float(v or 0):.8f}".rstrip("0").rstrip(".") or "0")

st_body = ParagraphStyle("body", fontName="Helvetica", fontSize=9.2, leading=13.6, textColor=C_TX)
st_soft = ParagraphStyle("soft", parent=st_body, textColor=C_SOFT)
st_nota = ParagraphStyle("nota", parent=st_body, fontSize=7.8, leading=11, textColor=C_MUTED)
st_h2 = ParagraphStyle("h2", fontName="Times-Italic", fontSize=14, leading=18, textColor=C_ORO_OSC, spaceBefore=14, spaceAfter=4)
st_kick = ParagraphStyle("kick", fontName="Helvetica", fontSize=6.8, leading=9, textColor=C_ORO_TXT, spaceBefore=10)
st_th = ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=6.4, leading=8.5, textColor=C_ORO_TXT)
st_th_r = ParagraphStyle("thr", parent=st_th, alignment=TA_RIGHT)
st_td = ParagraphStyle("td", parent=st_body, fontSize=8.4, leading=11.4)
st_td_r = ParagraphStyle("tdr", parent=st_td, alignment=TA_RIGHT)
st_td_s = ParagraphStyle("tds", parent=st_td, fontSize=7.6, leading=10)
st_td_s_r = ParagraphStyle("tdsr", parent=st_td_s, alignment=TA_RIGHT)
st_li = ParagraphStyle("li", parent=st_body, leftIndent=12, bulletIndent=2, spaceAfter=4)
st_legal = ParagraphStyle("legal", parent=st_body, fontSize=6.6, leading=9.2, textColor=colors.HexColor("#9ca3af"))


def tabla(filas, anchos, encabezado=True, alinear_der=(), chica=False):
    td, tdr = (st_td_s, st_td_s_r) if chica else (st_td, st_td_r)
    datos = []
    for k, fila in enumerate(filas):
        celdas = []
        for j, c in enumerate(fila):
            if isinstance(c, Flowable):
                celdas.append(c); continue
            if encabezado and k == 0:
                celdas.append(Paragraph(str(c).upper(), st_th_r if j in alinear_der else st_th))
            else:
                celdas.append(Paragraph(str(c), tdr if j in alinear_der else td))
        datos.append(celdas)
    t = Table(datos, colWidths=anchos, repeatRows=1 if encabezado else 0)
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, C_LINEA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 4 if chica else 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if chica else 5),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3)]))
    return t


class Sello(Flowable):
    def __init__(self, d=15 * mm):
        super().__init__(); self.width = self.height = d

    def draw(self):
        c, r = self.canv, self.width / 2
        c.setStrokeColor(C_ORO); c.setLineWidth(0.8); c.circle(r, r, r - 0.5, stroke=1, fill=0)
        c.setLineWidth(0.45); c.circle(r, r, r - 2.6, stroke=1, fill=0)
        c.setFillColor(C_ORO_OSC); c.setFont("Times-Roman", 10.5); c.drawCentredString(r, r - 3.6, "CMA")


def _leyenda(dibujo, items, x, y):
    for nombre, color, punteada in items:
        if punteada:
            dibujo.add(Line(x, y + 3, x + 14, y + 3, strokeColor=color, strokeWidth=1.2, strokeDashArray=[2, 2]))
        else:
            dibujo.add(Rect(x, y, 14, 6, fillColor=color, strokeColor=None))
        dibujo.add(String(x + 18, y, nombre, fontName="Helvetica", fontSize=7, fillColor=C_SOFT))
        x += 18 + len(nombre) * 3.9 + 16


def grafica_patrimonio(serie, ancho, alto=62 * mm):
    """Patrimonio (oro) contra capital aportado (marfil) y lo que habría generado CETES (acero)."""
    d = Drawing(ancho, alto)
    n = len(serie)
    paso = max(1, n // 160)
    pts = serie[::paso] + ([serie[-1]] if (n - 1) % paso else [])
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 8, 22, ancho - 70, alto - 40
    lp.data = [[(i, p[1]) for i, p in enumerate(pts)], [(i, p[2]) for i, p in enumerate(pts)], [(i, p[3]) for i, p in enumerate(pts)]]
    lp.lines[0].strokeColor, lp.lines[0].strokeWidth = C_ORO, 1.8
    lp.lines[1].strokeColor, lp.lines[1].strokeWidth = C_MARFIL, 1.1
    lp.lines[2].strokeColor, lp.lines[2].strokeWidth, lp.lines[2].strokeDashArray = C_ACERO, 1.0, [3, 2]
    vals = [v for p in pts for v in p[1:4]]
    lo, hi = min(vals), max(vals)
    margen = (hi - lo) * 0.08 or hi * 0.02 or 1
    lp.yValueAxis.valueMin, lp.yValueAxis.valueMax = lo - margen, hi + margen
    lp.yValueAxis.visible = False
    lp.xValueAxis.valueMin, lp.xValueAxis.valueMax = 0, len(pts) - 1
    marcas = sorted({0, (len(pts) - 1) // 3, 2 * (len(pts) - 1) // 3, len(pts) - 1})
    lp.xValueAxis.valueSteps = marcas
    lp.xValueAxis.labelTextFormat = lambda i: datetime.strptime(pts[int(i)][0], "%Y-%m-%d").strftime("%d/%m/%y")
    lp.xValueAxis.labels.fontName, lp.xValueAxis.labels.fontSize, lp.xValueAxis.labels.fillColor = "Helvetica", 6.8, C_MUTED
    lp.xValueAxis.strokeColor = C_LINEA
    d.add(lp)
    # escala a la derecha (3 niveles)
    for v in (lo, (lo + hi) / 2, hi):
        y = lp.y + lp.height * (v - lp.yValueAxis.valueMin) / (lp.yValueAxis.valueMax - lp.yValueAxis.valueMin)
        d.add(Line(lp.x, y, lp.x + lp.width, y, strokeColor=C_LINEA, strokeWidth=0.4))
        d.add(String(lp.x + lp.width + 6, y - 2.5, m(v, 0), fontName="Helvetica", fontSize=6.8, fillColor=C_MUTED))
    _leyenda(d, [("Patrimonio", C_ORO, False), ("Capital aportado", C_MARFIL, False), ("Si todo hubiera estado en CETES", C_ACERO, True)], 8, alto - 10)
    return d


def grafica_barras_h(etiquetas, valores, ancho, alto=None, fmt=lambda v: ms(v, 0)):
    n = len(valores)
    alto = alto or max(32 * mm, n * 7.2 * mm + 14)
    d = Drawing(ancho, alto)
    bc = HorizontalBarChart()
    bc.x, bc.y, bc.width, bc.height = 52, 8, ancho - 120, alto - 16
    bc.data = [list(reversed(valores))]
    bc.categoryAxis.categoryNames = list(reversed(etiquetas))
    bc.categoryAxis.labels.fontName, bc.categoryAxis.labels.fontSize, bc.categoryAxis.labels.fillColor = "Helvetica-Bold", 7.6, C_TX
    bc.categoryAxis.strokeColor = C_LINEA
    bc.categoryAxis.labels.dx = -4
    lim = max([abs(v) for v in valores] + [1]) * 1.15
    bc.valueAxis.valueMin, bc.valueAxis.valueMax = -lim if min(valores) < 0 else 0, lim
    bc.valueAxis.visible = False
    bc.bars.strokeColor = None
    bc.barWidth = 6
    for i, v in enumerate(reversed(valores)):
        bc.bars[(0, i)].fillColor = C_ORO if v >= 0 else C_NEG
    bc.barLabelFormat = fmt
    bc.barLabels.fontName, bc.barLabels.fontSize, bc.barLabels.fillColor = "Helvetica", 7, C_SOFT
    bc.barLabels.boxAnchor, bc.barLabels.dx = "w", 4
    bc.barLabels.boxTarget = "hi"
    d.add(bc)
    return d


def barra_composicion(comp, ancho):
    d = Drawing(ancho, 34)
    tot = sum(v for v in comp.values() if v > 0) or 1
    x = 0
    for k in ["ETF", "Acciones", "Cripto", "Otros", "Efectivo"]:
        v = comp.get(k, 0)
        if v <= 0:
            continue
        w = ancho * v / tot
        d.add(Rect(x, 20, max(w - 1.5, 0.5), 9, fillColor=colors.HexColor(COL_CLASE[k]), strokeColor=None))
        if w > 46:
            d.add(String(x, 8, f"{k} {v / tot * 100:.0f}%", fontName="Helvetica", fontSize=7, fillColor=C_SOFT))
        x += w
    return d


def _kpis(items, ancho):
    celdas = [[Paragraph(f"<font name='Helvetica' size='6.6' color='#8a7a4a'>{e(t).upper()}</font><br/>"
                         f"<font name='Times-Roman' size='15' color='{c or '#1f2937'}'>{v}</font><br/>"
                         f"<font name='Helvetica' size='7.2' color='#6b7280'>{s}</font>", ParagraphStyle("k", parent=st_body, leading=15))
               for t, v, s, c in items]]
    t = Table(celdas, colWidths=[ancho / len(items)] * len(items))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_SELLO), ("BOX", (0, 0), (-1, -1), 0.5, C_SELLO_BORDE),
                           ("LINEAFTER", (0, 0), (-2, -1), 0.5, C_SELLO_BORDE), ("LINEABOVE", (0, 0), (-1, 0), 1.4, C_ORO),
                           ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 8),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return t


def ficha(renglones, ancho):
    """Renglones (etiqueta, cifra, texto) en formato de ficha: etiqueta en versalitas doradas, cifra en Times, texto a la derecha.
    Sustituye a las viñetas: se lee como el resumen de un estado de cuenta."""
    st_et = ParagraphStyle("fet", fontName="Helvetica", fontSize=6.6, leading=9, textColor=C_ORO_TXT)
    st_ci = ParagraphStyle("fci", fontName="Times-Roman", fontSize=13, leading=15, textColor=C_TX)
    st_tx = ParagraphStyle("ftx", parent=st_body, fontSize=8.6, leading=12.2, textColor=C_SOFT)
    datos = [[Paragraph(e(et).upper().replace(" ", "&nbsp;"), st_et), Paragraph(e(ci), st_ci), Paragraph(e(tx), st_tx)] for et, ci, tx in renglones]
    t = Table(datos, colWidths=[ancho * 0.19, ancho * 0.23, ancho * 0.58])
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, 0), 0.9, C_ORO), ("LINEBELOW", (0, 0), (-1, -1), 0.5, C_LINEA),
                           ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]))
    return t


def _seccion(kicker, titulo):
    return [Paragraph(e(kicker).upper().replace(" ", "&nbsp;"), st_kick), Paragraph(e(titulo), st_h2)]


def generar_carta_pro_pdf(ctx, xp, folio, fecha_txt, escenarios, aviso_legal, aviso_cio=""):
    """ctx: datos de la carta base (mismas claves que generar_carta_pdf). xp: pro_ui.contexto_carta_pro."""
    ancho = A4[0] - 32 * mm
    hoy = datetime.now()
    xirr, rf = ctx["xirr"], ctx["rf"]
    capital = float(ctx["capital"] or 0)
    pat = float(ctx["patrimonio"] or 0)
    h = []

    # ---------------- Portada / resumen ejecutivo ----------------
    cab = Table([[Paragraph("C M A", ParagraphStyle("marca", fontName="Times-Roman", fontSize=19, leading=22, textColor=C_TX)),
                  Paragraph("PRIVATE WEALTH &middot; FINANCIAL LETTER &middot; EDICIÓN PRO",
                            ParagraphStyle("mr", fontName="Helvetica", fontSize=7.2, textColor=C_ORO_TXT, alignment=TA_RIGHT))]],
                colWidths=[ancho * 0.35, ancho * 0.65])
    cab.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 0.9, C_ORO), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    h += [cab, Spacer(1, 8), Paragraph(e(fecha_txt), ParagraphStyle("f", parent=st_body, fontSize=8.6, textColor=C_MUTED, alignment=TA_RIGHT)), Spacer(1, 10)]
    h.append(Paragraph(f"Estimado(a) {e(ctx['nombre'])}:", st_body)); h.append(Spacer(1, 5))
    h.append(Paragraph(
        f"Le compartimos la edición Pro de su carta: el estado detallado de su patrimonio, de dónde viene su resultado, cómo se compara "
        f"contra el mercado y CETES, el riesgo que asume y lo que la agenda de las próximas semanas tiene para sus posiciones. "
        f"Su patrimonio total es de <b>{m(pat)}</b>, construido con <b>{m(capital)}</b> de capital aportado.", st_body))
    gana = xirr is not None and xirr >= rf
    h += [Spacer(1, 10), _kpis([
        ("Patrimonio total", m(pat), f"capital aportado {m(capital, 0)}", None),
        ("Resultado en posiciones", ms(ctx["pnl"]), f"{ctx['retorno_pct']:+.2f}% sobre el costo", col(ctx["pnl"])),
        ("Rendimiento anual (XIRR)", "N/D" if xirr is None else f"{xirr * 100:+.2f}%", f"CETES {rf * 100:.2f}%", "#047857" if gana else "#6b7280"),
        ("Liquidez", m(ctx["liquidez"]), f"{ctx['liquidez'] / pat * 100 if pat else 0:.1f}% del patrimonio", None)], ancho)]
    if xp.get("lectura"):
        h += _seccion("Lectura del periodo", "Qué explica el movimiento y qué vigilar") + [ficha(xp["lectura"], ancho)]

    # ---------------- Evolución ----------------
    if xp.get("serie") and len(xp["serie"]) >= 3:
        h.append(KeepTogether(_seccion("Evolución", "Su patrimonio en el tiempo") + [grafica_patrimonio(xp["serie"], ancho)]))
        bloque = []
        if xp.get("periodos"):
            filas = [["Periodo", "Su portafolio", "S&amp;P 500 (en pesos)", "CETES", "Depósitos en el periodo"]]
            for p in xp["periodos"]:
                filas.append([e(p["periodo"]), f"<font color='{col(p['portafolio'])}'><b>{pc(p['portafolio'])}</b></font>", pc(p["spx"]), pc(p["cetes"]), m(p["depositos"], 0)])
            w = ancho / 5
            bloque += [Spacer(1, 4), tabla(filas, [w * 1.1, w, w * 1.05, w * 0.8, w * 1.05], alinear_der=(1, 2, 3, 4)),
                       Paragraph("Rendimiento ponderado por tiempo: los depósitos y retiros no cuentan como ganancia. El S&amp;P 500 se convierte a pesos "
                                 "con el tipo de cambio de cada día.", st_nota)]
        if bloque:
            h.append(KeepTogether(bloque))

    # ---------------- De dónde viene el resultado ----------------
    if xp.get("puente"):
        pu = xp["puente"]
        filas = [["Precio de los activos", f"<font color='{col(pu['precio'])}'>{ms(pu['precio'])}</font>"],
                 ["Tipo de cambio (USD/MXN desde sus compras)", f"<font color='{col(pu['tipo_cambio'])}'>{ms(pu['tipo_cambio'])}</font>"],
                 ["Comisiones e IVA", f"<font color='#6b7280'>{ms(pu['comisiones'])}</font>"],
                 ["<b>Resultado neto en posiciones</b>", f"<b><font color='{col(pu['neto'])}'>{ms(pu['neto'])}</font></b>"]]
        bloque = _seccion("Atribución", "¿De dónde viene su resultado?") + [tabla(filas, [ancho * 0.7, ancho * 0.3], encabezado=False, alinear_der=(1,))]
        att = xp.get("atribucion") or []
        if att:
            bloque += [Spacer(1, 6), Paragraph("Resultado por activo (MXN)", ParagraphStyle("st", parent=st_soft, fontSize=8.2)),
                       grafica_barras_h([a[0] for a in att], [a[1] for a in att], ancho)]
        h.append(KeepTogether(bloque))

    # ---------------- Composición ----------------
    if xp.get("posiciones"):
        bloque = _seccion("Composición", "De qué está hecho su patrimonio")
        if xp.get("composicion"):
            bloque.append(barra_composicion(xp["composicion"], ancho))
        filas = [["Activo", "Clase", "Títulos", "Costo prom.", "Precio", "Valor", "Resultado", "Rend.", "Peso", "Beta", "Vol."]]
        for p in xp["posiciones"]:
            filas.append([f"<b>{e(p['ticker'])}</b>", e(p["clase"]), tit(p["titulos"]), m(p["costo"]), m(p["precio"]), m(p["valor"]),
                          f"<font color='{col(p['pnl'])}'>{ms(p['pnl'])}</font>", f"<font color='{col(p['rend'])}'>{p['rend']:+.1f}%</font>",
                          f"{p['peso']:.1f}%", "—" if p.get("beta") is None else f"{p['beta']:.2f}", "—" if p.get("vol") is None else f"{p['vol']:.0f}%"])
        w = ancho / 11
        bloque += [tabla(filas, [w * 0.9, w * 0.95, w * 0.95, w * 1.1, w * 1.05, w * 1.15, w * 1.15, w * 0.85, w * 0.8, w * 0.6, w * 0.6],
                         alinear_der=tuple(range(2, 11)), chica=True),
                   Paragraph("Beta: cuánto se mueve el activo frente al S&amp;P 500 (1.00 = igual). Vol.: variación anual típica de su precio.", st_nota)]
        h += bloque

    # ---------------- Asignación y rebalanceo ----------------
    asig = ctx.get("asignacion") or []
    if asig or xp.get("dca"):
        bloque = _seccion("Asignación", "Parámetros y escenario de distribución")
        if xp.get("dca"):
            dca = xp["dca"]
            base = ("su efectivo disponible registrado en la Terminal" if dca.get("precargado")
                    else f"el monto capturado en el simulador (su efectivo disponible es {m(dca.get('liquidez', 0))})")
            bloque.append(Paragraph(f"<b>Capital a distribuir: {m(dca['capital'])}</b>, que corresponde a {base}. El escenario reparte ese monto "
                                    "entre las clases que quedan por debajo de su parámetro, hasta acercar cada una a su peso objetivo.", st_body))
            filas = [["Clase", "Valor hoy", "Peso hoy", "Parámetro", "Distribución", "Peso después"]]
            for r in dca["filas"]:
                filas.append([e(r["clase"]), m(r.get("valor", 0), 0), f"{r['hoy']:.1f}%", f"{r['objetivo']:.0f}%", m(r["monto"]), f"{r['despues']:.1f}%"])
            resto = max(float(dca.get("liquidez", 0)) - float(dca["capital"]), 0.0)
            filas.append(["<b>Efectivo disponible</b>", m(dca.get("liquidez", 0), 0), "—", "—", f"-{m(dca['capital'])}", f"queda {m(resto, 0)}"])
            w = ancho / 6
            bloque += [Spacer(1, 4), tabla(filas, [w * 1.25, w, w * 0.8, w * 0.8, w * 1.05, w * 1.1], alinear_der=(1, 2, 3, 4, 5)),
                       Paragraph("Los pesos se calculan sobre lo invertido (sin efectivo). Escenario aritmético: no es una instrucción de compra.", st_nota)]
        h.append(KeepTogether(bloque))

    # ---------------- Riesgo y estrés ----------------
    r = xp.get("riesgo")
    if r:
        pct_var = r["var95"] / pat * 100 if pat else 0
        filas = [["Métrica", "Su portafolio", "Ref. conservadora", "Ref. agresiva", "Qué mide"],
                 ["Volatilidad anual", f"<b>{r['vol'] * 100:.1f}%</b>", "8%", "25%", "Qué tanto sube y baja el portafolio en un año"],
                 ["Beta vs S&amp;P 500", f"<b>{r['beta']:.2f}</b>", "0.45", "1.30", "Cuánto se mueve contra la bolsa de EE.UU."],
                 ["Caída máxima (12 m)", f"<b>{abs(r['max_dd']) * 100:.1f}%</b>", "12%", "35%", "Peor caída desde un punto alto"],
                 ["Concentración (HHI)", f"<b>{r['hhi']:.2f}</b>", "0.10", "0.25", "0 = muy repartido, 1 = un solo activo"],
                 ["Correlación media", f"<b>{r['corr_media']:.2f}</b>", "0.30", "0.60", "Qué tanto se mueven sus activos en bloque"],
                 ["Sharpe", f"<b>{r['sharpe']:.2f}</b>", "—", "—", "Rendimiento sobre CETES por unidad de riesgo"],
                 ["VaR 95% diario", f"<b>{m(r['var95'], 0)}</b>", "≈0.8%", "≈2.5%", f"Baja que solo se supera 1 de cada 20 días ({pct_var:.1f}% de su patrimonio)"]]
        bloque = _seccion("Riesgo", "Perfil de riesgo (últimos 12 meses)") + [
            tabla(filas, [ancho * 0.19, ancho * 0.14, ancho * 0.14, ancho * 0.13, ancho * 0.40], alinear_der=(1, 2, 3)),
            Paragraph("Referencia conservadora: portafolio balanceado de bajo riesgo (alrededor de 30% en acciones globales y 70% en renta fija). "
                      "Referencia agresiva: portafolio 100% en acciones de crecimiento, tecnología, emergentes y cripto. Entre más cerca de una u otra "
                      "quede su cifra, más se parece su portafolio a ese perfil en ese eje.", st_nota)]
        if xp.get("riesgo_lectura"):
            bloque += [Spacer(1, 6), ficha(xp["riesgo_lectura"], ancho)]
        h.append(KeepTogether(bloque))
    if xp.get("estres"):
        filas = [["Escenario histórico", "Caída S&amp;P 500", "Impacto estimado", "Patrimonio resultante"]]
        for x in xp["estres"]:
            filas.append([e(x["escenario"]), f"{x['spx']:.1f}%", f"<font color='#6b7280'>{ms(x['impacto'])}</font>", m(x["estresado"])])
        h.append(KeepTogether(_seccion("Estrés", "¿Qué pasaría en una crisis como las del pasado?") + [
            tabla(filas, [ancho * 0.34, ancho * 0.2, ancho * 0.22, ancho * 0.24], alinear_der=(1, 2, 3)),
            Paragraph(f"Impacto = valor de cada posición × su beta × la caída del índice. Su efectivo ({m(ctx['liquidez'], 0)}) no se mueve con el mercado. "
                      "Escenario aritmético: no considera el tipo de cambio ni la recuperación posterior.", st_nota)]))

    # ---------------- Dividendos y reportes ----------------
    dv = xp.get("dividendos")
    if dv:
        filas = [["Fecha ex", "Activo", "Por título", "Títulos", "Bruto MXN", "Estado"]]
        for x in dv["filas"]:
            filas.append([e(x["fecha"]), f"<b>{e(x['activo'])}</b>", f"{x['por_titulo']:,.4f} {e(x['moneda'])}", f"{x['titulos']:.6g}", m(x["mxn"]), e(x["estado"])])
        w = ancho / 6
        h.append(KeepTogether(_seccion("Dividendos", "Ingresos por dividendos") + [
            Paragraph(f"Cobrado desde su inicio: <b>{m(dv['cobrado'])}</b> · últimos 12 meses: <b>{m(dv['doce_meses'])}</b> (brutos estimados, antes de retenciones).", st_body),
            Spacer(1, 4), tabla(filas, [w * 0.95, w * 0.8, w * 1.15, w * 0.9, w, w * 1.2], alinear_der=(2, 3, 4)),
            Paragraph("Estimados con los títulos que tenía un día antes de la fecha ex y el tipo de cambio de ese día. Para su declaración, "
                      "confirme contra la constancia fiscal de su casa de bolsa.", st_nota)]))
    if xp.get("reportes_resultado"):
        filas = [["Fecha", "Emisora", "Resultado"]] + [[e(x["fecha"]), f"<b>{e(x['activo'])}</b>", e(x["detalle"])] for x in xp["reportes_resultado"]]
        h.append(KeepTogether(_seccion("Emisoras", "Reportes trimestrales recientes de sus emisoras") + [
            tabla(filas, [ancho * 0.14, ancho * 0.12, ancho * 0.74], chica=True)]))

    # ---------------- Agenda ----------------
    if xp.get("agenda"):
        filas = [["Fecha", "Tipo", "Evento", "Detalle"]] + [
            [e(x["fecha"]), e(x["tipo"]), f"<b>{e(x['titulo'])}</b>", e(x["detalle"][:170] + ("…" if len(x["detalle"]) > 170 else ""))] for x in xp["agenda"]]
        h.append(KeepTogether(_seccion("Agenda", "Lo que viene en las próximas 8 semanas") + [
            tabla(filas, [ancho * 0.13, ancho * 0.12, ancho * 0.25, ancho * 0.5], chica=True)]))

    # ---------------- Proyección ----------------
    pr = xp.get("proyeccion")
    if pr and pr.get("filas"):
        tx = pr.get("xirr")
        filas = [["Fecha", "Solo sus aportaciones", "Aportaciones + su rendimiento" + (f" ({tx * 100:+.2f}%)" if tx is not None else ""),
                  f"Aportaciones + CETES ({rf * 100:.2f}%)"]] + [
            [e(x["fecha"]), m(x["solo_aportaciones"], 0), m(x["con_xirr"], 0) if x.get("con_xirr") is not None else "—", m(x["con_cetes"], 0)]
            for x in pr["filas"]]
        nota_x = ("Su rendimiento es su XIRR actual" + (" (limitado a ±25% para proyectar)" if pr.get("xirr_original") is not None and abs(pr["xirr_original"]) > 0.25 else "")
                  + "; con poco historial puede cambiar mucho de un mes a otro." if tx is not None else "Aún no hay historia suficiente para calcular su XIRR.")
        h.append(KeepTogether(_seccion("Proyección", "Hacia dónde va con su ritmo de ahorro") + [
            Paragraph(f"Con una aportación de {m(pr['aporte'], 0)} al mes, partiendo de su patrimonio actual. La primera columna depende solo de usted; "
                      "las otras dos suman un supuesto de rendimiento.", st_body), Spacer(1, 4),
            tabla(filas, [ancho * 0.16, ancho * 0.26, ancho * 0.31, ancho * 0.27], alinear_der=(1, 2, 3)),
            Paragraph(nota_x + " Proyección con supuestos explícitos, no una promesa de rendimiento.", st_nota)]))

    # ---------------- Escenarios, disciplina, flujos y operaciones ----------------
    # «Escenarios observados» se retiró de la edición Pro (decisión 2026-10-16); el parámetro `escenarios` se conserva por compatibilidad.
    f = {k: v for k, v in (ctx.get("flujos") or {}).items() if v}
    act = ctx.get("actividad") or []
    if f or act:
        bloque = _seccion("Movimientos", "Flujo de caja y operaciones recientes")
        if f:
            bloque.append(tabla([[e(k), m(v)] for k, v in f.items()], [ancho * 0.68, ancho * 0.32], encabezado=False, alinear_der=(1,)))
        if act:
            filas = [["Fecha", "Tipo", "Activo", "Títulos", "T.C.", "Total MXN"]] + [
                [e(a["fecha"]), e(a["tipo"]), f"<b>{e(a['ticker'])}</b>", tit(a["titulos"]), f"{a['tc']:.4f}", m(a["total"])] for a in act]
            w = ancho / 6
            bloque += [Spacer(1, 6), tabla(filas, [w * 1.1, w * 0.95, w * 0.9, w, w * 0.9, w * 1.15], alinear_der=(3, 4, 5), chica=True)]
        h += bloque

    if ctx.get("cio"):
        caja = Table([[Paragraph(e(ctx["cio"]).replace("\n", "<br/>"), ParagraphStyle("cio", parent=st_body, fontSize=8.4, leading=12))]], colWidths=[ancho])
        caja.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_SELLO), ("LINEBEFORE", (0, 0), (0, -1), 1.5, C_ORO),
                                  ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 10)]))
        h += _seccion("CIO Virtual", "Boletín del CIO Virtual (informativo)") + [caja, Spacer(1, 3), Paragraph(e(aviso_cio), st_legal)]

    # ---------------- Metodología (sello) ----------------
    principios = [
        ("Precisión al centavo", "El costo usa el tipo de cambio que usted pagó en cada operación, con comisiones e IVA."),
        ("Rendimiento sin trampas", "Los depósitos no cuentan como ganancia: el rendimiento por periodo es ponderado por tiempo y el anual (XIRR) usa la fecha de cada flujo."),
        ("Comparación honesta", "Su resultado se contrasta contra el S&P 500 convertido a pesos y contra CETES, la referencia libre de riesgo."),
        ("Riesgo medido", "Doce meses de precios diarios: volatilidad, beta, caída máxima, VaR 95%, concentración y correlación."),
        ("Fuentes", "Cotizaciones, dividendos y reportes de Yahoo Finance; agenda de tasas de los calendarios oficiales de la FED y Banxico."),
        ("Información, no promesas", "Toda proyección declara sus supuestos. Ninguna cifra es una garantía ni una recomendación personalizada."),
    ]
    st_pt = ParagraphStyle("pt", parent=st_body, fontSize=8, leading=11.2, textColor=C_SOFT)
    celda = lambda t, d: Paragraph(f"<font name='Helvetica-Bold' color='#1f2937' size='8.6'>{t}</font><br/>{e(d)}", st_pt)
    ancho_in = ancho - 28
    grid = Table([[celda(*principios[i]), celda(*principios[i + 1])] for i in (0, 2, 4)], colWidths=[ancho_in / 2, ancho_in / 2])
    grid.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, C_SELLO_BORDE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    enc = Table([[Sello(), Paragraph("<font name='Helvetica' size='7' color='#8a7a4a'>E S T Á N D A R &nbsp; C M A</font><br/>"
                                     "<font name='Times-Italic' size='14' color='#8a6d1f'>Cómo construimos cada número</font>", ParagraphStyle("st", parent=st_body, leading=17))]],
                colWidths=[18 * mm, ancho_in - 18 * mm])
    enc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    sello = Table([[[enc, Spacer(1, 6), grid, Spacer(1, 6), Paragraph(f"Emitido el {hoy:%d/%m/%Y} &middot; Folio {folio} &middot; Edición Pro",
                                                                      ParagraphStyle("fo", parent=st_body, fontSize=7.4, textColor=C_ORO_TXT, alignment=TA_RIGHT))]]], colWidths=[ancho])
    sello.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), C_SELLO), ("BOX", (0, 0), (-1, -1), 0.6, C_SELLO_BORDE), ("LINEABOVE", (0, 0), (-1, 0), 1.6, C_ORO),
                               ("LEFTPADDING", (0, 0), (-1, -1), 14), ("RIGHTPADDING", (0, 0), (-1, -1), 14), ("TOPPADDING", (0, 0), (-1, -1), 14), ("BOTTOMPADDING", (0, 0), (-1, -1), 12)]))
    h += [Spacer(1, 18), KeepTogether([sello]), Spacer(1, 16),
          Paragraph("Quedamos a sus órdenes para revisar cualquier punto.", st_body), Spacer(1, 5),
          Paragraph("<font name='Times-Roman' size='12'>CMA &middot; Private Wealth</font><br/><font color='#6b7280'>Terminal APPortafolio</font>", st_body),
          Spacer(1, 14), Table([[""]], colWidths=[ancho], style=[("LINEABOVE", (0, 0), (-1, 0), 0.5, C_LINEA)]),
          Paragraph("Documento informativo generado automáticamente con datos registrados por el cliente y cotizaciones de mercado (Yahoo Finance). "
                    "Los rendimientos son no realizados y no garantizan resultados futuros. Las proyecciones y escenarios usan supuestos explícitos y no "
                    "constituyen una recomendación personalizada de inversión.<br/><br/>" + e(aviso_legal), st_legal)]

    def fondo(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(C_PAPEL); canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
        canvas.setFont("Helvetica", 6.8); canvas.setFillColor(C_ORO_TXT)
        canvas.drawString(16 * mm, 10 * mm, f"CMA · Private Wealth · Edición Pro · Folio {folio}")
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, f"Página {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"CMA Financial Letter Pro · {ctx['nombre']}", author="CMA · Private Wealth", subject=f"Folio {folio}")
    doc.build(h, onFirstPage=fondo, onLaterPages=fondo)
    return buf.getvalue()


def paginas_png(pdf_bytes, escala=1.4, maximo=12):
    """Vista previa fiel: las páginas del PDF como imágenes (pypdfium2). Devuelve [] si la librería no está."""
    try:
        import pypdfium2 as pdfium
    except Exception:
        return []
    out = []
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        for i in range(min(len(doc), maximo)):
            img = doc[i].render(scale=escala).to_pil()
            b = io.BytesIO(); img.save(b, format="PNG", optimize=True); out.append(b.getvalue())
    finally:
        doc.close()
    return out
