# Radiografía APortafolio · Auditoría ejecutiva

> **Fecha:** 7 de octubre de 2026 · **Alcance:** `app.py` (3,266 líneas), `fp_edicion_ui.py`, `fp_fase4_ui.py`, `fp_fase5_inteligencia.py`, `fp_fase6_ui_importacion.py`, `seguridad_auth.py`, `telegram_deeplink.py`, `.streamlit/config.toml`, `requirements.txt`, `.devcontainer/devcontainer.json`.
> **Fuera de alcance (no existe en este repo):** el código del bot de Telegram y sus migraciones (`app.py:1310` remite a "el repositorio del bot (carpeta sql/)"). El bot se audita solo por el contrato que comparte con la web: tablas `fp_*` y funciones SQL en Neon.
> **Prompts del sistema auditados:** `PROMPT_MAESTRO` (`app.py:387`) y el prompt del CIO Virtual escrito directamente en el código (`app.py:3084`).
> **Regla de esta auditoría:** no se modificó ningún archivo de código.

---

## 0. Veredicto en 60 segundos

El producto tiene **buena intención de diseño y mala física**. La capa visual "Institutional Dark" ya existe (tokens CSS, `config.toml`, paleta de Plotly), pero se apoya en un **script monolítico que en cada clic vuelve a ejecutar 3,266 líneas**, reabre conexiones a Neon con una validación previa en cada una, descarga datos de Yahoo y redibuja gráficas que nadie ve. Hoy funciona porque hay pocos usuarios. **Con 100 usuarios concurrentes no se degrada poco a poco: se rompe**, por un error del pool de conexiones que tumba las conexiones de todos los usuarios a la vez (ver 1.2).

**Los 7 hallazgos que no pueden esperar** (ordenados por riesgo):

| # | Hallazgo | Dónde | Por qué importa |
|---|---|---|---|
| 1 | **`bcrypt` no está en `requirements.txt`**: `seguridad_auth` cae en silencio a SHA-256 sin sal. Tampoco está instalado en este entorno local. | `requirements.txt`, `seguridad_auth.py:9-11` | Todas las contraseñas se guardan con un hash débil, aunque el código asegure que "migra a bcrypt". |
| 2 | **Montos guardados como `REAL`** (float4, unas 7 cifras significativas). | `app.py:364-365` | $1,234,567.89 no cabe en ese tipo: el sistema contable de una plataforma de patrimonio redondea centavos e incluso pesos. |
| 3 | **`pool.closeall()` cuando falla una sola conexión**: cierra las conexiones que están usando las demás sesiones. | `app.py:311-315` | Bajo carga provoca una cascada de errores en todos los usuarios. |
| 4 | **Inyección de HTML** con datos del usuario o de Telegram sin escapar en `st.markdown(..., unsafe_allow_html=True)`. | `app.py:1247, 1268, 1293, 2024, 2693, 2948` | Un concepto como `<a href=…>` escrito por Telegram o importado por CSV se dibuja dentro de la terminal "bancaria". |
| 5 | **El estado de IA no se separa por cliente**: `cio_report` y `ai_memory` viven en la sesión del gestor, no en la del cliente. | `app.py:2773, 2895, 3101, 3265` | Si el admin cambia de cliente, el boletín del cliente A aparece en la Carta CMA del cliente B. |
| 6 | **Sin índices** en `transactions.user_id` ni en `cash_movements.user_id`. | `app.py:364-365` | Cada lectura recorre la tabla completa de todos los clientes. |
| 7 | **`.gitignore` no está versionado**: el untracked actual es lo único que protege `secrets.toml`. | `git status` | Un `git add .` de un colaborador sube `DATABASE_URL`, `GEMINI_API_KEY` y `admin_password`. |

---

## 1. Arquitectura y rendimiento (el motor)

### 1.1 Modelo de ejecución: todo se recalcula en cada clic

Streamlit vuelve a ejecutar el script completo con cada interacción. En la ruta **Terminal**, un solo clic (por ejemplo, cambiar el filtro del historial) dispara:

