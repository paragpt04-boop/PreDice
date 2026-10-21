# PreDice

PreDice es un proyecto de monitorización y predicción de criptoactivos: **API de análisis con históricos reales de Bitunix** y futura aplicación Android nativa.

> Estado: fundamento del motor predictivo y API inicial. **No hay APK compilada ni despliegue VPS confirmado**. Ninguna señal constituye una garantía ni debe interpretarse como orden automática.

## Principios de predicción

- Solo velas **cerradas**. Sin datos futuros en las características ni en el conjunto de entrenamiento.
- Modelo basal de vecinos históricos análogos (*k-nearest analogues*), con pronósticos porcentuales y escenarios.
- Validación *walk-forward* cronológica. Las probabilidades indicadas son **votos empíricos, no probabilidades calibradas**.
- **ESPERAR** si la muestra es insuficiente o la señal no supera filtros básicos. No se anuncian supuestas certezas.
- Registro SQLite de cada predicción y conciliación posterior contra el cierre real.
- Sin autenticación a Bitunix; solo endpoints públicos. No coloca órdenes.

## API backend

Python 3.11+:

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8097
```

Endpoints: `/health`, `/api/v1/assets?q=btc`, `/api/v1/tickers?symbols=BTCUSDT,ETHUSDT`, `/api/v1/predict/BTCUSDT?horizon=15m`, `/api/v1/history?symbol=BTCUSDT`, `/api/v1/calculate` (POST). Documentación interactiva: `/docs`.

Para ejecutar pruebas offline:

```bash
cd backend
python -m unittest discover -s tests -v
```

`docker compose up -d --build` expone el backend **solo en 127.0.0.1:8097**, evitando alterar servicios actuales. La APK necesitará un dominio HTTPS con reverse proxy/autenticación antes de acceder desde el exterior.

Variables: `PREDICE_DB=/data/predice.sqlite3` en contenedor; `PREDICE_ALLOWED_ORIGINS` para orígenes web autorizados.

## Arquitectura prevista

```
Android nativo (Kotlin/Compose)
   -> HTTPS/API autenticada [pendiente]
   -> FastAPI -> Bitunix API pública
                 -> ventanas de históricos cerrados
                 -> motor de predicciones + pruebas walk-forward
                 -> SQLite (auditoría)
```

## Próximas etapas

1. Telemetría continua/WebSocket, almacenamiento de velas y análisis de profundidad/funding.
2. Validación más amplia con más ciclos de mercado, calibración de probabilidades, métricas después de comisiones/slippage y detección de cambios de régimen.
3. Android nativo con watchlist persistente, selector de horizontes, gráficos, radar y calculadora.
4. CI de pruebas y empaquetado, despliegue aislado en VPS tras inventariar lo que ya está corriendo.

Documentación oficial: [Bitunix Kline](https://www.bitunix.com/api-docs/futures/market/get_kline), [Tickers](https://www.bitunix.com/api-docs/futures/market/get_tickers.html), [Trading Pairs](https://www.bitunix.com/api-docs/futures/market/get_trading_pairs.html).
