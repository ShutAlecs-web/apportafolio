"""
pro_ui.py · Componentes del Modo Pro (rediseño 2026-10) y del encabezado común.

Capa aditiva (Norma 3): app.py llama a estas funciones; si alguna falla, app.py captura el error y la sección
se omite con un aviso discreto en lugar de tumbar la Terminal. Las utilidades de app.py (estilo de gráficas,
caché de precios, Gemini…) llegan en el objeto `H` para no crear importaciones circulares.

Lenguaje: informativo y condicional (Norma 2). Ninguna salida instruye a comprar o vender.
"""
import html as _html
import math
from datetime import datetime, timedelta, timezone, date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ZONA_MX = timezone(timedelta(hours=-6))   # CDMX sin horario de verano desde 2022

ORO, ORO2, ORO3, LUZ = "#c9a24a", "#e2c575", "#f3e2b0", "#fff4d6"
ACERO, PIZARRA, VERDE, GRIS = "#7fa3c9", "#6b7385", "#5fbf9a", "#9aa3b2"
PALETA_ORO = ["#f3e2b0", "#e2c575", "#c9a24a", "#a8883f", "#8a6f33", "#6b5628"]
PALETA_GRIS = ["#9aa3b2", "#7d8494", "#6b7385", "#565d6c"]
ESCALA_RENDIMIENTO = [[0.0, "#5f6879"], [0.25, "#959dad"], [0.5, "#e2a91f"], [0.72, "#7cb82f"], [1.0, "#12a150"]]

e = lambda x: _html.escape(str(x if x is not None else ""))


def m(v, d=2):
    v = float(v or 0)
    return f"{'-' if v < 0 else ''}${abs(v):,.{d}f}"


def ms(v, d=2):
    v = float(v or 0)
    return f"{'+' if v >= 0 else '-'}${abs(v):,.{d}f}"


def pc(v, d=2):
    v = float(v or 0)
    return f"{'+' if v >= 0 else ''}{v:.{d}f}%"


def cls(v):
    return "ap-pos" if float(v or 0) >= 0 else "ap-neg"


def titulo_seccion(texto):
    st.markdown("<h4 class='notranslate' translate='no' style='color:#ffffff; font-family:\"Playfair Display\", serif; font-size:1.2rem; "
                f"font-style:italic; margin:22px 0 12px 0; letter-spacing:1px;'>{e(texto)}</h4>", unsafe_allow_html=True)


def selector(etiqueta, opciones, key, default=None):
    """Botones segmentados (Streamlit >= 1.40); en versiones anteriores, radio horizontal."""
    default = default if default in opciones else opciones[0]
    f = getattr(st, "segmented_control", None)
    if f is not None:
        if key not in st.session_state:
            st.session_state[key] = default
        v = f(etiqueta, opciones, key=key, label_visibility="collapsed")
        return v if v in opciones else default
    return st.radio(etiqueta, opciones, key=key, horizontal=True, label_visibility="collapsed", index=opciones.index(default))


# =====================================================================================================
# 1. ENCABEZADO (ambos modos): saludo según la hora + estado de mercados EE.UU. y México
# =====================================================================================================
def _horario_verano_eua(dt_utc):
    """EE.UU.: del 2.º domingo de marzo (7:00 UTC) al 1.er domingo de noviembre (6:00 UTC)."""
    y = dt_utc.year
    mar = datetime(y, 3, 8, tzinfo=timezone.utc); mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc); nov += timedelta(days=(6 - nov.weekday()) % 7)
    return mar + timedelta(hours=7) <= dt_utc < nov + timedelta(hours=6)


def estado_mercados(ahora_utc=None):
    """NYSE 9:30–16:00 hora de Nueva York. La BMV opera alineada al mismo horario (por eso en CDMX abre 7:30 u 8:30).
    No contempla días feriados. Devuelve [(mercado, abierto, texto en hora CDMX)]."""
    ahora = ahora_utc or datetime.now(timezone.utc)
    off_et = -4 if _horario_verano_eua(ahora) else -5
    et = ahora + timedelta(hours=off_et)
    apertura = et.replace(hour=9, minute=30, second=0, microsecond=0)
    cierre = et.replace(hour=16, minute=0, second=0, microsecond=0)
    habil = et.weekday() < 5
    abierto = habil and apertura <= et < cierre
    a_mx = lambda t: (t - timedelta(hours=off_et) + timedelta(hours=-6)).strftime("%H:%M")
    if abierto:
        texto = f"abierto · cierra {a_mx(cierre)}"
    else:
        sig = apertura if (habil and et < apertura) else apertura + timedelta(days=1)
        while sig.weekday() >= 5:
            sig += timedelta(days=1)
        dia = "hoy" if sig.date() == et.date() else ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"][sig.weekday()]
        texto = f"cerrado · abre {dia} {a_mx(sig)}"
    return [("EE.UU. · NYSE", abierto, texto), ("México · BMV", abierto, texto)]


def saludo(ahora_mx=None):
    h = (ahora_mx or datetime.now(ZONA_MX)).hour
    return "Buenos días" if 5 <= h < 12 else ("Buenas tardes" if 12 <= h < 19 else "Buenas noches")


def html_encabezado(nombre, pro=False):
    pills = "".join(
        f"<span class='ap-mkt {'on' if ab else ''}'><i></i>{e(n)} <b>{e(t)}</b></span>" for n, ab, t in estado_mercados())
    eti = "Terminal Pro" if pro else "Vista general"
    return (f"<div class='ap-masthead ap-masthead-v2 notranslate' translate='no'><div>"
            f"<p class='ap-eyebrow'>CMA Wealth · {eti}</p><h3>{e(saludo())}, {e(nombre)}</h3></div>"
            f"<div class='ap-mkts'>{pills}</div></div>")


def html_meta_historial(n_ops, n_mov, ultimo):
    return (f"<div class='ap-hist-meta notranslate' translate='no'>"
            f"<div><span>Operaciones</span><b>{n_ops}</b></div><div><span>Movimientos de caja</span><b>{n_mov}</b></div>"
            f"<div><span>Último registro</span><b>{e(ultimo)}</b></div></div>")


# =====================================================================================================
# 1-B. INDICADORES PRO · patrimonio con su gráfica de 30 días + columna de P&L, liquidez y XIRR con mini líneas
# =====================================================================================================
def _serie_efectivo(cash_df, idx):
    caja = cash_df.copy()
    caja["fecha"] = pd.to_datetime(caja["fecha"]).dt.normalize()
    entradas, salidas = {"DEPOSITO", "VENTA", "DIVIDENDO"}, {"COMPRA", "RETIRO", "COMISION", "IMPUESTO"}
    monto = caja["monto_mxn"].astype(float).abs()
    caja["delta"] = np.where(caja["tipo"].isin(entradas), monto, np.where(caja["tipo"].isin(salidas), -monto, 0.0))
    acum = caja.groupby("fecha")["delta"].sum().sort_index().cumsum()
    return acum.reindex(acum.index.union(idx)).ffill().reindex(idx).fillna(0.0).clip(lower=0.0)


def _svg_linea(vals, w, h, color=ORO2, area=False, luz=False, uid="a"):
    v = [float(x) for x in vals if x is not None and np.isfinite(float(x))]
    if len(v) < 2:
        return ""
    mn, mx = min(v), max(v)
    rango = (mx - mn) or (abs(mx) * 0.01 or 1.0)
    pts = [(w * i / (len(v) - 1), h - 3 - (h - 6) * (x - mn) / rango) for i, x in enumerate(v)]
    d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
    relleno = (f"<defs><linearGradient id='g{uid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{color}' stop-opacity='0.28'/>"
               f"<stop offset='1' stop-color='{color}' stop-opacity='0'/></linearGradient></defs><path d='{d} L{w} {h} L0 {h}Z' fill='url(#g{uid})'/>") if area else ""
    brillo = (f"<path class='ap-luz-svg' d='{d}' pathLength='1000' fill='none' stroke='{LUZ}' stroke-width='2.2' vector-effect='non-scaling-stroke'/>") if luz else ""
    return (f"<svg viewBox='0 0 {w} {h}' preserveAspectRatio='none' class='ap-spk' aria-hidden='true'>{relleno}"
            f"<path d='{d}' fill='none' stroke='{color}' stroke-width='1.6' vector-effect='non-scaling-stroke'/>{brillo}</svg>")


COLOR_CLASE = {"ETF": "#c9a24a", "Acción": "#8a6f33", "Cripto": "#f3e2b0", "Efectivo": "#7fa3c9", "Otro": "#6b7385"}
ETQ_CLASE = {"ETF": "ETF", "Acción": "Acciones", "Cripto": "Cripto", "Efectivo": "Efectivo", "Otro": "Otros"}


def html_composicion(summary, liquidez, total):
    partes = {}
    if summary is not None and not summary.empty:
        for c, v in summary.groupby(summary["Clase"].fillna("Otro"))["valor_actual"].sum().items():
            partes[c if c in COLOR_CLASE else "Otro"] = partes.get(c if c in COLOR_CLASE else "Otro", 0.0) + float(v)
    partes["Efectivo"] = float(liquidez)
    orden = [k for k in ["ETF", "Acción", "Cripto", "Otro", "Efectivo"] if partes.get(k, 0) > 0]
    tot = sum(partes[k] for k in orden) or 1.0
    barra = "".join(f"<div style='width:{partes[k] / tot * 100:.2f}%;background:{COLOR_CLASE[k]}' title='{ETQ_CLASE[k]}'></div>" for k in orden)
    ley = "".join(f"<div><p class='ap-t' style='margin:0'><i style='background:{COLOR_CLASE[k]}'></i>{ETQ_CLASE[k]}</p>"
                  f"<p class='ap-m' style='margin:0'>{m(partes[k], 0)} <span class='ap-s'>{partes[k] / tot * 100:.0f}%</span></p></div>" for k in orden)
    return f"<div class='ap-comp'>{barra}</div><div class='ap-comp-ley'>{ley}</div>"


def figura_patrimonio(H, df):
    """Patrimonio diario con escala, depósitos marcados y luz (formato de la opción D)."""
    v = df["valor"].astype(float)
    flujos = df["capital"].astype(float).diff().fillna(0.0)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df.index, y=v, mode="lines", line=dict(color=ORO2, width=1.8), fill="tozeroy", fillcolor="rgba(201,162,74,0.10)",
                             hovertemplate="%{x|%d %b %Y} · $%{y:,.2f}<extra></extra>", name="Patrimonio"))
    for f, x in flujos[flujos.abs() > 0.5].items():
        fig.add_vline(x=f, line=dict(color=ACERO, width=1, dash="dot"))
        fig.add_annotation(x=f, y=1, yref="paper", text="depósito" if x > 0 else "retiro", showarrow=False, xanchor="left",
                           font=dict(color=ACERO, size=10), xshift=3)
    fig.add_trace(go.Scatter(x=[df.index[-1]], y=[v.iloc[-1]], mode="markers", marker=dict(size=9, color=ORO2, line=dict(color="#050608", width=2)),
                             hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=df.index, y=v, mode="lines", line=dict(color=LUZ, width=2.0), hoverinfo="skip", showlegend=False, name="luz"))
    H.style(fig, height=240, showlegend=False, margin=dict(t=18, b=6, l=4, r=4))
    lo, hi = float(v.min()), float(v.max())
    pad = (hi - lo) * 0.12 or hi * 0.02 or 1
    fig.update_yaxes(range=[lo - pad, hi + pad], side="right", tickprefix="$", tickformat=",.0f", nticks=4)
    fig.update_xaxes(range=[df.index[0], df.index[-1]], nticks=4, tickformat="%d %b")
    fig.update_layout(hovermode="x")
    return fig


def render_kpis_pro(H, cash_df, tx_df, total, pnl, retorno, capital, costo, liquidez, xirr, rf, summary=None):
    """Un solo cuadro: patrimonio + composición (izquierda), gráfica con escala y periodo (derecha) y abajo P&L, liquidez y XIRR.
    Devuelve True si se dibujó (app.py usa las tarjetas anteriores como respaldo)."""
    serie = None
    try:
        df = H.series_bola_nieve(cash_df, tx_df, total, rf) if cash_df is not None and not cash_df.empty else None
        if df is not None and df["valor"].notna().sum() >= 3:
            serie = df.dropna(subset=["valor"])
    except Exception as ex:
        H.log.warning("KPI Pro · sin serie: %s", ex)
    gana = xirr is not None and xirr >= rf
    with st.container(key="kpi_pro_card"):
        c1, c2 = st.columns([1, 1.45], gap="medium")
        with c1:
            st.markdown(
                "<div class='notranslate' translate='no'><p class='ap-t'>Patrimonio total</p>"
                f"<p class='ap-kpi-num ap-m'>{m(total)}</p>"
                f"<p class='ap-s' style='margin:0'><span class='{cls(pnl)}'>{ms(pnl)} · {pc(retorno)}</span> en tus posiciones · capital aportado {m(capital, 0)}</p>"
                f"{html_composicion(summary, liquidez, total)}</div>", unsafe_allow_html=True)
        with c2:
            if serie is None:
                st.markdown(f"<p class='ap-s' style='margin-top:30px'>Costo de posiciones {m(costo)}. La gráfica aparece cuando hay historial de precios "
                            "y al menos un depósito.</p>", unsafe_allow_html=True)
                vista = None
            else:
                periodo = selector("Periodo", ["7D", "30D", "3M", "Todo"], key="kpi_periodo", default="30D")
                dias = {"7D": 7, "30D": 30, "3M": 92}.get(periodo)
                vista = serie[serie.index >= serie.index[-1] - pd.Timedelta(days=dias)] if dias else serie
                if len(vista) < 2:
                    vista = serie.iloc[-2:]
                tw = _indice_twr(vista)
                mercado = (tw.iloc[-1] / tw.iloc[0] - 1) * 100
                depositos = float(vista["capital"].iloc[-1] - vista["capital"].iloc[0])
                st.markdown(f"<p class='ap-s ap-kpi-lectura notranslate' translate='no'><span class='{cls(mercado)}'>{pc(mercado)}</span> mercado en el periodo "
                            f"(sin depósitos) · depósitos netos {m(depositos, 0)}</p>", unsafe_allow_html=True)
                st.plotly_chart(figura_patrimonio(H, vista), use_container_width=True, config=H.cfg, key="kpi_graf")
        s30 = serie.iloc[-31:] if serie is not None else None
        pnl_vals = (s30["valor"] - s30["capital"]).tolist() if s30 is not None else []
        liq_vals = _serie_efectivo(cash_df, s30.index).tolist() if s30 is not None else []
        rend_vals = _indice_twr(s30).tolist() if s30 is not None and len(s30) >= 3 else []
        lateral = [
            ("P&amp;L neto acumulado", ms(pnl), cls(pnl), f"{pc(retorno)} sobre el costo", _svg_linea(pnl_vals, 120, 34, ORO2 if pnl >= 0 else GRIS, uid="p")),
            ("Liquidez disponible", m(liquidez), "ap-oro", f"{liquidez / total * 100 if total else 0:.1f}% del patrimonio", _svg_linea(liq_vals, 120, 34, ORO3, uid="l")),
            ("Rentabilidad XIRR", "N/D" if xirr is None else pc(xirr * 100), "" if xirr is None else ("ap-pos" if gana else "ap-neg"),
             f"CETES {rf * 100:.2f}%" + ("" if xirr is None else f" · {(xirr - rf) * 100:+.2f} pp"), _svg_linea(rend_vals, 120, 34, ORO2, uid="x")),
        ]
        st.markdown("<div class='ap-kpi-pie notranslate' translate='no'>" + "".join(
            f"<div><div style='min-width:0'><p class='ap-t'>{t}</p><p class='ap-m {c}' style='font-size:1.2rem;margin:0'>{v}</p>"
            f"<p class='ap-s' style='margin:2px 0 0'>{sub}</p></div><div class='ap-kpi-spk'>{svg}</div></div>" for t, v, c, sub, svg in lateral)
            + "</div>", unsafe_allow_html=True)
    return True