| Paso | Línea | Costo |
|---|---|---|
| `SELECT user_id, username FROM users` (todos los usuarios, incluso si quien entra no es admin) | `app.py:1998` | 1 viaje a la base de datos |
| `es_admin()` | `app.py:1999` → `375` | 1 viaje |
| `get_user_profile(user_id)` **y** `get_user_profile(active_client_id)` | `app.py:2050, 2612` | 2 viajes (el mismo dato si no eres admin) |
| `fp_estado_telegram` → `fp_vinculo_activo` | `app.py:2077` | 1 viaje |
| `cargar_tablas_terminal` (transacciones + caja) | `app.py:2110` | 2 viajes con lectura completa |
| `get_prices_and_sparklines` | `app.py:2457` | Caché de 5 min, pero la clave cambia (ver 1.4) |
| XIRR calculado **3 veces** con `iterrows` | `app.py:2734, 2748, 3261` | CPU |
| Gráfica "Bola de Nieve" original construida **aunque se pinte la v2** | `app.py:2570-2601` | CPU + memoria |
| Carta CMA: HTML completo + `components.html` de 1,100 px **en cada clic** | `app.py:3257` → `1891` | CPU + carga útil enviada al navegador |

En la ruta **"Tu dinero hoy"** es peor:

- `fp_dinero_libre()` (la función SQL más pesada del sistema) corre **hasta 3 veces por clic**: en `fp_fase5_inteligencia.py:270` (vía `ui_panel_inteligencia`), en `app.py:1316` y dentro del fragmento en `app.py:1164`.
- `recolectar_contexto` (`fp_fase5_inteligencia.py:265`) hace unas 10 consultas por clic, **3 de ellas a `information_schema`** (`_columnas`), que en Neon son lentas, para descubrir un esquema que no cambia mientras la app corre.
- `ui_planificacion` (`app.py:2090`) dibuja **las 3 pestañas en cada clic**: `st.tabs` ejecuta todas, no solo la visible. Eso incluye simulaciones de Avalancha de hasta 600 meses (`fp_fase4_ui.py:577`).

### 1.2 Cuellos de botella en la conexión Streamlit + Neon

1. **Validación antes de cada uso** (`app.py:286-294`): cada `db_conn()` hace `rollback → SELECT 1 → rollback` antes de la consulta real. Con unos 10 a 15 `db_conn()` por clic, eso **duplica la latencia hacia Neon**. Los `keepalives` ya están configurados (`app.py:283`); lo correcto es quitar el `SELECT 1` y reintentar una sola vez si aparece un `OperationalError`.
2. **`ThreadedConnectionPool` no espera, falla** (`app.py:281`): si se piden más de 10 conexiones lanza `PoolError` al instante. El código reintenta 3 veces con 0.3 s de espera y luego lanza `RuntimeError`, que el usuario ve como pantalla roja.
3. **Bug crítico de concurrencia** (`app.py:311-315`): en el segundo intento fallido ejecuta `pool.closeall()` y `get_pool.clear()`. Las conexiones que **otras sesiones** están usando en ese momento se cierran debajo de ellas. Un solo usuario con una conexión mala tumba a todos los demás.
4. **Conexiones anidadas** (`app.py:2062-2065`): el formulario de perfil abre una conexión y, sin soltarla, `verificar_usuario` pide **otra**. Son 2 conexiones de un pool de 10 por cada usuario que guarda su perfil.
5. **Arranque en frío de Neon**: tras la suspensión automática, la primera consulta tarda segundos. El bot y la web lo sufren por separado. Lo positivo: `DATABASE_URL` ya apunta al endpoint `-pooler` (verificado sin exponer el valor), así que el límite real está en el pool de Python y no en Neon.
6. **Telegram ↔ Web**: no hay un cuello de botella directo porque se comunican solo a través de Neon, y está bien que sea así. El riesgo es de **contrato**: la web llama a `fp_dinero_libre`, `fp_buscar_compromiso`, `fp_generar_codigo_vinculacion`, etc., cuyo código vive en otro repositorio. Además `fp_fase4_ui.py:184` **ejecuta DDL desde la web**. Así hay dos dueños del esquema, y tarde o temprano se van a desalinear.

