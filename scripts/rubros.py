"""Reglas para sugerir el rubro de un producto a partir de su descripción.

Cada descripción se normaliza (mayúsculas, sin tildes ni Ñ, y sin frases como "sin azúcar")
y gana la PRIMERA regla que coincide. Por eso el orden importa: lo que no es comida va antes
(así "crema con aceite de coco" no cae en aceite) y lo específico antes que lo general
("dulce de leche" antes que "leche"). Un mismo rubro puede tener más de una regla.

Es una ayuda para revisar a mano, no una clasificación confiable: eso es la fase 2.
"""

# Frases que se borran antes de clasificar: "sin azúcar" no es azúcar.
SIN_AZUCAR = r"(\bSIN|\bMENOS|\bS/|\bS|\bCERO|\b0%?|\bBAJ[OA] EN|\bREDUCIDO EN)\.? ?AZUC\w*"

RUBROS = [
    ("crema de leche",
     r"CREMA DE LECHE|CREMA DOBLE|CREMA (PARA |P/ ?)?(BATIR|COCINAR)|CREMA CHANTILLY"
     r"|CREMA (UAT|UHT|LIVIANA|CLASICA)"
     r"|CREMA (LA SERENISIMA|TONADITA|TREGAR|SANCOR|LAS TRES|L3N|MILKAUT|LS)\b"),
    ("fórmulas infantiles",
     r"FORMULA (LACTEA|INFANTIL)|LECHE INF|NIDINA|NUTRILON|\bNIDO\b|\bVITAL ?[123]\b"
     r"|\bBABY ?[123]\b|ETAPA [123]|SANCOR BEBE|\bNAN\b"),
    ("mascotas",
     r"\b(PERROS?|GATOS?|GATITOS?|CACHORROS?)\b|CAT CHOW|DOG CHOW|PEDIGREE|WHISKAS|\bGATI\b|DOGUI"
     r"|EUKANUBA|PRO ?PLAN|SIEGER|OLD PRINCE"),
    ("electro y tecnología",
     r"\bCELULAR\b|SMARTPHONE|\bHELADER(A)?\b|LAVARROPAS|TERMOTANQUE|^MICROONDAS|TOSTADORA|LICUADORA"
     r"|BATIDORA|PROCESADORA|CAFETERA|VENTILADOR|TELEVISOR|\bNOTEBOOK|AURICULARES?|PARLANTE|CARGADOR"
     r"|\bPS[45]\b|XBOX|NINTENDO|\bREFLECTOR\b|LAMPARA (LED|BULB)|\bLED (BULB|VALUE)|JARRA ELE|PAVA ELE"
     r"|\bTV\b"),
    ("librería",
     r"^LB\b|\bLIBROS?\b|RESALTADOR|SACAPUNTA|PLASTILINA|CUADERNO|CARTUCHERA|\bMOCHILAS?\b|\bLAPICES\b"
     r"|\bLAPIZ (DE COLOR|NEGRO|GRAFITO)|LAPICERA|BIROME|BORRADOR|MARCADORES?|\bCARPETA|TEMPERA\b|\bCRAYON"
     r"|POSTIT|ABROCHADORA|\bTIJERA"),
    ("ropa y calzado",
     r"\bBOXER\b|ZAPATILLA|SWEATER|CAMPERA|\bCAMPE\b"
     r"|\bPOLERA\b|PANTALON|\bJOGGER\b|SOUTIEN|\bSLIP\b|\bCAMISA\b|\bREMERAS?\b|\bVEST\b|VESTIDO"
     r"|\bBUZO\b|BERMUDA|\bPIJAMA|RINONERA|CINTURON|\bJEANS?\b|SOQUETES?|CALZONCILLO|ZAPATO|SANDALIA"
     r"|OJOTA|CHINELA"),
    ("ferretería y jardín",
     r"\bPILAS?\b|TORNILLO|\bTACHAS?\b|\bLATEX\b|PINTURA|BARNIZ|PINO (PATAGONICO|CIPRES)|\bCLAVOS?\b"
     r"|MARTILLO|DESTORNILLADOR|\bLIJAS?\b|CINTA (AISLADORA|DE EMBALAR)|TIERRA (PARA|NEGRA)|\bABONO"),
    ("aire libre y verano",
     r"\bPILETAS?\b|SALVAVIDAS|SILLA PLEGABLE|REPOSERA|SOMBRILLA|INFLABLE|BOLSA (DE )?DORMIR|CONSERVADORA"
     r"|\bCARPA\b|HAMACA|COLCHONETA"),
    ("juguetes",
     r"\bLEGO\b|JUGUETE|MUNECA|PELUCHE|ROMPECABEZAS|JUEGO DE MESA|\bBARBIE\b|HOT WHEELS"
     r"|\bFUNKO\b|\bSLIME\b|AUTITO|\bPOP ?IT\b|FIGURA DE ACCION"),
    ("bazar y hogar",
     r"\bMUGS?\b|\bBOWL\b|PLATO (HONDO|PLAYO|POSTRE)|SET (DE )?(VASOS|DUCHA|COPAS|CUBIERTOS)"
     r"|COLADOR|SARTEN|BASURERO|\bCEST[AO]\b|DISPENSADOR|ALMOHADON|\bGLOBOS?\b|CEPILLO .*BANO"
     r"|HERMETIC|\bSABANAS?\b|\bMANTEL"),
    ("bebés",
     r"PANAL|HUGGIES|PAMPERS|BABYSEC|ESTRELLITAS|BABY|JOHNSON|TOALLITAS HUM|OLEO CALCAREO|MAMADERA"
     r"|CHUPETE|\bBEBES?\b|\bBEB\b"
     r"|\b(COLONIA|SHAMPOO|JABON|ACONDICIONADOR|CREMA|TALCO) (LIQUIDO |LIQ )?(INF|INFANTIL)\b|\bPIBES\b"),
    ("higiene femenina",
     r"TOALLAS? ?(FEM|HIG|FEMENINA|NOCTURNA|DIARIA)|\bTOALL\b|\bTOA\b|NOSOTRAS|KOTEX|SIEMPRE ?LIBRE"
     r"|\bLINA\b|PLENITUD|ALWAYS|TAMPON|PROTECTOR(ES)? (DIARIO|LARG)|\bPROT DIARIO|POST ?PARTO"
     r"|LADYSOFT|CAREFREE|CARREFREE|INCONTINENCIA|\bINTIM"),
    ("higiene bucal",
     r"DENTAL|DENTRIFICO|CEPILLO (DENTAL|DE DIENTES|DIENTES)|\bCEP DENT|ENJ(UAGUE|UAG)?\.? ?BUCAL"
     r"|LISTERINE|HILO DEN|FLOSSER|COLGATE|ORAL ?B\b|SENSODYNE|KOLYNOS|PRODENT|\bCRE DENT"
     r"|\bCREM DENT|COREGA|PALILL INTERDENT|INTERDENT"),
    ("limpieza ropa",
     r"\bROPA\b|WOOLITE|QUERUBIN|SUAVIZANTE|QUITAMANCH|PRELAVADO|PERFUMANTE|PERF FRAGANZA"),
    ("limpieza hogar",
     r"ACOND(ICIONADOR)?\.? (DE |P/|PARA )?PISOS|LIMPIADOR.*PISOS|LUSTRAMUEBLES"),
    ("cuidado del cabello",
     r"SHAMPOO|\bSH\b|ACONDICIONADOR|\bACOND\b|\bAC DOVE|\bCTC\b|\bCP\b|MASCARILLA"
     r"|MASCARA (P/|PARA |DE )?(CABELLO|CAPILAR|TRAT)|\bMASC\b|TRATAMIENTO|\bOLEO\b|COLORACION"
     r"|COLOR PERM|\bTIN\b|\bTINT\b|TINTURA|NUTRISSE|EXCELLENCE|COR INTENSA|IGORA|FIJADOR"
     r"|GEL (CAPILAR|FUERTE|FIJADOR)|ROBY|LORD ?CHESELINE|SEDAL|PANTENE|ELVIVE|TRESEMME|FRUCTIS"
     r"|HEAD ?(&|Y)? ?SHOULDERS|\bH&S\b|PLUSBELLE|TIO NACHO|ANTICANAS|KERATIN|QUERATINA"),
    ("afeitado",
     r"AFEITAR|AFEITADO|GILLETTE|MACH ?3|PRESTOBARBA|ESPUMA (DE )?(AFEITAR|SENSITIV)|CARTUCHO"
     r"|\bBIC\b|SCHICK|DEPILATORI"),
    ("jabón de tocador",
     r"TOCADOR|\bJAB TOC|JABON ANTIBAC|\bJAB(ON)? CRE|JABON CREMOSO"
     r"|JABON (LIQ\w*\.? )?(P/|PARA )?MANOS|ESPADOL|ASEPXIA|PROTEX|JABON (DE )?GLICERINA|\bLUX\b"
     r"|PALMOLIVE|JABON (EN )?BARRA"),
    ("papeles",
     r"PAPEL HIG|\bP HIG\b|ROLLO (D/|DE )?COCINA|ROLLO COCINA|SERVILLET|PANUELO|\bELITE\b|HIGIENOL"
     r"|SUSSEX|FELPITA|CAMPANITA"),
    ("cuidado personal",
     r"FACIAL|DESMAQU|MICELA"),
    ("limpieza hogar",
     r"LAVANDINA|DETERGENTE|\bDET\b|LAVAVAJILLA|\bLAVAV|ABRILLANTADOR|FINISH|LIMPIADOR|\bLIMP\b"
     r"|LIMPIAHORNOS|ANTIGRASA|DESINF|DESENGRAS|INSECTICIDA|MATA ?MOS|\bMOSQ|ESPIRAL|\bRAID\b|FUYI"
     r"|AROMATIZ|AROM\.? ?AMB|AMBIEN|DIFUSOR|GLADE|SAPOLIO|PROCENEX|\bCIF\b|MR ?MUSCULO|ULTRA BRILL"
     r"|LUSTRAMUEBLES|\bBLEM\b|\bCERA\b|CERAMICOL|AUTOBRILLO|DESTAPA|PLOMERO|CANASTA|INODORO|\bWC\b"
     r"|\bPATO\b|ESPONJA|VIRULANA|MORTIMER|\bPANOS?\b|ESCOBILLON|ESCOBA|SECADOR|GUANTE"
     r"|RESIDUO|ASURIN|BOLSA ROLLO|FOSFOROS|\bFOS\b|POMADA|CALZADO|WASSINGTON|SELTON|SARRO|LYSOFORM"
     r"|POETT|MULTIMAX|MAGISTRAL|ALCOHOL ETILICO|\bVELAS?\b|^VELA"),
    ("desodorantes",
     r"DESODOR|\bDEO\b|\bDESO\b|ANTITRANS|REXONA|\bAXE\b|SPEED STICK|PEDICO|TALCO|\bDESOD\b"),
    ("limpieza ropa",
     r"\bROPA\b|JABON (LIQ\w*|LIQUIDO)\.? ?(P/|PARA )?(ROPA|DILUIR|DIL)|JABON (EN |E/)?(POLVO|PVO)"
     r"|JABON EN PAN|\bJAB\.? (PVO|POLV)|\bJAB\.? LIQ.*(ROPA|DIL|ECOLAV|BICARB|MATIC|BLANCO|BCO)"
     r"|ECOLAV|BICARB|\bMATIC\b|SUAVIZANTE|QUITAMANCH|QUI MANCH|VANISH|PRELAVADO|APRESTO|\bAPR\b"
     r"|TRENET|ROBIN|\bSKIP\b|ARIEL|\bZORRO\b|DREEFT|COMFORT|VIVERE|PERFUMANTE|PERF FRAGANZA"
     r"|WOOLITE|QUERUBIN"),
    ("cuidado personal",
     r"CREMA (CORP|DE MANOS|P/MANOS|FACIAL|HIDRAT|HUMECT|NUTRIT|ANTI|DE PEINAR|P/PEINAR|PARA PEINAR|DE PIES|P/PIES|REAFIRM|NIVEA|DOVE|SOFT)"
     r"|\bCR\b|\bCREM CORP|CORPORAL|BODY|MICELA|DESMAQU|SERUM|GEL (DE )?LIMPIEZA|NEUTROGENA|NIVEA"
     r"|DOVE|PROTECTOR|BRONCEADOR|SOLAR|ESMALTE|QUITAESM|ALGODON|\bALGOD\b|POMPON|HISOPO|COTONETE"
     r"|CURITA|APOSITO|PRESERVATIVO|SKYN|ALCOHOL (PURO|EN GEL|FRICC|96)|BIALCOHOL"
     r"|AGUA OXIGENADA|VASELINA|\bOFF\b|REPELENTE|JABON|\bJAB\b|LUBRICANTE|HINDS|TEATRICAL"
     r"|\bPERF\b|PERFUME|COLONIA|\bEDT\b|\bEDP\b|EAU DE (TOILETTE|PARFUM)|ST\.? ?IVES|VILLENEUVE|PALMOLIVE|\bLUX\b|PIERNAS|GOICOECHEA|GOICOCHEA|PONDS|MIST FACIAL"),
    ("tapas y pastas frescas",
     r"TAPAS? (P |P/|PARA |DE )?(EMPANAD|PASCUALINA|TARTA)|T/EMP|PASCUALINA|PASC CRIOLLA|RAVIOL"
     r"|CAPP?EL+ET+I|SORRENTINO|NOQUI|LA SALTENA"),
    ("comidas preparadas",
     r"X PORCION|POR PORCION|A LA CRIOLLA|FALAFEL"),
    ("snacks",
     r"PAPAS FRITAS|PAPAS FR\b|PAPA ACANALADA|PALITOS SALADOS|PALITOS DE QUESO|CHIZITOS|CHEETOS"
     r"|DORITOS|PRINGLES|\bLAYS\b|PAPAS (PAY|RURALES|RUSTICAS)|CHIPS D(E|/) ?PAPAS|PEHUAMAR|RUEDITAS|MANI (SALADO|TOSTADO|PELADO|JAPONES)|NACHOS"
     r"|TUTUCAS|KRACHITOS|\b3D'?S\b|TUBITOS"),
    ("caldos y sopas",
     r"\bCALDOS?\b|\bCALD\b|\bSOPAS?\b|\bSOP\b"),
    ("sal",
     r"\bSAL (FINA|ENTREFINA|GRUESA|MODIFICADA|CLASICA|DE MESA|MARINA|ROSADA|LIGHT|PAQUETE)|SALERO"
     r"|CELUSAL"),
    ("facturas y tortas",
     r"PAN DULCE"),
    ("pan y panificados",
     r"^PAN\b"),
    ("especias y condimentos",
     r"OREGANO|PIMENTON|PIMIENTA|PROVENZAL|CONDIMENTO|\bCOND\b|SABORIZADOR|\bSAB (ALICANTE|KNORR)"
     r"|AJI MOLIDO|CANELA (MOLIDA|EN RAMA|ALICANTE)|ROMERO|\bANIS\b|PEREJIL|CEBOLLA DESH"
     r"|AJO (TRITURADO|DESH|EN POLVO)|NUEZ MOSCADA|COMINO|LAUREL|CURRY|AZAFRAN|MIX DE SABORES|MIX SABOR"
     r"|BOLSA P/HORNO|VINAGRE|ACETO|JUGO DE LIMON|MINERVA"),
    ("salsas listas",
     r"SALSA (LISTA|POMAROLA|FILETTO|TUCO|PIZZA|POMODORO|BOLOGNESA|CASERA|TIPO CASERA|GUISO)"
     r"|\bSSA PO|POMAROLA|FILETTO|\bTUCO\b"),
    ("aderezos",
     r"MAYONESA|KETCHUP|MOSTAZA|ADEREZO"
     r"|SALSA (GOLF|CAESAR|ALIOLI|SOJA|DE SOJA|GUACAMOLE|TERIYAKI|COLESLAW|BBQ|BARBACOA|CHIMICHURRI|TARTARA|BLANCA)"
     r"|\bSSA\b|SAVORA|HELLMANN"),
    ("harina",
     r"\bHARINA\b|\bHARIN\b|POLENTA|PRESTOPRONTA"),
    ("repostería",
     r"PURE (INS|INSTANT)|BIZCOCHUELO|\bBIZCOCH\b|PREMEZCLA|GELATINA|\bGELAT?\b|POLVO (P/|PARA )|\bPVO\b|LEVADUR"
     r"|\bLEV\b|ALMIDON|MAIZENA|ESENCIA|VAINILLA LIQ|BANO (REPOS|DE REPOS)|REPOSTER"
     r"|COCO (RALL|ALICANTE RALL)|EXQUISITA|ROYAL|POSTRE (EN )?POLVO|AZUCAR IMPALPABLE|CACAO AMARGO"),
    ("helados",
     r"HELADO|\bFRIGOR\b|CREMA HELADA"),
    ("cerveza",
     r"CERVEZA"),
    ("amargos sin alcohol",
     r"\bTERMA\b|TRES TORRES|AMARGO (SERRANO|LIMON|POMELO|CITRUS|BLANCO)|\bS(IN)?\.? ?/?ALCOHOL"
     r"|BEB\.? HIERB|BEBIDA AMARGO"),
    ("vino y espumantes",
     r"\bVINO\b|MALBEC|CABERNET|TORRONTES|CHARDONNAY|MERLOT|SYRAH|BONARDA|\bTINTO\b|ESPUMANTE"
     r"|CHAMPAGNE|SIDRA"),
    ("bebidas espirituosas",
     r"VODKA|WHISKY|WHISKEY|\bGIN\b|\bRON\b|FERNET|VERMOUTH|APERITIVO|LICOR|GANCIA|CYNAR|CAMPARI"
     r"|RAMAZZOTTI|CARPANO|PUNT E MES|SMIRNOFF|ABSOLUT|BRANCA|BALLANTINE|CHIVAS|JOHNNIE|RED LABEL"
     r"|WHITE HORSE|BLENDERS|TEQUILA|MALIBU|HAVANA|SERNOVA|SPIRITO BLU|GORDON|DR\.? LEMON"),
    ("embutidos frescos",
     r"CHORIZ|MORCILLA|LONGANIZA|\bCHORI\b|SALCHICHAS? PARRILLER"),
    ("facturas y tortas",
     r"FACTURA|MEDIALUNA|MEDIAS LUNAS|BUDIN|MADALENA|PAN DULCE|PANETT?ONE|\bTORTAS?\b|PUDDING|\bPUDIN\b|HOJALDRE|CUERNITO|CROISSANT"),
    ("galletitas y tostadas",
     r"GALLETIT|\bGALL\b|GALLETA|BIZCOCHO|\bBIZC\b|TOSTADA|\bTOST\b|OBLEA|CRACKER|CRIOLLITA|GRISIN"
     r"|PEPAS|\bVAINILLAS\b|ROSQUITA|BISCUIT|\bTABLITAS?\b"),
    ("cacao",
     r"CACAO (EN )?(POLVO|PLV|E/POLVO)|\bCACAO\b.*FORTIFICADO|NESQUIK|TODDY|CHOCOLINO|NESCAO"
     r"|BASE (DE )?CACAO"),
    ("café",
     r"\bCAFE\b|NESCAFE|CABRALES|CAPPUCCINO|CAPUCHINO|COFFEE|\bNESC\b"),
    ("té e infusiones",
     r"\bTE\b|SAQUITO|MATE COCIDO|HERBORISTERIA|\bHRB\b|BOLDO|MANZANILLA|\bTILO\b|PEPERINA|INFUSION"
     r"|\bCHAI\b"),
    ("yerba",
     r"YERBA|\bYM\b"),
    ("alfajores",
     r"ALFAJOR|\bALF\b|\bALFA\b"),
    ("dulces y untables",
     r"MANTECA DE (MANI|CACAHUETE)|CREMA DE (MANI|AVELLANA)|RELLENO UNTABLE|NUTELLA|PASTA DE MANI|PASTA MANI"),
    ("golosinas",
     r"ACARAMELAD|MERENGUE|GARRAPINADA|KIT ?KAT|\bBIS\b|HABANITOS|DONUTS|DONAS|ROCHER|BON ?O ?BON|KINDER|TIC ?TAC|BELDENT|MOGUL"
     r"|SUGUS|CHICLE|GOMITA|CHUPETIN|\bBOMBON(ES)?\b|TURRON|MANTECOL|TABLETA|\bTAB\b|CADBURY"),
    ("yogur",
     r"YOGU|\bYOG\b|LECHE FERMENTADA|ACTIMEL"),
    ("postres lácteos",
     r"DANETTE|SERENITO|\bFLAN\b|POSTRE|ARROZ CON LECHE|CHOCOFLAN"),
    ("dulce de leche",
     r"DULCE DE LECHE|\bDDL\b"),
    ("bebida láctea",
     r"BEBIDA LACTEA|\bBEB\.? ?LACT|B\.? ?LACTEA|CHOCOLATAD|LECHE SAB|LECHE PROTEIN.*CHOC"
     r"|LECHE CHOC"),
    ("jugos",
     r"\bJUGOS?\b|\bADES\b|CEPITA|DEL VALLE|CITRIC|\bTUTTI\b|PURA ?FRUTTA|BAGGIO|NECTAR"
     r"|ALIMENTO LIQ|ALIMENTIO|\bTANG\b|CLIGHT"),
    ("bebidas vegetales",
     r"BEBIDA VEGETAL|LECHE DE (COCO|ALMENDRA|AVENA|SOJA|ARROZ)"
     r"|BEBIDA (DE |A BASE DE )?(ALMENDRA|AVENA|COCO|SOJA|ARROZ)"),
    ("endulzantes",
     r"EDULC|ENDULZ|STEVIA|SACARINA|SUCRALOSA|HILERET|CHUKER|SUCARYL"),
    ("cereales",
     r"CEREAL|ALMOHADITA|COPOS|AVENA|GRANOLA|SEMOLA|VITINA|SALVAD|LASFOR|QUINOA|MUESLI|ZUCARITAS|FORMIS|NESTUM"
     r"|MULTICER"),
    ("azúcar",
     r"AZUCAR"),
    ("dulces y untables",
     r"MERMELADA|\bMERM\b|ERMER|DULCE (DE )?(MEMBRILLO|BATATA|BAT|MEMB)|\bDCE\b|\bMIEL\b"
     r"|PASTA DE MANI|PASTA MANI|RELLENO UNTABLE|NUTELLA"),
    ("golosinas",
     r"CHOCOLATE|\bCHOC\b|\bCHOCO\b|CHOCOLATIN|\bBOMBON(ES)?\b|\bBOM\b|CARAMELO|\bCARAM\b|CHICLE|GOMITA"
     r"|PASTILLA|CHUPETIN|HUEVO (DE )?CHOC|KINDER|KIT ?KAT|ROCHER|BON ?O ?BON|BANANITA"
     r"|TIC ?TAC|BELDENT|TOPLINE|\bTLINE\b|MOGUL|SUGUS|MENTHO ?PLUS|TURRON|CONFITE|ROCKLET|MANTECOL"
     r"|TABLETA"),
    ("panificados",
     r"^PAN\b|BAGUETTE|\bPITA\b|\bPAN (LACTAL|DE MOLDE|BLANCO|INTEGRAL|RALLADO|DULCE|DE PANCHO|DE HAMBURG|DE VIENA|ARABE|SALVADO|FRANCES)"
     r"|LACTAL|BIMBO|FARGO|REBOZADOR|PREPIZZA|PIZZETA"),
    ("hamburguesas",
     r"HAMBURG|\bHAMB\b|BURGER|VEGGIES|MEDALLON(ES)? (DE CARNE|DOBLE|D/|DE (ESPINACA|VERDURA|LENTEJA|GARBANZO|QUINOA|SOJA|VEGETAL))|\bPATY\b"),
    ("salchichas",
     r"SALCHICHA|\bSALCHI?\b|VIENISSIMA|PATYVIENA"),
    ("fideos",
     r"FIDEO|\bFID\b|SPAGHETTI|TALLARIN|MOSTACHOL|TIRABUZON|\bMONO\b|MOSTACCIOLI|CODITO|PENNE"
     r"|RIGATI|MUNICION|FETTUCC|RAMEN"),
    ("arroz",
     r"\bARROZ\b|RISOTTO"),
    ("congelados",
     r"CONGELAD|\bIQF\b|\bCONG\b|NUGGET|SUPREMITA|SUPREMAS|SUPR DE POLL|PATITAS|BOCADITOS DE POLLO"
     r"|PALITOS DE POLLO|PAL POLLO|MC ?CAIN|\bMCC\b|NOISETTE|GRANJA DEL SOL|GREEN LIFE|\bGDS\b"
     r"|MEDALLON(ES)? DE POLLO"),
    ("queso",
     r"QUESO|RICOTA|RICOTTA|\bQSO\b"),
    ("fiambres",
     r"\bPATE\b|LOMO HORNEADO|\bARROLLADO|JAMON|\bJAM\b|SALAME|SALCHICHON|PANCETA|BONDIOLA|\bFUET\b|LOMO (COCIDO|FET)|LEBERWURST"
     r"|MORTADELA|MATAMBRE|PALETA (COCIDA|FET)"),
    ("leche",
     r"\bLECHE\b|\bL\.? POLV"),
    ("manteca",
     r"MANTECA"),
    ("margarina",
     r"MARGARINA|DANICA|MARGADAN"),
    ("huevos",
     r"\bHUEVOS?\b"),
    ("aceite",
     r"ACEITE (DE )?(GIRASOL|OLIVA|MAIZ|MEZCLA|SOJA|CANOLA)"
     r"|\bACEITE\b.*\b(1[,.]5|900|1) ?(L|LT|LTS|ML|CC)\b|ROCIO|FRITOLIM|\bACEIT\b"),
    ("conservas",
     r"TOMATE|\bPURE\b|ARVEJA|\bATUN\b|\bCHOCLO|LENTEJA|POROTO|GARBANZO|ACEITUNA|PALMITO|ALMIBAR"
     r"|SARDINA|CABALLA|JARDINERA|\bMITADES\b|EN TROZOS"),
    ("isotónicas y energizantes",
     r"ISOTONIC|\bISOT\b|GATORADE|POWERADE|ENERGIZANTE|\bENERG\b|\bMONSTER\b|\bSPEED\b|RED ?BULL"
     r"|BEBIDA SALES"),
    ("gaseosa",
     r"GASEOSA|\bGASEO\b|COCA.?COLA|PEPSI|SPRITE|FANTA|SEVEN ?UP|7 ?UP|AGUA TONICA|\bTONICA\b"
     r"|\bSODA\b|PASO DE LOS TOROS|SCHWEPPES|SCHWEEPPS|MIRINDA|MANAOS"),
    ("agua",
     r"\bAGUA\b|AQUARIUS|LEVITE|VILLAVICENCIO|ECO DE LOS ANDES|GLACIAR|BONAQUA"),
    # Lo fresco va al final: así lo que tiene una regla más específica (jugo de naranja, gaseosa de
    # manzana, chorizo de cerdo) no cae acá
    ("carne de cerdo",
     r"CERDO|LECHON|PECHITO"),
    ("otras carnes",
     r"CORDERO|CABRITO|CONEJO|CHIVITO|JABALI|\bCIERVO"),
    ("carne vacuna",
     r"NOVILLO|NOVILLITO|VACUNO|ENTRANA|\bVACIO\b|\bFALDA\b|PECETO|\bNALGA\b|BIFE|OSOBUCO|CUADRIL"
     r"|PICANA|CARNAZA|TIRA (DE )?ASADO|CARNE PICADA"),
    ("pollo",
     r"\bPOLLO\b|PECHUGA|MUSLO|\bPOLLITO|CUARTO (TRASERO|DELANTERO)|ALITAS"),
    ("pescados y mariscos",
     r"PESCADO|MERLUZA|SALMON|PALOMETA|CORVINA|TRUCHA|LENGUADO|CALAMAR|CAMARON|LANGOSTINO|MEJILLON"
     r"|PEJERREY|SURUBI|ABADEJO|CAZON"),
    ("verduras",
     r"PAPINES|\bPAPAS? (BLANCA|NEGRA|ROSADA|SPUNTA|LAVADA)|ZANAHORIA|ZAPALLO|ZAPALLITO|CALABAZA|LECHUGA"
     r"|REPOLLO|REPOLLITOS|BRUSELA|BROCOLI|COLIFLOR|PIMIENTO|MORRON|CHAMPIGNON|PORTOBELLO|VERDEO|ACELGA"
     r"|ESPINACA|BERENJENA|PEPINO|PUERRO|REMOLACHA|BATATA|ACHICORIA|RUCULA|RABANITO|\bAPIO\b|\bCEBOLLA"
     r"|\bHONGOS?\b"),
    ("frutos secos y semillas",
     r"\bMIX (SALADITO|DE FRUTOS|KOS)|FRUTOS SECOS|\bNUECES\b|\bNUEZ\b|ALMENDRAS|PISTACHO|CASTANA|\bPASAS\b"
     r"|\bCHIA\b|SEMILLAS"),
    ("frutas",
     r"ARANDANO|MANZANA|\bPERAS?\b|BANANA|NARANJA|MANDARINA|\bLIMON(ES)?\b|POMELO|FRUTILLA|FRAMBUESA"
     r"|DURAZNO|CIRUELA|\bUVAS?\b|\bMELON|SANDIA|KIWI|PALTA|\bANANA\b|CEREZA|DAMASCO|\bMANGO\b|\bHIGOS?\b"),
]