# =====================================================================================================
# 2. GRÁFICA PRINCIPAL PRO: (A) portafolio contra índices · (D) contribución por activo
# =====================================================================================================
def _indice_twr(df):
    """Índice base 100 ponderado por tiempo: quita el efecto de depósitos y retiros (flujo = cambio de capital)."""
    v = df["valor"].astype(float).values
    cap = df["capital"].astype(float).values
    idx = [100.0]
    for i in range(1, len(v)):
        flujo = cap[i] - cap[i - 1]
        r = ((v[i] - flujo) / v[i - 1] - 1) if v[i - 1] > 0 else 0.0
        idx.append(idx[-1] * (1 + (r if np.isfinite(r) else 0.0)))
    return pd.Series(idx, index=df.index)


def _contribucion_por_activo(tx_df, idx, cierres_fn, yf_symbol):
    """Ganancia acumulada por activo (MXN) día por día: títulos × precio − lo invertido neto en ese activo."""
    tx = tx_df.copy()
    tx["fecha"] = pd.to_datetime(tx["fecha"]).dt.normalize()
    tx["titulos"] = tx["titulos"].astype(float)
    tx["neto"] = np.where(tx["tipo_operacion"] == "COMPRA", 1.0, -1.0) * tx["total_mxn"].astype(float).abs()
    pos = tx.pivot_table(index="fecha", columns="ticker", values="titulos", aggfunc="sum").sort_index().cumsum()
    inv = tx.pivot_table(index="fecha", columns="ticker", values="neto", aggfunc="sum").sort_index().cumsum()
    pos = pos.reindex(pos.index.union(idx)).ffill().reindex(idx).fillna(0.0)
    inv = inv.reindex(inv.index.union(idx)).ffill().reindex(idx).fillna(0.0)
    tickers = [t for t in pos.columns if pos[t].abs().sum() > 0]
    simbolos = tuple(yf_symbol(t) for t in tickers)
    inicio = (idx[0] - timedelta(days=10)).strftime("%Y-%m-%d")
    precios = cierres_fn(simbolos, inicio)
    precios = precios.reindex(precios.index.union(idx)).ffill().bfill().reindex(idx)
    salida = {}
    for t, s in zip(tickers, simbolos):
        if s not in precios.columns:
            continue
        valor = pos[t] * precios[s].fillna(0.0)
        c = (valor - inv[t]).where(pos[t] > 1e-12, other=np.nan)
        # tras vender todo, la ganancia realizada se queda fija (no regresa a cero)
        salida[t] = c.ffill().fillna(0.0)
    return pd.DataFrame(salida, index=idx)


def render_grafica_pro(H, cash_df, tx_df, total_portafolio, rf):
    titulo_seccion("Rendimiento del portafolio")
    df = H.series_bola_nieve(cash_df, tx_df, total_portafolio, rf)
    if df is None or df.empty or df["valor"].notna().sum() < 3:
        st.info("Se necesita historial de precios y al menos un depósito para comparar tu rendimiento.")
        return
    df = df.dropna(subset=["valor"])
    c1, c2 = st.columns([1.4, 1])
    with c1:
        vista = selector("Vista", ["Portafolio vs índices", "Por activo"], key="pro_graf_vista")
    with c2:
        periodo = selector("Periodo", ["1M", "3M", "Todo"], key="pro_graf_periodo", default="Todo")
    dias = {"1M": 31, "3M": 92}.get(periodo)
    if dias:
        df = df[df.index >= df.index[-1] - pd.Timedelta(days=dias)]
    if len(df) < 3:
        st.caption("Aún no hay suficientes días en este periodo.")
        return

    with st.container(key="graf_pro_card"):
        fig = go.Figure()
        if vista == "Portafolio vs índices":
            tw = _indice_twr(df)
            port = (tw / tw.iloc[0] - 1) * 100
            dias_t = np.asarray((df.index - df.index[0]).days, dtype=float)
            cetes = (np.power(1 + rf, dias_t / 365.0) - 1) * 100
            try:
                spx = H.cierres_mxn(("^GSPC",), (df.index[0] - timedelta(days=10)).strftime("%Y-%m-%d"))["^GSPC"]
                spx = spx.reindex(spx.index.union(df.index)).ffill().bfill().reindex(df.index)
                spx = (spx / spx.iloc[0] - 1) * 100
            except Exception:
                spx = None
            if spx is not None:
                fig.add_trace(go.Scatter(x=df.index, y=spx, mode="lines", name=f"S&P 500 (en pesos) {pc(spx.iloc[-1], 1)}",
                                         line=dict(color=GRIS, width=1.4), hovertemplate="S&P 500: %{y:+.2f}%<extra></extra>"))
            fig.add_trace(go.Scatter(x=df.index, y=cetes, mode="lines", name=f"CETES {pc(cetes[-1], 1)}",
                                     line=dict(color=ACERO, width=1.4, dash="dash"), hovertemplate="CETES: %{y:+.2f}%<extra></extra>"))
            fig.add_trace(go.Scatter(x=df.index, y=port, mode="lines", name=f"Portafolio {pc(port.iloc[-1], 1)}",
                                     line=dict(color=ORO2, width=2.4), hovertemplate="Portafolio: %{y:+.2f}%<extra></extra>"))
            fig.add_trace(go.Scatter(x=df.index, y=port, mode="lines", line=dict(color=LUZ, width=2.2),
                                     hoverinfo="skip", showlegend=False, name="luz"))   # última traza = luz (CSS)
            fig.add_hline(y=0, line=dict(color="#2a303b", width=1))
            ytf, nota = "+.1f", ("Rendimiento ponderado por tiempo: tus depósitos no cuentan como ganancia. "
                                 "S&P 500 convertido a pesos con el tipo de cambio de cada día.")
            fig.update_yaxes(ticksuffix="%", tickformat="+.1f")
        else:
            contrib = _contribucion_por_activo(tx_df, df.index, H.cierres_mxn, H.yf_symbol)
            if contrib.empty:
                st.caption("Sin precios históricos por activo.")
                return
            contrib = contrib - contrib.iloc[0] if dias else contrib
            orden = contrib.iloc[-1].sort_values(ascending=False)
            k_oro = k_gris = 0
            for t in orden.index:
                serie = contrib[t]
                if orden[t] >= 0:
                    col = PALETA_ORO[k_oro % len(PALETA_ORO)]; k_oro += 1
                else:
                    col = PALETA_GRIS[k_gris % len(PALETA_GRIS)]; k_gris += 1
                etiqueta = f"{t} {ms(orden[t], 0)}"
                fig.add_trace(go.Scatter(x=df.index, y=serie.clip(lower=0), mode="lines", stackgroup="pos", name=etiqueta,
                                         legendgroup=t, line=dict(width=0.6, color=col), fillcolor=col,
                                         customdata=serie, hovertemplate=f"<b>{e(t)}</b>: " + "%{customdata:+,.2f} MXN<extra></extra>"))
                fig.add_trace(go.Scatter(x=df.index, y=serie.clip(upper=0), mode="lines", stackgroup="neg", showlegend=False,
                                         legendgroup=t, line=dict(width=0.6, color=col), fillcolor=col, hoverinfo="skip"))
            fig.add_hline(y=0, line=dict(color="#2a303b", width=1))
            nota = ("Ganancia o pérdida acumulada de cada activo en pesos (títulos × precio − lo invertido). "
                    "Arriba de cero suma a tu resultado; abajo, resta.")
            fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        H.style(fig, height=380, showlegend=True, margin=dict(t=10, b=10, l=6, r=12))
        fig.update_layout(hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0))
        fig.update_xaxes(range=[df.index[0], df.index[-1]], nticks=6, tickformat="%d %b", automargin=True)
        st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="graf_pro")
        st.caption(nota)


# =====================================================================================================
# 3. CALENDARIO DE DIVIDENDOS (histórico + próximos), base para contabilidad
# =====================================================================================================
@st.cache_data(ttl=86400, max_entries=200, show_spinner=False)
def _dividendos_yf(simbolo):
    import yfinance as yf
    try:
        s = yf.Ticker(simbolo).dividends
    except Exception:
        return []
    if s is None or len(s) == 0:
        return []
    out = []
    for f, v in s.items():
        try:
            out.append((pd.Timestamp(f).tz_localize(None).normalize().strftime("%Y-%m-%d") if pd.Timestamp(f).tzinfo else
                        pd.Timestamp(f).normalize().strftime("%Y-%m-%d"), float(v)))
        except Exception:
            continue
    return out


@st.cache_data(ttl=43200, max_entries=200, show_spinner=False)
def _calendario_yf(simbolo):
    """Próximos eventos de la emisora según Yahoo: reporte, fecha ex-dividendo y fecha de pago."""
    import yfinance as yf
    try:
        cal = yf.Ticker(simbolo).calendar
    except Exception:
        return {}
    if cal is None:
        return {}
    if isinstance(cal, pd.DataFrame):   # yfinance antiguo
        try:
            cal = {str(k): v for k, v in cal.iloc[:, 0].to_dict().items()}
        except Exception:
            return {}
    def _f(v):
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        try:
            return pd.Timestamp(v).strftime("%Y-%m-%d") if v is not None else None
        except Exception:
            return None
    return {"reporte": _f(cal.get("Earnings Date")), "ex": _f(cal.get("Ex-Dividend Date")), "pago": _f(cal.get("Dividend Date"))}


def tabla_dividendos(H, tx_df):
    """Dividendos brutos estimados por evento: títulos que tenías un día antes de la fecha ex × monto por título × TC del día."""
    if tx_df is None or tx_df.empty:
        return pd.DataFrame()
    tx = tx_df.copy()
    tx["fecha"] = pd.to_datetime(tx["fecha"]).dt.normalize()
    tx["titulos"] = tx["titulos"].astype(float)
    inicio = tx["fecha"].min()
    filas = []
    tickers = [t for t in tx["ticker"].unique() if str(H.asset_class.get(t, "")).lower() != "cripto" and t != "BTC"]
    try:
        fx = H.cierres_mxn(("USDMXN=X", "GBPMXN=X", "EURMXN=X"), (inicio - timedelta(days=10)).strftime("%Y-%m-%d"))
    except Exception:
        fx = pd.DataFrame()
    fx_hoy = {"USD": H.usd_mxn}
    def _tc(moneda, f):
        col = {"USD": "USDMXN=X", "GBP": "GBPMXN=X", "GBp": "GBPMXN=X", "GBX": "GBPMXN=X", "EUR": "EURMXN=X"}.get(moneda)
        if moneda == "MXN":
            return 1.0
        base = None
        if col and not fx.empty and col in fx.columns:
            s = fx[col].dropna()
            s = s[s.index <= f]
            base = float(s.iloc[-1]) if len(s) else None
        base = base or fx_hoy.get("USD", 18.0)
        return base / 100.0 if moneda in ("GBp", "GBX") else base
    hoy = pd.Timestamp(datetime.now(ZONA_MX).date())
    for t in tickers:
        sym = H.yf_symbol(t)
        moneda = H.moneda(sym)
        mov = tx[tx["ticker"] == t].sort_values("fecha")
        for f_ex, monto in _dividendos_yf(sym):
            fx_ex = pd.Timestamp(f_ex)
            if fx_ex < inicio:
                continue
            titulos = float(mov[mov["fecha"] < fx_ex]["titulos"].sum())
            if titulos <= 1e-12:
                continue
            filas.append({"fecha_ex": f_ex, "pago": None, "activo": t, "por_titulo": monto, "moneda": moneda, "titulos": titulos,
                          "bruto": monto * titulos, "bruto_mxn": monto * titulos * _tc(moneda, fx_ex), "estado": "Cobrado" if fx_ex <= hoy else "Próximo"})
        cal = _calendario_yf(sym)
        if cal.get("ex") and pd.Timestamp(cal["ex"]) > hoy:
            hist = _dividendos_yf(sym)
            ultimo = hist[-1][1] if hist else 0.0
            titulos = float(mov["titulos"].sum())
            if titulos > 1e-12 and ultimo > 0:
                filas.append({"fecha_ex": cal["ex"], "pago": cal.get("pago"), "activo": t, "por_titulo": ultimo, "moneda": moneda, "titulos": titulos,
                              "bruto": ultimo * titulos, "bruto_mxn": ultimo * titulos * _tc(moneda, hoy), "estado": "Próximo (estimado)"})
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).sort_values("fecha_ex", ascending=False).reset_index(drop=True)


