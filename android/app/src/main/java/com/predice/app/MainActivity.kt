package com.predice.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import java.util.Locale
import kotlinx.coroutines.delay

private val Mint=Color(0xFF64F4C5)
private val Night=Color(0xFF090F1E)
private val Panel=Color(0xFF151F32)
private fun number(value: Double)=String.format(Locale.US,"%,.2f",value)

class MainActivity: ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme=darkColorScheme(primary=Mint,background=Night,surface=Panel,secondary=Color(0xFF9EAAFF))) {
                PreDice()
            }
        }
    }
}

@Composable private fun PreDice(vm: MarketViewModel=viewModel()) {
    val state by vm.state.collectAsStateWithLifecycle()
    var page by rememberSaveable { mutableStateOf("Mercado") }
    var query by rememberSaveable { mutableStateOf("") }
    var url by rememberSaveable { mutableStateOf("") }
    var token by remember { mutableStateOf("") }
    var horizon by rememberSaveable { mutableStateOf("1h") }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) { while(true) { now=System.currentTimeMillis(); delay(1000) } }
    Scaffold(containerColor=Night,bottomBar={
        NavigationBar(containerColor=Panel) {
            listOf("Mercado","Análisis","Simular","Registro","Ajustes").forEachIndexed { index,label ->
                NavigationBarItem(selected=page==label,onClick={page=label},icon={Text(listOf("◈","⌁","±","≡","⚙")[index],fontSize=23.sp)},label={Text(label,fontSize=10.sp)})
            }
        }
    }) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(16.dp),contentPadding=PaddingValues(vertical=20.dp)) {
            item {
                Text("P R E D I C E",color=Mint,fontWeight=FontWeight.Black,fontSize=25.sp)
                Text("El mercado, con perspectiva.",color=Color(0xFF94A6C2),fontSize=13.sp)
            }
            state.error?.let { error->item { Surface(color=Color(0xFF502333),shape=RoundedCornerShape(16.dp)) { Text(error,Modifier.padding(16.dp)) } } }
            if(page=="Ajustes") {
                item { Text("Conecta tu espacio",style=MaterialTheme.typography.headlineMedium) }
                item { Text("Servidor personal HTTPS. El token se mantiene solo durante esta sesión.") }
                item { OutlinedTextField(url,{url=it},label={Text("https://tu-servidor")},modifier=Modifier.fillMaxWidth(),singleLine=true) }
                item { OutlinedTextField(token,{token=it},label={Text("Token de acceso")},visualTransformation=PasswordVisualTransformation(),modifier=Modifier.fillMaxWidth(),singleLine=true) }
                item { Button(onClick={vm.connect(url,token); page="Mercado"},modifier=Modifier.fillMaxWidth()) { Text("Conectar") } }
                item { Text("Datos: Binance spot. SHORT es un escenario hipotético; no se envían órdenes. Los resultados no están garantizados.") }
            } else {
                item { Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    FilterChip(state.source=="binance",{vm.chooseSource("binance")},label={Text("Binance · spot")})
                    FilterChip(state.source=="bitunix",{vm.chooseSource("bitunix")},label={Text("Bitunix · futuros")})
                } }
                item { LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) { items(state.watch) { symbol->FilterChip(selected=state.symbol==symbol,onClick={vm.select(symbol)},label={Text(symbol.removeSuffix("USDT"))}) } } }
                item {
                    Column(Modifier.fillMaxWidth().background(Brush.linearGradient(listOf(Panel,Color(0xFF193C43))),RoundedCornerShape(26.dp)).padding(22.dp)) {
                        Text(state.symbol,color=Mint,fontWeight=FontWeight.Bold)
                        Text(state.price?.let { "$"+number(it) } ?: "—",fontSize=38.sp,fontWeight=FontWeight.Bold)
                        val fresh=state.connected && now-state.tick<15000
                        Text(if(fresh) "● EN VIVO · ${if(state.source=="bitunix") "Bitunix futuros" else "Binance spot"}" else "○ Esperando precio actualizado",color=if(fresh) Mint else Color(0xFFFFC478),fontSize=12.sp)
                        if(state.tick>0) Text("Último dato: ${java.util.Date(state.tick)}",fontSize=10.sp)
                    }
                }
                if(page=="Mercado") {
                    item { OutlinedTextField(query,{query=it;vm.search(it)},label={Text("Nombre, símbolo o enlace")},singleLine=true,modifier=Modifier.fillMaxWidth()) }
                    items(state.search) { (symbol,name)->OutlinedButton(onClick={vm.add(symbol)},modifier=Modifier.fillMaxWidth()) { Text("+ $name · $symbol") } }
                    item { Text("Últimas 24 horas",style=MaterialTheme.typography.titleLarge) }
                    item { PriceChart(state.candles) }
                    item { Text(state.status,color=Color(0xFF94A6C2)) }
                    if(state.symbol in state.watch) item { TextButton(onClick={vm.remove()}) { Text("Quitar de seguimiento") } }
                    item { Button(onClick={page="Análisis"},modifier=Modifier.fillMaxWidth()) { Text("Explorar predicciones →") } }
                }
                if(page=="Análisis") {
                    item { LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) { items(listOf("5m","15m","1h","4h","24h")) { h->FilterChip(selected=horizon==h,onClick={horizon=h},label={Text(h)}) } } }
                    val prediction=state.forecasts.firstOrNull { it.optString("horizon")==horizon }
                    if(prediction==null) item { Text("Recopilando histórico y evaluando el modelo. No hay una predicción disponible todavía.") }
                    else item {
                        val stale=prediction.optBoolean("stale") || now-(prediction.optLong("origin")+300000)>420000 || now>=prediction.optLong("target")+300000
                        Column(Modifier.fillMaxWidth().background(Panel,RoundedCornerShape(24.dp)).padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                            Text(if(stale) "ESPERAR · Dato desactualizado" else prediction.getString("signal"),color=Mint,fontSize=23.sp,fontWeight=FontWeight.Bold)
                            Text("Movimiento esperado: ${number(prediction.getDouble("expected_pct"))}%",fontSize=20.sp)
                            Text("Probabilidad de subida: ${number(prediction.getDouble("probability_up")*100)}%")
                            LinearProgressIndicator(progress={prediction.getDouble("probability_up").toFloat()},modifier=Modifier.fillMaxWidth())
                            Text("Intervalo nominal 90%: ${number(prediction.getDouble("lower_pct"))}% a ${number(prediction.getDouble("upper_pct"))}%")
                            Text("La cobertura real puede cambiar con el mercado.",fontSize=12.sp)
                            if(!stale && !prediction.isNull("entry")) {
                                Text("Entrada orientativa: ${number(prediction.getDouble("entry"))}")
                                Text("Stop: ${number(prediction.getDouble("stop"))} · Objetivo: ${number(prediction.getDouble("take_profit"))}")
                                Text("Cerrar al alcanzar stop/objetivo o al vencer el horizonte. Revisar spread y liquidez antes de entrar.")
                            }
                            val m=prediction.getJSONObject("metrics")
                            HorizontalDivider()
                            Text("Evidencia fuera de muestra",fontWeight=FontWeight.Bold)
                            Text("Brier ${number(m.getDouble("brier"))} · Base ${number(m.getDouble("baseline_brier"))}")
                            Text("Error de calibración ${number(m.getDouble("ece")*100)}% · Cobertura ${number(m.getDouble("coverage90")*100)}%")
                            Text("${m.getInt("samples")} observaciones · ${m.getInt("nonoverlap_samples")} sin solapamiento")
                            Text(prediction.getString("reason"),fontSize=12.sp)
                        }
                    }
                }
                if(page=="Simular") item { Calculator(vm,state) }
                if(page=="Registro") {
                    item { AlertEditor(vm) }
                    items(state.alerts) { a->Text("${a.getString("symbol")} · ${a.getDouble("threshold")} · "+if(a.isNull("fired")) "Pendiente" else "Activada") }
                    item { Text("Predicción frente a resultado",style=MaterialTheme.typography.titleLarge) }
                    items(state.history) { h->
                        val p=org.json.JSONObject(h.getString("payload"))
                        Card(Modifier.fillMaxWidth()) { Column(Modifier.padding(16.dp)) {
                            Text("${h.getString("horizon")} · ${java.util.Date(h.getLong("origin")+300000)}")
                            Text("Estimado ${number(p.getDouble("expected_pct"))}%")
                            Text(if(h.isNull("outcome")) "Resultado pendiente" else "Realizado ${number(h.getDouble("outcome"))}%",color=Mint)
                            Text("Modelo ${p.getString("model")}",fontSize=10.sp)
                        } }
                    }
                }
            }
            item { Text("Probabilidades, no certezas. Una señal puede fallar. Sin operaciones automáticas.",color=Color(0xFF94A6C2),fontSize=11.sp) }
        }
    }
}

