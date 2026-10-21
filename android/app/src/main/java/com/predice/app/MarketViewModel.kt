package com.predice.app

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

data class MarketState(
    val symbol: String = "BTCUSDT", val source: String = "binance", val watch: List<String> = emptyList(),
    val search: List<Pair<String,String>> = emptyList(), val price: Double? = null,
    val tick: Long = 0, val connected: Boolean = false, val error: String? = null,
    val candles: List<Double> = emptyList(), val forecasts: List<JSONObject> = emptyList(),
    val history: List<JSONObject> = emptyList(), val alerts: List<JSONObject> = emptyList(),
    val calculation: JSONObject? = null, val status: String = "Configura tu conexión segura"
)
class MarketViewModel: ViewModel() {
    private val mutable = MutableStateFlow(MarketState())
    val state = mutable.asStateFlow()
    private val client = OkHttpClient.Builder().callTimeout(25,java.util.concurrent.TimeUnit.SECONDS).build()
    private var base = ""
    private var token = ""
    private var socket: WebSocket? = null
    private var polling: Job? = null
    private var selection = 0
    private var searchJob: Job? = null
    private fun path(path: String)=path+(if(path.contains('?')) "&" else "?")+"source=${mutable.value.source}"
    private fun update(f: (MarketState)->MarketState) { synchronized(mutable) { mutable.value=f(mutable.value) } }
    private suspend fun request(path: String, method: String="GET", data: JSONObject?=null): String = withContext(Dispatchers.IO) {
        val body=if(method in listOf("POST","PUT")) (data?.toString() ?: "").toRequestBody("application/json".toMediaType()) else null
        client.newCall(Request.Builder().url(base+path).header("Authorization","Bearer $token").method(method,body).build()).execute().use {
            if(!it.isSuccessful) error("Servidor: ${it.code}")
            it.body?.string() ?: error("Respuesta vacía")
        }
    }
    private fun JSONArray.objects()=List(length()) { getJSONObject(it) }
    fun connect(url: String, access: String) {
        if(!url.startsWith("https://") || access.isBlank()) { update { it.copy(error="Introduce HTTPS y tu token") }; return }
        base=url.trimEnd('/'); token=access; select(mutable.value.symbol)
    }
    fun search(query: String) {
        searchJob?.cancel()
        searchJob=viewModelScope.launch {
            delay(350)
            try { val data=JSONArray(request(path("/assets?q="+java.net.URLEncoder.encode(query,"UTF-8"))))
                update { it.copy(search=data.objects().map { a->a.getString("symbol") to a.getString("name") },error=null) }
            } catch(e: CancellationException) { throw e } catch(e: Exception) { update { it.copy(error=e.message) } }
        }
    }
    fun add(symbol: String) = viewModelScope.launch {
        try { request(path("/watchlist/$symbol"),"PUT"); update { it.copy(search=emptyList()) }; select(symbol) }
        catch(e: Exception) { update { it.copy(error=e.message) } }
    }
    fun remove() = viewModelScope.launch {
        try { request(path("/watchlist/${mutable.value.symbol}"),"DELETE"); select(mutable.value.symbol) }
        catch(e: Exception) { update { it.copy(error=e.message) } }
    }
    fun chooseSource(source: String) {
        if(source==mutable.value.source) return
        socket?.cancel(); polling?.cancel(); searchJob?.cancel(); selection++
        update { it.copy(source=source,watch=emptyList(),search=emptyList(),forecasts=emptyList(),history=emptyList(),alerts=emptyList(),price=null,connected=false) }
        select("BTCUSDT")
    }
    fun select(symbol: String) {
        if(base.isBlank()) return
        selection++; val generation=selection
        polling?.cancel(); socket?.close(1000,"Changed asset")
        update { it.copy(symbol=symbol,price=null,tick=0,connected=false,candles=emptyList(),forecasts=emptyList(),history=emptyList(),status="Recopilando datos…") }
        polling=viewModelScope.launch {
            while(isActive && generation==selection) {
                try {
                    val watch=JSONArray(request(path("/watchlist")))
                    val candles=JSONArray(request(path("/candles/$symbol")))
                    val forecasts=JSONObject(request(path("/predictions/$symbol")))
                    val history=JSONArray(request(path("/history/$symbol")))
                    val alerts=JSONArray(request(path("/alerts")))
                    if(generation==selection) update { it.copy(watch=List(watch.length()){i->watch.getString(i)},
                        candles=candles.objects().map {c->c.getDouble("close")}, forecasts=forecasts.getJSONArray("items").objects(),
                        history=history.objects(),alerts=alerts.objects(),status=forecasts.getString("state"),error=null) }
                    if(!mutable.value.connected) openSocket(symbol,generation)
                } catch(e: CancellationException) { throw e } catch(e: Exception) { update { it.copy(error=e.message,connected=false) } }
                delay(15000)
            }
        }
    }
    private fun openSocket(symbol: String,generation: Int) {
        socket?.cancel()
        socket=client.newWebSocket(Request.Builder().url(base.replaceFirst("https://","wss://")+path("/ws/$symbol")).header("Authorization","Bearer $token").build(),object: WebSocketListener() {
            override fun onMessage(webSocket: WebSocket,text: String) {
                runCatching { JSONObject(text) }.onSuccess { j-> if(generation==selection) update { it.copy(price=j.getDouble("price"),tick=j.getLong("timestamp"),connected=true) } }
            }
            override fun onFailure(webSocket: WebSocket,t: Throwable,response: Response?) { if(generation==selection) update { it.copy(connected=false) } }
            override fun onClosed(webSocket: WebSocket,code: Int,reason: String) { if(generation==selection) update { it.copy(connected=false) } }
        })
    }
    fun calculate(side: String,amount: String,entry: String,exit: String,fee: String,stop: String) = viewModelScope.launch {
        try {
            val j=JSONObject().put("side",side).put("amount",amount.toDouble()).put("entry",entry.toDouble()).put("exit",exit.toDouble()).put("fee_bps",fee.toDouble())
            if(stop.isNotBlank()) j.put("stop",stop.toDouble())
            val result=JSONObject(request("/calculate","POST",j)); update { it.copy(calculation=result,error=null) }
        } catch(e: Exception) { update { it.copy(error="Revisa los importes: ${e.message}") } }
    }
    fun alert(threshold: String,above: Boolean) = viewModelScope.launch {
        try { request("/alerts","POST",JSONObject().put("symbol",mutable.value.symbol).put("source",mutable.value.source).put("threshold",threshold.toDouble()).put("above",above)); update { it.copy(status="Alerta guardada") } }
        catch(e: Exception) { update { it.copy(error=e.message) } }
    }
    override fun onCleared() { socket?.cancel(); polling?.cancel(); client.dispatcher.executorService.shutdown() }
}