def render_dividendos(H, tx_df, nombre_cliente):
    titulo_seccion("Calendario de dividendos")
    try:
        df = tabla_dividendos(H, tx_df)
    except Exception as ex:
        H.log.warning("Dividendos · %s", ex)
        st.caption("No pude consultar los dividendos en este momento.")
        return
    if df.empty:
        st.markdown("<div class='ap-card-pro notranslate' translate='no'><p class='ap-s' style='margin:0'>Tus posiciones actuales no han pagado "
                    "dividendos desde tu primera compra. Los ETF de acumulación (como ISAC, EIMI, XNAS o XDWH) reinvierten sus dividendos "
                    "dentro del fondo, así que no generan pagos.</p></div>", unsafe_allow_html=True)
        return
    cobr = df[df["estado"] == "Cobrado"]
    hace12 = (pd.Timestamp(datetime.now(ZONA_MX).date()) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")
    prox = df[df["estado"] != "Cobrado"].sort_values("fecha_ex")
    prox_txt = f"{prox.iloc[0]['activo']} · {prox.iloc[0]['fecha_ex']}" if len(prox) else "Sin fecha anunciada"
    st.markdown(
        "<div class='ap-banda ap-filo notranslate' translate='no'>"
        f"<div><p class='ap-t'>Cobrado desde tu inicio</p><p class='ap-v ap-m'>{m(cobr['bruto_mxn'].sum())}</p><p class='ap-s'>bruto estimado, antes de retenciones</p></div>"
        f"<div><p class='ap-t'>Últimos 12 meses</p><p class='ap-v ap-m'>{m(cobr[cobr['fecha_ex'] >= hace12]['bruto_mxn'].sum())}</p><p class='ap-s'>{len(cobr)} pago(s)</p></div>"
        f"<div><p class='ap-t'>Próximo</p><p class='ap-v ap-m' style='font-size:1.25rem'>{e(prox_txt)}</p>"
        f"<p class='ap-s'>{m(prox.iloc[0]['bruto_mxn']) + ' estimado' if len(prox) else 'Yahoo Finance aún no publica la fecha'}</p></div></div>",
        unsafe_allow_html=True)
    if len(cobr):
        mens = cobr.assign(mes=pd.to_datetime(cobr["fecha_ex"]).dt.to_period("M").dt.to_timestamp())
        piv = mens.pivot_table(index="mes", columns="activo", values="bruto_mxn", aggfunc="sum").fillna(0.0)
        fig = go.Figure()
        for k, t in enumerate(piv.columns):
            fig.add_trace(go.Bar(x=piv.index, y=piv[t], name=t, marker_color=PALETA_ORO[k % len(PALETA_ORO)],
                                 hovertemplate=f"<b>{e(t)}</b> " + "%{x|%b %Y}: $%{y:,.2f} MXN<extra></extra>"))
        H.style(fig, height=260, showlegend=True, margin=dict(t=10, b=10, l=6, r=12))
        fig.update_layout(barmode="stack", legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="left", x=0))
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        fig.update_xaxes(tickformat="%b %Y")
        st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="dividendos_graf")
    filas = "".join(
        f"<tr><td class='ap-m'>{e(r['fecha_ex'])}</td><td class='ap-m'>{e(r['pago'] or '—')}</td><td class='tk'>{e(r['activo'])}</td>"
        f"<td class='n ap-m'>{r['por_titulo']:,.4f} {e(r['moneda'])}</td><td class='n ap-m'>{float(r['titulos']):.6g}</td>"
        f"<td class='n ap-m'>{m(r['bruto_mxn'])}</td><td><span class='ap-pill{'' if r['estado'] == 'Cobrado' else ' gris'}'>{e(r['estado'])}</span></td></tr>"
        for _, r in df.iterrows())
    st.markdown("<div class='ap-tw notranslate' translate='no' style='max-height:320px;'><table><tr><th>Fecha ex</th><th>Pago</th><th>Activo</th>"
                "<th class='n'>Por título</th><th class='n'>Títulos</th><th class='n'>Bruto MXN</th><th>Estado</th></tr>"
                f"{filas}</table></div>", unsafe_allow_html=True)
    c1, c2 = st.columns([1, 2.4], vertical_alignment="center")
    c1.download_button("Exportar para contabilidad (CSV)", data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"Dividendos_{nombre_cliente}_{datetime.now(ZONA_MX):%Y%m%d}.csv", mime="text/csv",
                       use_container_width=True, key="dividendos_csv")
    c2.caption("Montos brutos estimados con los títulos que tenías un día antes de la fecha ex y el tipo de cambio de ese día. "
               "No incluyen retenciones en el país de origen; el monto real es el que reporta tu casa de bolsa.")


# =====================================================================================================
# 4. PROGRESO PRO · escalera por aportaciones con supuesto de rendimiento seleccionable
# =====================================================================================================
_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def aportacion_mensual_estimada(cash_df, pmt, user_freq):
    por_mes = {"SEMANAL": 52 / 12, "QUINCENAL": 2.0, "MENSUAL": 1.0}.get(user_freq, 1.0)
    if pmt and pmt > 0:
        return float(pmt) * por_mes
    dep = cash_df[cash_df["tipo"] == "DEPOSITO"] if cash_df is not None and not cash_df.empty else pd.DataFrame()
    if dep.empty:
        return 0.0
    f = pd.to_datetime(dep["fecha"])
    meses = max(1.0, (f.max() - f.min()).days / 30.44)
    return float(dep["monto_mxn"].astype(float).abs().sum()) / meses


def render_progreso_pro(cash_df, patrimonio, capital_aportado, pmt, user_freq, xirr, rf, cliente_id):
    titulo_seccion("Progreso y futuro · escalera de aportaciones")
    k_ap = f"pro_aporte_{cliente_id}"
    if k_ap not in st.session_state:
        st.session_state[k_ap] = float(round(aportacion_mensual_estimada(cash_df, pmt, user_freq), -1))
    opciones = ["Solo aportaciones", f"CETES {rf * 100:.2f}%", "Conservador 7%"]
    if xirr is not None:
        opciones.append(f"Tu XIRR {xirr * 100:.2f}%")
    c1, c2 = st.columns([1, 1.6], vertical_alignment="bottom")
    with c1:
        aporte = st.number_input("Aportación mensual (MXN)", min_value=0.0, step=500.0, key=k_ap,
                                 help="Precargada con tu ritmo real de depósitos. Cámbiala para ver otro plan.")
    with c2:
        st.caption("Supuesto de rendimiento anual")
        sup = selector("Supuesto", opciones, key="pro_prog_sup", default=opciones[0])   # base: solo aportaciones
    tasa = 0.0 if sup == opciones[0] else (rf if sup == opciones[1] else (0.07 if sup == opciones[2] else max(min(xirr or 0, 0.25), -0.25)))
    r_m = (1 + tasa) ** (1 / 12) - 1
    hoy = datetime.now(ZONA_MX).date()
    filas, valor, aportado = [], float(patrimonio), float(capital_aportado)
    hitos = [h for h in [10000, 25000, 50000, 100000, 250000, 500000, 1000000] if h > patrimonio]
    eta = {}
    for mes in range(1, 61):
        valor = valor * (1 + r_m) + aporte
        aportado += aporte
        for h in hitos:
            if h not in eta and valor >= h:
                y, mm = hoy.year + (hoy.month - 1 + mes) // 12, (hoy.month - 1 + mes) % 12
                eta[h] = f"{_MESES[mm]} {y}"
        if mes % 4 == 0 and mes <= 36:
            y, mm = hoy.year + (hoy.month - 1 + mes) // 12, (hoy.month - 1 + mes) % 12
            filas.append((f"{_MESES[mm].capitalize()} {y}", aportado, valor))
    tope = max(f[2] for f in filas) if filas else 1
    cuerpo = "".join(
        f"<div class='ap-esc'><span class='ap-m'>{e(n)}</span>"
        f"<div class='ap-esc-bar'><b class='base' style='width:{a / tope * 100:.1f}%'></b><b class='extra' style='left:{a / tope * 100:.1f}%;width:{max(v - a, 0) / tope * 100:.1f}%'></b></div>"
        f"<span class='ap-m n'>{m(v, 0)}</span><span class='ap-m n ap-pos'>{ms(v - a, 0) if tasa else '—'}</span></div>"
        for n, a, v in filas)
    chips = "".join(f"<span class='ap-pill'>{m(h, 0)} · {e(eta.get(h, 'más de 5 años'))}</span>" for h in hitos[:5])
    st.markdown(
        f"<div class='ap-card-pro ap-filo notranslate' translate='no'>"
        f"<div class='ap-esc ap-esc-cab'><span>Fecha</span><span>Aportado <i class='sw base'></i> + rendimiento <i class='sw extra'></i></span><span class='n'>Valor estimado</span><span class='n'>Rendimiento</span></div>"
        f"{cuerpo}<div class='ap-chips' style='margin-top:14px'>{chips}</div>"
        f"<p class='ap-s'>La parte marfil es lo que tú aportas: depende solo de ti. La parte dorada es el supuesto de rendimiento "
        f"({e(sup)}), que se suma encima y puede ser mayor, menor o negativo. Tu XIRR usa poco historial, así que es el supuesto más inestable. "
        f"Proyección con supuestos explícitos, no una promesa.</p></div>", unsafe_allow_html=True)


# =====================================================================================================
# 5. POSICIONES PRO · tabla analítica / riesgo contra retorno / mapa de P&L
# =====================================================================================================
def _svg_spark(vals, w=84, h=22):
    try:
        v = [float(x) for x in (vals or []) if x is not None and np.isfinite(float(x))]
    except Exception:
        v = []
    if len(v) < 2:
        return ""
    mn, mx = min(v), max(v)
    col = ORO2 if v[-1] >= v[0] else GRIS
    pts = " ".join(f"{w * i / (len(v) - 1):.1f},{h - 2 - (h - 4) * (x - mn) / ((mx - mn) or 1):.1f}" for i, x in enumerate(v))
    return f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'><polyline points='{pts}' fill='none' stroke='{col}' stroke-width='1.4'/></svg>"


def render_posiciones_pro(H, summary, vols, betas):
    titulo_seccion("Tus posiciones")
    if summary is None or summary.empty:
        st.caption("Aún no tienes posiciones abiertas.")
        return
    vista = selector("Vista de posiciones", ["Tabla analítica", "Riesgo vs retorno", "Mapa de P&L", "Ver las tres"], key="pro_posi_vista")
    df = summary.sort_values("valor_actual", ascending=False).copy()
    df["vol"] = df["ticker"].map(lambda t: vols.get(t, np.nan))
    df["beta"] = df["ticker"].map(lambda t: betas.get(t, np.nan))
    if vista in ("Tabla analítica", "Ver las tres"):
        pill = lambda c: "a" if c == "ETF" else ("v" if c == "Cripto" else "")
        filas = "".join(
            f"<tr><td class='tk'>{e(r['ticker'])} <span class='ap-pill {pill(r['Clase'])}' style='margin-left:6px'>{e(r['Clase'])}</span></td>"
            f"<td class='n ap-m'>{float(r['titulos']):.8g}</td><td class='n ap-m'>{m(r['costo_promedio'])}</td><td class='n ap-m'>{m(r['precio_mercado'])}</td>"
            f"<td class='n ap-m'>{m(r['valor_actual'])}</td><td class='n ap-m {cls(r['pnl'])}'>{ms(r['pnl'])}</td><td class='n ap-m {cls(r['retorno_pct'])}'>{pc(r['retorno_pct'])}</td>"
            f"<td class='n ap-m'>{float(r['ponderacion_pct']):.1f}%</td><td class='n ap-m'>{'—' if pd.isna(r['beta']) else f'{r.beta:.2f}'}</td>"
            f"<td class='n ap-m'>{'—' if pd.isna(r['vol']) else f'{r.vol:.0f}%'}</td><td>{_svg_spark(r.get('Tendencia (30D)'))}</td></tr>"
            for _, r in df.iterrows())
        st.markdown("<div class='ap-tw notranslate' translate='no'><table style='min-width:980px'><tr><th>Activo</th><th class='n'>Títulos</th>"
                    "<th class='n'>Costo prom.</th><th class='n'>Precio</th><th class='n'>Valor</th><th class='n'>P&amp;L</th><th class='n'>Rend.</th>"
                    "<th class='n'>Peso</th><th class='n'>Beta</th><th class='n'>Vol.</th><th>30 días</th></tr>"
                    f"{filas}</table></div>", unsafe_allow_html=True)
    if vista in ("Riesgo vs retorno", "Ver las tres"):
        d = df.dropna(subset=["vol"])
        if d.empty:
            st.caption("Sin historial suficiente para medir volatilidad.")
        else:
            fig = go.Figure(go.Scatter(
                x=d["vol"], y=d["retorno_pct"], mode="markers+text", text=d["ticker"], textposition="middle center",
                textfont=dict(color="#ffffff", size=11), customdata=np.stack([d["ponderacion_pct"], d["valor_actual"]], axis=-1),
                marker=dict(size=(12 + d["ponderacion_pct"].astype(float) * 2.6).clip(upper=60), sizemode="diameter",
                            color=["rgba(226,197,117,0.30)" if v >= 0 else "rgba(154,163,178,0.30)" for v in d["retorno_pct"]],
                            line=dict(color=[ORO2 if v >= 0 else GRIS for v in d["retorno_pct"]], width=1.4)),
                hovertemplate="<b>%{text}</b><br>Volatilidad %{x:.0f}%<br>Rendimiento %{y:+.2f}%<br>Peso %{customdata[0]:.1f}%<extra></extra>"))
            fig.add_hline(y=0, line=dict(color="#2a303b", width=1))
            H.style(fig, height=380, showlegend=False, xgrid=True, margin=dict(t=10, b=10, l=6, r=12))
            fig.update_xaxes(title=dict(text="Volatilidad anual", font=dict(size=11)), ticksuffix="%")
            fig.update_yaxes(title=dict(text="Rendimiento", font=dict(size=11)), ticksuffix="%", tickformat="+.0f")
            with st.container(key="posi_scatter_card"):
                st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="posi_scatter")
                st.caption("Arriba a la izquierda: más rendimiento con menos volatilidad. El tamaño de cada burbuja es su peso en el portafolio.")
    if vista in ("Mapa de P&L", "Ver las tres"):
        d = df.copy()
        d["etq"] = d["ticker"]
        fig = px.treemap(d, path=["Clase", "ticker"], values="valor_actual", color="retorno_pct",
                         color_continuous_scale=ESCALA_RENDIMIENTO, color_continuous_midpoint=0, custom_data=["pnl", "retorno_pct"])
        fig.update_traces(texttemplate="<b>%{label}</b><br>%{customdata[1]:+.2f}%", marker=dict(line=dict(color="#050608", width=1.5)),
                          hovertemplate="<b>%{label}</b><br>Valor $%{value:,.2f}<br>P&L %{customdata[0]:+,.2f}<br>Rend. %{customdata[1]:+.2f}%<extra></extra>",
                          root_color="rgba(0,0,0,0)")
        H.style(fig, height=380, margin=dict(t=6, b=6, l=6, r=6))
        fig.update_coloraxes(colorbar=dict(title=dict(text="Rend. %", font=dict(size=11)), len=0.7))
        with st.container(key="posi_tree_card"):
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="posi_tree")


