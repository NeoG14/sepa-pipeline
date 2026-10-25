// Sitio de precios SEPA: lee los JSON que arma publicar/exportar_json.py (carpeta datos/).
// Sin dependencias salvo Chart.js para los gráficos grandes; los gráficos chicos son SVG a mano.
"use strict";

const PROVINCIAS = {
  "AR-C": "Ciudad de Buenos Aires", "AR-B": "Buenos Aires", "AR-K": "Catamarca", "AR-H": "Chaco",
  "AR-U": "Chubut", "AR-X": "Córdoba", "AR-W": "Corrientes", "AR-E": "Entre Ríos", "AR-P": "Formosa",
  "AR-Y": "Jujuy", "AR-L": "La Pampa", "AR-F": "La Rioja", "AR-M": "Mendoza", "AR-N": "Misiones",
  "AR-Q": "Neuquén", "AR-R": "Río Negro", "AR-A": "Salta", "AR-J": "San Juan", "AR-D": "San Luis",
  "AR-Z": "Santa Cruz", "AR-S": "Santa Fe", "AR-G": "Santiago del Estero", "AR-V": "Tierra del Fuego",
  "AR-T": "Tucumán",
};
// Un color fijo por cadena en el gráfico grande del producto
const COLORES = { "2": "#8250df", "9": "#1f6feb", "10": "#0a7f5a", "11": "#bf8700", "12": "#cf222e", "13": "#6e7781", "15": "#e85aad" };
const CORTOS = { "13": "Coop. Obrera" };
const DIAS_NO_DISPONIBLE = 7;
const MAX_RESULTADOS = 50;
const MAX_MARCAS = 8;
const EMPATE = 0.005;  // menos de 0,5 puntos de diferencia con la más barata es un empate
const GRUPO_EMPATE = 0.02;  // en los rankings por grupo, menos de 2 puntos: hay menos productos y el orden se mueve
const GRUPO_CARA = 0.06;  // la más cara de un grupo se marca en naranja desde 6 puntos
const SVG = "http://www.w3.org/2000/svg";

const estado = {
  meta: null, indice: null, porClave: new Map(), canasta: null, historia: new Map(), hoy: new Map(),
  comparacion: new Map(), pagina: 0, grupoComparacion: "",
  producto: null, marcas: new Set(), graficos: {},
};
const $ = id => document.getElementById(id);