# ---------------------------------------------------------------------------------------------
# Cómo se aplican las reglas. Lo usan scripts/evaluar_reglas.py y, más adelante, el modelo de dbt.
import re
import unicodedata
from collections import Counter

# Rubros de las reglas que cambiaron de nombre en la taxonomía de 85
RENOMBRADOS = {"bebés": "pañales y cuidado del bebé", "repostería": "repostería y premezclas",
               "panificados": "pan y panificados"}

# Si alguna cadena escribe "congelado", el producto es congelado aunque las demás no lo digan
# (la guía de etiquetado: congelado solo si la descripción o la marca lo dicen)
EXPLICITO_CONGELADO = re.compile(r"CONGELAD|\bIQF\b|\bCONG\b")

REGLAS = [(rubro, re.compile(patron)) for rubro, patron in RUBROS]


def normalizar(texto):
    """Mayúsculas, sin tildes ni Ñ y sin frases como "sin azúcar"."""
    # Igual que strip_accents de DuckDB: Á->A, Ü->U y también Ñ->N (los patrones escriben BANO, CASTANA)
    descompuesto = unicodedata.normalize("NFD", (texto or "").upper())
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(SIN_AZUCAR, " ", sin_tildes)


def rubro_de_descripcion(descripcion):
    """Índice de la primera regla que coincide, o None."""
    texto = normalizar(descripcion)
    for i, (_, patron) in enumerate(REGLAS):
        if patron.search(texto):
            return i
    return None