# =====================================================================================================
# 6. RENDIMIENTO PRO · tríada + puente de P&L + piruletas
# =====================================================================================================
def puente_pnl(summary, tx_df, usd_mxn):
    """Descompone el P&L no realizado: efecto precio, efecto tipo de cambio y comisiones (suma = valor − costo)."""
    precio_ef = fx_ef = com_ef = 0.0
    compras = tx_df[tx_df["tipo_operacion"] == "COMPRA"]
    for _, p in summary.iterrows():
        c = compras[compras["ticker"] == p["ticker"]]
        bought = float(c["titulos"].sum())
        if bought <= 0:
            continue
        esc = float(p["titulos"]) / bought
        p_mxn, p_usd = float(p["precio_mercado"]), float(p.get("precio_mercado_usd") or 0.0)
        for _, r in c.iterrows():
            tit, pre, tc = float(r["titulos"]), float(r["precio_unitario"]), float(r["tipo_cambio"] or 1.0)
            fees = float(r["comision"]) + float(r["iva"])
            coherente = p_usd > 0 and p_mxn > 0 and abs(p_usd * usd_mxn / p_mxn - 1) < 0.03
            if str(r["moneda"]).upper() == "MXN" or tc <= 1.0001 or not coherente:
                precio_ef += esc * tit * (p_mxn - pre * tc)
                com_ef -= esc * fees * tc
            else:
                precio_ef += esc * tit * (p_usd - pre) * tc
                fx_ef += esc * tit * p_usd * (usd_mxn - tc)
                com_ef -= esc * fees * tc
    return precio_ef, fx_ef, com_ef


def render_rendimiento_pro(H, summary, tx_df, xirr, rf, friccion, usd_mxn):
    titulo_seccion("Análisis de rendimiento y atribución")
    gana = xirr is not None and xirr >= rf
    cetes_txt = "Sin historia suficiente" if xirr is None else (f"Sí · {(xirr - rf) * 100:+.2f} pp" if gana else f"Todavía no · {(xirr - rf) * 100:+.2f} pp")
    st.markdown(
        "<div class='ap-banda ap-filo notranslate' translate='no'>"
        f"<div><p class='ap-t'>Rentabilidad ponderada (XIRR)</p><p class='ap-v ap-m {'' if xirr is None else cls(xirr)}'>{'N/D' if xirr is None else pc(xirr * 100)}</p><p class='ap-s'>con las fechas exactas de tus depósitos</p></div>"
        f"<div><p class='ap-t'>Fricción financiera</p><p class='ap-v ap-m'>{m(friccion)}</p><p class='ap-s'>comisiones e IVA pagados</p></div>"
        f"<div><p class='ap-t'>¿Le ganas a CETES?</p><p class='ap-v ap-m {'ap-pos' if gana else 'ap-neg'}'>{e(cetes_txt)}</p><p class='ap-s'>contra {rf * 100:.2f}% anual</p></div>"
        "</div>", unsafe_allow_html=True)
    if summary is None or summary.empty:
        return
    c1, c2 = st.columns([1, 1.3])
    with c1:
        pr, fx, co = puente_pnl(summary, tx_df, usd_mxn)
        neto = pr + fx + co
        fig = go.Figure(go.Waterfall(
            x=["Precio", "Tipo de cambio", "Comisiones", "P&L neto"], y=[pr, fx, co, neto], measure=["relative", "relative", "relative", "total"],
            text=[ms(pr), ms(fx), ms(co), m(neto)], textposition="outside", textfont=dict(family="IBM Plex Mono, monospace", color="#e6e9ef", size=12),
            increasing=dict(marker=dict(color=VERDE)), decreasing=dict(marker=dict(color=PIZARRA)), totals=dict(marker=dict(color=ORO2)),
            connector=dict(line=dict(color="#2a303b", width=1)), hovertemplate="%{x}: %{y:+,.2f} MXN<extra></extra>"))
        H.style(fig, height=330, title="¿De dónde viene tu P&L?", showlegend=False, margin=dict(t=40, b=10, l=6, r=6))
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
        with st.container(key="puente_card"):
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="puente_pnl")
            st.caption("Tipo de cambio: lo que ganaste o perdiste porque el dólar subió o bajó desde que compraste. "
                       "En compras registradas en pesos, ese efecto queda dentro de «Precio».")
    with c2:
        d = summary.sort_values("pnl").copy()
        fig = go.Figure()
        for _, r in d.iterrows():
            col = ORO2 if r["pnl"] >= 0 else GRIS
            fig.add_shape(type="line", x0=0, x1=float(r["pnl"]), y0=r["ticker"], y1=r["ticker"], line=dict(color=col, width=1.6))
        fig.add_trace(go.Scatter(x=d["pnl"], y=d["ticker"], mode="markers+text", text=[ms(v, 0) for v in d["pnl"]],
                                 textposition=["middle right" if v >= 0 else "middle left" for v in d["pnl"]],
                                 textfont=dict(family="IBM Plex Mono, monospace", size=11, color=[ORO2 if v >= 0 else GRIS for v in d["pnl"]]),
                                 marker=dict(size=11, color=[ORO2 if v >= 0 else GRIS for v in d["pnl"]]),
                                 hovertemplate="<b>%{y}</b>: %{x:+,.2f} MXN<extra></extra>"))
        H.style(fig, height=330, title="Atribución neta por activo (MXN)", showlegend=False, xgrid=True, ygrid=False, margin=dict(t=40, b=10, l=6, r=40))
        lim = float(max(d["pnl"].abs().max(), 1)) * 1.35
        fig.update_xaxes(range=[-lim, lim], tickprefix="$", zeroline=True, zerolinecolor="#2a303b")
        with st.container(key="piruletas_card"):
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="piruletas")


# =====================================================================================================
# 7. RIESGO PRO · radar de perfil + matriz agrupada por familia + lectura de métricas
# =====================================================================================================
REFERENCIA_AGRESIVA = {"Volatilidad": 0.25, "Beta": 1.30, "Caída": 0.35, "Concentración": 0.25, "Correlación": 0.60}
TOPES = {"Volatilidad": 0.40, "Beta": 2.0, "Caída": 0.40, "Concentración": 0.50, "Correlación": 1.0}


def metricas_riesgo_pro(H, summary, total_portafolio, rf):
    tickers = summary["ticker"].tolist()
    r_usd, r_mxn, betas = H.riesgo(tickers)
    if r_usd.empty or r_mxn.empty:
        return None
    pesos = (summary.set_index("ticker")["ponderacion_pct"] / 100).to_dict()
    port = pd.Series(0.0, index=r_mxn.index)
    for t in r_mxn.columns:
        if t in pesos:
            port += r_mxn[t] * pesos[t]
    vol = float(port.std() * np.sqrt(252))
    sharpe = (float(port.mean() * 252) - rf) / vol if vol > 0 else 0.0
    acum = (1 + port).cumprod()
    max_dd = float(((acum - acum.cummax()) / acum.cummax()).min())
    var95 = total_portafolio * abs(float(np.percentile(port, 5)))
    beta = float(sum(pesos.get(t, 0) * betas.get(t, 1.0) for t in tickers))
    inv = summary["valor_actual"].astype(float)
    w = inv / inv.sum() if inv.sum() > 0 else inv
    hhi = float((w ** 2).sum())
    corr = r_usd.corr()
    n = corr.shape[0]
    corr_media = float((np.nansum(corr.values) - np.nansum(np.diag(corr.values))) / (n * (n - 1))) if n > 1 else 0.0
    spx_dd, spx_vol = None, None
    try:
        simbolos = tuple(dict.fromkeys([H.yf_symbol(t) for t in tickers] + ["^GSPC", "USDMXN=X"]))
        s = H.cierres_riesgo(simbolos)["^GSPC"].dropna()
        a = s / s.cummax()
        spx_dd = float(a.min() - 1)
        spx_vol = float(s.pct_change().dropna().std() * np.sqrt(252))
    except Exception:
        pass
    vols = {t: float(r_mxn[t].std() * np.sqrt(252) * 100) for t in r_mxn.columns}
    return {"vol": vol, "sharpe": sharpe, "max_dd": max_dd, "var95": var95, "beta": beta, "hhi": hhi, "corr_media": corr_media,
            "corr": corr, "betas": betas, "vols": vols, "spx_dd": spx_dd, "spx_vol": spx_vol}


def render_riesgo_pro(H, R, summary, total_portafolio):
    titulo_seccion("Módulo cuantitativo de riesgo")
    if R is None:
        st.info("Se necesitan al menos 30 días de precios para medir el riesgo.")
        return
    tuyo = {"Volatilidad": R["vol"], "Beta": R["beta"], "Caída": abs(R["max_dd"]), "Concentración": R["hhi"], "Correlación": max(R["corr_media"], 0)}
    ejes = list(tuyo)
    norm = lambda d: [min(max(d[k] / TOPES[k], 0), 1) for k in ejes]
    c1, c2 = st.columns([1, 1.15])
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(r=norm(REFERENCIA_AGRESIVA) + norm(REFERENCIA_AGRESIVA)[:1], theta=ejes + ejes[:1], name="Referencia agresiva",
                                      line=dict(color=ACERO, width=1.4, dash="dash"), fill="toself", fillcolor="rgba(127,163,201,0.06)", hoverinfo="skip"))
        fig.add_trace(go.Scatterpolar(r=norm(tuyo) + norm(tuyo)[:1], theta=ejes + ejes[:1], name="Tu portafolio",
                                      line=dict(color=ORO2, width=2.2), fill="toself", fillcolor="rgba(201,162,74,0.22)", hoverinfo="skip"))
        H.style(fig, height=340, showlegend=True, margin=dict(t=20, b=10, l=30, r=30))
        fig.update_layout(polar=dict(bgcolor="rgba(0,0,0,0)", radialaxis=dict(range=[0, 1], showticklabels=False, gridcolor="#2a303b", linecolor="#2a303b"),
                                     angularaxis=dict(gridcolor="#2a303b", linecolor="#2a303b", tickfont=dict(color="#a3a9b6", size=12))),
                          legend=dict(orientation="h", yanchor="top", y=-0.05, xanchor="center", x=0.5))
        with st.container(key="radar_card"):
            st.markdown("<p class='ap-t'>Tu perfil de riesgo</p>", unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="radar_riesgo")
    with c2:
        clase = summary.set_index("ticker")["Clase"].to_dict()
        orden = sorted(R["corr"].columns, key=lambda t: (["ETF", "Acción", "Cripto"].index(clase.get(t)) if clase.get(t) in ["ETF", "Acción", "Cripto"] else 9, t))
        c = R["corr"].loc[orden, orden]
        z, txt = [], []
        for i, a in enumerate(orden):
            fila_z, fila_t = [], []
            for j, b in enumerate(orden):
                v = float(c.iloc[i, j])
                if j > i:
                    fila_z.append(None); fila_t.append("")
                elif i == j:
                    fila_z.append(None); fila_t.append("")
                else:
                    fila_z.append(0.5 if v < 0 else (1.5 if v < 0.3 else (2.5 if v < 0.6 else 3.5))); fila_t.append(f"{v:.2f}")
            z.append(fila_z); txt.append(fila_t)
        cs = [[0, "#2a3a4a"], [0.25, "#2a3a4a"], [0.25, "#3a3220"], [0.5, "#3a3220"], [0.5, "#8a6f33"], [0.75, "#8a6f33"], [0.75, "#c9a24a"], [1, "#c9a24a"]]
        fig = go.Figure(go.Heatmap(z=z, x=orden, y=orden, text=txt, texttemplate="%{text}", textfont=dict(family="IBM Plex Mono, monospace", size=11, color="#f3f4f6"),
                                   colorscale=cs, zmin=0, zmax=4, showscale=False, xgap=2, ygap=2, hoverongaps=False,
                                   hovertemplate="%{y} · %{x}: %{text}<extra></extra>"))
        H.style(fig, height=340, margin=dict(t=10, b=10, l=6, r=6), xgrid=False, ygrid=False)
        fig.update_yaxes(autorange="reversed")
        with st.container(key="matriz_card"):
            st.markdown("<p class='ap-t'>Matriz de correlación agrupada por familia</p>", unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="matriz_familia")
            st.markdown("<div class='ap-chips notranslate' translate='no'><span class='ap-sw' style='--c:#c9a24a'>≥ 0.60 se mueven juntos</span>"
                        "<span class='ap-sw' style='--c:#8a6f33'>0.30–0.60 medio</span><span class='ap-sw' style='--c:#3a3220'>0–0.30 independientes</span>"
                        "<span class='ap-sw' style='--c:#2a3a4a'>negativa · se compensan</span></div>", unsafe_allow_html=True)

    # Qué significa la referencia agresiva y dónde estás tú
    lectura = {
        "Volatilidad": (f"{R['vol'] * 100:.1f}%", "25%", "Qué tanto sube y baja tu portafolio en un año."),
        "Beta": (f"{R['beta']:.2f}", "1.30", "Cuánto se mueve contra la bolsa de EE.UU. (1.00 = igual)."),
        "Caída": (f"{abs(R['max_dd']) * 100:.1f}%", "35%", "La peor caída desde un punto alto en 12 meses."),
        "Concentración": (f"{R['hhi']:.2f}", "0.25", "Qué tan cargado está en pocos activos (0 = muy repartido, 1 = un solo activo)."),
        "Correlación": (f"{R['corr_media']:.2f}", "0.60", "Qué tanto se mueven tus activos en bloque."),
    }
    filas = "".join(f"<tr><td class='tk'>{k}</td><td class='n ap-m ap-oro'>{v[0]}</td><td class='n ap-m'>{v[1]}</td><td style='color:#a3a9b6;white-space:normal'>{v[2]}</td></tr>"
                    for k, v in lectura.items())
    st.markdown("<div class='ap-card-pro notranslate' translate='no'><p class='ap-t'>¿Qué es la referencia agresiva?</p>"
                "<p class='ap-s' style='margin:0 0 10px'>Es un portafolio típico 100 % en acciones de crecimiento (tecnología, emergentes y cripto): "
                "volatilidad cercana a 25 %, beta de 1.3 y caídas de hasta 35 % en un mal año. Sirve como techo de comparación: "
                "mientras tu figura dorada quede dentro de la azul, tu portafolio asume menos riesgo que ese perfil en ese eje.</p>"
                f"<div class='ap-tw' style='border:0'><table><tr><th>Eje</th><th class='n'>Tú</th><th class='n'>Agresivo</th><th>Qué mide</th></tr>{filas}</table></div></div>",
                unsafe_allow_html=True)

    # Lectura en lenguaje llano (formato de la opción B)
    beta, sharpe, dd, var95 = R["beta"], R["sharpe"], R["max_dd"], R["var95"]
    mov = (f"Te mueves {abs(1 - beta) * 100:.0f}% {'menos' if beta < 1 else 'más'} que el mercado." if abs(1 - beta) >= 0.03 else "Te mueves prácticamente igual que el mercado.")
    sh = (f"Ganas {sharpe:.2f} puntos de rendimiento por cada punto de riesgo asumido." if sharpe > 0 else "Por ahora el rendimiento no compensa el riesgo asumido frente a CETES.")
    if R.get("spx_dd"):
        ratio = abs(dd) / abs(R["spx_dd"]) if R["spx_dd"] else 0
        cmp = "la mitad" if 0.4 <= ratio <= 0.6 else (f"{ratio:.1f} veces" if ratio > 1.05 else f"{ratio * 100:.0f}%")
        cai = f"Tu peor caída ({dd * 100:.1f}%) fue {cmp} de la del S&P 500 ({R['spx_dd'] * 100:.1f}%)."
        ref_dd = f"S&P 500 en 12 m: {R['spx_dd'] * 100:.1f}%"
    else:
        cai, ref_dd = f"Tu peor caída en 12 meses fue de {dd * 100:.1f}%.", "Sin dato del S&P 500"
    pct_var = var95 / total_portafolio * 100 if total_portafolio else 0
    fila = lambda n, v, ref, w, txt: (f"<div class='ap-fila-r'><div><p class='ap-t' style='margin:0'>{n}</p><p class='ap-s' style='margin:2px 0 0'>{e(ref)}</p></div>"
                                      f"<span class='ap-m ap-oro' style='font-size:1.25rem'>{v}</span><div><div class='ap-trk'><b style='width:{min(max(w, 2), 100):.0f}%'></b></div>"
                                      f"<p class='ap-s' style='margin:6px 0 0'>{e(txt)}</p></div></div>")
    st.markdown("<div class='ap-card-pro ap-filo notranslate' translate='no'><p class='ap-t'>Lectura de tus métricas</p>"
                + fila("Beta", f"{beta:.2f}", "Referencia S&P 500 = 1.00", beta / 2 * 100, mov)
                + fila("Sharpe", f"{sharpe:.2f}", "Bueno por encima de 1.00", (sharpe + 1) / 3 * 100, sh)
                + fila("Drawdown máx.", f"{dd * 100:.1f}%", ref_dd, abs(dd) / 0.4 * 100, cai)
                + fila("VaR 95 %", m(var95, 0), f"{pct_var:.1f}% del patrimonio", pct_var / 5 * 100,
                       f"1 de cada 20 días podrías ver una baja mayor a {m(var95, 0)}.")
                + "</div>", unsafe_allow_html=True)