@Composable private fun PriceChart(values: List<Double>) {
    if(values.size<2) { Text("El gráfico aparecerá al recibir velas reales."); return }
    Canvas(Modifier.fillMaxWidth().height(180.dp)) {
        val low=values.min(); val span=(values.max()-low).coerceAtLeast(.000001)
        val path=Path()
        values.forEachIndexed { i,v-> val x=i.toFloat()/(values.size-1)*size.width; val y=size.height-((v-low)/span*size.height).toFloat()
            if(i==0) path.moveTo(x,y) else path.lineTo(x,y)
        }
        drawPath(path,Mint,style=Stroke(width=3.dp.toPx()))
    }
}

@Composable private fun Calculator(vm: MarketViewModel,state: MarketState) {
    var side by rememberSaveable { mutableStateOf("LONG") }
    var amount by rememberSaveable { mutableStateOf("") }
    var entry by rememberSaveable { mutableStateOf("") }
    var exit by rememberSaveable { mutableStateOf("") }
    var stop by rememberSaveable { mutableStateOf("") }
    var fee by rememberSaveable { mutableStateOf("10") }
    Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text("Diseña tu escenario",style=MaterialTheme.typography.headlineSmall)
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("LONG","SHORT").forEach { s->FilterChip(side==s,{side=s},label={Text(s)}) } }
        OutlinedTextField(amount,{amount=it},label={Text("Importe USDT")},modifier=Modifier.fillMaxWidth())
        OutlinedTextField(entry,{entry=it},label={Text("Precio de entrada")},modifier=Modifier.fillMaxWidth())
        OutlinedTextField(exit,{exit=it},label={Text("Precio de cierre")},modifier=Modifier.fillMaxWidth())
        OutlinedTextField(stop,{stop=it},label={Text("Stop opcional")},modifier=Modifier.fillMaxWidth())
        OutlinedTextField(fee,{fee=it},label={Text("Comisión por lado (bps: 10 = 0,1%)")},modifier=Modifier.fillMaxWidth())
        Text("Deslizamiento supuesto: 5 bps por lado. Sin apalancamiento, funding ni coste de préstamo.",fontSize=12.sp)
        Button(onClick={vm.calculate(side,amount,entry,exit,fee,stop)}) { Text("Calcular resultado neto") }
        state.calculation?.let { c->Text("Neto: ${number(c.getDouble("net"))} USDT",fontSize=24.sp,color=Mint)
            Text("Costes: ${number(c.getDouble("costs"))} USDT")
            if(!c.isNull("risk")) Text("Pérdida al stop estimada: ${number(c.getDouble("risk"))} USDT") }
    }
}

@Composable private fun AlertEditor(vm: MarketViewModel) {
    var threshold by rememberSaveable { mutableStateOf("") }
    var above by rememberSaveable { mutableStateOf(true) }
    Column {
        Text("Alertas de precio",style=MaterialTheme.typography.titleLarge)
        OutlinedTextField(threshold,{threshold=it},label={Text("Precio objetivo")},modifier=Modifier.fillMaxWidth())
        Row { FilterChip(above,{above=true},label={Text("Por encima")}); Spacer(Modifier.width(8.dp)); FilterChip(!above,{above=false},label={Text("Por debajo")}) }
        Button(onClick={vm.alert(threshold,above)}) { Text("Guardar alerta") }
        Text("Consulta las activaciones aquí. Notificaciones push aún no disponibles.",fontSize=12.sp)
    }
}