def rubro_de_producto(descripciones):
    """Rubro de un producto a partir de la descripción de cada cadena.

    Gana el rubro con más votos entre cadenas (empate: el de la regla que va primero), salvo que
    alguna cadena diga explícitamente "congelado": ahí el producto es congelado.
    """
    votos, primera = Counter(), {}
    for descripcion in descripciones:
        i = rubro_de_descripcion(descripcion)
        if i is not None:
            rubro = REGLAS[i][0]
            votos[rubro] += 1
            primera[rubro] = min(primera.get(rubro, i), i)
    rubro = max(votos, key=lambda r: (votos[r], -primera[r])) if votos else None
    textos = [normalizar(d) for d in descripciones]
    # Congelado porque lo dice una cadena, o porque la regla lo reconoció por marca o por producto
    if rubro == "congelados" or (rubro != "helados" and any(EXPLICITO_CONGELADO.search(t) for t in textos)):
        return subrubro_congelado(" ".join(textos))
    return rubro


# Dentro de congelados, el rubro sale de qué producto es (en este orden)
SUBRUBROS_CONGELADOS = [
    ("carnes y pescados congelados", re.compile(r"MEDALLON(ES)? (DE )?(PESCADO|MERLUZA|SALMON)")),
    ("hamburguesas", re.compile(r"HAMBURG|BURGER|MEDALLON")),
    ("carnes y pescados congelados",
     re.compile(r"POLLO|CARNE|PESCADO|MERLUZA|SALMON|NUGGET|SUPREMA|PATITAS|BASTONCITO|CAMARON|LANGOSTINO"
                r"|CALAMAR|RABAS|CERDO|CORDERO|CHIVITO|CABRITO")),
    ("comidas congeladas",
     re.compile(r"EMPANADA|PIZZA|TARTA|LASAGNA|LASANA|RAVIOL|CANELON|NOQUI|MILANESA|PASTA|FIDEO|PARMIGIANA"
                r"|COMIDA|ARROLLADO|PANQUEQUE")),
    ("vegetales congelados",
     re.compile(r"VERDURA|VEGETAL|PAPA|ARVEJ|ESPINACA|ACELGA|BROCOLI|CHOCLO|ZAPALLO|MIX|PRIMAV|CALABAZA"
                r"|COLIFLOR|BATATA")),
]


def subrubro_congelado(texto):
    """Rubro de un producto que dice "congelado". Si no se reconoce qué es, queda "congelados"."""
    for rubro, patron in SUBRUBROS_CONGELADOS:
        if patron.search(texto):
            return rubro
    return "congelados"