# =====================================================================================================
# 8. SIMULADOR DE ESTRÉS · escenarios históricos
# =====================================================================================================
ESCENARIOS = {"Crisis financiera 2008 · -56.8%": -56.8, "COVID-19 2020 · -33.9%": -33.9, "Alza de tasas 2022 · -25.4%": -25.4,
              "Burbuja puntocom · -49.1%": -49.1, "Corrección típica · -10%": -10.0}


def _poner_escenario():
    v = ESCENARIOS.get(st.session_state.get("pro_esc_sel"))
    if v is not None:
        st.session_state["pro_esc_spx"] = v


def render_estres_pro(summary, betas, liquidez, total_portafolio):
    titulo_seccion("Simulador de estrés · escenarios históricos")
    if summary is None or summary.empty:
        return
    if "pro_esc_spx" not in st.session_state:
        st.session_state["pro_esc_spx"] = -33.9
    nombres = list(ESCENARIOS)
    f = getattr(st, "pills", None)
    if f is not None:
        f("Escenario", nombres, key="pro_esc_sel", on_change=_poner_escenario, label_visibility="collapsed")
    else:
        st.radio("Escenario", nombres, key="pro_esc_sel", on_change=_poner_escenario, horizontal=True, label_visibility="collapsed")
    with st.container(key="estres_card"):
        spx = st.slider("Caída del S&P 500", min_value=-60.0, max_value=0.0, step=0.5, key="pro_esc_spx", format="%.1f%%")
        imp = [(r["ticker"], float(r["valor_actual"]) * betas.get(r["ticker"], 1.0) * spx / 100) for _, r in summary.iterrows()]
        imp = [(t, max(v, -float(summary.loc[summary["ticker"] == t, "valor_actual"].iloc[0]))) for t, v in imp]   # no se pierde más de lo que vale
        tot = sum(v for _, v in imp)
        mx = max([abs(v) for _, v in imp] + [1])
        st.markdown(
            "<div class='ap-banda notranslate' translate='no' style='border:0;background:transparent;box-shadow:none;margin:6px 0 4px'>"
            f"<div><p class='ap-t'>Impacto estimado</p><p class='ap-v ap-m ap-neg'>{ms(tot)}</p><p class='ap-s'>{tot / total_portafolio * 100 if total_portafolio else 0:+.1f}% del patrimonio</p></div>"
            f"<div><p class='ap-t'>Patrimonio estresado</p><p class='ap-v ap-m'>{m(total_portafolio + tot)}</p><p class='ap-s'>hoy {m(total_portafolio)}</p></div>"
            f"<div><p class='ap-t'>Colchón de efectivo</p><p class='ap-v ap-m ap-oro'>{m(liquidez)}</p><p class='ap-s'>{liquidez / total_portafolio * 100 if total_portafolio else 0:.0f}% no se mueve con el mercado</p></div></div>"
            + "".join(f"<div class='ap-fila-b'><span class='tk'>{e(t)}</span><span class='ap-trk der'><b style='width:{abs(v) / mx * 100:.1f}%'></b></span><span class='ap-m n ap-neg'>{ms(v)}</span></div>"
                      for t, v in sorted(imp, key=lambda x: x[1]))
            + "<p class='ap-s'>Impacto = valor de cada posición × su beta × la caída del S&amp;P 500. Escenario aritmético: no considera "
              "correlaciones cambiantes, el tipo de cambio ni la recuperación posterior.</p>", unsafe_allow_html=True)


# =====================================================================================================
# 9. BOLETÍN CIO · línea de tiempo histórica y futura (dividendos, reportes, macro y tus operaciones)
# =====================================================================================================
# Agenda macro oficial (fuentes: calendario FOMC de la Reserva Federal y calendario de anuncios de Banxico).
# Se actualiza una vez al año; lo que no esté aquí lo agrega el CIO Virtual (Gemini) al pulsar el botón.
AGENDA_MACRO = {
    "FED": ["2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17", "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
            "2027-01-27", "2027-03-17", "2027-04-28", "2027-06-09", "2027-07-28", "2027-09-15", "2027-10-27", "2027-12-08"],
    "Banxico": ["2026-02-05", "2026-03-26", "2026-05-07", "2026-06-25", "2026-08-06", "2026-09-24", "2026-11-05", "2026-12-17"],
}
_TXT_MACRO = {"FED": ("Decisión de tasas FED", "Anuncio de política monetaria de la Reserva Federal (13:00 h CDMX aprox.). Mueve las tasas de largo plazo, "
                      "el dólar y las valuaciones de tecnología y crecimiento."),
              "Banxico": ("Decisión de tasas Banxico", "Anuncio de política monetaria del Banco de México (13:00 h CDMX). Influye en la tasa de CETES "
                          "y en el tipo de cambio USD/MXN, que afecta el valor en pesos de tus activos en dólares.")}

PROMPT_CIO_JSON = """Eres el CIO Virtual de un Multi-Family Office mexicano. Portafolio: {activos}.
Eventos de emisoras ya confirmados por Yahoo Finance (no los repitas en eventos_macro): {eventos}.
Fecha de hoy: {hoy}.

Responde ÚNICAMENTE con un JSON válido con esta forma:
{{"panorama": "un párrafo de 60 a 90 palabras sobre el entorno macro y cómo se relaciona con estos activos",
  "eventos_macro": [{{"fecha": "YYYY-MM-DD", "titulo": "Inflación EE.UU. (CPI)", "detalle": "40 a 60 palabras: qué se espera y por qué importa a este portafolio"}}],
  "detalles_emisoras": {{"TICKER": "30 a 50 palabras: qué parámetros suele observar el mercado en su próximo evento"}},
  "dividendos_fiscal": "40 a 70 palabras informativas sobre retenciones y conceptos a verificar"}}

Reglas: eventos_macro solo en las próximas 8 semanas (inflación EE.UU. y México, empleo EE.UU., PIB); las decisiones de la FED y de Banxico ya están en la agenda,
inclúyelas solo si aportas un detalle. Si no conoces la fecha exacta, omite el evento.
Lenguaje informativo y condicional ("se observa", "en caso de"). Prohibido recomendar comprar, vender o mantener y prohibido el imperativo. Sin markdown."""

COLOR_TIPO = {"Dividendo": VERDE, "Reporte": ORO2, "Macro": ACERO, "Operación": "#d9d4c7"}
TIPOS_CIO = ["Dividendo", "Reporte", "Macro", "Operación"]
ETQ_TIPO = {"Dividendo": "Dividendos", "Reporte": "Reportes", "Macro": "Macro", "Operación": "Tus operaciones"}


def _num(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=43200, max_entries=200, show_spinner=False)
def _reportes_yf(simbolo):
    """Reportes trimestrales (pasados y próximos) con utilidad por acción estimada y reportada, según Yahoo Finance."""
    import yfinance as yf
    try:
        df = yf.Ticker(simbolo).get_earnings_dates(limit=16)
    except Exception:
        return []
    if df is None or len(df) == 0:
        return []
    out = []
    for f, r in df.iterrows():
        try:
            ts = pd.Timestamp(f)
            ts = ts.tz_localize(None) if ts.tzinfo else ts
        except Exception:
            continue
        out.append({"fecha": ts.normalize().strftime("%Y-%m-%d"), "eps_est": _num(r.get("EPS Estimate")),
                    "eps_real": _num(r.get("Reported EPS")), "sorpresa": _num(r.get("Surprise(%)"))})
    return out


@st.cache_data(ttl=43200, max_entries=200, show_spinner=False)
def _cierres_2a(simbolo):
    """Cierres diarios de 2 años en la moneda de cotización (para medir la reacción del precio a cada reporte)."""
    import yfinance as yf
    try:
        s = yf.Ticker(simbolo).history(period="2y")["Close"].dropna()
    except Exception:
        return pd.Series(dtype=float)
    if getattr(s.index, "tz", None) is not None:
        s.index = s.index.tz_localize(None)
    s.index = pd.to_datetime(s.index).normalize()
    return s


def _reaccion(cierres, fecha):
    """Cambio entre el último cierre antes del reporte y el primer cierre después (2 sesiones: cubre antes y después de apertura)."""
    if cierres is None or cierres.empty:
        return None
    f = pd.Timestamp(fecha)
    antes, despues = cierres[cierres.index < f], cierres[cierres.index > f]
    if antes.empty or despues.empty:
        return None
    return (float(despues.iloc[0]) / float(antes.iloc[-1]) - 1) * 100


def eventos_cio(H, summary, tx_df, js=None):
    """Bitácora completa de eventos desde tu primera operación hasta 4 meses adelante."""
    hoy = pd.Timestamp(datetime.now(ZONA_MX).date())
    tx = tx_df.copy() if tx_df is not None and not tx_df.empty else pd.DataFrame(columns=["fecha", "ticker", "titulos"])
    if not tx.empty:
        tx["fecha"] = pd.to_datetime(tx["fecha"]).dt.normalize()
        tx["titulos"] = tx["titulos"].astype(float)
    inicio = (tx["fecha"].min() if not tx.empty else hoy - pd.Timedelta(days=90)) - pd.Timedelta(days=7)
    fin = hoy + pd.Timedelta(days=120)
    en_cartera = set(summary["ticker"]) if summary is not None and not summary.empty else set()
    ev = []

    # 1) Tus operaciones
    for _, r in tx.sort_values("fecha").iterrows():
        tit, pre, tc = abs(float(r["titulos"])), float(r.get("precio_unitario") or 0), float(r.get("tipo_cambio") or 1)
        mon = str(r.get("moneda") or "").upper()
        ev.append({"fecha": r["fecha"].strftime("%Y-%m-%d"), "tipo": "Operación", "clave": r["ticker"],
                   "titulo": f"{str(r.get('tipo_operacion', '')).capitalize()} de {r['ticker']}",
                   "detalle": f"{tit:.8g} títulos a {pre:,.4f} {mon or ''} · T.C. {tc:,.4f} · total {m(r.get('total_mxn'))} MXN.",
                   "monto_mxn": float(r.get("total_mxn") or 0), "datos": {}})

    # 2) Dividendos (los mismos montos del calendario de dividendos: títulos al día anterior a la fecha ex × monto × T.C. del día)
    try:
        div = tabla_dividendos(H, tx_df)
    except Exception:
        div = pd.DataFrame()
    for _, r in div.iterrows():
        pago = f" · pago {r['pago']}" if r.get("pago") else ""
        ev.append({"fecha": r["fecha_ex"], "tipo": "Dividendo", "clave": r["activo"],
                   "titulo": f"{r['activo']} · {'dividendo' if r['estado'] == 'Cobrado' else 'próximo dividendo'}",
                   "detalle": (f"{r['por_titulo']:,.4f} {r['moneda']} por título{pago}. Tenías {float(r['titulos']):.6g} títulos un día antes de la fecha ex: "
                               f"bruto ≈ {r['bruto']:,.4f} {r['moneda']} ≈ {m(r['bruto_mxn'])} MXN con el tipo de cambio de ese día, "
                               "antes de retenciones." + (" Monto estimado con el último dividendo pagado." if "estimado" in str(r["estado"]) else "")),
                   "monto_mxn": float(r["bruto_mxn"]), "datos": {"por_titulo": r["por_titulo"], "moneda": r["moneda"], "titulos": r["titulos"]}})

    # 3) Reportes trimestrales: solo emisoras (no ETF ni cripto) y solo mientras tenías la posición, más los próximos de lo que tienes hoy
    tickers = [t for t in (tx["ticker"].unique() if not tx.empty else []) if str(H.asset_class.get(t, "Acción")) not in ("ETF", "Cripto") and t != "BTC"]
    for t in tickers:
        sym = H.yf_symbol(t)
        mov = tx[tx["ticker"] == t]
        rep = _reportes_yf(sym)
        cierres = _cierres_2a(sym) if rep else None
        cal = _calendario_yf(sym)
        fechas_rep = [pd.Timestamp(x["fecha"]) for x in rep]
        if cal.get("reporte") and all(abs((pd.Timestamp(cal["reporte"]) - f).days) > 7 for f in fechas_rep):
            rep = rep + [{"fecha": cal["reporte"], "eps_est": None, "eps_real": None, "sorpresa": None}]
        for x in rep:
            f = pd.Timestamp(x["fecha"])
            if not (inicio <= f <= fin):
                continue
            tenia = float(mov[mov["fecha"] < f]["titulos"].sum()) > 1e-12
            if f <= hoy and not tenia:
                continue
            if f > hoy and t not in en_cartera:
                continue
            if f <= hoy and x["eps_real"] is not None:
                reac = _reaccion(cierres, f)
                sor = f" ({x['sorpresa']:+.1f}% vs lo esperado)" if x["sorpresa"] is not None else ""
                est = f" contra {x['eps_est']:.2f} estimada" if x["eps_est"] is not None else ""
                det = (f"Utilidad por acción reportada {x['eps_real']:.2f}{est}{sor}."
                       + (f" Reacción del precio en 2 sesiones: {reac:+.1f}%." if reac is not None else ""))
                titulo = f"{t} · reporte trimestral"
            elif f > hoy:
                det = (f"Reporte trimestral programado. Utilidad por acción estimada por el consenso: {x['eps_est']:.2f}." if x["eps_est"] is not None
                       else "Reporte trimestral programado; Yahoo Finance aún no publica el consenso.")
                titulo = f"{t} · próximo reporte"
            else:
                det, titulo = "Reporte trimestral (sin cifras disponibles en Yahoo Finance).", f"{t} · reporte trimestral"
            ev.append({"fecha": x["fecha"], "tipo": "Reporte", "clave": t, "titulo": titulo, "detalle": det, "monto_mxn": None,
                       "datos": {"eps_real": x["eps_real"], "eps_est": x["eps_est"], "sorpresa": x["sorpresa"]}})

    # 4) Macro: agenda oficial + lo que agregue el CIO Virtual
    macro_js = {}
    for x in (js or {}).get("eventos_macro", []) or []:
        try:
            macro_js[pd.Timestamp(x.get("fecha")).strftime("%Y-%m-%d")] = x
        except Exception:
            continue
    for banco, fechas in AGENDA_MACRO.items():
        for f in fechas:
            if inicio <= pd.Timestamp(f) <= fin:
                titulo, det = _TXT_MACRO[banco]
                extra = macro_js.get(f)
                if extra and banco.lower() in str(extra.get("titulo", "")).lower():
                    det = str(extra.get("detalle") or det)
                    macro_js.pop(f, None)
                ev.append({"fecha": f, "tipo": "Macro", "clave": banco, "titulo": titulo, "detalle": det, "monto_mxn": None, "datos": {}})
    for f, x in macro_js.items():
        if inicio <= pd.Timestamp(f) <= fin:
            tit = str(x.get("titulo", "Evento macro"))
            ev.append({"fecha": f, "tipo": "Macro", "clave": tit.split("(")[0].strip()[:14], "titulo": tit, "detalle": str(x.get("detalle", "")),
                       "monto_mxn": None, "datos": {}})
    ev.sort(key=lambda x: (x["fecha"], TIPOS_CIO.index(x["tipo"])))
    return ev, inicio, fin


