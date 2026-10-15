-- =====================================================================
-- Corrección de registros del 15/10/2026 · Terminal APPortafolio (Neon)
-- Correr en el SQL Editor de Neon, bloque por bloque.
-- Las operaciones y su movimiento de caja comparten el timestamp del id:
--   transactions.id = 'TXN-<ts>'   ·   cash_movements.id = 'CMV-<ts>'
-- =====================================================================

-- 1) VERIFICAR: debe salir UNA sola fila (la compra de GOOGL con el TC live ~18.42)
SELECT t.id, t.user_id, t.fecha, t.ticker, t.titulos, t.precio_unitario, t.comision,
       t.tipo_cambio, t.total_mxn, c.id AS caja_id, c.monto_mxn AS caja_monto
  FROM transactions t
  LEFT JOIN cash_movements c ON c.id = 'CMV-' || substring(t.id FROM 5)
 WHERE t.ticker = 'GOOGL' AND t.fecha = '2026-10-15' AND t.tipo_cambio < 18.6;

-- 2) CORREGIR GOOGL: TC real de GBM (4,181.76 MXN / 224.48 USD = 18.6287)
--    Total esperado: (0.32074 × 349.47 + 0.28) × 18.6287 = 2,093.29 MXN
BEGIN;

UPDATE cash_movements c
   SET monto_mxn = -ROUND((t.titulos * t.precio_unitario + t.comision + t.iva) * 18.6287, 2)
  FROM transactions t
 WHERE t.ticker = 'GOOGL' AND t.fecha = '2026-10-15' AND t.tipo_cambio < 18.6
   AND c.id = 'CMV-' || substring(t.id FROM 5);

UPDATE transactions
   SET tipo_cambio = 18.6287,
       total_mxn   = ROUND((titulos * precio_unitario + comision + iva) * 18.6287, 2)
 WHERE ticker = 'GOOGL' AND fecha = '2026-10-15' AND tipo_cambio < 18.6;

-- Revisa que GOOGL quede en 18.6287 / 2093.29 y su caja en -2093.29 antes de confirmar
SELECT t.ticker, t.tipo_cambio, t.total_mxn, c.monto_mxn
  FROM transactions t
  JOIN cash_movements c ON c.id = 'CMV-' || substring(t.id FROM 5)
 WHERE t.fecha = '2026-10-15' AND t.ticker IN ('GOOGL', 'ASML', 'BTC');

COMMIT;   -- si algo no cuadra, en lugar de COMMIT corre: ROLLBACK;

-- 3) OPCIONAL · BTC con 8 decimales (solo después de desplegar el nuevo app.py)
--    Hoy está como 0.00114 títulos + 0.09 USDT de comisión (total 1,713.31, correcto en costo).
--    Esto deja los títulos netos exactos de Binance y suma ambas comisiones (BTC + conversión) en Fricción:
--    (0.00113886 × 81,282.01 + 0.1857) × 18.472 = 1,713.36 MXN
-- BEGIN;
-- UPDATE cash_movements c
--    SET monto_mxn = -ROUND((0.00113886 * t.precio_unitario + 0.1857) * t.tipo_cambio, 2)
--   FROM transactions t
--  WHERE t.ticker = 'BTC' AND t.fecha = '2026-10-15' AND c.id = 'CMV-' || substring(t.id FROM 5);
-- UPDATE transactions
--    SET titulos = 0.00113886, comision = 0.1857,
--        total_mxn = ROUND((0.00113886 * precio_unitario + 0.1857) * tipo_cambio, 2)
--  WHERE ticker = 'BTC' AND fecha = '2026-10-15';
-- COMMIT;