### 1.3 Base de datos: integridad y SQL

- `REAL` para dinero y `TEXT` para fechas (`app.py:364-365`). Hay que migrar a `NUMERIC(18,6)` para títulos y `NUMERIC(18,2)` para MXN, y a `DATE`/`TIMESTAMPTZ` para fechas. **Es el hallazgo #2 y no es cosmético**: el P&L ya se calcula sobre valores redondeados.
- Falta un índice compuesto: `CREATE INDEX ON transactions (user_id, fecha)` y `CREATE INDEX ON cash_movements (user_id, fecha)`.
- ID de operación = `TXN-{timestamp}` (`app.py:2175`): dos registros en el mismo microsegundo, o un doble clic, generan colisión o duplicado. La Terminal **no tiene token de idempotencia** (el módulo FP sí lo tiene en `app.py:1211`).
- `init_db()` (`app.py:351`) ejecuta `ALTER TABLE` y `UPDATE` en cada arranque en frío. Eso es trabajo de migraciones, no de la app.

### 1.4 Dónde poner `st.cache_data` / `st.cache_resource` (exacto)

> Regla de oro: `st.cache_data` es **global entre usuarios**. Toda función cacheada que lea datos de un cliente **debe recibir `uid` como argumento** y su caché se debe limpiar (`fn.clear()`) después de cada escritura.

| Función / bloque | Línea | Recomendación |
|---|---|---|
| `cargar_tablas_terminal(uid)` | `app.py:2099` | `@st.cache_data(ttl=60)` + `.clear()` después de cada `INSERT` en `2176`, `2194` |
| `all_users` | `app.py:1998` | Envolver en función `@st.cache_data(ttl=300)`, **solo si `ES_ADMIN`**. Un cliente no necesita la lista de usuarios. Limpiar al crear un cliente (`2017`). |
| `es_admin(uid)` | `app.py:375` | `@st.cache_data(ttl=60)` |
| `get_user_profile(uid)` | `app.py:340` | `@st.cache_data(ttl=300)` + `.clear()` al guardar el perfil (`2067-2069`) |
| `fp_categorias(uid)`, `fp_cuentas(uid)` | `app.py:866, 871` | `@st.cache_data(ttl=300)`: hoy se consultan en cada ejecución del fragmento |
| `fp_vinculo_activo(uid)` | `app.py:907` | `@st.cache_data(ttl=30)` |
| `_columnas(cur, tabla)` en fp5, fp4 y fp6 | `fp_fase5_inteligencia.py:112` y equivalentes | Caché de proceso (`@st.cache_resource` con un diccionario por tabla): el esquema no cambia en tiempo de ejecución |
| `fetch_asset_deep_dive` | `app.py:2784` | Ya está cacheada, pero **definida dentro de un `if`**: se redefine en cada clic. Hay que moverla al nivel del módulo. |
| `get_prices_and_sparklines(tickers, fallback)` | `app.py:2297` | **Sacar `fallback` de la clave de caché**: contiene `costo_promedio`, que cambia con cada compra y provoca un fallo de caché. Mejor aún, cachear **por símbolo** (`tuple(sorted(...))`) y aplicar el fallback fuera. Con `max_entries=50` y 100 portafolios distintos, la caché se vacía y se vuelve a llenar sin parar. |
| `get_live_usd()` | `app.py:249` | Eliminarla: usa `MXN=X`, mientras que el resto de la app usa `USDMXN=X` (`2317`). Son dos fuentes para el mismo tipo de cambio. |
| `fp_dinero_libre` | `app.py:830` | **No cachear** (cambia con cada gasto). **Calcularla una sola vez por clic** y pasar `dl` a `ui_panel_inteligencia` y al fragmento. |
| `generar_carta_cma` | `app.py:1782` | No cachear: **generarla solo bajo demanda** (con un botón) en lugar de en cada clic |
| `_esquema_cacheado` / `_fuente_funcion` | `fp_edicion_ui.py:296, 311` | Bien resuelto (el `_db_conn` con guion bajo no entra en la clave). Mantener. |

### 1.5 Pandas: procesamiento innecesario