def _niveles(fechas_ts, gap_dias):
    """Altura de cada etiqueta (arriba/abajo de la línea) para que no se encimen las cercanas."""
    alturas = [1.25, -1.25, 2.15, -2.15, 3.0, -3.0]
    ultimo = {h: None for h in alturas}
    out = []
    for k, f in enumerate(fechas_ts):
        elegido = None
        orden = alturas if k % 2 == 0 else alturas[1:2] + alturas[0:1] + alturas[3:4] + alturas[2:3] + alturas[5:6] + alturas[4:5]
        for h in orden:
            if ultimo[h] is None or (f - ultimo[h]).days >= gap_dias:
                elegido = h
                break
        if elegido is None:
            elegido = min(alturas, key=lambda h: ultimo[h])
        ultimo[elegido] = f
        out.append(elegido)
    return out


def figura_timeline(H, eventos, x0, x1, inicio, fin, hoy, detalle_corto):
    fechas = [pd.Timestamp(x["fecha"]) for x in eventos]
    gap = max(2, int((x1 - x0).days / 11))
    lv = _niveles(fechas, gap)
    fig = go.Figure()
    # línea de tiempo con marcas semanales (o mensuales si la ventana es larga)
    fig.add_shape(type="line", x0=inicio, x1=fin, y0=0, y1=0, line=dict(color="#3a4252", width=1.4), layer="below")
    paso = 7 if (x1 - x0).days <= 120 else 30
    marcas = pd.date_range(inicio.normalize(), fin, freq=f"{paso}D")
    mx, my = [], []
    for t in marcas:
        mx += [t, t, None]; my += [-0.14, 0.14, None]
    fig.add_trace(go.Scatter(x=mx, y=my, mode="lines", line=dict(color="#3a4252", width=1), hoverinfo="skip", showlegend=False))
    # conectores punteados
    for tipo in TIPOS_CIO:
        cx, cy = [], []
        for f, h, x in zip(fechas, lv, eventos):
            if x["tipo"] == tipo:
                cx += [f, f, None]; cy += [0, h - (0.28 if h > 0 else -0.28), None]
        if cx:
            fig.add_trace(go.Scatter(x=cx, y=cy, mode="lines", line=dict(color=COLOR_TIPO[tipo], width=1, dash="dot"), hoverinfo="skip", showlegend=False))
    # etiquetas: clave en color + nombre corto en gris
    for tipo in TIPOS_CIO:
        idx = [k for k, x in enumerate(eventos) if x["tipo"] == tipo]
        if not idx:
            continue
        txt = []
        for k in idx:
            x = eventos[k]
            corto = {"Dividendo": "Dividendo", "Reporte": "Reporte", "Macro": "Tasas" if x["clave"] in AGENDA_MACRO else "Macro",
                     "Operación": str(x["titulo"]).split(" ")[0]}[tipo]
            txt.append(f"<b>{e(x['clave'])}</b>" + (f"<br><span style='color:#8b94a7'>{corto}</span>" if detalle_corto else ""))
        fig.add_trace(go.Scatter(x=[fechas[k] for k in idx], y=[lv[k] for k in idx], mode="text", text=txt,
                                 textfont=dict(color=COLOR_TIPO[tipo], size=11, family="Inter, sans-serif"),
                                 textposition=["top center" if lv[k] > 0 else "bottom center" for k in idx], hoverinfo="skip", showlegend=False,
                                 unselected=dict(textfont=dict(color=COLOR_TIPO[tipo]))))
    # puntos sobre la línea (los únicos que se pueden tocar)
    for tipo in TIPOS_CIO:
        idx = [k for k, x in enumerate(eventos) if x["tipo"] == tipo]
        if not idx:
            continue
        fig.add_trace(go.Scatter(
            x=[fechas[k] for k in idx], y=[0] * len(idx), mode="markers", name=ETQ_TIPO[tipo], customdata=idx,
            marker=dict(size=12 if tipo != "Operación" else 9, color=COLOR_TIPO[tipo], symbol="circle" if tipo != "Operación" else "diamond",
                        line=dict(color="#050608", width=2)),
            text=[eventos[k]["titulo"] for k in idx], hovertemplate="%{x|%d %b %Y} · %{text}<extra></extra>",
            selected=dict(marker=dict(size=17, opacity=1)), unselected=dict(marker=dict(opacity=1))))
    fig.add_shape(type="line", x0=hoy, x1=hoy, y0=-3.4, y1=3.4, line=dict(color="#6b7385", width=1, dash="dash"), layer="below")
    fig.add_annotation(x=hoy, y=3.55, text="Hoy", showarrow=False, font=dict(color="#a3a9b6", size=11))
    H.style(fig, height=310, showlegend=True, xgrid=False, ygrid=False, margin=dict(t=14, b=6, l=6, r=6))
    fig.update_yaxes(range=[-3.7, 3.9], visible=False, fixedrange=True)
    # Sin rangeslider: repetía todas las etiquetas en miniatura. Para moverse en el tiempo: arrastrar (pan) o cambiar la ventana.
    fig.update_xaxes(range=[x0, x1], tickformat="%d %b" if paso == 7 else "%b %Y", showline=False, showgrid=False)
    fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0), dragmode="pan", clickmode="event+select",
                      hovermode="closest")
    return fig


def _texto_reporte_cio(js):
    if not js:
        return None
    partes = ["PANORAMA: " + str(js.get("panorama", "")).strip()]
    for x in js.get("eventos_macro", []) or []:
        partes.append(f"• {x.get('fecha', '')} · {x.get('titulo', '')}: {x.get('detalle', '')}")
    for k, v in (js.get("detalles_emisoras") or {}).items():
        partes.append(f"• {k}: {v}")
    if js.get("dividendos_fiscal"):
        partes.append("DIVIDENDOS (INFORMATIVO): " + str(js["dividendos_fiscal"]))
    return "\n".join(partes)


def _multi(etiqueta, opciones, key, default):
    f = getattr(st, "pills", None)
    if f is not None:
        if key not in st.session_state:
            st.session_state[key] = list(default)
        try:
            v = f(etiqueta, opciones, selection_mode="multi", key=key, label_visibility="collapsed")
            return list(v or [])
        except TypeError:
            pass
    return st.multiselect(etiqueta, opciones, default=default, key=key + "_ms", label_visibility="collapsed")