// --- utilidades -------------------------------------------------------------------------------
const leer = clave => { try { return localStorage.getItem(clave); } catch { return null; } };
const guardar = (clave, valor) => { try { localStorage.setItem(clave, valor); } catch { /* sin almacenamiento */ } };
const normalizar = t => (t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
const pesos = v => v.toLocaleString("es-AR", { style: "currency", currency: "ARS", maximumFractionDigits: 2 });
const pesosRedondo = v => "$ " + v.toLocaleString("es-AR", { maximumFractionDigits: 0 });
// En la tabla: sin decimales si el precio es entero, con dos si tiene centavos
const pesosCelda = v => "$ " + v.toLocaleString("es-AR", Number.isInteger(v)
  ? { maximumFractionDigits: 0 } : { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const porcentaje = v => v.toLocaleString("es-AR", { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + " %";
const fechaDe = dia => { const d = new Date(estado.meta.fecha_base + "T12:00:00"); d.setDate(d.getDate() + dia); return d; };
const fecha = dia => fechaDe(dia).toLocaleDateString("es-AR", { day: "numeric", month: "numeric" });
const fechaLarga = dia => fechaDe(dia).toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" });
const mayuscula = t => t.charAt(0).toUpperCase() + t.slice(1);
const cadena = id => estado.meta.cadenas?.[id]?.nombre ?? `Cadena ${id}`;
const corto = id => CORTOS[id] ?? cadena(id);
const color = id => COLORES[id] ?? "#8c959f";
const provincia = () => $("provincia").value;
const ordenCadenas = () => estado.meta.orden_cadenas ?? [];
const cadenasDeProvincia = codigo => estado.meta.cadenas_por_provincia?.[codigo] ?? [];
const diasGrafico = () => estado.meta.dias_grafico ?? 13;
const plural = (n, uno, varios) => `${n.toLocaleString("es-AR")} ${n === 1 ? uno : varios}`;
const celda = (texto, clase) => { const td = document.createElement("td"); td.textContent = texto; if (clase) td.className = clase; return td; };
const elemento = (tag, clase, texto) => { const e = document.createElement(tag); if (clase) e.className = clase; if (texto != null) e.textContent = texto; return e; };

// Nombres y marcas que vienen todo en mayúsculas: en minúscula, con la marca capitalizada
const titulo = t => t.toLowerCase().replace(/(^|[\s.-])(\p{L})/gu, (m, antes, letra) => antes + letra.toUpperCase());
const marcaVisible = m => (m ? titulo(m) : "Sin marca");
// Un nombre cuenta como "en mayúsculas" si al menos el 80 % de sus letras lo son: así no lo salva una
// unidad en minúscula al final ("CARAMELOS MASTICABLES TUTI FRUTTI, LENGUETAZO, 13 gr")
function enMayusculas(texto) {
  const letras = texto.match(/\p{L}/gu) ?? [];
  return letras.length > 0 && letras.filter(l => l === l.toUpperCase() && l !== l.toLowerCase()).length / letras.length >= 0.8;
}
function nombreVisible(p) {
  if (!enMayusculas(p.nombre)) return p.nombre;
  let nombre = p.nombre.toLowerCase();
  nombre = nombre.charAt(0).toUpperCase() + nombre.slice(1);
  const marca = p.marca?.toLowerCase();
  const i = marca ? nombre.toLowerCase().indexOf(marca) : -1;
  return i < 0 ? nombre : nombre.slice(0, i) + titulo(p.marca) + nombre.slice(i + marca.length);
}

// "A", "A y B", "A, B y C"
function listar(nombres) {
  return nombres.length < 2 ? (nombres[0] ?? "") : `${nombres.slice(0, -1).join(", ")} y ${nombres.at(-1)}`;
}

async function json(ruta) {
  const r = await fetch(ruta);
  if (!r.ok) throw new Error(`${ruta}: ${r.status}`);
  return r.json();
}

// --- inicio -----------------------------------------------------------------------------------
async function iniciar() {
  [estado.meta, estado.canasta] = await Promise.all([json("datos/meta.json"), json("datos/canasta.json")]);
  const dato = estado.meta.dia_dato;
  const publicado = new Date(estado.meta.publicado);
  $("publicado").textContent = `Datos del ${fechaLarga(dato)}. Publicado el `
    + `${publicado.toLocaleDateString("es-AR", { weekday: "long", day: "numeric", month: "long" })} a las `
    + `${publicado.toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" })}.`;
  $("lema").textContent = `Datos oficiales de SEPA · ${plural(ordenCadenas().length, "cadena", "cadenas")}`;
  document.querySelectorAll(".dias-grafico").forEach(e => { e.textContent = diasGrafico(); });
  $("leyenda-dias").textContent = `últimos ${diasGrafico()} días`;

  const elegida = leer("provincia") || "AR-B";
  const selector = $("provincia");
  for (const [codigo, nombre] of Object.entries(PROVINCIAS).sort((a, b) => a[1].localeCompare(b[1], "es"))) {
    selector.add(new Option(nombre, codigo, false, codigo === elegida));
  }
  selector.addEventListener("change", () => { guardar("provincia", provincia()); cambiarProvincia(); });

  // Buscador de la portada: lleva el texto a la vista de resultados
  const irAResultados = texto => {
    if (!texto.trim()) return;
    $("texto-resultados").value = texto.trim();
    estado.marcas.clear();
    irVista("buscar");
  };
  // El link de la introducción de la portada: sube y pone el cursor en el buscador del encabezado
  $("ir-buscador").addEventListener("click", e => {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: "smooth" });
    $("texto-encabezado").focus({ preventScroll: true });
  });
  // Buscador del encabezado: lleva el texto a los resultados y se vacía (ahí sigue la búsqueda)
  $("formulario-encabezado").addEventListener("submit", e => {
    e.preventDefault();
    irAResultados($("texto-encabezado").value);
    $("texto-encabezado").value = "";
  });

  // Buscador de resultados: busca mientras se escribe
  let espera;
  $("texto-resultados").addEventListener("input", () => { clearTimeout(espera); estado.marcas.clear(); espera = setTimeout(buscar, 150); });
  $("formulario-resultados").addEventListener("submit", e => { e.preventDefault(); estado.marcas.clear(); buscar(); });
  for (const id of ["comparables", "con-cambios"]) {
    $(id).addEventListener("click", () => {
      $(id).setAttribute("aria-pressed", String($(id).getAttribute("aria-pressed") !== "true"));
      buscar();
    });
  }
  $("orden").addEventListener("change", buscar);
  $("orden-comparacion").addEventListener("change", () => { estado.pagina = 0; mostrarComparacion(); });
  $("grupo-comparacion").addEventListener("change", e => { estado.grupoComparacion = e.target.value; estado.pagina = 0; mostrarComparacion(); });

  window.addEventListener("hashchange", mostrarRuta);
  // Otro clic en el logo estando ya en #inicio no cambia la dirección: se limpia igual
  $("logo").addEventListener("click", e => { if (location.hash === "#inicio") { e.preventDefault(); mostrarRuta(); } });
  aplicarVista();
  await cambiarProvincia();
  cargarIndice();
}

async function cambiarProvincia() {
  document.querySelectorAll(".nombre-provincia").forEach(e => { e.textContent = PROVINCIAS[provincia()]; });
  mostrarPortada();
  mostrarCanastaProvincia();
  estado.pagina = 0;
  await Promise.all([cargarHoy(), cargarComparacion()]);
  mostrarComparacion();
  buscar();
  if (ruta().vista === "producto" && estado.producto) mostrarProducto(estado.producto);
}

function elegirProvincia(codigo) {
  $("provincia").value = codigo;
  guardar("provincia", codigo);
  cambiarProvincia();
}

// Los códigos de los productos con que se compara la provincia (la lista de la página de la canasta)
async function cargarComparacion() {
  const codigo = provincia();
  if (!estado.comparacion.has(codigo)) {
    try { estado.comparacion.set(codigo, await json(`datos/comparacion/${codigo}.json`)); }
    catch { estado.comparacion.set(codigo, []); }  // provincia sin comparación
  }
}

// Precios de hoy de la provincia elegida (uno por provincia, se baja solo el que hace falta)
async function cargarHoy() {
  const codigo = provincia();
  if (!estado.hoy.has(codigo)) {
    try { estado.hoy.set(codigo, await json(`datos/hoy/${codigo}.json`)); }
    catch { estado.hoy.set(codigo, {}); }  // provincia sin precios
  }
}

// Una fila de hoy/<provincia>.json: [precio de cada cadena en orden_cadenas (0 = no lo vende),
// y opcionalmente [[posición de la cadena, hace cuántos días, precio anterior], ...]]
function filaHoy(clave) {
  const fila = estado.hoy.get(provincia())?.[clave];
  if (!fila) return null;
  const orden = ordenCadenas();
  const conCambios = Array.isArray(fila.at(-1));
  const precios = new Map();
  (conCambios ? fila.slice(0, -1) : fila).forEach((p, i) => { if (p) precios.set(orden[i], p); });
  const cambios = conCambios ? fila.at(-1).map(([i, hace, anterior]) => ({ id: orden[i], hace, anterior })) : [];
  return precios.size ? { precios, cambios } : null;
}

// Precio de una cadena en cada día del gráfico chico (el primero es el más viejo; el último, hoy).
// Se arma hacia atrás: un cambio de hace N días vale desde ese día; antes regía el precio anterior.
function serieCadena(hoy, id) {
  const n = diasGrafico();
  const cambios = hoy.cambios.filter(c => c.id === id).sort((a, b) => a.hace - b.hace);
  return Array.from({ length: n }, (_, k) => {
    const hace = n - 1 - k;
    let precio = hoy.precios.get(id);
    for (const c of cambios) { if (hace > c.hace) precio = c.anterior; else break; }
    return precio;
  });
}

// --- portada ----------------------------------------------------------------------------------
// Ranking de hoy de la provincia elegida (fct_canasta_provincia): índice de precios sobre los
// productos que tienen todas las cadenas de la provincia. diferencia = cuánto más cara que la más
// barata (0 = la más barata); las que quedan a menos de EMPATE de la más barata están empatadas.
function rankingProvincia(codigo) {
  const filas = estado.canasta.provincias.filter(f => f[1] === codigo)
    .map(([dia, , id, cadenas, productos, indice, diferencia, puesto]) => ({ dia, id, cadenas, productos, indice, diferencia, puesto }));
  if (!filas.length) return { dia: null, filas: [] };
  const dia = Math.max(...filas.map(f => f.dia));
  return { dia, filas: filas.filter(f => f.dia === dia).sort((a, b) => a.diferencia - b.diferencia) };
}
const empatada = f => f.diferencia < EMPATE;

function mostrarPortada() {
  const codigo = provincia(), nombre = PROVINCIAS[codigo];
  const { filas: hoy } = rankingProvincia(codigo);
  // Con menos de dos cadenas no hay con quién comparar: se avisa arriba de todo
  const aviso = $("portada-aviso");
  aviso.hidden = hoy.length >= 2;
  aviso.textContent = hoy.length === 1 ? `En ${nombre}, solo informa precios ${cadena(hoy[0].id)}. Sin otra cadena no hay con quién comparar.`
    : hoy.length === 0 ? `En ${nombre}, ninguna cadena informa precios hoy.` : "";
  mostrarEvolucion();
  mostrarGrupos();
  mostrarKilo();
}

// --- evolución de los precios de cada cadena -------------------------------------------------
// datos/indice/<provincia>.json (ver publicar/indice_json.py): s = {cadena: [[día, índice]]} con base 100 el primer día y
// n = {cadena: productos que entran en su índice}. El índice de cada cadena sale de comparar, día a día, TODOS sus
// productos con código de barras (decenas de miles), no una canasta fija. Solo dice cuánto cambió, no cuál es más barata.
const indiceDatos = {};          // provincia -> contenido del archivo (null si no hay)
const cadenasOcultas = new Set(); // cadenas que el visitante apagó en el gráfico; se mantiene al cambiar de provincia

// Cambio en puntos porcentuales respecto del primer día: "+0,4 %", "−0,2 %", "0 %"
const cambioTexto = (v, decimales) => {
  const n = Math.abs(v).toLocaleString("es-AR", { minimumFractionDigits: decimales, maximumFractionDigits: Math.max(decimales, 1) });
  return Math.round(Math.abs(v) * 10) === 0 ? "0 %" : `${v > 0 ? "+" : "−"}${n} %`;   // "−0,0 %" se muestra como "0 %"
};

// Botones de cadenas, el mismo control en todos los gráficos: tocar una cadena la oculta o la muestra, y el gráfico
// ajusta su escala a las que quedan. `ids` va en el mismo orden que las líneas del gráfico `grafico`.
function botonesCadenas(contenedor, ids, ocultas, grafico) {
  const chart = () => estado.graficos[grafico];
  const botones = ids.map((id, i) => {
    const b = elemento("button", "chip-cadena");
    b.type = "button";
    b.setAttribute("aria-pressed", String(!ocultas.has(id)));
    const punto = elemento("span", "punto-cadena");
    punto.style.setProperty("--color", color(id));
    b.append(punto, document.createTextNode(cadena(id)));
    b.addEventListener("click", () => {
      if (ocultas.has(id)) ocultas.delete(id); else ocultas.add(id);
      b.setAttribute("aria-pressed", String(!ocultas.has(id)));
      chart()?.setDatasetVisibility(i, !ocultas.has(id));
      chart()?.update();
    });
    return b;
  });
  const todas = elemento("button", "chip-cadena chip-todas", "Mostrar todas");
  todas.type = "button";
  todas.addEventListener("click", () => {
    ocultas.clear();
    botones.forEach(b => b.setAttribute("aria-pressed", "true"));
    ids.forEach((_, i) => chart()?.setDatasetVisibility(i, true));
    chart()?.update();
  });
  contenedor.replaceChildren(...botones, todas);
}

async function mostrarEvolucion() {
  const codigo = provincia(), seccion = $("canasta-evolucion");
  if (!(codigo in indiceDatos)) {
    try { indiceDatos[codigo] = await json(`datos/indice/${codigo}.json`); }
    catch { indiceDatos[codigo] = null; }
  }
  if (codigo !== provincia()) return;   // eligió otra provincia mientras cargaba
  const datos = indiceDatos[codigo];
  const series = Object.entries(datos?.s ?? {}).map(([id, puntos]) => ({ id, puntos })).filter(s => s.puntos.length >= 2)
    .sort((a, b) => Number(a.id) - Number(b.id));
  const primero = series.length ? Math.min(...series.map(s => s.puntos[0][0])) : 0;
  const ultimo = series.length ? Math.max(...series.map(s => s.puntos.at(-1)[0])) : 0;
  const dias = ultimo - primero;
  seccion.hidden = !series.length || dias < 7;
  if (seccion.hidden) { estado.graficos.evolucion?.destroy(); return; }
  const nombre = PROVINCIAS[codigo];
  // El índice parte de 100 el primer día; en el gráfico se muestra como cambio acumulado: 0 % el primer día
  $("evolucion-resumen").textContent = `Cuánto subió o bajó el precio de cada cadena desde el ${fecha(primero)}.`;
  $("evolucion-nota").textContent =
    `Cada día se compara el precio de lista de cada cadena en ${nombre} con el del día anterior, producto por producto, y los cambios se acumulan. ` +
    "Todos los productos con código de barras pesan lo mismo, sea caro o barato. No dice cuál cadena es más barata, sino cuánto cambió el precio de cada una. " +
    "La compra de $ 100.000 es un ejemplo: el mismo porcentaje dicho en pesos. Sin promociones.";

  // Cambio acumulado de cada cadena en su último día con datos, de mayor a menor, y la mediana entre cadenas
  const finales = series.map(s => ({ id: s.id, dia: s.puntos.at(-1)[0], cambio: s.puntos.at(-1)[1] - 100 }))
    .sort((a, b) => b.cambio - a.cambio);
  const valores = finales.map(f => f.cambio).sort((a, b) => a - b), m = valores.length;
  const mediana = m % 2 ? valores[(m - 1) / 2] : (valores[m / 2 - 1] + valores[m / 2]) / 2;
  const compra = v => "$\u00a0" + (Math.round(100000 * (1 + v / 100) / 100) * 100).toLocaleString("es-AR");
  $("evolucion-cifra-valor").textContent = cambioTexto(mediana, 1);
  $("evolucion-cifra-texto").textContent = m === 1
    ? `cambió el precio de la única cadena con datos en ${nombre} entre el ${fecha(primero)} y el ${fecha(ultimo)}.`
    : `es la mediana de las ${m} cadenas de ${nombre} entre el ${fecha(primero)} y el ${fecha(ultimo)}.`;
  $("evolucion-compra").replaceChildren(
    document.createTextNode(`Una compra que el ${fecha(primero)} costaba $\u00a0100.000, el ${fecha(ultimo)} cuesta unos `),
    elemento("strong", null, compra(mediana)), document.createTextNode("."));
  $("evolucion-col-cambio").textContent = `Desde el ${fecha(primero)}`;
  $("evolucion-col-compra").textContent = "Compra de $\u00a0100.000";
  $("evolucion-lista").replaceChildren(...finales.map(f => {
    const tr = document.createElement("tr"), nombreCadena = document.createElement("td");
    const punto = elemento("span", "punto-cadena-fijo");
    punto.style.setProperty("--color", color(f.id));
    nombreCadena.append(punto, document.createTextNode(cadena(f.id)));
    if (f.dia < ultimo) nombreCadena.append(elemento("span", "nota-fila", ` datos hasta el ${fecha(f.dia)}`));
    tr.append(nombreCadena, celda(cambioTexto(f.cambio, 1), "num"), celda(compra(f.cambio), "num"));
    return tr;
  }));

  // Panel fijo debajo del gráfico con los valores del día señalado (en el celular un cartel flotante tapa las líneas)
  const panelDia = $("evolucion-dia");
  const panelVacio = () => panelDia.replaceChildren(elemento("span", "nota", "Tocá el gráfico para ver los valores de un día."));
  panelVacio();
  let diaPanel = null;
  const mostrarPanel = ({ tooltip }) => {
    if (!tooltip.opacity || !tooltip.dataPoints?.length) { diaPanel = null; panelVacio(); return; }
    const dia = tooltip.dataPoints[0].parsed.x;
    if (dia === diaPanel && panelDia.dataset.visibles === String(tooltip.dataPoints.length)) return;
    diaPanel = dia;
    panelDia.dataset.visibles = String(tooltip.dataPoints.length);
    const lista = elemento("div", "panel-dia-valores");
    for (const p of [...tooltip.dataPoints].sort((a, b) => b.parsed.y - a.parsed.y)) {
      const item = elemento("span", "panel-dia-item"), punto = elemento("span", "punto-cadena-fijo");
      punto.style.setProperty("--color", p.dataset.borderColor);
      item.append(punto, document.createTextNode(`${p.dataset.label} ${cambioTexto(p.parsed.y, 1)}`));
      lista.append(item);
    }
    panelDia.replaceChildren(elemento("strong", "panel-dia-fecha", fecha(dia)), lista);
  };


  botonesCadenas($("evolucion-cadenas"), series.map(s => s.id), cadenasOcultas, "evolucion");

  if (typeof Chart === "undefined") return;
  estado.graficos.evolucion?.destroy();
  const estilo = getComputedStyle(document.documentElement);
  const texto = estilo.getPropertyValue("--suave").trim(), grilla = estilo.getPropertyValue("--linea").trim();
  estado.graficos.evolucion = new Chart($("grafico-evolucion"), {
    type: "line",
    data: { datasets: series.map(s => ({
      label: cadena(s.id), borderColor: color(s.id), backgroundColor: color(s.id), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4,
      hidden: cadenasOcultas.has(s.id), data: s.puntos.map(([x, y]) => ({ x, y: y - 100 })) })) },
    options: {
      maintainAspectRatio: false, animation: false, parsing: false,
      interaction: { mode: "index", intersect: false },
      layout: { padding: { right: 48 } },   // lugar para el valor de hoy al final de cada línea
      scales: {
        x: { type: "linear", min: primero, max: ultimo, ticks: { color: texto, stepSize: 1, callback: v => fecha(v) }, grid: { display: false } },
        y: { title: { display: true, text: `Cambio del precio desde el ${fecha(primero)}`, color: texto },
             ticks: { color: texto, callback: v => cambioTexto(v, 0) }, grid: { color: grilla } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false, external: mostrarPanel },
      },
    },
    plugins: [valorFinal],
  });
}

// Escribe el cambio acumulado al final de cada línea visible, separando los que quedarían encimados
const valorFinal = {
  id: "valorFinal",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea } = chart, items = [];
    chart.data.datasets.forEach((d, i) => {
      if (!chart.isDatasetVisible(i)) return;
      const punto = chart.getDatasetMeta(i).data.at(-1);
      if (punto) items.push({ y: punto.y, texto: cambioTexto(d.data.at(-1).y, 1), color: d.borderColor });
    });
    items.sort((a, b) => a.y - b.y);
    for (let k = 1; k < items.length; k++) items[k].y = Math.max(items[k].y, items[k - 1].y + 13);
    ctx.save();
    ctx.font = "600 11px 'Source Sans 3', system-ui, sans-serif";
    ctx.textBaseline = "middle";
    for (const it of items) { ctx.fillStyle = it.color; ctx.fillText(it.texto, chartArea.right + 6, it.y); }
    ctx.restore();
  },
};

// --- precio por kilo --------------------------------------------------------------------------
// datos/kilo/<provincia>.json: productos [[nombre, grupo]] y filas [posición del producto, cadena,
// productos, precio por kilo, tipo (1 baja fuerte, 2 promoción), precio anterior o de promoción].
// Se baja solo cuando se muestra la provincia. Solo entran los productos con al menos dos cadenas, y
// se muestra una sección por vez (se elige en el desplegable).
const kiloDatos = {};   // provincia -> contenido del archivo (null si no hay)
const ORDEN_KILO = ["Carne vacuna", "Cerdo", "Pollo", "Pescado", "Fiambres y quesos", "Frutas", "Verduras"];
let kiloGrupo = null;   // sección elegida; se mantiene al cambiar de provincia
const kiloPesos = v => "$ " + v.toLocaleString("es-AR", { maximumFractionDigits: 0 });

function kiloCelda(etiqueta, texto, clase) {
  const e = document.createElement(etiqueta);
  e.textContent = texto;
  if (clase) e.className = clase;
  return e;
}

async function mostrarKilo() {
  const codigo = provincia(), seccion = $("kilo");
  if (!(codigo in kiloDatos)) {
    try { kiloDatos[codigo] = await json(`datos/kilo/${codigo}.json`); }
    catch { kiloDatos[codigo] = null; }
  }
  if (codigo !== provincia()) return;   // eligió otra provincia mientras cargaba
  const datos = kiloDatos[codigo];
  const porProducto = new Map();
  for (const f of datos?.filas ?? []) {
    if (!porProducto.has(f[0])) porProducto.set(f[0], new Map());
    porProducto.get(f[0]).set(String(f[1]), f);
  }
  // producto -> sus precios por cadena, solo los que tienen al menos dos cadenas, agrupados por sección
  const porGrupo = new Map();
  for (const [i, celdas] of porProducto) {
    if (celdas.size < 2) continue;
    const [nombre, grupo] = datos.productos[i];
    if (!porGrupo.has(grupo)) porGrupo.set(grupo, []);
    porGrupo.get(grupo).push({ nombre, celdas });
  }
  if (!porGrupo.size) { seccion.hidden = true; return; }
  const posicion = g => (ORDEN_KILO.indexOf(g) + 1) || 99;
  const grupos = [...porGrupo.keys()].sort((a, b) => posicion(a) - posicion(b) || a.localeCompare(b, "es"));
  if (!grupos.includes(kiloGrupo)) kiloGrupo = grupos[0];

  const total = [...porGrupo.values()].reduce((s, l) => s + l.length, 0);
  $("kilo-bajada").textContent = `En ${PROVINCIAS[codigo]}: ${total} productos que se venden al peso en al menos dos cadenas, con el último precio informado. No tienen ranking como el resto de los productos porque no comparten código de barras entre cadenas, así que se comparan por su precio por kilo.`;
  const selector = $("kilo-grupo");
  selector.replaceChildren(...grupos.map(g => {
    const o = kiloCelda("option", `${g} (${porGrupo.get(g).length})`);
    o.value = g;
    return o;
  }));
  selector.value = kiloGrupo;
  selector.onchange = () => { kiloGrupo = selector.value; dibujarKilo(kiloGrupo, porGrupo.get(kiloGrupo)); };
  dibujarKilo(kiloGrupo, porGrupo.get(kiloGrupo));
  seccion.hidden = false;
}

function dibujarKilo(grupo, productos) {
  // columnas: las cadenas que tienen algún producto de la sección, en el orden de siempre
  const ids = ordenCadenas().map(String).filter(id => productos.some(p => p.celdas.has(id)));
  const masBaratas = new Map(ids.map(id => [id, 0]));
  const tabla = $("kilo-tabla");
  tabla.replaceChildren();
  const cabecera = tabla.createTHead().insertRow();
  cabecera.append(kiloCelda("th", "Producto"), ...ids.map(id => kiloCelda("th", cadena(id), "num")));
  for (const th of cabecera.children) th.scope = "col";

  const cuerpo = tabla.createTBody();
  for (const { nombre, celdas } of productos) {
    const minimo = Math.min(...[...celdas.values()].map(f => f[3]));
    const fila = cuerpo.insertRow();
    const cabeza = kiloCelda("th", nombre, "kilo-producto");
    cabeza.scope = "row";
    fila.append(cabeza);
    for (const id of ids) {
      const f = celdas.get(id);
      const td = kiloCelda("td", f ? kiloPesos(f[3]) : "—", "num");
      if (!f) td.classList.add("uno");
      else {
        td.append(kiloCelda("span", "/kg", "kilo-unidad"));
        if (f[3] === minimo) { td.classList.add("barato"); masBaratas.set(id, masBaratas.get(id) + 1); }
        if (f[2] === 1) td.classList.add("uno");
        td.title = `${f[2]} ${f[2] === 1 ? "producto" : "productos"}`;
        if (f[4] === 1) td.append(kiloCelda("span", `↓ bajó ${Math.round((1 - f[3] / f[5]) * 100)} %`, "kilo-oferta"));
        if (f[4] === 2) td.append(kiloCelda("span", "promoción", "kilo-oferta"));
      }
      fila.append(td);
    }
  }
  // resumen: qué cadena tiene más veces el precio más bajo (un empate cuenta para las dos)
  const maximo = Math.max(...masBaratas.values());
  const lideres = ids.filter(id => masBaratas.get(id) === maximo).map(cadena);
  $("kilo-resumen").textContent = lideres.length === 1
    ? `${lideres[0]} tiene el precio más bajo en ${maximo} de ${productos.length} productos.`
    : `${listar(lideres)} tienen el precio más bajo en ${maximo} de ${productos.length} productos cada una.`;
  $("kilo-resumen").textContent += grupo === "Fiambres y quesos"
    ? " Precios por kilo: 100 g cuestan la décima parte (por ejemplo, $\u00a018.000/kg son $\u00a01.800 los 100\u00a0g)."
    : " Todos los precios son por kilo.";
}

// Precio aislado: el de una cadena que está solo, lejos de todos los demás. Con 3 cadenas o más, se
// compara con el precio MÁS CERCANO de otra cadena: si hasta ese está a más de AISLADO veces (para
// arriba o para abajo), ninguna otra cadena tiene un precio parecido. Ejemplos del 21/10 en Buenos
// Aires: bizcochos a $ 300 en 2 sucursales de Cencosud, contra $ 1.499 el más cercano (5 veces: un
// probable remate); jabón a $ 590 en La Anónima contra $ 939 (1,59 veces). No se marcan los pañales a
// $ 34.300 en La Anónima, con Changomas a $ 30.369 (1,13 veces): es una cadena más cara, no un error.
// Contra la mediana no funcionaba: con tres cadenas a $ 19.000, la mediana bajaba y marcaba ese pañal.
// Los aislados se muestran marcados pero no cuentan para la más barata, la más cara ni la diferencia;
// el dato sigue igual en el archivo y en la ficha del producto.
const AISLADO = 1.5;
const AVISO_AISLADO = "Ninguna otra cadena tiene un precio parecido (el más cercano está a más de 1,5 veces): puede ser un remate en pocas sucursales o un error de la cadena. No cuenta para la más barata ni para la diferencia.";
function sinAislados(precios) {
  if (precios.size < 3) return precios;
  return new Map([...precios].filter(([id, p]) => {
    const cercano = Math.min(...[...precios].filter(([otra]) => otra !== id).map(([, q]) => Math.max(p / q, q / p)));
    return cercano <= AISLADO;
  }));
}

// --- ranking por grupo ------------------------------------------------------------------------
// canasta.json, "grupos" (fct_canasta_provincia_grupo): el mismo índice que el ranking de la provincia,
// pero por grupo de producto y solo del último día. Solo vienen los grupos con 30 o más productos por
// cadena. Con tan pocos productos el orden entre cadenas parecidas cambia de un día a otro, por eso el
// empate es de GRUPO_EMPATE (2 puntos) y no de EMPATE (0,5), que se mide con unos 590 productos.
const NOMBRE_GRUPO = { "Lácteos y refrigerados": "lácteos", "Panadería y rotisería": "panadería" };

function rankingsGrupo(codigo) {
  const porGrupo = new Map();
  for (const [dia, prov, grupo, id, productos, indice, diferencia, puesto] of estado.canasta.grupos ?? []) {
    if (prov !== codigo) continue;
    if (!porGrupo.has(grupo)) porGrupo.set(grupo, { grupo, dia, productos, filas: [] });
    porGrupo.get(grupo).filas.push({ id, indice, diferencia, puesto });
  }
  for (const g of porGrupo.values()) g.filas.sort((a, b) => a.diferencia - b.diferencia);
  return [...porGrupo.values()].sort((a, b) => b.productos - a.productos || a.grupo.localeCompare(b.grupo, "es"));
}

function mostrarGrupos() {
  const grupos = rankingsGrupo(provincia());
  $("grupos").hidden = !grupos.length;
  if (!grupos.length) return;
  const barata = f => f.diferencia < GRUPO_EMPATE;
  const tope = Math.max(...grupos.map(g => g.filas.at(-1).diferencia), GRUPO_EMPATE);  // misma escala en todas las tarjetas

  // La bajada: quién gana en qué grupo, y dónde hay empate
  const nombre = g => NOMBRE_GRUPO[g.grupo] ?? g.grupo.toLowerCase();
  const unica = new Map(), empates = [];
  for (const g of grupos) {
    const baratas = g.filas.filter(barata);
    if (baratas.length === 1) unica.set(baratas[0].id, [...(unica.get(baratas[0].id) ?? []), nombre(g)]);
    else empates.push(nombre(g));
  }
  const conjuntos = grupos.map(g => new Set(g.filas.filter(barata).map(f => f.id)));
  const encabezaTodo = [...conjuntos[0]].some(id => conjuntos.every(s => s.has(id)));
  $("grupos-bajada").textContent = [
    grupos.length > 1 && !encabezaTodo ? "Ninguna cadena es la más barata en todo." : "",
    ...[...unica].map(([id, nombres]) => `${cadena(id)} es la más barata en ${listar(nombres)}.`),
    empates.length ? `En ${listar(empates)} hay cadenas prácticamente empatadas.` : "",
  ].filter(Boolean).join(" ");

  $("grupos-lista").replaceChildren(...grupos.map(g => {
    const baratas = g.filas.filter(barata), resto = g.filas.filter(f => !barata(f));
    const todas = !resto.length;
    const tarjeta = elemento("article", "tarjeta-grupo");
    const cabecera = elemento("header", "grupo-cabecera");
    cabecera.append(elemento("h3", null, g.grupo),
      elemento("span", "nota", `${plural(g.productos, "producto comparado", "productos comparados")} en cada cadena`));
    const mejores = elemento("div", "grupo-baratas");
    mejores.append(
      elemento("span", "grupo-etiqueta", todas ? "Prácticamente empatadas" : baratas.length > 1 ? "Las más baratas" : "La más barata"),
      elemento("span", "grupo-nombres", baratas.map(f => cadena(f.id)).join(" · ")),
      ...(baratas.length > 1 ? [elemento("span", "nota", todas ? `Menos de ${GRUPO_EMPATE * 100} % de diferencia entre todas`
        : `Prácticamente iguales: menos de ${GRUPO_EMPATE * 100} % de diferencia`)] : []));
    // La lista tiene todas las cadenas, con su diferencia contra la más barata; las empatadas, en azul
    const lista = elemento("ol", "grupo-lista");
    lista.setAttribute("aria-label", "Todas las cadenas, de menos a más cara");
    lista.append(...g.filas.map((f, i) => {
      const buena = barata(f), cara = !buena && i === g.filas.length - 1 && f.diferencia >= GRUPO_CARA;
      const clase = buena ? " barata" : cara ? " cara" : "";
      const fila = elemento("li", "fila-grupo");
      const pista = elemento("span", "pista");
      const barra = elemento("span", "barra" + clase);
      barra.style.width = `${f.diferencia / tope * 100}%`;
      pista.append(barra);
      fila.append(elemento("span", null, corto(f.id)), pista,
        elemento("span", "grupo-valor" + clase, f.diferencia === 0 ? porcentaje(0) : `+${porcentaje(f.diferencia * 100)}`));
      return fila;
    }));
    const ver = elemento("a", "grupo-ver", `Ver los ${plural(g.productos, "producto", "productos")} que se comparan →`);
    ver.href = "#canasta";
    ver.addEventListener("click", evento => {
      evento.preventDefault();
      verProductosGrupo(g.grupo);
    });
    tarjeta.append(cabecera, mejores, lista, ver);
    return tarjeta;
  }));
}

// Del link de una tarjeta: abre la vista de la canasta con la lista filtrada por ese grupo y baja hasta la lista
async function verProductosGrupo(grupo) {
  estado.grupoComparacion = grupo;
  estado.pagina = 0;
  irVista("canasta");
  await new Promise(r => setTimeout(r, 0));   // después de que la vista se muestre y suba al principio
  mostrarComparacion();
  $("comparacion-titulo").scrollIntoView({ block: "start" });
}

// --- buscador ---------------------------------------------------------------------------------
async function cargarIndice() {
  const filas = await json("datos/indice.json");
  // El último dato de cada fila es el rubro (posición en meta.rubros, -1 = sin clasificar); de ahí sale el grupo
  estado.indice = filas.map(([clave, nombre, marca, presentacion, cadenas, archivo, rubro]) =>
    ({ clave, nombre, marca, presentacion, cadenas, archivo, grupo: estado.meta.rubros?.[rubro]?.[1] ?? null,
       texto: normalizar(`${nombre} ${marca ?? ""} ${clave}`) }));
  estado.porClave = new Map(estado.indice.map(p => [p.clave, p]));
  $("texto-resultados").disabled = false;
  mostrarComparacion();
  buscar();
  await mostrarRuta();  // un link directo a un producto necesita el índice
}

// --- vistas -----------------------------------------------------------------------------------
// Una sola página con cuatro vistas: inicio, buscar, producto y canasta. La vista sale del # de la
// dirección: así funcionan el botón Atrás del navegador y los links directos a un producto
// (#producto=7790742625304).
function ruta() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (h.startsWith("producto=")) return { vista: "producto", clave: h.slice("producto=".length) };
  if (h === "buscar" || h === "canasta") return { vista: h };
  if (h === "como") return { vista: estado.vista ?? "inicio" };  // el pie: se queda la vista actual
  return { vista: "inicio" };
}

