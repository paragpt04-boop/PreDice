package com.predice.mobile

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.LocalContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.net.URLEncoder
import java.util.Locale
import java.util.concurrent.TimeUnit

private val bg=Color(0xFF090D1D)
private val panel=Color(0xFF171D31)
private val aqua=Color(0xFF49E7CB)
private val purple=Color(0xFF9881FF)
private val quiet=Color(0xFF9AA7BD)
private val red=Color(0xFFFF728A)
private val round=RoundedCornerShape(20.dp)
private fun fmt(v:Double?, digits:Int=2):String =
 if(v==null || !v.isFinite()) "—" else String.format(Locale.US,"%.${digits}f",v)

private class Feed {
 val configured=BuildConfig.API_BASE_URL.startsWith("https://") &&
    !BuildConfig.API_BASE_URL.contains(".invalid")
 private val base=BuildConfig.API_BASE_URL.trimEnd('/') + "/"
 private val client=OkHttpClient.Builder().connectTimeout(7,TimeUnit.SECONDS)
  .readTimeout(18,TimeUnit.SECONDS).build()
 suspend fun get(path:String):JSONObject = withContext(Dispatchers.IO) {
  client.newCall(Request.Builder().url(base+path).build()).execute().use { response ->
   if(!response.isSuccessful) throw IllegalStateException("API HTTP ${response.code}")
   JSONObject(response.body?.string() ?: throw IllegalStateException("Sin respuesta"))
  }
 }
 suspend fun assets(term:String):List<String> {
  val a=get("api/v1/assets?q="+URLEncoder.encode(term,"UTF-8")).getJSONArray("assets")
  return (0 until a.length()).map { a.getJSONObject(it).getString("symbol") }
 }
 suspend fun tickers(watch:List<String>):Map<String,Double> {
  if(watch.isEmpty()) return emptyMap()
  val a=get("api/v1/tickers?symbols="+watch.joinToString(",")).getJSONArray("items")
  return (0 until a.length()).associate { i ->
   val entry=a.getJSONObject(i)
   entry.getString("symbol") to entry.getDouble("price")
  }
 }
 suspend fun predict(symbol:String,horizon:String):JSONObject =
  get("api/v1/predict/"+symbol+"?horizon="+horizon)
}

private fun symbolOf(raw:String):String? {
 val v=raw.uppercase(Locale.US).trim()
 val embedded=Regex("[A-Z0-9]{2,20}USDT").findAll(v).lastOrNull()?.value
 if(embedded!=null) return embedded
 return if(v.matches(Regex("[A-Z0-9]{2,20}"))) v+"USDT" else null
}

class MainActivity:ComponentActivity() {
 override fun onCreate(savedInstanceState:Bundle?) {
  super.onCreate(savedInstanceState)
  setContent {
   MaterialTheme(colorScheme=darkColorScheme(
     primary=aqua,background=bg,surface=panel,onSurface=Color.White
   )) { Application() }
  }
 }
}

@Composable
private fun Chip(label:String, selected:Boolean, onClick:()->Unit) {
 Surface(
  modifier=Modifier.clickable(onClick=onClick),
  color=if(selected) aqua else panel,shape=RoundedCornerShape(12.dp)
 ) {
  Text(label,Modifier.padding(horizontal=13.dp,vertical=11.dp),
   fontSize=12.sp,fontWeight=FontWeight.Bold,
   color=if(selected) bg else Color.White)
 }
}

@Composable
private fun Line(label:String,value:String) {
 Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
  Text(label,color=quiet,fontSize=12.sp)
  Text(value,color=Color.White,fontSize=12.sp,fontWeight=FontWeight.Bold)
 }
}