def render_cio_pro(H, summary, cliente_id, tx_df=None, nombre_cliente="cliente"):
    titulo_seccion("Boletín del CIO Virtual · línea de tiempo")
    if (summary is None or summary.empty) and (tx_df is None or tx_df.empty):
        return
    hoy = pd.Timestamp(datetime.now(ZONA_MX).date())
    tickers = summary["ticker"].tolist() if summary is not None and not summary.empty else []
    k_js = f"cio_json_{cliente_id}"
    js = st.session_state.get(k_js)

    c1, c2 = st.columns([1, 2.2], vertical_alignment="center")
    generar = c1.button("Actualizar con el CIO Virtual", use_container_width=True, key="cio_generar")
    c2.caption("Dividendos, reportes y tus operaciones vienen de tu registro y de Yahoo Finance; la agenda de la FED y de Banxico, de sus calendarios "
               "oficiales. El botón suma la agenda macro restante y el contexto de Gemini.")
    with st.spinner("Armando tu línea de tiempo (dividendos, reportes y agenda macro)…"):
        eventos, inicio, fin = eventos_cio(H, summary, tx_df, js)
    if generar:
        clave = H.gemini_key()
        if not clave:
            st.warning("Configura GEMINI_API_KEY para activar al CIO Virtual.")
        else:
            with st.spinner("El CIO Virtual está revisando el calendario y el entorno macro…"):
                prox = [x for x in eventos if pd.Timestamp(x["fecha"]) >= hoy and x["tipo"] in ("Reporte", "Dividendo")]
                prompt = PROMPT_CIO_JSON.format(activos=", ".join(tickers), hoy=hoy.strftime("%Y-%m-%d"),
                                                eventos="; ".join(f"{x['fecha']} {x['titulo']}" for x in prox[:20]) or "ninguno")
                texto, err = H.gemini(prompt, clave, temperature=0.3, json_mode=True, presupuesto_s=90)
                datos = H.json(texto) if texto else None
                if datos:
                    st.session_state[k_js] = js = datos
                    st.session_state["cio_report"] = _texto_reporte_cio(datos)   # la Carta CMA lo incluye
                    eventos, inicio, fin = eventos_cio(H, summary, tx_df, js)
                else:
                    H.log.warning("CIO Virtual · sin JSON: %s", err)
                    st.info("El CIO Virtual está consolidando datos. Intenta de nuevo en unos minutos.")
    if not eventos:
        st.markdown("<div class='ap-card-pro'><p class='ap-s' style='margin:0'>Aún no hay eventos para mostrar.</p></div>", unsafe_allow_html=True)
        return

    # resumen superior
    prox = [x for x in eventos if pd.Timestamp(x["fecha"]) >= hoy and x["tipo"] != "Operación"]
    div_c = [x for x in eventos if x["tipo"] == "Dividendo" and pd.Timestamp(x["fecha"]) <= hoy]
    rep_c = [x for x in eventos if x["tipo"] == "Reporte" and pd.Timestamp(x["fecha"]) <= hoy and x["datos"].get("eps_real") is not None]
    sup = [x for x in rep_c if (x["datos"].get("sorpresa") or 0) > 0]
    st.markdown(
        "<div class='ap-banda ap-filo notranslate' translate='no'>"
        f"<div><p class='ap-t'>Próximo evento</p><p class='ap-v ap-m' style='font-size:1.15rem'>{e(prox[0]['titulo']) if prox else '—'}</p>"
        f"<p class='ap-s'>{e(prox[0]['fecha']) + ' · en ' + str((pd.Timestamp(prox[0]['fecha']) - hoy).days) + ' días' if prox else 'sin eventos próximos'}</p></div>"
        f"<div><p class='ap-t'>Dividendos registrados</p><p class='ap-v ap-m'>{m(sum(x['monto_mxn'] or 0 for x in div_c))}</p>"
        f"<p class='ap-s'>{len(div_c)} pago(s) bruto(s) desde tu inicio</p></div>"
        f"<div><p class='ap-t'>Reportes con resultado</p><p class='ap-v ap-m'>{len(sup)} de {len(rep_c)}</p>"
        f"<p class='ap-s'>superaron la utilidad estimada</p></div></div>", unsafe_allow_html=True)

    # controles
    f1, f2, f3 = st.columns([1.5, 1.6, 1], vertical_alignment="center")
    with f1:
        ventana = selector("Ventana", ["6 semanas", "±3 meses", "Desde tu inicio"], key="cio_ventana")
    with f2:
        tipos = _multi("Tipos", [ETQ_TIPO[t] for t in TIPOS_CIO], key="cio_tipos", default=[ETQ_TIPO[t] for t in TIPOS_CIO])
    with f3:
        activos = ["Todos"] + sorted({x["clave"] for x in eventos if x["tipo"] != "Macro"})
        activo = st.selectbox("Activo", activos, key="cio_activo", label_visibility="collapsed")
    tipos_sel = [t for t in TIPOS_CIO if ETQ_TIPO[t] in tipos] or TIPOS_CIO
    vis = [x for x in eventos if x["tipo"] in tipos_sel and (activo == "Todos" or x["clave"] == activo or x["tipo"] == "Macro")]
    if ventana == "6 semanas":
        x0, x1 = hoy - pd.Timedelta(days=7), hoy + pd.Timedelta(days=42)
    elif ventana == "±3 meses":
        x0, x1 = hoy - pd.Timedelta(days=92), hoy + pd.Timedelta(days=92)
    else:
        x0, x1 = inicio, fin
    if not vis:
        st.caption("No hay eventos con esos filtros.")
        return

    fig = figura_timeline(H, vis, x0, x1, inicio, fin, hoy, detalle_corto=(x1 - x0).days <= 100)
    sel_idx = None
    with st.container(key="cio_card"):
        try:
            evento = st.plotly_chart(fig, use_container_width=True, config={**H.cfg, "scrollZoom": False}, key=f"cio_timeline_{ventana}",
                                     on_select="rerun", selection_mode="points")
            pts = (evento or {}).get("selection", {}).get("points", []) if isinstance(evento, dict) else getattr(getattr(evento, "selection", None), "points", [])
            for p in pts or []:
                cd = p.get("customdata") if isinstance(p, dict) else None
                if cd is not None:
                    sel_idx = int(cd[0] if isinstance(cd, (list, tuple)) else cd)
                    break
        except TypeError:   # Streamlit sin selección en gráficas
            st.plotly_chart(fig, use_container_width=True, config=H.cfg, key="cio_timeline_simple")
        st.caption("Toca un punto para ver el detalle. Arrastra la línea hacia los lados para moverte en el tiempo, o cambia la ventana arriba.")
        opciones = [f"{x['fecha']} · {x['titulo']}" for x in vis]
        if sel_idx is None or sel_idx >= len(vis):   # por defecto, el próximo evento de la ventana
            sel_idx = next((k for k, x in enumerate(vis) if pd.Timestamp(x["fecha"]) >= hoy), len(vis) - 1)
        elegido = st.selectbox("Detalle del evento", opciones, index=sel_idx, key=f"cio_sel_{ventana}_{sel_idx}_{len(vis)}", label_visibility="collapsed")
        x = vis[opciones.index(elegido)]
        detalle = x["detalle"]
        if x["tipo"] == "Reporte" and pd.Timestamp(x["fecha"]) > hoy:
            extra = ((js or {}).get("detalles_emisoras") or {}).get(x["clave"])
            detalle += " " + (extra or "Pulsa «Actualizar con el CIO Virtual» para ver qué suele observar el mercado en este evento.")
        from urllib.parse import quote_plus
        q = x["titulo"] if x["tipo"] == "Macro" else f"{x['clave']} {('dividend' if x['tipo'] == 'Dividendo' else 'earnings')} {x['fecha'][:7]}"
        enlaces = [("Noticias en Google", f"https://news.google.com/search?q={quote_plus(q)}&hl=es-419&gl=MX&ceid=MX:es-419")]
        if x["tipo"] != "Macro":
            sym = quote_plus(H.yf_symbol(x["clave"]))
            enlaces.insert(0, ("Noticias en Yahoo Finance", f"https://finance.yahoo.com/quote/{sym}/news"))
            if x["tipo"] == "Dividendo":
                enlaces.insert(1, ("Historial de dividendos", f"https://finance.yahoo.com/quote/{sym}/history/?filter=div"))
        else:
            oficial = {"FED": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
                       "Banxico": "https://www.banxico.org.mx/publicaciones-y-prensa/anuncios-de-las-decisiones-de-politica-monetaria/anuncios-politica-monetaria-t.html"}.get(x["clave"])
            if oficial:
                enlaces.insert(0, ("Comunicado oficial", oficial))
        estado = "Próximo" if pd.Timestamp(x["fecha"]) > hoy else ("Hoy" if pd.Timestamp(x["fecha"]) == hoy else "Histórico")
        st.markdown(
            f"<div class='ap-card-pro notranslate' translate='no' style='margin-top:6px;border-left:2px solid {COLOR_TIPO[x['tipo']]}'>"
            f"<p class='ap-t'>{e(ETQ_TIPO[x['tipo']])} · {e(x['fecha'])} · {estado}</p>"
            f"<p style='font:italic 400 1.15rem/1.35 \"Playfair Display\", serif;color:#f3e2b0;margin:0 0 8px'>{e(x['titulo'])}</p>"
            f"<p style='color:#cfd3db;margin:0 0 10px;font-size:0.9rem;line-height:1.6'>{e(detalle)}</p>"
            + (f"<p class='ap-m ap-oro' style='margin:0 0 10px'>{m(x['monto_mxn'])} MXN</p>" if x.get("monto_mxn") and x["tipo"] == "Dividendo" else "")
            + " ".join(f"<a class='ap-link' href='{e(u)}' target='_blank' rel='noopener noreferrer'>{e(n)} ↗</a>" for n, u in enlaces)
            + "</div>", unsafe_allow_html=True)

    # bitácora (sirve de base para el área fiscal)
    with st.expander(f"Bitácora de eventos · {len(vis)} registro(s)", expanded=False):
        filas = "".join(
            f"<tr><td class='ap-m'>{e(x['fecha'])}</td><td><span class='ap-pill' style='color:{COLOR_TIPO[x['tipo']]};border-color:{COLOR_TIPO[x['tipo']]}55'>"
            f"{e(ETQ_TIPO[x['tipo']])}</span></td><td class='tk'>{e(x['clave'])}</td><td style='white-space:normal;min-width:260px;color:#a3a9b6'>{e(x['detalle'])}</td>"
            f"<td class='n ap-m'>{m(x['monto_mxn']) if x.get('monto_mxn') else '—'}</td></tr>" for x in reversed(vis))
        st.markdown("<div class='ap-tw notranslate' translate='no' style='max-height:380px'><table style='min-width:720px'><tr><th>Fecha</th><th>Tipo</th>"
                    f"<th>Activo</th><th>Detalle</th><th class='n'>Monto MXN</th></tr>{filas}</table></div>", unsafe_allow_html=True)
        tabla = pd.DataFrame([{"fecha": x["fecha"], "tipo": x["tipo"], "activo": x["clave"], "evento": x["titulo"], "detalle": x["detalle"],
                               "monto_mxn": x.get("monto_mxn"), **{k: v for k, v in x["datos"].items()}} for x in vis])
        st.download_button("Exportar bitácora (CSV)", data=tabla.to_csv(index=False).encode("utf-8"),
                           file_name=f"Bitacora_CIO_{nombre_cliente}_{datetime.now(ZONA_MX):%Y%m%d}.csv", mime="text/csv", key="cio_csv")
        st.caption("Montos brutos estimados; para tu declaración, confirma contra la constancia fiscal de tu casa de bolsa.")

    if js and js.get("panorama"):
        st.markdown(f"<div class='ap-card-pro notranslate' translate='no'><p class='ap-t'>Panorama</p><p style='color:#cfd3db;margin:0;line-height:1.65'>{e(js['panorama'])}</p>"
                    + (f"<p class='ap-t' style='margin-top:12px'>Dividendos y consideraciones fiscales (informativo)</p><p class='ap-s' style='margin:0'>{e(js.get('dividendos_fiscal', ''))}</p>" if js.get("dividendos_fiscal") else "")
                    + "</div>", unsafe_allow_html=True)


# =====================================================================================================
# 10. RADIOGRAFÍA · gráfica con tus compras marcadas
# =====================================================================================================
def figura_ficha_tecnica(H, hist, ticker, tx_df, usd_mxn, moneda_grafica):
    close = hist["Close"].astype(float)
    ma50, ma200 = close.rolling(50).mean(), close.rolling(200, min_periods=60).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=ma200, mode="lines", name="MA200", line=dict(color=PIZARRA, width=1.2, dash="dash"), hovertemplate="MA200 %{y:,.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=hist.index, y=ma50, mode="lines", name="MA50", line=dict(color=ACERO, width=1.2), hovertemplate="MA50 %{y:,.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=hist.index, y=close, mode="lines", name=ticker, fill="tozeroy", fillcolor="rgba(201,162,74,0.10)",
                             line=dict(color=ORO2, width=1.8), hovertemplate="%{x|%d %b %Y} · %{y:,.2f}<extra></extra>"))
    compras = []
    c = tx_df[(tx_df["ticker"] == ticker) & (tx_df["tipo_operacion"] == "COMPRA")] if tx_df is not None and not tx_df.empty else pd.DataFrame()
    for _, r in c.iterrows():
        pre, tc, mon = float(r["precio_unitario"]), float(r["tipo_cambio"] or 1), str(r["moneda"]).upper()
        if moneda_grafica == "USD":
            precio = pre if mon == "USD" else pre / (usd_mxn or 18.0)
        elif moneda_grafica == "MXN":
            precio = pre * tc if mon == "USD" else pre
        else:
            continue
        f = pd.Timestamp(r["fecha"])
        if hist.index.tz is not None:
            f = f.tz_localize(hist.index.tz)
        compras.append((f, precio, float(r["titulos"]), mon != moneda_grafica))
    en_rango = [x for x in compras if x[0] >= hist.index[0]]   # compras anteriores a la ventana de 1 año: solo en la tabla
    if en_rango:
        fig.add_trace(go.Scatter(x=[x[0] for x in en_rango], y=[x[1] for x in en_rango], mode="markers", name="Tus compras",
                                 marker=dict(size=12, color=LUZ, line=dict(color=ORO, width=2.5), symbol="circle"),
                                 customdata=[[x[2], "≈ " if x[3] else ""] for x in en_rango],
                                 hovertemplate="<b>Compraste</b> %{x|%d %b %Y}<br>a %{customdata[1]}%{y:,.2f} · %{customdata[0]:.6g} títulos<extra></extra>"))
    fig.add_trace(go.Scatter(x=hist.index, y=close, mode="lines", line=dict(color=LUZ, width=2.0), hoverinfo="skip", showlegend=False, name="luz"))
    H.style(fig, height=380, showlegend=True, margin=dict(t=10, b=10, l=6, r=12))
    fig.update_layout(hovermode="x unified", legend=dict(orientation="h", yanchor="top", y=-0.12, xanchor="left", x=0))
    lo, hi = float(close.min()), float(close.max())
    fig.update_yaxes(range=[lo * 0.92, hi * 1.05])
    return fig, compras


def html_compras_caro_barato(compras, precio_actual, low52, high52):
    if not compras:
        return "<p class='ap-s'>Aún no tienes compras de este activo.</p>"
    filas = ""
    for f, p, t, aprox in compras:
        dif = (precio_actual / p - 1) * 100 if p else 0
        rng = (p - low52) / (high52 - low52) * 100 if high52 and low52 and high52 != low52 else 50
        nivel = "zona baja del rango" if rng < 33 else ("zona media" if rng < 66 else "zona alta del rango")
        filas += (f"<div class='ap-fila-c'><span class='ap-m'>{f:%d %b %Y}</span><span class='ap-m'>{'≈ ' if aprox else ''}{p:,.2f}</span>"
                  f"<span class='ap-m {cls(dif)}'>{pc(dif, 1)}</span><span class='ap-s' style='margin:0'>{nivel} ({rng:.0f}%)</span></div>")
    return ("<div class='ap-fila-c ap-fila-c-cab'><span>Fecha</span><span>Precio</span><span>Hoy vs compra</span><span>Rango 52 s</span></div>" + filas)


# =====================================================================================================
# 11. SMART DCA · barras de 100 %
# =====================================================================================================
def html_dca_barras(hoy, objetivo, despues, montos, capital):
    colores = {"ETF": ORO, "Acción": "#8a6f33", "Cripto": ORO3}
    def barra(nombre, d):
        tot = sum(d.values()) or 1
        segs = "".join(f"<div style='width:{v / tot * 100:.2f}%;background:{colores.get(k, GRIS)}'>{e(k if k != 'Acción' else 'Acc.')} {v / tot * 100:.0f}%</div>"
                       if v / tot * 100 >= 9 else f"<div style='width:{v / tot * 100:.2f}%;background:{colores.get(k, GRIS)}'></div>" for k, v in d.items())
        return f"<p class='ap-t' style='margin-top:12px'>{e(nombre)}</p><div class='ap-stack'>{segs}</div>"
    cifras = "".join(f"<div><p class='ap-t'>{e('Acciones' if k == 'Acción' else k)}</p><p class='ap-m {'ap-oro' if v > 0 else ''}' style='font-size:1.2rem;margin:0'>{m(v)}</p></div>"
                     for k, v in montos.items())
    return (f"<div class='ap-card-pro ap-filo notranslate' translate='no'>{barra('Hoy', hoy)}{barra('Objetivo', objetivo)}"
            f"{barra(f'Después de distribuir {m(capital, 0)}', despues)}<div class='ap-banda' style='border:0;background:transparent;box-shadow:none;margin:14px 0 0'>{cifras}</div>"
            f"<p class='ap-s'>Escenario aritmético: reparte el capital hacia las clases que están por debajo de su parámetro. No es una instrucción de compra.</p></div>")


# =====================================================================================================
# 12. HISTORIAL PRO · agrupado por mes + buscador
# =====================================================================================================
def _filtra(df, q, columnas):
    if not q:
        return df
    q = q.strip().lower()
    mask = pd.Series(False, index=df.index)
    for c in columnas:
        mask |= df[c].astype(str).str.lower().str.contains(q, regex=False, na=False)
    return df[mask]


def render_historial_pro_tx(tx_df):
    q = st.text_input("Buscar", placeholder="Buscar activo, fecha (2026-07) o monto…", key="hist_buscar_tx", label_visibility="collapsed")
    df = tx_df.copy()
    df["_monto"] = df["total_mxn"].astype(float).map(lambda v: f"{v:,.2f}")
    df = _filtra(df, q, ["ticker", "fecha", "tipo_operacion", "clase", "_monto"]).sort_values(["fecha", "timestamp"], ascending=False)
    if df.empty:
        st.caption("Sin resultados para esa búsqueda.")
        return
    df["_mes"] = pd.to_datetime(df["fecha"]).dt.to_period("M")
    html = ""
    for per, g in df.groupby("_mes", sort=False):
        nombre = f"{_MESES[per.month - 1].capitalize()} {per.year}"
        filas = "".join(
            f"<div class='ap-mov'><span class='ap-m' style='color:#6b7280'>{e(str(r['fecha'])[5:])}</span><span class='tk'>{e(r['ticker'])}</span>"
            f"<span class='ap-s ap-m' style='margin:0'>{e(r['tipo_operacion'])} · {abs(float(r['titulos'])):.8g} títulos · T.C. {float(r['tipo_cambio']):.4f}</span>"
            f"<span class='ap-m n'>{m(r['total_mxn'])}</span></div>" for _, r in g.iterrows())
        html += (f"<div class='ap-mes'><div class='ap-mes-cab'><span>{e(nombre)}</span><span class='ap-m'>{m(g['total_mxn'].astype(float).sum())} · "
                 f"{len(g)} operación(es)</span></div>{filas}</div>")
    st.markdown(f"<div class='notranslate' translate='no' style='max-height:520px;overflow:auto'>{html}</div>", unsafe_allow_html=True)


