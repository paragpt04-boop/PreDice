# PreDice

Android nativo en Kotlin + Jetpack Compose y backend Python/FastAPI. Plataforma de investigación: probabilidades, intervalos y abstención explícita; no promete rentabilidad ni ejecuta órdenes.

## Incluido

- Búsqueda de pares USDT por símbolo y nombres populares; parseo local de enlaces Binance/CoinGecko/CoinMarketCap o Bitunix según la fuente seleccionada. No se admiten tokens arbitrarios sin mercado disponible.
- Fuentes separadas: Binance spot y Bitunix futuros LAST_PRICE. Cada una tiene watchlist, histórico, predicciones, alertas y precios WebSocket propios. Los datos no se mezclan.
- Horizontes 5m/15m/1h/4h/24h; retorno esperado, probabilidad calibrada, intervalo nominal 90%, métricas y condiciones de señal LONG/SHORT/WAIT.
- Evaluación temporal con purga, baselines y CLI walk-forward. Historial SQLite con resolución exacta de objetivos.
- Calculadora de P/L neto y riesgo al stop; alertas persistentes sondeadas cada 15s y consultables en app (sin push).
- Contenedor sin privilegios, puerto loopback, token requerido y APK debug mediante CI.

## Backend

Python 3.12, un único worker Uvicorn:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export PREDICE_TOKEN='GENERAR_UN_SECRETO_PROPIO'
uvicorn predice.app:app --host 127.0.0.1 --port 8080
python -m pytest -q
python -m predice.backtest BTCUSDT --output backtest.json
python -m predice.backtest BTCUSDT --source bitunix --output bitunix-backtest.json
```

El servicio precarga BTC/ETH/SOL y necesita acceso público a Binance. Errores o huecos inhiben nuevos pronósticos; los anteriores se marcan obsoletos. Los enlaces nunca se descargan. La API requiere Bearer excepto /health. Esta es una instancia personal, no multiusuario.

## Android

JDK 17, Gradle 8.11.1, Android SDK 35:

```sh
cd android
gradle assembleDebug lintDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`; CI lo publica como artefacto PreDice-debug-apk. En Ajustes indicar URL HTTPS y token. No hay endpoint de producción preconfigurado. El token solo vive en memoria durante la sesión.

## Estado y límites

Primera versión de investigación. Notificaciones push, firma de distribución, revisión visual en dispositivo y despliegue VPS pendientes. El modelo es una referencia estadística evaluable; no se ha demostrado ventaja operativa. La primera carga de Bitunix consulta paginadamente hasta 16.000 velas cerradas; se retrasa si la API pública limita solicitudes. Los precios de futuros no equivalen a spot y el escenario de costes no incluye funding ni liquidación.

Consultar [metodología y límites](docs/MODEL_CARD.md) y [procedimiento de despliegue y rollback](docs/DEPLOYMENT.md).

Fuentes de integración: [Binance market-data-only](https://github.com/binance/binance-spot-api-docs/blob/master/faqs/market_data_only.md), [WebSocket](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md), [Bitunix kline](https://www.bitunix.com/api-docs/futures/market/get_kline), [Bitunix WebSocket](https://www.bitunix.com/api-docs/futures/websocket/public/Ticker%20Channel.html), [Compose BOM](https://developer.android.com/develop/ui/compose/bom).