- `iterrows` en `calc_liquidez_real` (`2240`), `xirr_portafolio` (`1387`) y `calc_xirr` (`2729`); `apply` fila por fila en `2579`. Todo eso se puede vectorizar con `np.where` y `groupby`, como ya hace `series_bola_nieve` (`1462-1465`).
- `summary` se copia 3 veces (`3190`, `2755`, `posiciones_para_carta`).
- `series_bola_nieve` crea una serie **diaria** desde el primer depósito hasta hoy y un bucle por cada flujo (`1452-1455`). Con 5 años de historia son unos 1,800 puntos por flujo. Es aceptable, pero solo se justifica si la gráfica se muestra.

---

## 2. Poda estratégica (qué QUITAR)

### 2.1 Deuda técnica, sin anestesia

- **Monolito de 3,266 líneas** con lógica de negocio, SQL, CSS, HTML, prompts y UI mezclados. Hay 86 `unsafe_allow_html`, 152 bloques `style='...'` escritos a mano y **40 colores hex distintos** en `app.py`, aunque el tema define unos 15 tokens.
- **Helpers copiados en 4 módulos**: `_abrir`, `_columnas`, `_elegir`, `_f`, `_dinero`/`fp_dinero`, `_norm`, `_hoy`, `ZONA_MX`, `_MESES`, `_como_dialogo`. Cada módulo se proclama "AISLADO (Norma 2)". El aislamiento se pagó con duplicación.
- **El mapeo de tickers de Yahoo está repetido 5 veces**: `2301-2303`, `2327`, `2386-2387`, `2787` y la función `_yf_symbol` (`2392`), que solo usan algunos.
- **`ASSET_CLASS` / `ASSET_SECTOR` escritos a mano para un solo portafolio** (`476-477`). Cualquier cliente con otros tickers ve "Otro / Desconocido", y el simulador de rebalanceo (`3128`) **lo ignora por completo**. Lo grave es que la tabla `transactions` **ya guarda `clase`** (el formulario la pide en `2155`) y nadie la usa.
- **El admin está escrito en el código**: `USR-001` en `app.py:372, 378, 2126`. El formulario de operaciones solo aparece si `active_client_id == "USR-001"`, así que un segundo gestor no puede registrar operaciones.
- **46 comentarios "Sprint / P0-B / Alternativa"** dentro del código: es historia que pertenece a git o a un ADR, no a la ejecución.
- **Gestión de estado con trucos**: `st.session_state["modo_pro_toggle"] = st.session_state["modo_pro_toggle"]` (`2028-2029`) y `_ContenedorSilencioso` (`1361`), una clase falsa creada para "no pintar" columnas.
- **El texto de la UI contradice al motor**: la etiqueta "Cotización Pura … USD" (`2965`) aparece también para activos `.MX`.

### 2.2 Lista exacta para borrar hoy