@Composable
private fun Application() {
 val ctx=LocalContext.current
 val store=remember { ctx.getSharedPreferences("watchlist",0) }
 val feed=remember { Feed() }
 val coins=remember {
  mutableStateListOf<String>().apply {
   addAll(store.getString("symbols","BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT")!!
     .split(",").filter { it.isNotBlank() })
  }
 }
 var tab by remember { mutableIntStateOf(0) }
 var selected by remember { mutableStateOf(coins.firstOrNull()?:"BTCUSDT") }
 var horizon by remember { mutableStateOf("15m") }
 var query by remember { mutableStateOf("") }
 var suggestions by remember { mutableStateOf<List<String>>(emptyList()) }
 var prices by remember { mutableStateOf<Map<String,Double>>(emptyMap()) }
 var forecast by remember { mutableStateOf<JSONObject?>(null) }
 var error by remember { mutableStateOf("") }
 var refresh by remember { mutableIntStateOf(0) }
 var loading by remember { mutableStateOf(false) }

 fun save() { store.edit().putString("symbols",coins.joinToString(",")).apply() }
 fun add(coin:String) {
  if(coin.isBlank()) return
  if(coin !in coins) { coins.add(coin);save() }
  selected=coin;query="";suggestions=emptyList();tab=1
 }

 LaunchedEffect(query) {
  suggestions=emptyList()
  if(query.isBlank() || !feed.configured) return@LaunchedEffect
  delay(350)
  try { suggestions=feed.assets(query) } catch(_:Exception) {}
 }
 LaunchedEffect(coins.joinToString(","),refresh) {
  if(!feed.configured) {
   error="Configura un dominio HTTPS del backend para activar los datos en vivo."
   return@LaunchedEffect
  }
  while(true) {
   try { prices=feed.tickers(coins.toList());error="" }
   catch(e:Exception) { error=e.message ?: "Cotizaciones no disponibles" }
   delay(15000)
  }
 }
 LaunchedEffect(selected,horizon,refresh) {
  forecast=null
  if(!feed.configured) return@LaunchedEffect
  loading=true
  try { forecast=feed.predict(selected,horizon) }
  catch(e:Exception) { error=e.message ?: "Pronóstico no disponible" }
  finally { loading=false }
 }

 Column(Modifier.fillMaxSize().background(bg)) {
  Row(Modifier.fillMaxWidth().padding(18.dp),verticalAlignment=Alignment.CenterVertically) {
   Box(Modifier.size(43.dp).background(
    Brush.linearGradient(listOf(aqua,purple)),round),contentAlignment=Alignment.Center) {
    Text("◈",fontSize=30.sp,color=bg,fontWeight=FontWeight.Black)
   }
   Spacer(Modifier.width(12.dp))
   Column(Modifier.weight(1f)) {
    Text("PreDice",fontSize=24.sp,color=Color.White,fontWeight=FontWeight.Black)
    Text("PREDICCIÓN INTELIGENTE",fontSize=9.sp,color=quiet,letterSpacing=1.5.sp)
   }
   TextButton(onClick={refresh++}) { Text("↻",fontSize=25.sp,color=aqua) }
  }
  Row(Modifier.fillMaxWidth().padding(horizontal=18.dp),
   horizontalArrangement=Arrangement.spacedBy(8.dp)) {
   listOf("Radar","Predicción","Simulador").forEachIndexed { i,s ->
    Box(Modifier.weight(1f).background(if(tab==i)aqua else panel,
     RoundedCornerShape(12.dp)).clickable { tab=i }.padding(vertical=13.dp)) {
     Text(s,Modifier.fillMaxWidth(),fontSize=12.sp,fontWeight=FontWeight.Bold,
      color=if(tab==i) bg else Color.White,textAlign=TextAlign.Center)
    }
   }
  }
  if(error.isNotEmpty()) Text(error,Modifier.padding(18.dp),color=red,fontSize=11.sp)
  Spacer(Modifier.height(12.dp))
  when(tab) {
   0 -> Column(Modifier.fillMaxSize().padding(horizontal=18.dp)) {
    Text("Radar del mercado",fontSize=25.sp,fontWeight=FontWeight.Black,color=Color.White)
    Text("Futuros Bitunix · actualización cada 15 segundos",fontSize=11.sp,color=quiet)
    Spacer(Modifier.height(14.dp))
    OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),
     label={Text("Nombre, par USDT o enlace")},singleLine=true,
     shape=round)
    if(query.isNotBlank()) {
     symbolOf(query)?.let { coin ->
      TextButton(onClick={add(coin)}) {
       Text("＋ Añadir $coin",color=aqua)
      }
     }
     suggestions.take(6).forEach { coin ->
      TextButton(onClick={add(coin)}) {
       Text("＋ $coin",color=Color.White)
      }
     }
    }
    Spacer(Modifier.height(14.dp))
    Text("MI LISTA · ${coins.size} MONEDAS",fontSize=11.sp,color=aqua)
    Spacer(Modifier.height(10.dp))
    LazyColumn(verticalArrangement=Arrangement.spacedBy(9.dp),
     contentPadding=PaddingValues(bottom=30.dp)) {
     items(coins.toList(),key={it}) { coin ->
      Row(Modifier.fillMaxWidth().background(panel,round).padding(15.dp),
       verticalAlignment=Alignment.CenterVertically) {
       Box(Modifier.size(39.dp).background(purple.copy(alpha=.18f),round),
        contentAlignment=Alignment.Center) {
        Text(coin.take(1),color=purple,fontWeight=FontWeight.Black)
       }
       Spacer(Modifier.width(12.dp))
       Column(Modifier.weight(1f).clickable { selected=coin;tab=1 }) {
        Text(coin.removeSuffix("USDT"),color=Color.White,fontWeight=FontWeight.Bold,fontSize=18.sp)
        Text(coin,color=quiet,fontSize=10.sp)
       }
       Text(if(prices[coin]!=null) "$"+fmt(prices[coin],if((prices[coin]?:0.0)<1) 5 else 2) else "—",
        color=aqua,fontWeight=FontWeight.Bold,fontSize=15.sp,
        modifier=Modifier.clickable { selected=coin;tab=1 })
       TextButton(onClick={coins.remove(coin);save()}) { Text("×",color=quiet,fontSize=20.sp) }
      }
     }
    }
   }
   1 -> Column(Modifier.verticalScroll(rememberScrollState()).padding(horizontal=18.dp),
    verticalArrangement=Arrangement.spacedBy(15.dp)) {
    Text("Motor predictivo",fontSize=26.sp,color=Color.White,fontWeight=FontWeight.Black)
    Text("Velas cerradas · patrones históricos · validación cronológica",
     fontSize=11.sp,color=quiet)
    Row(Modifier.horizontalScroll(rememberScrollState()),
     horizontalArrangement=Arrangement.spacedBy(8.dp)) {
     coins.forEach { coin -> Chip(coin.removeSuffix("USDT"),selected==coin) { selected=coin } }
    }
    Row(Modifier.horizontalScroll(rememberScrollState()),
     horizontalArrangement=Arrangement.spacedBy(8.dp)) {
     listOf("5m","15m","1h","4h","24h").forEach { h ->
      Chip(h,horizon==h) { horizon=h }
     }
    }
    if(loading) LinearProgressIndicator(Modifier.fillMaxWidth(),color=aqua)
    val p=forecast
    val change=if(p?.isNull("expected_change_pct")==false)
     p.optDouble("expected_change_pct") else null
    Column(Modifier.fillMaxWidth().background(panel,round).padding(20.dp),
     verticalArrangement=Arrangement.spacedBy(15.dp)) {
     Text("CAMBIO ESPERADO · $selected · $horizon",fontSize=11.sp,color=quiet)
     Text(if(change!=null) "${if(change>=0) "+" else ""}${fmt(change)}%" else "Sin datos suficientes",
      fontSize=34.sp,fontWeight=FontWeight.Black,
      color=if((change?:0.0)>=0) aqua else red)
     val signal=p?.optString("signal","WAIT") ?: "WAIT"
     Text(when(signal) {
      "LONG_CANDIDATE" -> "LONG POSIBLE · requiere confirmación"
      "SHORT_CANDIDATE" -> "SHORT POSIBLE · requiere confirmación"
      else -> "ESPERAR · ventaja no confirmada"
     },color=Color.White,fontWeight=FontWeight.Bold)
     HorizontalDivider(color=quiet.copy(alpha=.3f))
     Line("Precio al cierre",if(p?.has("base_price")==true) "$"+fmt(p.optDouble("base_price"),5) else "—")
     Line("Votos históricos alcistas",if(p?.has("up_pattern_vote_pct")==true)
      fmt(p.optDouble("up_pattern_vote_pct"))+"%" else "—")
     Line("Escenario 10–90%",if(p?.has("scenario_p10_pct")==true)
      "${fmt(p.optDouble("scenario_p10_pct"))}% a ${fmt(p.optDouble("scenario_p90_pct"))}%" else "—")
     val stats=p?.optJSONObject("walk_forward")
     Line("Pruebas walk-forward",stats?.optInt("evaluations",0)?.toString() ?: "—")
     Line("Acierto histórico",if(stats?.isNull("accuracy_pct")==false)
      fmt(stats.optDouble("accuracy_pct"))+"%" else "—")
    }
    Column(Modifier.fillMaxWidth().background(Color(0xFF2A2440),round).padding(15.dp)) {
     Text("⚠ Modelo experimental",fontWeight=FontWeight.Bold,color=Color.White)
     Spacer(Modifier.height(5.dp))
     Text("Los votos de patrones NO son probabilidades calibradas. " +
       "Las señales no ejecutan operaciones ni garantizan resultados.",
      color=Color(0xFFE1D6FF),fontSize=12.sp)
    }
   }
   else -> ProfitCalculator(forecast,selected)
  }
 }
}

