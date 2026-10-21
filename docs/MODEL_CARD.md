# Modelo de investigación v2

No hay una precisión prometida. Este primer modelo es una referencia reproducible, no un sistema avanzado cuya superioridad esté demostrada.

Datos Binance spot USDT: velas cerradas de 5 minutos; historial inicial de 16.000 velas (~56 días). Características causales: retornos, volatilidad, desviación respecto a media y volumen relativo. No incluye noticias, order book ni funding. Los precios spot no equivalen al precio de ejecución de futuros.
Bitunix futuros se ingiere como una serie independiente de velas LAST_PRICE cerradas. Se entrena, calibra y evalúa por separado de Binance; no se mezclan historiales ni métricas. LAST_PRICE no es el precio de marca ni garantiza el precio ejecutable. La primera evaluación walk-forward de Bitunix debe revisarse antes de atribuirle cualquier ventaja.

Evaluación inicial Bitunix BTCUSDT: siete ventanas de 6.000 velas por horizonte. El Brier medio del ensemble fue mayor que el baseline en los cinco horizontes; los pronósticos finales de esas ventanas se abstuvieron. Ver `docs/evaluation/BTCUSDT-bitunix-backtest.json`. Esto no demuestra capacidad de predicción rentable.

Por horizonte 1/3/12/48/288 velas: ensemble fijo 50/50 de Ridge y gradient boosting para retorno; logística y gradient boosting para dirección, combinando sus logits antes de Platt. Árboles regularizados (7 hojas, 80 iteraciones, mínimo 80 muestras por hoja); sin early stopping aleatorio ni ajuste sobre test. Normalización solo sobre entrenamiento. División cronológica 55/20/25 con purga de tantas velas como horizonte en ambas fronteras. Platt se ajusta exclusivamente en calibración. Intervalo residual con cuantil conformal nominal 90%; no se garantiza cobertura bajo dependencia temporal o cambios de régimen.

El informe BTCUSDT-backtest.json conserva la primera referencia lineal v1. Los informes v2 se identifican por la versión en cada resultado; no comparar versiones como una selección independiente después de observar sus tests. Cualquier mejora requiere confirmación prospectiva.

Se reportan Brier, ECE con diez bins, fiabilidad por bin, MAE, cobertura, baseline de frecuencia de entrenamiento y retorno cero; también tamaño y Brier sobre observaciones no solapadas. Las señales se abstienen si no superan ambos baselines, ECE >= 8%, cobertura <85%, menos de 100 observaciones no solapadas, o si el intervalo no permite margen >30 bps (10 bps de comisión y 5 bps de deslizamiento por lado) y probabilidad direccional >=60%. Son umbrales de investigación, no evidencia de rentabilidad. Stop usa anchura residual y mínimo 0,3%; take profit usa 2R. No es una política de ejecución validada.

La CLI `python -m predice.backtest BTCUSDT` (o `--source bitunix`) ejecuta un backtest walk-forward de ventanas de 6.000 velas con paso 1.500: reajusta cada modelo y calibrador y evalúa tramos de prueba cronológicos sin solapamiento entre ventanas. Conserva las métricas de cada ventana para revisar degradación entre regímenes.

Limitaciones: la señal en vivo usa un holdout cronológico; no hay simulación histórica de ejecución, costes dinámicos, funding, liquidación ni deslizamiento extremo. El muestreo solapado dentro de cada ventana puede sobreestimar evidencia; no hay intervalos bootstrap de métricas. 24h probablemente se abstendrá por tamaño efectivo insuficiente. El uso repetido del holdout para habilitar señales requiere una evaluación prospectiva adicional. No se optimizan parámetros sobre el holdout.

Cada pronóstico conserva origen, objetivo, versión, hash de precios/volúmenes, splits y métricas en SQLite. El resultado usa exactamente la vela objetivo; no se sustituye por una posterior. Historial append-only desde la API, pero no resistente a manipulación por administrador de SQLite. No llamar a esto un registro criptográficamente inmutable.

Próxima condición para producción: evaluación walk-forward en múltiples regímenes y exchanges, bootstrap por bloques, comparación de modelos, costes realistas y periodo prospectivo. Las pruebas sintéticas prueban software, no rentabilidad.