| # | Borrar | Ubicación | Ganancia |
|---|---|---|---|
| 1 | `hash_password()` + `import hashlib` (código muerto) | `app.py:349`, `app.py:10` | Elimina la confusión sobre qué hash se usa |
| 2 | Imports sin uso: `ui_boton_cascada, ui_boton_deudas, ui_boton_metas` | `app.py:26` | Limpieza |
| 3 | `google-generativeai` (no se importa: Gemini se llama por REST) | `requirements.txt` | Despliegue más ligero. **En su lugar agregar `bcrypt` y `requests`** y fijar la versión mínima de `streamlit>=1.37`. |
| 4 | Gráfica "Bola de Nieve" original (`fig_snow`, `df_hist`, `calc_flujo`) | `app.py:2570-2601` | La v2 ya trae su propio respaldo. Si la v2 devuelve `None`, basta un `st.caption`. |
| 5 | `calc_xirr()` duplicada | `app.py:2724-2736` | Usar `xirr_portafolio()` **una sola vez** y reutilizar el resultado en las 3 partes |
| 6 | Cinta de cotizaciones animada (marquee) | `app.py:2483-2532` + `.marquee-wrapper` en `1355` | Quita 8 símbolos de la descarga de Yahoo, una animación permanente y el estilo de app de trading de los 2010 (ver 3.1) |
| 7 | `get_live_usd()` y `live_usd_rate` | `app.py:248-253` | Una sola fuente de tipo de cambio |
| 8 | `_ContenedorSilencioso` | `app.py:1361-1367, 3028` | Un `if not MODO_SENIOR:` alrededor de las 4 tarjetas |
| 9 | Clases CSS fantasma `m-card` / `m-title` (no existen) | `app.py:3136` | Hoy esa tarjeta sale sin estilo; usar `pos-box` |
| 10 | Respaldos para Streamlit antiguo: `_fp_fragmento` con `getattr`, `experimental_dialog`, chequeo de `LineChartColumn` | `app.py:1140, 1580-1583`; `fp_edicion_ui.py:113`; `fp_fase4_ui.py:914`; `fp_fase6_ui_importacion.py:843` | El entorno tiene 1.63. Basta fijar la versión mínima en `requirements.txt`. |
| 11 | Enlaces duplicados a Telegram: `st.code("/vincular …")` + botón de enlace directo + enlace `t.me` extra | `app.py:985-995` | Son tres formas de hacer lo mismo. Dejar solo `render_boton_telegram`. |
| 12 | Importar la fuente Montserrat (solo la usa el botón de Telegram) | `app.py:111`, `telegram_deeplink.py:45` | Una petición de fuente menos; usar Inter |
| 13 | Bloque comentado `responseSchema`, `render_fp_telegram` comentado y `st.toast` comentado | `app.py:518-524, 2074, 2852-2853` | Código muerto |
| 14 | `_autoprueba()` dentro del módulo de producción | `fp_fase6_ui_importacion.py:885-927` | Mover a `tests/` |
| 15 | `siguiente_mejor_accion()` y `semaforo_preparacion()` | `fp_fase5_inteligencia.py:631-638` | No las usa nadie en este repo, y cada una recalcula todo. *Verificar antes que el bot no las importe.* |
| 16 | `_resolver_tabla()`, una función de relleno que ignora `_db_conn` | `fp_edicion_ui.py:212-214` | Usar la constante directamente |
| 17 | Variable `icono` con emojis (🟢🟡🔴💎) que nunca se dibuja | `fp_fase5_inteligencia.py:47-50` | Datos muertos |

---

## 3. UI/UX y producto (la experiencia "Private Wealth")

### 3.1 Qué rompe la inmersión de banca privada

1. **La cinta de cotizaciones animada** (`app.py:2524-2526`): una píldora de 30 px de radio con margen negativo y desplazamiento infinito de 80 s. Es la estética de un *day-trader*, no de un *family office*. La banca privada transmite calma; el movimiento constante transmite urgencia.
2. **Colores neón fuera de la paleta**: `#00f0ff` (cian) en XIRR (`2747`) y en el nivel "Pro" (`2653`); `#f97316` (naranja) y `#fbbf24` (ámbar) en la racha (`2651-2652`); y en fp5, `#e07a5f` (terracota) para "negativo" (`fp_fase5_inteligencia.py:41`), mientras que en el resto del sistema lo negativo es gris pizarra `#94a3b8`. **Un mismo concepto se pinta con dos colores.**
3. **Dos familias de grises que casi coinciden**: los tokens `--ap-text-muted #8b94a7` y `--ap-text-faint #5b6475` conviven con `#8b949e`, `#64748b`, `#e5e7eb`, `#111827` y `#1f2937`, todos escritos a mano en cientos de `style=`. El ojo no lo nombra, pero lo percibe: "algo no está alineado".
4. **Tono de voz roto**: "Tu Empleado del Mes (MVP)", "el mercado da revanchas", "¡pero crecen!", "Escudo anti-baneo", "Extrayendo telemetría", "Data Feed Inyectada al Modelo (Live News)", "Bulls/Bears" y "Nivel DCA: Leyenda". Un banquero privado no habla así.
5. **Riesgo legal en la interfaz**:
   - El botón **"Ejecutar Operación"** (`2166`) sugiere que se ejecuta una orden en un bróker; solo registra. Debería decir "Registrar operación".
   - **La Siguiente Mejor Acción de fp5 usa imperativos de inversión**: "Tienes $X libres: **transfiérelos a Terminal**… invertirlos de forma constante hace crecer tu patrimonio" (`fp_fase5_inteligencia.py:559-563`). Contradice el reencuadre legal P0-B que el commit `312eba9` aplicó a la Terminal. Hoy el blindaje legal es solo parcial.