@Composable
private fun ProfitCalculator(outlook:JSONObject?,symbol:String) {
 var margin by remember { mutableStateOf("10") }
 var side by remember { mutableStateOf("LONG") }
 var leverage by remember { mutableFloatStateOf(2f) }
 var target by remember { mutableStateOf("") }
 val base=if(outlook?.has("base_price")==true) outlook.optDouble("base_price") else null
 val projected=target.toDoubleOrNull() ?: if(base!=null && outlook?.has("expected_change_pct")==true)
  base*(1+outlook.optDouble("expected_change_pct")/100) else null
 val notional=margin.toDoubleOrNull()?.times(leverage.toInt())
 val pnl=if(notional!=null && base!=null && base>0 && projected!=null)
  notional * (projected/base-1) * (if(side=="LONG") 1 else -1) -
  notional*.0016 else null
 Column(Modifier.verticalScroll(rememberScrollState()).padding(18.dp),
  verticalArrangement=Arrangement.spacedBy(14.dp)) {
  Text("Simulador de P&L",fontSize=26.sp,fontWeight=FontWeight.Black,color=Color.White)
  Text("Calcula ganancias o pérdidas hipotéticas · $symbol",color=quiet,fontSize=12.sp)
  Column(Modifier.fillMaxWidth().background(panel,round).padding(18.dp),
   verticalArrangement=Arrangement.spacedBy(13.dp)) {
   Row(horizontalArrangement=Arrangement.spacedBy(10.dp)) {
    listOf("LONG","SHORT").forEach { s ->
     Button(onClick={side=s},modifier=Modifier.weight(1f),
      colors=ButtonDefaults.buttonColors(containerColor=if(side==s)aqua else bg)) {
      Text(s,color=if(side==s)bg else Color.White)
     }
    }
   }
   OutlinedTextField(margin,{margin=it},Modifier.fillMaxWidth(),singleLine=true,
    label={Text("Capital (USDT)")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal))
   Text("Apalancamiento · ${leverage.toInt()}x",color=Color.White)
   Slider(leverage,{leverage=it},valueRange=1f..10f,steps=8)
   OutlinedTextField(target,{target=it},Modifier.fillMaxWidth(),singleLine=true,
    label={Text("Precio objetivo opcional")},
    keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal))
   HorizontalDivider(color=quiet.copy(alpha=.3f))
   Line("Capital nominal",if(notional!=null)fmt(notional)+" USDT" else "—")
   Line("Entrada",if(base!=null)"$"+fmt(base,5) else "—")
   Line("Salida simulada",if(projected!=null)"$"+fmt(projected,5) else "—")
   Text("Resultado neto estimado",color=quiet,fontSize=12.sp)
   Text(if(pnl!=null)"${if(pnl>=0)"+" else ""}${fmt(pnl)} USDT" else "Sin precio real",
    fontSize=33.sp,fontWeight=FontWeight.Black,color=if((pnl?:0.0)>=0)aqua else red)
  }
  Text("Comisiones y deslizamiento supuestos: 0,08% por lado. " +
   "No incluye funding ni liquidación. No envía órdenes.",
   color=quiet,fontSize=12.sp)
 }
}