def render_historial_pro_caja(cash_df):
    q = st.text_input("Buscar", placeholder="Buscar concepto, tipo o fecha…", key="hist_buscar_caja", label_visibility="collapsed")
    df = cash_df.copy()
    df["_monto"] = df["monto_mxn"].astype(float).map(lambda v: f"{v:,.2f}")
    df = _filtra(df, q, ["concepto", "tipo", "fecha", "_monto"]).sort_values(["fecha", "id"], ascending=False)
    if df.empty:
        st.caption("Sin resultados para esa búsqueda.")
        return
    df["_mes"] = pd.to_datetime(df["fecha"]).dt.to_period("M")
    html = ""
    for per, g in df.groupby("_mes", sort=False):
        neto = g["monto_mxn"].astype(float).sum()
        filas = "".join(
            f"<div class='ap-mov'><span class='ap-m' style='color:#6b7280'>{e(str(r['fecha'])[5:])}</span><span class='tk'>{e(r['tipo'])}</span>"
            f"<span class='ap-s' style='margin:0'>{e(r['concepto'])}</span><span class='ap-m n {cls(r['monto_mxn'])}'>{ms(r['monto_mxn'])}</span></div>"
            for _, r in g.iterrows())
        html += (f"<div class='ap-mes'><div class='ap-mes-cab'><span>{e(_MESES[per.month - 1].capitalize())} {per.year}</span>"
                 f"<span class='ap-m {cls(neto)}'>{ms(neto)} neto</span></div>{filas}</div>")
    st.markdown(f"<div class='notranslate' translate='no' style='max-height:520px;overflow:auto'>{html}</div>", unsafe_allow_html=True)


# =====================================================================================================
# CSS del Modo Pro (se inyecta una vez desde app.py)
# =====================================================================================================
CSS_PRO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&display=swap');
.ap-m { font-family: 'IBM Plex Mono', ui-monospace, Menlo, monospace !important; letter-spacing: -0.01em; }
.ap-card-pro, .ap-banda { background: linear-gradient(180deg, var(--ap-surface-2), var(--ap-surface)); border: 1px solid var(--ap-border); border-radius: 14px;
    padding: 18px 20px; margin-bottom: 14px; box-shadow: var(--ap-shadow); position: relative; color: var(--ap-text); }
.ap-banda { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); padding: 0; }
.ap-banda > div { padding: 16px 20px; border-left: 1px solid var(--ap-border); min-width: 0; }
.ap-banda > div:first-child { border-left: 0; }
.ap-banda .ap-v { font-size: 1.45rem; }
.ap-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.ap-sw { font-size: 0.72rem; color: var(--ap-text-muted); display: inline-flex; align-items: center; gap: 6px; margin-right: 8px; }
.ap-sw::before { content: ""; width: 10px; height: 10px; border-radius: 2px; background: var(--c); }
.ap-pill.a { color: #7fa3c9; border-color: rgba(127,163,201,0.4); } .ap-pill.v { color: #5fbf9a; border-color: rgba(95,191,154,0.4); }
.ap-trk { height: 9px; background: var(--ap-surface-2); border-radius: 3px; overflow: hidden; position: relative; }
.ap-trk b { position: absolute; top: 0; bottom: 0; left: 0; border-radius: 3px; background: linear-gradient(90deg, #8a6f33, #e2c575); }
.ap-trk.der b { left: auto; right: 0; background: linear-gradient(270deg, #9aa3b2, #4b5262); }
.ap-fila-r { display: grid; grid-template-columns: 170px 90px 1fr; gap: 14px; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--ap-border); }
.ap-fila-r:last-child { border-bottom: 0; }
.ap-fila-b { display: grid; grid-template-columns: 70px 1fr 110px; gap: 12px; align-items: center; padding: 6px 0; font-size: 0.85rem; }
.ap-fila-c { display: grid; grid-template-columns: 110px 100px 110px 1fr; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--ap-border); font-size: 0.85rem; align-items: center; }
.ap-fila-c-cab { font-size: 0.64rem; letter-spacing: 1.4px; text-transform: uppercase; color: var(--ap-text-faint); }
.ap-esc { display: grid; grid-template-columns: 100px 1fr 120px 100px; gap: 14px; align-items: center; padding: 9px 0; border-bottom: 1px solid var(--ap-border); font-size: 0.86rem; }
.ap-esc-cab { font-size: 0.64rem; letter-spacing: 1.4px; text-transform: uppercase; color: var(--ap-text-faint); }
.ap-esc-bar { position: relative; height: 10px; background: var(--ap-surface-2); border-radius: 3px; overflow: hidden; }
.ap-esc-bar b { position: absolute; top: 0; bottom: 0; }
.ap-esc-bar b.base, .sw.base { background: #d9d4c7; opacity: 0.55; } .ap-esc-bar b.extra, .sw.extra { background: linear-gradient(90deg, #a8883f, #e2c575); }
.sw { display: inline-block; width: 10px; height: 8px; border-radius: 2px; vertical-align: middle; margin-left: 4px; }
.ap-stack { display: flex; height: 22px; border-radius: 6px; overflow: hidden; }
.ap-stack div { display: flex; align-items: center; justify-content: center; font: 600 0.7rem 'Inter', sans-serif; color: #15120b; white-space: nowrap; overflow: hidden; }
.ap-mes { background: var(--ap-surface); border: 1px solid var(--ap-border); border-radius: 12px; margin-bottom: 10px; }
.ap-mes-cab { display: flex; justify-content: space-between; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--ap-border); color: #e2c575;
    font-size: 0.72rem; letter-spacing: 1.6px; text-transform: uppercase; }
.ap-mov { display: grid; grid-template-columns: 56px 70px 1fr 120px; gap: 10px; padding: 9px 16px; border-bottom: 1px solid var(--ap-border); font-size: 0.85rem; align-items: center; color: var(--ap-text); }
.ap-mov:last-child { border-bottom: 0; }
.ap-link { display: inline-block; margin-right: 14px; color: #e2c575 !important; text-decoration: none; font-size: 0.85rem; border-bottom: 1px solid rgba(201,162,74,0.4); }
/* Indicadores Pro (opción D) */
.ap-kpi-d { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); gap: 14px; margin-bottom: 18px; }
.ap-kpi-d .ap-card-pro { margin-bottom: 0; }
.ap-kpi-pat { padding-bottom: 8px; overflow: hidden; }
.ap-kpi-num { font-size: 2.5rem; line-height: 1.1; margin: 0 0 6px; color: #ffffff; font-variant-numeric: tabular-nums; }
.ap-kpi-graf { margin: 10px -20px -8px; height: 120px; }
.ap-kpi-graf .ap-spk { width: 100%; height: 120px; display: block; }
.ap-kpi-col { display: grid; gap: 14px; }
.ap-kpi-mini { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 14px 18px; }
.ap-kpi-spk { flex: 0 0 120px; height: 34px; } .ap-kpi-spk .ap-spk { width: 120px; height: 34px; display: block; }
.ap-luz-svg { stroke-dasharray: 70 2000; stroke-dashoffset: 70; opacity: 0; filter: drop-shadow(0 0 4px rgba(233,211,154,0.95));
    animation: ap-hilo-svg 9s cubic-bezier(.45,.05,.35,1) 1.5s infinite; }
@keyframes ap-hilo-svg { 0% { stroke-dashoffset: 70; opacity: 0; } 3% { opacity: 1; } 34% { opacity: 1; } 38% { stroke-dashoffset: -1000; opacity: 0; } 100% { stroke-dashoffset: -1000; opacity: 0; } }
@media (prefers-reduced-motion: reduce) { .ap-luz-svg { animation: none; opacity: 0; } }
/* Indicadores Pro · un solo cuadro (B + gráfica de D) */
.st-key-kpi_pro_card { background: linear-gradient(180deg, var(--ap-surface-2), var(--ap-surface)); border: 1px solid rgba(201,162,74,0.38) !important;
    border-radius: 14px; padding: 18px 20px 0; position: relative; box-shadow: var(--ap-shadow); margin-bottom: 18px; gap: 0.6rem; }
.st-key-kpi_pro_card::after { content: ""; position: absolute; inset: 0; border-radius: inherit; padding: 1.2px; pointer-events: none; opacity: 0; z-index: 2;
    background: conic-gradient(from var(--ap-ang), transparent 0deg, transparent 290deg, rgba(233,211,154,0) 312deg, rgba(255,244,214,0.9) 338deg, rgba(233,211,154,0) 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ap-borde-luz 12s linear 2s infinite; }
.stMarkdown p.ap-kpi-num, p.ap-kpi-num { font-size: 2.5rem !important; line-height: 1.1 !important; margin: 0 0 6px !important; color: #ffffff !important; font-weight: 400 !important; }
.ap-comp { display: flex; gap: 2px; height: 12px; border-radius: 4px; overflow: hidden; margin: 16px 0 12px; }
.ap-comp-ley { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 14px; }
.ap-comp-ley i { display: inline-block; width: 8px; height: 8px; border-radius: 2px; margin-right: 6px; }
.ap-kpi-lectura { margin: 0 !important; }
.ap-kpi-pie { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid var(--ap-border); margin: 4px -20px 0; }
.ap-kpi-pie > div { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 14px 20px; border-left: 1px solid var(--ap-border); min-width: 0; }
.ap-kpi-pie > div:first-child { border-left: 0; }
.st-key-kpi_graf .scatterlayer .trace:last-child .js-line { stroke-dasharray: 90 6000 !important; opacity: 0; filter: drop-shadow(0 0 4px rgba(233,211,154,0.95));
    animation: ap-hilo 9s cubic-bezier(.45,.05,.35,1) 1.5s infinite; }
/* Encabezado nuevo (ambos modos) */
.ap-masthead-v2 { align-items: center; }
.ap-mkts { display: flex; flex-wrap: wrap; gap: 8px; }
.ap-mkt { display: inline-flex; align-items: center; gap: 8px; font-size: 0.72rem; color: var(--ap-text-muted); border: 1px solid var(--ap-border-strong);
    border-radius: 999px; padding: 6px 12px; white-space: nowrap; }
.ap-mkt b { font-weight: 500; color: var(--ap-text); }
.ap-mkt i { width: 7px; height: 7px; border-radius: 50%; background: #6b7385; }
.ap-mkt.on i { background: #5fbf9a; animation: ap-latido 2.4s ease-in-out infinite; }
@keyframes ap-latido { 0%, 100% { opacity: 0.35; } 50% { opacity: 1; } }
.ap-hist-meta { display: flex; justify-content: flex-end; gap: 22px; margin-bottom: -54px; position: relative; z-index: 2; pointer-events: none; }
.ap-hist-meta div { display: flex; flex-direction: column; align-items: flex-end; }
.ap-hist-meta span { font-size: 0.6rem; letter-spacing: 1.6px; text-transform: uppercase; color: var(--ap-text-faint); }
.ap-hist-meta b { font-family: 'IBM Plex Mono', monospace; font-weight: 500; color: var(--ap-text); font-size: 0.9rem; }
/* Contenedores Plotly del Pro con filo */
.st-key-graf_pro_card, .st-key-radar_card, .st-key-matriz_card, .st-key-puente_card, .st-key-piruletas_card, .st-key-estres_card,
.st-key-cio_card, .st-key-posi_scatter_card, .st-key-posi_tree_card, .st-key-ficha_card {
    background: linear-gradient(180deg, var(--ap-surface-2), var(--ap-surface)); border: 1px solid rgba(201,162,74,0.38) !important;
    border-radius: 14px; padding: 16px 18px 8px; position: relative; box-shadow: var(--ap-shadow); }
.st-key-graf_pro_card::after, .st-key-radar_card::after, .st-key-estres_card::after, .st-key-cio_card::after, .st-key-ficha_card::after {
    content: ""; position: absolute; inset: 0; border-radius: inherit; padding: 1.2px; pointer-events: none; opacity: 0; z-index: 2;
    background: conic-gradient(from var(--ap-ang), transparent 0deg, transparent 290deg, rgba(233,211,154,0) 312deg, rgba(255,244,214,0.9) 338deg, rgba(233,211,154,0) 360deg);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); -webkit-mask-composite: xor; mask-composite: exclude;
    animation: ap-borde-luz 12s linear 2.5s infinite; }
.st-key-radar_card::after { animation-delay: 5s; } .st-key-estres_card::after { animation-delay: 7s; } .st-key-cio_card::after { animation-delay: 9s; }
.st-key-graf_pro .scatterlayer .trace:last-child .js-line, .st-key-ficha_graf .scatterlayer .trace:last-child .js-line {
    stroke-dasharray: 90 6000 !important; opacity: 0; filter: drop-shadow(0 0 4px rgba(233,211,154,0.95)); animation: ap-hilo 9s cubic-bezier(.45,.05,.35,1) 1.5s infinite; }
/* Carta en blanco (Pro) */
.st-key-carta_card_claro { background: #fbf8f0 !important; border: 1px solid #e3d7b5 !important; border-top: 2px solid #b8962e !important; border-radius: 14px;
    padding: 18px 20px 10px; position: relative; }
.st-key-carta_card_claro .ap-carta h3 { color: #8a6d1f !important; }
.st-key-carta_card_claro .ap-carta p, .st-key-carta_card_claro [data-testid="stCaptionContainer"] p { color: #4b5563 !important; }
.st-key-carta_card_claro [data-testid="stExpander"] details { background: #ffffff !important; border-color: #e3d7b5 !important; }
.st-key-carta_card_claro [data-testid="stExpander"] summary, .st-key-carta_card_claro [data-testid="stExpander"] summary p,
.st-key-carta_card_claro [data-testid="stExpander"] summary svg { color: #1f2937 !important; fill: #1f2937 !important; }
.st-key-carta_card_claro [data-testid="stDownloadButton"] button { background: #1f2937 !important; color: #f3e2b0 !important; border: 0 !important; }
.st-key-carta_card_claro [data-testid="stDownloadButton"] button p { color: #f3e2b0 !important; font-weight: 600 !important; }
@media (max-width: 760px) {
    .ap-kpi-pie { grid-template-columns: 1fr; } .ap-kpi-pie > div { border-left: 0; border-top: 1px solid var(--ap-border); } .ap-kpi-pie > div:first-child { border-top: 0; }
    .stMarkdown p.ap-kpi-num, p.ap-kpi-num { font-size: 2rem !important; }
    .ap-kpi-d { grid-template-columns: 1fr; } .ap-kpi-num { font-size: 2rem; } .ap-kpi-graf { height: 90px; } .ap-kpi-graf .ap-spk { height: 90px; }
    .ap-fila-r { grid-template-columns: 1fr 80px; } .ap-fila-r > div:last-child { grid-column: 1 / -1; }
    .ap-esc { grid-template-columns: 74px 1fr 92px; } .ap-esc > :last-child { display: none; }
    .ap-mov { grid-template-columns: 48px 60px 1fr; } .ap-mov > :nth-child(3) { display: none; } .ap-mov > :last-child { grid-column: 3; }
    .ap-fila-c { grid-template-columns: 90px 80px 1fr; } .ap-fila-c > :last-child { display: none; }
    .ap-hist-meta { justify-content: flex-start; margin-bottom: 10px; }
    .ap-banda > div { border-left: 0; border-top: 1px solid var(--ap-border); } .ap-banda > div:first-child { border-top: 0; }
}
</style>
"""