6. **Carga cognitiva en el sidebar del gestor**: unos 15 bloques apilados (selector de cliente, perfil, alta de cliente, sección, **Cerrar sesión en medio**, Modo Pro, Modo Lectura, Estrategia y Perfil con cambio de contraseña, Conectar Telegram, CSV/Excel, buscar ticker, **Registrar Operación expandido con 10 campos**, depósitos/retiros). El sidebar es navegación, alta de datos y ajustes de cuenta al mismo tiempo.
7. **Matriz de modos**: Sección (2) × Modo Pro (2) × Modo Lectura Junior/Senior (2) = **8 versiones de la app** que hay que probar y que el usuario debe entender. "Pro" y "Senior" son ejes que se cruzan y confunden.
8. **Demasiados protagonistas en "Tu dinero hoy"**: banner de Telegram + tarjeta de Siguiente Mejor Acción + semáforo con punto que "respira" (animación infinita, `fp_fase5_inteligencia.py:662`) + tarjeta principal "Hoy puedes gastar" + 4 KPIs + anillos + Health Score. Hay **tres números que compiten** por ser "el número del día".
9. **Fricción operativa**: "Creado con éxito. **Recarga la página**." (`2018`); la lectura V5 de Gemini **se dispara sola** al cambiar el selectbox y puede bloquear la pantalla hasta 45 s (`2886`).

### 3.2 Tres ajustes concretos para elevar la plataforma

**① Un encabezado sobrio en lugar de la cinta animada**
Eliminar la cinta y llevar al encabezado editorial (`.ap-masthead`, que ya existe en `app.py:189`) **3 datos fijos** en versalitas y números tabulares: `USD/MXN 18.42 · S&P 500 +0.31% · Datos al 14:05 CDMX`. La marca de hora "Datos al…" es una micro-señal de confianza institucional: dice "sabemos que Yahoo tiene retraso y te lo decimos". Al mismo tiempo, crear **un solo helper `ap_titulo_seccion(texto, icono)`** que reemplace los unos 20 `<h4 style=...>` copiados a mano. El resultado es una sola jerarquía tipográfica y cero animaciones.

**② Navegación por páginas y una sola acción principal**
Pasar de sidebar con radio y toggles a `st.navigation` con 4 destinos: **Patrimonio** (hoy Terminal, versión esencial) · **Flujo** (Tu dinero hoy) · **Análisis** (hoy Modo Pro) · **Documentos** (Carta CMA y exportes). Unificar Pro y Senior en una sola preferencia, **"Vista: Esencial / Analítica"**, guardada en `users` (no en la sesión). Todos los formularios (operación, depósito, gasto) salen del sidebar y se abren desde **un único botón dorado "+ Registrar"** que lanza un `st.dialog` con 3 opciones. El sidebar queda con: selector de cliente (solo admin), navegación y menú de usuario abajo. De unos 15 bloques se pasa a 3.

**③ Inteligencia bajo demanda y confirmaciones discretas**
- La lectura V5 deja de dispararse sola: aparece un botón **"Generar lectura cuantitativa"** con un `st.status` que muestra pasos ("Datos de mercado ✓ · Técnicos ✓ · Síntesis…"). Se elimina la espera opaca de 45 s y las llamadas involuntarias a Gemini (y lo que cuestan).
- Al registrar un gasto, una operación o un depósito: `st.toast("Gasto de $420 registrado · Deshacer")` en lugar de `st.success` + recarga completa. Bajo el número principal aparece un **delta temporal** (`−$420 vs. hace un momento`) durante un solo ciclo. El usuario ve la consecuencia de su acción sin buscarla.
- En "Tu dinero hoy" queda **un solo número protagonista** ("Hoy puedes gastar"). La Siguiente Mejor Acción baja a una línea con enlace ("1 acción sugerida →"), y el semáforo pierde la animación.