function aplicarVista() {
  const { vista } = ruta();
  estado.vista = vista;
  $("portada").hidden = vista !== "inicio";
  $("resultados").hidden = vista !== "buscar";
  $("producto").hidden = vista !== "producto";
  $("canasta").hidden = vista !== "canasta";
  document.querySelectorAll(".menu a").forEach(a => {
    if (a.getAttribute("href") === "#" + vista) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}

async function mostrarRuta() {
  if (location.hash === "#inicio") {  // el logo y "Hoy": volver al inicio sin la búsqueda anterior
    $("texto-resultados").value = "";
    estado.marcas.clear();
    estado.origen = null;
    estado.producto = null;
    buscar();
  }
  const anterior = estado.vista;
  const r = ruta();
  aplicarVista();
  if (r.vista === "buscar") buscar();
  if (r.vista === "producto" && estado.indice) {
    const p = estado.indice.find(x => x.clave === r.clave);
    if (p) { estado.producto = p; await mostrarProducto(p); }
    else {
      $("producto-nombre").textContent = "No encontramos ese producto";
      $("producto-detalle").textContent = `Código ${r.clave}. Puede que ya no esté en el catálogo.`;
    }
  }
  if (location.hash === "#como") return;  // el navegador ya bajó al pie
  if (anterior === "producto" && estado.origen?.vista === r.vista) {
    window.scrollTo(0, estado.origen.y);  // volver a la misma altura de la lista
  } else window.scrollTo(0, 0);
}

function irVista(vista) {
  if (location.hash === "#" + vista) mostrarRuta();
  else location.hash = vista;
}

function buscar() {
  if (!estado.indice) return;
  const consulta = $("texto-resultados").value.trim();
  const texto = normalizar(consulta);
  const nombreProvincia = PROVINCIAS[provincia()];
  if (texto.length < 3) {
    $("resultados-titulo").textContent = "Buscá un producto";
    $("leyenda-resultados").hidden = true;
    $("tabla").replaceChildren();
    $("resultados-nota").textContent = `Escribí al menos 3 letras: un producto, una marca o un código de barras. Se muestran los precios de hoy en ${nombreProvincia}.`;
    mostrarMarcas([]);
    return;
  }
  const palabras = texto.split(/\s+/);
  const comparables = $("comparables").getAttribute("aria-pressed") === "true";
  const conCambios = $("con-cambios").getAttribute("aria-pressed") === "true";

  // Primero lo que coincide con el texto y tiene precio hoy en la provincia; las marcas salen de ahí
  const porTexto = estado.indice.filter(p => palabras.every(w => p.texto.includes(w)));
  const conPrecio = porTexto.map(p => ({ p, hoy: filaHoy(p.clave) })).filter(r => r.hoy);
  const enOtras = porTexto.length - conPrecio.length;
  const coinciden = conPrecio.filter(r => (!comparables || r.hoy.precios.size >= 2) && (!conCambios || r.hoy.cambios.length));
  mostrarMarcas(coinciden.map(r => r.p));
  const encontrados = coinciden.filter(r => !estado.marcas.size || estado.marcas.has(r.p.marca ?? "Sin marca"));

  for (const r of encontrados) {
    r.validos = sinAislados(r.hoy.precios);
    const valores = [...r.validos.values()];
    r.minimo = Math.min(...valores);
    r.diferencia = Math.max(...valores) / r.minimo - 1;
  }
  const orden = $("orden").value;
  const porNombre = (a, b) => a.p.nombre.localeCompare(b.p.nombre, "es");
  encontrados.sort((a, b) => {
    if (orden === "precio") return a.minimo - b.minimo || porNombre(a, b);
    if (orden === "diferencia") return b.diferencia - a.diferencia || porNombre(a, b);
    if (orden === "nombre") return porNombre(a, b);
    return b.hoy.precios.size - a.hoy.precios.size || b.p.cadenas - a.p.cadenas || porNombre(a, b);
  });

  $("resultados-titulo").textContent = `«${consulta}» en ${nombreProvincia}`;
  $("leyenda-resultados").hidden = !encontrados.length;
  const otras = enOtras ? ` Otros ${plural(enOtras, "producto se vende", "productos se venden")} solo en otras provincias.` : "";
  $("resultados-nota").textContent = (!encontrados.length
    ? `No hay productos con esas palabras y esos filtros en ${nombreProvincia}.${comparables ? " Probá sacar el filtro Comparables." : ""}`
    : encontrados.length > MAX_RESULTADOS
      ? `${encontrados.length.toLocaleString("es-AR")} productos: se muestran los primeros ${MAX_RESULTADOS}. Agregá una palabra para afinar.`
      : `${plural(encontrados.length, "producto", "productos")}.`) + otras
    + (encontrados.length ? " Diferencia: cuánto más cuesta en la cadena más cara que en la más barata." : "");

  const mostrados = encontrados.slice(0, MAX_RESULTADOS);
  // Columnas: las cadenas de la provincia (y cualquier otra que aparezca), por nombre
  const ids = new Set(cadenasDeProvincia(provincia()));
  for (const r of mostrados) for (const id of r.hoy.precios.keys()) ids.add(id);
  const columnas = [...ids].sort((a, b) => corto(a).localeCompare(corto(b), "es"));
  const tabla = $("tabla");
  tabla.style.setProperty("--cadenas", columnas.length);
  tabla.replaceChildren(...(mostrados.length ? [encabezadoTabla(columnas), ...mostrados.map(r => filaResultado(r, columnas, palabras))] : []));
}

function mostrarMarcas(productos) {
  const cuenta = new Map();
  for (const p of productos) { const m = p.marca ?? "Sin marca"; cuenta.set(m, (cuenta.get(m) ?? 0) + 1); }
  const principales = [...cuenta.entries()].sort((a, b) => b[1] - a[1]).slice(0, MAX_MARCAS);
  for (const m of estado.marcas) if (!cuenta.has(m)) estado.marcas.delete(m);
  $("marcas-cuenta").textContent = estado.marcas.size ? `(${estado.marcas.size})` : "▾";
  $("marcas").replaceChildren(...(principales.length ? principales.map(([marca, n]) => {
    const etiqueta = elemento("label", "opcion");
    const caja = document.createElement("input");
    caja.type = "checkbox"; caja.checked = estado.marcas.has(marca);
    caja.addEventListener("change", () => { caja.checked ? estado.marcas.add(marca) : estado.marcas.delete(marca); buscar(); });
    etiqueta.append(caja, elemento("span", null, marca === "Sin marca" ? marca : marcaVisible(marca)), elemento("span", "cuenta", n.toLocaleString("es-AR")));
    return etiqueta;
  }) : [elemento("p", "nota", "Sin resultados")]));
}

// El nombre con las palabras buscadas en negrita (sin construir HTML a mano)
function resaltar(texto, palabras) {
  const normal = normalizar(texto);
  const fragmento = document.createDocumentFragment();
  if (normal.length !== texto.length) { fragmento.append(texto); return fragmento; }
  const marcado = new Array(texto.length).fill(false);
  for (const w of palabras) {
    for (let i = normal.indexOf(w); i >= 0; i = normal.indexOf(w, i + w.length)) marcado.fill(true, i, i + w.length);
  }
  for (let i = 0; i < texto.length;) {
    let j = i;
    while (j < texto.length && marcado[j] === marcado[i]) j++;
    fragmento.append(marcado[i] ? elemento("strong", null, texto.slice(i, j)) : texto.slice(i, j));
    i = j;
  }
  return fragmento;
}

function encabezadoTabla(columnas) {
  const fila = elemento("div", "fila-tabla encabezado-tabla");
  fila.setAttribute("role", "row");
  const titulos = ["Producto y cómo cambió", ...columnas.map(corto), "Diferencia"];
  fila.append(...titulos.map(t => { const e = elemento("span", null, t); e.setAttribute("role", "columnheader"); return e; }));
  return fila;
}

function filaResultado({ p, hoy, minimo, validos }, columnas, palabras) {
  const fila = elemento("div", "fila-tabla fila-resultado");
  fila.setAttribute("role", "row");
  // La más barata, la más cara y la diferencia se calculan sin los precios aislados (sinAislados)
  const valores = [...validos.values()];
  const maximo = Math.max(...valores);
  const compara = validos.size > 1 && maximo > minimo;

  const info = elemento("div", "celda-producto");
  info.setAttribute("role", "cell");
  const enlace = elemento("a", "nombre");
  enlace.href = "#producto=" + encodeURIComponent(p.clave);
  enlace.append(resaltar(nombreVisible(p), palabras));
  // Para volver a la misma vista y a la misma altura de la lista (búsqueda o canasta)
  enlace.addEventListener("click", () => { estado.origen = { vista: estado.vista, y: window.scrollY }; });
  const detalle = [p.marca && marcaVisible(p.marca), p.presentacion, plural(hoy.precios.size, "cadena", "cadenas")].filter(Boolean).join(" · ");
  const evolucion = elemento("div", "evolucion");
  const cambio = textoCambios(hoy);
  evolucion.append(miniGrafico(hoy), elemento("span", cambio.hay ? "cambio" : "cambio sin-cambios", cambio.texto));
  info.append(enlace, elemento("span", "detalle", detalle), evolucion);
  // El aviso también en texto: en el celular no hay mouse para ver el title de la celda
  const aislados = [...hoy.precios.keys()].filter(id => !validos.has(id));
  if (aislados.length) {
    info.append(elemento("span", "nota-aislado",
      `${listar(aislados.map(corto))}: precio muy distinto al resto (¿remate en pocas sucursales o error?), no cuenta para la comparación.`));
  }
  fila.append(info);

  // En el celular las celdas se ordenan de la más barata a la más cara (--orden)
  const puesto = new Map([...hoy.precios.entries()].sort((a, b) => a[1] - b[1]).map(([id], i) => [id, i]));
  for (const id of columnas) {
    const precio = hoy.precios.get(id);
    const aislado = precio && !validos.has(id);
    const clase = !precio ? " sin" : aislado ? " aislado" : compara && precio === minimo ? " barata" : compara && precio === maximo ? " cara" : "";
    const e = elemento("span", "precio" + clase, precio ? pesosCelda(precio) : "—");
    e.setAttribute("role", "cell");
    e.dataset.cadena = corto(id);
    e.style.setProperty("--orden", aislado ? 98 : puesto.get(id) ?? 99);  // los aislados, al final
    if (!precio) e.setAttribute("aria-label", `${cadena(id)}: no lo vende`);
    if (aislado) {
      e.title = AVISO_AISLADO;
      e.setAttribute("aria-label", `${cadena(id)}: ${pesosCelda(precio)}. ${AVISO_AISLADO}`);
    }
    fila.append(e);
  }
  const diferencia = elemento("span", "diferencia", compara ? "+" + porcentaje((maximo / minimo - 1) * 100) : "—");
  diferencia.setAttribute("role", "cell");
  fila.append(diferencia);
  return fila;
}

// "Qué cambió" en los días del gráfico chico, en una o dos frases
function textoCambios(hoy) {
  const n = diasGrafico();
  const ids = [...new Set(hoy.cambios.map(c => c.id))];
  if (!ids.length) return { hay: false, texto: `Sin cambios en los últimos ${n} días.` };
  const resumen = ids.map(id => {
    const serie = serieCadena(hoy, id);
    const propios = hoy.cambios.filter(c => c.id === id);
    return {
      id, veces: propios.length, neto: serie.at(-1) / serie[0] - 1,
      dia: estado.meta.dia_dato - Math.min(...propios.map(c => c.hace)),
    };
  });
  const frase = r => {
    const sentido = r.neto > 0 ? "subió" : "bajó", cuanto = porcentaje(Math.abs(r.neto) * 100);
    if (r.veces === 1) return `${corto(r.id)} ${sentido} ${cuanto} el ${fecha(r.dia)}.`;
    if (r.neto === 0) return `${corto(r.id)} cambió ${r.veces} veces y volvió al mismo precio.`;
    return `${corto(r.id)} cambió ${r.veces} veces: ${sentido} ${cuanto} en total.`;
  };
  const resto = hoy.precios.size - ids.length;
  if (ids.length === 1) {
    return { hay: true, texto: frase(resumen[0]) + (resto === 1 ? " La otra cadena, sin cambios." : resto > 1 ? ` Las otras ${resto} cadenas, sin cambios.` : "") };
  }
  if (ids.length === 2) return { hay: true, texto: resumen.map(frase).join(" ") };
  const mayor = resumen.reduce((a, b) => (Math.abs(b.neto) > Math.abs(a.neto) ? b : a));
  return {
    hay: true,
    texto: `Cambiaron ${ids.length} de ${hoy.precios.size} cadenas.` + (mayor.neto
      ? ` La mayor ${mayor.neto > 0 ? "suba" : "baja"}: ${corto(mayor.id)}, ${mayor.neto > 0 ? "+" : "−"}${porcentaje(Math.abs(mayor.neto) * 100)}.` : ""),
  };
}

// Gráfico chico: la línea de la cadena más barata hoy (azul), la de la más cara hoy (naranja) y,
// en gris punteado, las otras cadenas que cambiaron el precio (si no, el texto de al lado habla de
// un cambio que el gráfico no muestra)
function miniGrafico(hoy) {
  const ordenadas = [...sinAislados(hoy.precios).entries()].sort((a, b) => a[1] - b[1]);
  const barata = ordenadas[0][0];
  const cara = ordenadas.length > 1 && ordenadas.at(-1)[1] > ordenadas[0][1] ? ordenadas.at(-1)[0] : null;
  const otras = [...new Set(hoy.cambios.map(c => c.id))].filter(id => id !== barata && id !== cara);
  const series = [...otras.map(id => ({ id, clase: "otra" })), cara && { id: cara, clase: "cara" }, { id: barata, clase: "barata" }]
    .filter(Boolean).map(s => ({ ...s, valores: serieCadena(hoy, s.id) }));
  const todos = series.flatMap(s => s.valores);
  let min = Math.min(...todos), max = Math.max(...todos);
  if (min === max) { min -= 1; max += 1; }
  const n = diasGrafico(), ancho = 150, alto = 44;
  const x = k => 2 + k / (n - 1) * (ancho - 4);
  const y = v => alto - 4 - (v - min) / (max - min) * (alto - 8);
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", `0 0 ${ancho} ${alto}`);
  svg.setAttribute("width", ancho);
  svg.setAttribute("height", alto);
  svg.setAttribute("class", "mini");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Precio de los últimos ${n} días: ${corto(barata)}, la más barata hoy`
    + (cara ? `; ${corto(cara)}, la más cara hoy` : "") + (otras.length ? `; ${listar(otras.map(corto))}, que cambiaron` : ""));
  for (const s of series) {
    // En escalones: plano hasta el día del cambio, como el gráfico grande
    const puntos = [];
    s.valores.forEach((v, k) => {
      if (k > 0 && v !== s.valores[k - 1]) puntos.push(`${x(k).toFixed(1)},${y(s.valores[k - 1]).toFixed(1)}`);
      puntos.push(`${x(k).toFixed(1)},${y(v).toFixed(1)}`);
    });
    const linea = document.createElementNS(SVG, "polyline");
    linea.setAttribute("points", puntos.join(" "));
    linea.setAttribute("class", s.clase);
    svg.append(linea);
  }
  return svg;
}

// --- ficha del producto -----------------------------------------------------------------------
// Qué pasó con el precio de una cadena, en palabras: el último cambio, o hace cuánto está igual.
// f.puntos = [[día, precio]] con un punto por cada cambio (el primero es el primer precio visto).
function textoCambioFila(f, hoy) {
  if (!f.disponible) return `No disponible desde el ${fecha(f.ultimo)}`;
  const cambios = f.puntos.length - 1;
  if (!cambios) {
    const dias = hoy - f.puntos[0][0];
    return dias > 0 ? `Sin cambios en ${plural(dias, "día", "días")}` : "Primer día con este producto";
  }
  const variacion = (f.precio / f.puntos.at(-2)[1] - 1) * 100;
  return `${variacion > 0 ? "Subió" : "Bajó"} ${porcentaje(Math.abs(variacion))} el ${fecha(f.desde)}`
    + (cambios > 1 ? ` · ${plural(cambios, "cambio", "cambios")} en total` : "");
}

async function mostrarProducto(p) {
  if (!estado.historia.has(p.archivo)) {
    estado.historia.set(p.archivo, await json(`datos/historia/${String(p.archivo).padStart(3, "0")}.json`));
  }
  const porProvincia = estado.historia.get(p.archivo)[p.clave] ?? {};
  $("producto").hidden = false;
  const origen = estado.origen?.vista;
  $("volver").href = origen === "canasta" ? "#canasta" : origen === "inicio" ? "#inicio" : "#buscar";
  $("volver").textContent = origen === "canasta" ? "← Volver a la canasta" : origen === "inicio" ? "← Volver al inicio" : "← Volver a la búsqueda";
  $("producto-nombre").textContent = nombreVisible(p);
  $("producto-detalle").textContent =
    [p.marca && marcaVisible(p.marca), p.presentacion, p.clave.includes("-") ? "código interno de una cadena" : `código ${p.clave}`].filter(Boolean).join(" · ");

  const lineas = porProvincia[provincia()];
  const tabla = $("producto-hoy");
  if (!lineas) {
    const otras = Object.keys(porProvincia).map(c => PROVINCIAS[c] ?? c).sort((a, b) => a.localeCompare(b, "es"));
    $("producto-aviso").textContent = `No hay precios de este producto en ${PROVINCIAS[provincia()]}. Hay en: ${otras.join(", ")}.`;
    tabla.replaceChildren();
    $("producto-iguales").textContent = "";
    $("producto-cadenas").replaceChildren();
    grafico("producto", $("grafico-producto"), [], { min: 0, max: estado.meta.dia_dato, pasos: true });
    return;
  }
  const hoy = estado.meta.dia_dato;
  const filas = Object.entries(lineas).map(([id, { p: puntos, u: ultimo }]) => {
    const [desde, precio] = puntos.at(-1);
    return { id, puntos, ultimo, desde, precio, disponible: hoy - ultimo <= DIAS_NO_DISPONIBLE };
  }).sort((a, b) => (b.disponible - a.disponible) || a.precio - b.precio);

  const disponibles = filas.filter(f => f.disponible).map(f => f.precio);
  const minimo = Math.min(...disponibles), maximo = Math.max(...disponibles);
  $("producto-aviso").textContent = filas.some(f => !f.disponible)
    ? "Las cadenas en gris no informan este producto hace más de 7 días: se muestra su último precio." : "";
  const encabezado = document.createElement("tr");
  encabezado.append(...["Cadena", "Precio", "Diferencia", "Cambio"].map((t, i) => elemento("th", i === 1 || i === 2 ? "num" : null, t)));
  tabla.replaceChildren(encabezado, ...filas.map(f => {
    const tr = document.createElement("tr");
    if (!f.disponible) tr.className = "no-disponible";
    const nombre = celda(cadena(f.id));
    const punto = elemento("span", "punto"); punto.style.background = color(f.id);
    nombre.prepend(punto);
    const barata = f.disponible && f.precio === minimo;
    const cara = f.disponible && maximo > minimo && f.precio === maximo;
    tr.append(nombre, celda(pesos(f.precio), "num" + (barata ? " barata" : cara ? " cara" : "")),
      celda(!f.disponible ? "—" : barata ? "la más barata" : "+" + porcentaje((f.precio / minimo - 1) * 100), "num" + (barata ? " barata" : cara ? " cara" : "")),
      celda(textoCambioFila(f, hoy)));
    return tr;
  }));

  // Una línea por cadena, plana hasta que cambia el precio; cada punto es un cambio. Las cadenas con exactamente la
  // misma historia quedan una encima de la otra: la primera se dibuja más gruesa y las demás más finas, así asoma
  // el color de cada una.
  const firma = f => JSON.stringify([f.puntos, Math.min(f.ultimo, hoy)]);
  const iguales = new Map();
  for (const f of filas) iguales.set(firma(f), [...(iguales.get(firma(f)) ?? []), f]);
  const juntas = [...iguales.values()].filter(g => g.length > 1);
  $("producto-iguales").textContent = juntas
    .map(g => `${listar(g.map(f => cadena(f.id)))} tuvieron siempre el mismo precio: sus líneas coinciden.`).join(" ");

  const ocultas = new Set();
  $("producto-tip").hidden = true;
  botonesCadenas($("producto-cadenas"), filas.map(f => f.id), ocultas, "producto");
  grafico("producto", $("grafico-producto"), filas.map(f => {
    const grupo = iguales.get(firma(f)), lugar = grupo.indexOf(f);
    return {
      label: cadena(f.id),
      // cada línea va desde su primer precio hasta el último día en que se vio (o hasta hoy)
      data: [...f.puntos.map(([x, y]) => ({ x, y })), { x: Math.min(f.ultimo, hoy), y: f.precio }],
      borderColor: color(f.id), backgroundColor: color(f.id), borderDash: f.disponible ? [] : [4, 4],
      borderWidth: 2 + Math.min(grupo.length - 1 - lugar, 5) * 3,
      pointRadius: ctx => (ctx.dataIndex > 0 && ctx.dataIndex < f.puntos.length ? 4 : 0),   // solo los cambios
      pointHoverRadius: 6, pointHitRadius: 12,
    };
  }), { min: 0, max: hoy, pasos: true });
  cartelDeDias("producto", $("grafico-producto"), $("producto-tip"), filas, hoy);
}

function mostrarCanastaProvincia() {
  const { dia, filas: hoy } = rankingProvincia(provincia());
  const tabla = $("provincia-ranking");
  $("provincia-dia").textContent = dia == null ? "" : fechaLarga(dia);
  if (!hoy.length) {
    $("provincia-nota").textContent = "Ninguna cadena informa precios aquí.";
    tabla.replaceChildren();
    return;
  }
  const productos = hoy[0].productos.toLocaleString("es-AR");
  $("provincia-nota").textContent = hoy.length < 2
    ? `Una sola cadena: no hay con quién comparar (${productos} productos).`
    : `Se comparan los ${productos} productos que tienen las ${hoy.length} cadenas de la provincia, con el mismo código de barras. Precio de lista: la mediana entre las sucursales de cada cadena.`;
  $("comparacion-titulo").textContent = `Los ${productos} productos que se comparan`;
  const encabezado = document.createElement("tr");
  encabezado.append(...["#", "Cadena", "vs. la mediana", "vs. la más barata"].map((t, i) => elemento("th", i >= 2 ? "num" : null, t)));
  const signo = v => (v > 0 ? "+" : v < 0 ? "−" : "") + porcentaje(Math.abs(v) * 100);
  tabla.replaceChildren(encabezado, ...hoy.map((f, i) => {
    const tr = document.createElement("tr");
    const clase = empatada(f) ? " barata" : i === hoy.length - 1 ? " cara" : "";
    tr.append(celda(String(f.puesto)), celda(cadena(f.id)), celda(signo(f.indice - 1), "num"),
      celda(f.diferencia === 0 ? "la más barata" : `+${porcentaje(f.diferencia * 100)}${empatada(f) ? " (empate)" : ""}`, "num" + clase));
    return tr;
  }));
}

// La lista de productos de la comparación, con la misma tabla que los resultados de búsqueda,
// de a POR_PAGINA
const POR_PAGINA = 25;
function mostrarComparacion() {
  if (!estado.indice) return;
  const todas = (estado.comparacion.get(provincia()) ?? []).map(clave => ({ p: estado.porClave.get(clave), hoy: filaHoy(clave) }))
    .filter(r => r.p && r.hoy);
  // Filtro por grupo (el desplegable, o el link de una tarjeta de la portada): los mismos grupos que las tarjetas
  const cuenta = new Map();
  for (const r of todas) if (r.p.grupo && r.p.grupo !== "No supermercado") cuenta.set(r.p.grupo, (cuenta.get(r.p.grupo) ?? 0) + 1);
  if (estado.grupoComparacion && !cuenta.has(estado.grupoComparacion)) estado.grupoComparacion = "";
  const opciones = [["", `Todos los grupos (${todas.length.toLocaleString("es-AR")})`],
    ...[...cuenta].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "es")).map(([g, n]) => [g, `${g} (${n.toLocaleString("es-AR")})`])];
  $("grupo-comparacion").replaceChildren(...opciones.map(([valor, texto]) => {
    const o = elemento("option", null, texto);
    o.value = valor;
    o.selected = valor === estado.grupoComparacion;
    return o;
  }));
  const filas = estado.grupoComparacion ? todas.filter(r => r.p.grupo === estado.grupoComparacion) : todas;
  for (const r of filas) {
    r.validos = sinAislados(r.hoy.precios);
    const valores = [...r.validos.values()];
    r.minimo = Math.min(...valores);
    r.diferencia = Math.max(...valores) / r.minimo - 1;
  }
  const orden = $("orden-comparacion").value;
  const porNombre = (a, b) => nombreVisible(a.p).localeCompare(nombreVisible(b.p), "es");
  filas.sort((a, b) => {
    if (orden === "nombre") return porNombre(a, b);
    if (orden === "precio") return a.minimo - b.minimo || porNombre(a, b);
    if (orden === "cambios") return b.hoy.cambios.length - a.hoy.cambios.length || b.diferencia - a.diferencia;
    return b.diferencia - a.diferencia || porNombre(a, b);
  });
  const paginas = Math.max(1, Math.ceil(filas.length / POR_PAGINA));
  estado.pagina = Math.min(estado.pagina, paginas - 1);
  const pagina = filas.slice(estado.pagina * POR_PAGINA, (estado.pagina + 1) * POR_PAGINA);
  const columnas = [...cadenasDeProvincia(provincia())].sort((a, b) => corto(a).localeCompare(corto(b), "es"));
  const tabla = $("tabla-comparacion");
  tabla.style.setProperty("--cadenas", columnas.length);
  tabla.replaceChildren(...(pagina.length ? [encabezadoTabla(columnas), ...pagina.map(r => filaResultado(r, columnas, []))] : []));

  const ir = n => () => { estado.pagina = n; mostrarComparacion(); $("comparacion-titulo").scrollIntoView({ block: "start" }); };
  const boton = (texto, n, activo) => {
    const b = elemento("button", "chip-filtro", texto);
    b.type = "button"; b.disabled = !activo;
    if (activo) b.addEventListener("click", ir(n));
    return b;
  };
  $("paginas").hidden = paginas < 2;
  $("paginas").replaceChildren(boton("← Anterior", estado.pagina - 1, estado.pagina > 0),
    elemento("span", "nota", `Página ${estado.pagina + 1} de ${paginas} · ${plural(filas.length, "producto", "productos")}`),
    boton("Siguiente →", estado.pagina + 1, estado.pagina < paginas - 1));
}

// --- gráficos ---------------------------------------------------------------------------------
// Línea vertical y un punto en cada línea visible, en el día que se está señalando (ver cartelDeDias)
const cruceDia = {
  id: "cruceDia",
  afterDatasetsDraw(chart) {
    const cruce = chart.$cruce;
    if (!cruce) return;
    const { ctx, chartArea } = chart;
    const estilo = getComputedStyle(document.documentElement);
    ctx.save();
    ctx.strokeStyle = estilo.getPropertyValue("--suave").trim();
    ctx.globalAlpha = 0.6;
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(cruce.x, chartArea.top);
    ctx.lineTo(cruce.x, chartArea.bottom);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    ctx.lineWidth = 2;
    ctx.strokeStyle = estilo.getPropertyValue("--fondo").trim();
    for (const p of cruce.puntos) {
      ctx.beginPath();
      ctx.arc(cruce.x, p.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = p.color;
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  },
};

function grafico(nombre, canvas, datasets, { min, max, pasos }) {
  estado.graficos[nombre]?.destroy();
  canvas.onpointermove = canvas.onpointerdown = canvas.onpointerleave = null;
  if (typeof Chart === "undefined") return;  // sin Chart.js (red bloqueada): el resto del sitio funciona
  const estilo = getComputedStyle(document.documentElement);
  const texto = estilo.getPropertyValue("--suave").trim(), grilla = estilo.getPropertyValue("--linea").trim();
  estado.graficos[nombre] = new Chart(canvas, {
    type: "line",
    // stepped "before": la línea sigue plana en el precio anterior y sube o baja recién en el día del cambio
    data: { datasets: datasets.map(d => ({ stepped: pasos ? "before" : false, borderWidth: 2, ...d })) },
    plugins: [cruceDia],
    options: {
      maintainAspectRatio: false, animation: false, parsing: false,
      events: [],   // el cartel y la línea vertical los maneja cartelDeDias
      layout: { padding: { right: 8, top: 8 } },
      scales: {
        x: { type: "linear", min, max, ticks: { color: texto, font: { size: 13 }, stepSize: 1, maxRotation: 0, autoSkipPadding: 12, callback: v => fecha(v) }, grid: { display: false } },
        y: { grace: "10%", ticks: { color: texto, font: { size: 13 }, callback: v => pesosRedondo(v) }, grid: { color: grilla } },
      },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },   // las cadenas se eligen con los botones de arriba
    },
  });
}

// Precio de una cadena en un día: el del último cambio hasta ese día; null si ese día no se la vio.
// f.puntos = [[día, precio]], un punto por cada cambio; f.ultimo = último día en que se la vio.
function precioEnDia(f, dia, hoy) {
  if (dia < f.puntos[0][0] || dia > Math.min(f.ultimo, hoy)) return null;
  let precio = f.puntos[0][1];
  for (const [d, p] of f.puntos) if (d <= dia) precio = p;
  return precio;
}

// El cartel del gráfico de un producto. Al pasar el mouse (o tocar) por un día, lista el precio de TODAS las cadenas
// visibles ese día, con una línea vertical y un punto en cada línea. Así no hay que acertarle a una línea: el día
// que se señala es el del cursor, y de ahí salen todos los precios.
function cartelDeDias(nombre, canvas, cartel, filas, hoy) {
  const chart = estado.graficos[nombre];
  if (!chart) return;
  const ocultar = () => {
    cartel.hidden = true;
    if (chart.$cruce) { chart.$cruce = null; chart.draw(); }
  };
  const mostrar = evento => {
    const caja = canvas.getBoundingClientRect();
    const px = evento.clientX - caja.left;
    const { left, right, top } = chart.chartArea;
    if (px < left - 4 || px > right + 4) return ocultar();
    const x = chart.scales.x;
    const dia = Math.min(Math.max(Math.round(x.getValueForPixel(px)), x.min), x.max);
    const delDia = filas.map((f, i) => ({ f, precio: precioEnDia(f, dia, hoy), visible: chart.isDatasetVisible(i) }))
      .filter(r => r.visible && r.precio != null)
      .sort((p, q) => p.precio - q.precio);
    if (!delDia.length) return ocultar();
    chart.$cruce = { x: x.getPixelForValue(dia), puntos: delDia.map(r => ({ y: chart.scales.y.getPixelForValue(r.precio), color: color(r.f.id) })) };
    chart.draw();

    cartel.replaceChildren(elemento("strong", "cartel-fecha", mayuscula(fechaLarga(dia))), ...delDia.map(({ f, precio }) => {
      const fila = elemento("div", "cartel-fila");
      const punto = elemento("span", "cartel-punto");
      punto.style.background = color(f.id);
      fila.append(punto, elemento("span", null, cadena(f.id)), elemento("span", "cartel-precio", pesos(precio)));
      // Si ese día cambió el precio, de cuánto fue
      const k = f.puntos.findIndex(([d]) => d === dia);
      if (k > 0) {
        const variacion = (precio / f.puntos[k - 1][1] - 1) * 100;
        fila.append(elemento("span", "cartel-cambio", `${variacion > 0 ? "Subió" : "Bajó"} ${porcentaje(Math.abs(variacion))} ese día (antes ${pesos(f.puntos[k - 1][1])})`));
      }
      return fila;
    }));
    cartel.hidden = false;
    const ancho = cartel.offsetWidth, cruce = chart.$cruce.x;
    const izquierda = cruce + 14 + ancho > canvas.clientWidth ? cruce - ancho - 14 : cruce + 14;
    cartel.style.left = `${Math.max(0, izquierda)}px`;
    cartel.style.top = `${top + 6}px`;
  };
  canvas.onpointermove = mostrar;
  canvas.onpointerdown = mostrar;
  canvas.onpointerleave = ocultar;
}

iniciar().catch(error => {
  console.error(error);
  const aviso = $("portada-aviso");
  aviso.textContent = "No se pudieron cargar los datos.";
  aviso.hidden = false;
});