---

## 4. Escalabilidad y siguiente nivel (qué MEJORAR)

### 4.1 Qué falla si mañana entran 100 usuarios concurrentes

| Capa | Punto de falla | Evidencia | Síntoma esperado |
|---|---|---|---|
| **Pool de conexiones** | Máximo 10 conexiones por proceso, sin espera; `closeall()` ante un fallo; conexiones anidadas | `app.py:281, 311-315, 2062-2065` | `RuntimeError: No fue posible obtener una conexión` en cascada desde unas 10 a 15 sesiones activas |
| **Hilos de Streamlit** | Todas las sesiones comparten un proceso (GIL). Gemini bloquea el hilo hasta 45 s (V5) o 90 s (CIO). | `app.py:2886, 3100` | Latencia general alta mientras alguien genera un boletín |
| **Gemini** | El límite de "anti-baneo" es **por sesión** (`session_state["last_gemini_call"]`). No hay límite global ni caché compartida. | `app.py:2846` | 30 usuarios que analizan NVDA = 30 llamadas idénticas, con 429 del proveedor y costo multiplicado |
| **Yahoo Finance** | Mismo IP de salida para todos; la caché se vacía por las claves de usuario; `tk.info` es lento | `app.py:2297, 2387, 2790` | `Too Many Requests`, precios en 0 y fallback silencioso al costo promedio (el patrimonio "se congela") |
| **Memoria** | `session_state` guarda DataFrames de preparación de importación, `ai_memory`, `cio_report` y la carta HTML; `cache_data` copia DataFrames por cada lectura | `fp_fase6_ui_importacion.py:783`, `app.py:2895` | Reinicios por falta de memoria si el hosting tiene alrededor de 1 GB |
| **Sesión y autenticación** | La identidad vive solo en `session_state`; no hay caducidad por inactividad ni límite de intentos de login; la lista completa de usuarios se carga para cualquier cliente | `app.py:1988-1989, 1998` | Fuerza bruta sin freno; exposición innecesaria de datos |
| **Aislamiento entre clientes** | `cio_report` y `ai_memory` se guardan por sesión, no por cliente | `app.py:3101, 3265, 2827` | Documento con datos de otro cliente (hallazgo #5) |
| **Escrituras** | IDs por timestamp y Terminal sin idempotencia | `app.py:2175` | Operaciones duplicadas con doble clic, que distorsionan el P&L |
| **Esquema** | DDL repartido entre `app.py:351`, `fp_fase4_ui.py:184` y el repo del bot | — | Desalineación del esquema cuando se despliega solo una de las dos partes |
| **Configuración de desarrollo** | El devcontainer arranca con `--server.enableXsrfProtection false --server.enableCORS false` | `.devcontainer/devcontainer.json` | Aceptable en Codespaces, **peligroso si alguien copia ese comando a producción** |

### 4.2 Propuestas de arquitectura (de menor a mayor esfuerzo)

**Fase 1 · Estabilizar (días, sin cambiar la arquitectura)**
1. **Pool**: quitar `closeall()` del camino normal; `getconn` con espera acotada (un semáforo `threading.BoundedSemaphore(maxconn)` en `cache_resource` alrededor de `getconn`/`putconn`); sin `SELECT 1` previo; reintento único ante `OperationalError`. Corregir la conexión anidada del perfil (`2062`). Subir `maxconn` a unas 20 (Neon `-pooler` lo soporta).
2. **Seguridad**: agregar `bcrypt` a `requirements.txt` (la migración silenciosa de `seguridad_auth` ya está escrita y se activará sola en cada login); escapar con `html_seguro()` **todo** dato de base de datos o de usuario dentro de HTML (6 puntos de la tabla del §0); limitar intentos de login (contador en tabla o `cache_resource` con TTL); caducidad de sesión por inactividad; versionar `.gitignore`.
3. **Datos**: migración a `NUMERIC` / `DATE` / `TIMESTAMPTZ` + índices `(user_id, fecha)`; IDs `uuid4`; token de idempotencia en el formulario de la Terminal (copiar el patrón `fp_token` de `app.py:1211`).
4. **Separación por cliente**: guardar `cio_report` y `ai_memory` bajo `(active_client_id, …)` y borrarlos al cambiar de cliente.
5. **Caché**: aplicar la tabla del §1.4 y calcular `fp_dinero_libre` una sola vez por clic.

**Fase 2 · Desacoplar lo externo (semanas)**
6. **Worker de datos de mercado**: un proceso programado (puede vivir junto al bot de Telegram, que ya es un proceso de larga duración) que cada 5 a 15 min descarga **el universo de tickers** (`SELECT DISTINCT ticker FROM transactions`) + FX + fundamentales y los escribe en `market_prices` / `market_fx` / `market_fundamentals` en Neon. La web **solo lee de Neon**: cero llamadas a Yahoo en el camino del usuario, precios consistentes entre usuarios y un "Datos al…" verdadero.
7. **IA con caché compartida y límite global**: tabla `ai_lecturas(ticker, fecha, contexto_hash, payload, fuente)`. La parte de mercado de la lectura V5 (técnicos, noticias, valuación) es **igual para todos** y se reutiliza durante el día; solo el bloque "contexto de cartera" es personal y puede calcularse localmente (ya existe `_sintesis_local_v5`). Agregar un semáforo global (`cache_resource` → `BoundedSemaphore(3)`) alrededor de `llamar_gemini`. El boletín CIO se genera **una vez al día por universo de activos**, no por clic.
8. **Una sola fuente de migraciones**: el repo del bot (`sql/`) o un directorio `migrations/` compartido. La web nunca ejecuta DDL.
9. **Módulo `core/`**: `db.py` (pool + `read_df` + helpers), `fp_core.py` (los helpers duplicados), `mercado.py` (símbolos, FX y precios desde Neon), `ui_kit.py` (tokens, `ap_titulo_seccion`, tarjetas). `app.py` pasa a orquestar páginas.

**Fase 3 · Siguiente nivel (solo si los números lo justifican)**
10. `st.navigation` con páginas (ver 3.2 ②): cada página ejecuta **solo su código**, lo que reduce el costo por clic de forma estructural.
11. Si se superan unos cientos de usuarios activos o se necesita tiempo real: mover el cálculo (dinero libre, XIRR, riesgo) a un servicio (FastAPI) **compartido con el bot**. Streamlit queda como cliente ligero y Telegram usa exactamente los mismos números. *Menos es más: no se necesita mientras la Fase 1 y la Fase 2 no estén hechas.*
12. Observabilidad: medir el tiempo de cada sección por clic (ya hay `logging`; agregar `time.perf_counter` por bloque) y alertas de errores (Sentry o similar). Sin esto, la próxima auditoría vuelve a ser a ojo.

---

## 5. Orden sugerido para decidir qué refactorizar primero

| Prioridad | Paquete | Esfuerzo | Riesgo que elimina |
|---|---|---|---|
| **P0** | `bcrypt` en requirements · versionar `.gitignore` · escapar HTML · aislar `cio_report`/`ai_memory` por cliente | Horas | Seguridad y fuga de datos entre clientes |
| **P0** | Pool de conexiones (closeall, anidadas, sin `SELECT 1`) | Horas | Caída en cascada con carga |
| **P1** | Migración `REAL → NUMERIC` + índices + IDs uuid + idempotencia | 1 a 2 días | Integridad contable |
| **P1** | Caché (§1.4) + `fp_dinero_libre` una vez por clic + carta bajo demanda | 1 día | Latencia por clic |
| **P2** | Poda (§2.2) + helpers comunes + clase de activo desde `transactions.clase` | 1 a 2 días | Deuda técnica |
| **P2** | UX: encabezado sobrio, "Registrar" en vez de "Ejecutar", Siguiente Mejor Acción sin imperativos de inversión | 1 día | Inmersión y riesgo legal |
| **P3** | Worker de mercado + caché de IA en Neon + navegación por páginas | 1 a 2 semanas | Escalabilidad real |
