import streamlit as st
import streamlit.components.v1 as components
import chess
import chess.pgn
import chess.svg
import chess.engine
import requests
import io
import shutil
import base64
import math
import asyncio
import edge_tts
from gtts import gTTS

st.set_page_config(page_title="Chess Premium & Entrenador", page_icon="💎", layout="centered")

# --- ESTILOS VISUALES PREMIUM TIPO CHESS.COM ---
st.markdown("""
<style>
    .stApp { background-color: #302e2b; color: white; }
    .coach-box {
        background-color: #262421;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 10px;
        border-left: 6px solid #81b64c;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.4);
    }
    .coach-avatar { font-size: 38px; }
    .coach-text { font-size: 15px; line-height: 1.45; color: #f1f1f1; }
    .badge {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
        margin-bottom: 5px;
    }
    .summary-card {
        background-color: #262421;
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 12px;
        border: 1px solid #3d3b38;
        text-align: center;
    }
    .elo-badge {
        background: linear-gradient(90deg, #1baca6, #5c8bb0);
        padding: 6px 14px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 18px;
        display: inline-block;
        margin-top: 6px;
    }
    .opening-banner {
        background-color: #211f1c;
        color: #c9c7c5;
        padding: 6px 12px;
        border-radius: 8px;
        font-size: 13px;
        text-align: center;
        margin-bottom: 8px;
        border: 1px solid #3a3835;
    }
</style>
""", unsafe_allow_html=True)

# --- VOCES HUMANAS NEURONALES ---
VOCES_HUMANAS = {
    "🎙️ Lorenzo (Voz Humana - Chile)": "es-CL-LorenzoNeural",
    "🎙️ Álvaro (Voz Humana - España)": "es-ES-AlvaroNeural",
    "🎙️ Dalia (Voz Humana - México)": "es-MX-DaliaNeural"
}

@st.cache_data(show_spinner=False)
def generar_audio_humano(texto, voz_id):
    try:
        async def _generar():
            comunicador = edge_tts.Communicate(texto, voz_id, rate="+12%")
            datos_audio = b""
            async for chunk in comunicador.stream():
                if chunk["type"] == "audio":
                    datos_audio += chunk["data"]
            return datos_audio
        audio = asyncio.run(_generar())
        if audio:
            return audio
    except Exception:
        pass
    tts = gTTS(text=texto, lang="es")
    buf = io.BytesIO()
    tts.write_to_fp(buf)
    return buf.getvalue()

# --- DICCIONARIO DE APERTURAS OFICIALES EN ESPAÑOL ---
LIBRO_APERTURAS = {
    "e2e4 e7e5 g1f3 b8c6 f1c4": "Apertura Italiana",
    "e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 f3g5": "Apertura Italiana: ¡Ataque Hígado Frito!",
    "e2e4 e7e5 g1f3 b8c6 f1b5": "Apertura Española (Ruy López)",
    "e2e4 e7e5 g1f3 b8c6 d2d4": "Apertura Escocesa",
    "e2e4 e7e5 g1f3 b8c6 b1c3 g8f6": "Apertura de los Cuatro Caballos",
    "e2e4 e7e5 f1c4": "Apertura del Alfil",
    "e2e4 e7e5 d1h5": "Ataque Parham (Intento de Mate del Pastor)",
    "e2e4 e7e5 f1c4 b8c6 d1h5": "Amenaza de Mate del Pastor",
    "e2e4 e7e5 f2f4": "Gambito de Rey",
    "e2e4 c7c5": "Defensa Siciliana",
    "e2e4 e7e6": "Defensa Francesa",
    "e2e4 c7c6": "Defensa Caro-Kann",
    "e2e4 d7d5": "Defensa Escandinava",
    "e2e4 d7d6": "Defensa Pirc",
    "d2d4 d7d5 c2c4": "Gambito de Dama",
    "d2d4 d7d5 c2c4 e7e6": "Gambito de Dama Declinado",
    "d2d4 d7d5 c2c4 c7c6": "Defensa Eslava",
    "d2d4 d7d5 f1f4": "Sistema Londres",
    "d2d4 g8f6 c2c4 g7g6": "Defensa India de Rey",
    "c2c4": "Apertura Inglesa",
    "g1f3 d7d5": "Apertura Reti"
}

def detectar_apertura(lista_uci):
    mejor_nombre = "Juego Abierto / Desarrollo"
    cadena = ""
    for i, uci in enumerate(lista_uci[:8]):
        cadena = (cadena + " " + uci).strip()
        if cadena in LIBRO_APERTURAS:
            mejor_nombre = LIBRO_APERTURAS[cadena]
    return mejor_nombre

# --- MATEMÁTICAS PREMIUM DE CHESS.COM (PROBABILIDAD DE VICTORIA Y CAPS) ---
def cp_a_probabilidad_ganar(cp):
    cp_limitado = max(-1500.0, min(1500.0, float(cp)))
    return 50.0 + 50.0 * (2.0 / (1.0 + math.exp(-0.00368208 * cp_limitado)) - 1.0)

def calcular_precision_jugada(perdida_prob):
    if perdida_prob <= 0:
        return 100.0
    acc = 103.1668 * math.exp(-0.04354 * perdida_prob) - 3.1669
    return max(0.0, min(100.0, acc))

# --- TRADUCTOR Y DETECTOR DE MOTIVOS TÁCTICOS EN ESPAÑOL ---
NOMBRES_PIEZAS = {
    chess.PAWN: "el peón", chess.KNIGHT: "el caballo",
    chess.BISHOP: "el alfil", chess.ROOK: "la torre",
    chess.QUEEN: "la dama", chess.KING: "el rey"
}

VALORES_PIEZAS = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0
}

def material_bando(board, color):
    total = 0
    for pt, val in VALORES_PIEZAS.items():
        total += len(board.pieces(pt, color)) * val
    return total

def jugada_en_espanol(board, move):
    if not move or move not in board.legal_moves:
        return "otra jugada"
    if board.is_castling(move):
        return "enroque corto" if chess.square_file(move.to_square) == 6 else "enroque largo"
    pieza = board.piece_at(move.from_square)
    nombre_pieza = NOMBRES_PIEZAS.get(pieza.piece_type, "la pieza") if pieza else "la pieza"
    casilla_destino = chess.square_name(move.to_square)
    
    texto = f"{nombre_pieza} a {casilla_destino}"
    if board.is_capture(move):
        pieza_capturada = board.piece_at(move.to_square)
        if pieza_capturada:
            nom_cap = NOMBRES_PIEZAS.get(pieza_capturada.piece_type, "una pieza")
            texto = f"{nombre_pieza} por {casilla_destino} capturando {nom_cap}"
        else:
            texto = f"captura al paso en {casilla_destino}"
    
    board_copia = board.copy()
    board_copia.push(move)
    if board_copia.is_checkmate():
        texto += " dando ¡Jaque Mate!"
    elif board_copia.is_check():
        texto += " dando jaque"
    return texto

def detectar_motivo_tactico(board_antes, move_hecho):
    b = board_antes.copy()
    color_jugador = b.turn
    color_rival = not color_jugador
    b.push(move_hecho)
    
    # 1. ¿Hizo un Ataque Doble (Tenedor / Fork)?
    atacadas_valiosas = []
    for sq in b.attacks(move_hecho.to_square):
        p_enemiga = b.piece_at(sq)
        if p_enemiga and p_enemiga.color == color_rival:
            if p_enemiga.piece_type == chess.KING or VALORES_PIEZAS.get(p_enemiga.piece_type, 0) >= 5:
                atacadas_valiosas.append(NOMBRES_PIEZAS[p_enemiga.piece_type])
    if len(atacadas_valiosas) >= 2:
        return f"¡Ataque doble! Desde {chess.square_name(move_hecho.to_square)} atacas al mismo tiempo a {atacadas_valiosas[0]} y a {atacadas_valiosas[1]}."

    # 2. ¿Clavó una pieza del rival (Pin)?
    for sq in chess.SQUARES:
        p = b.piece_at(sq)
        if p and p.color == color_rival and p.piece_type != chess.KING:
            if b.is_pinned(color_rival, sq) and not board_antes.is_pinned(color_rival, sq):
                return f"¡Buena clavada! Inmovilizas {NOMBRES_PIEZAS[p.piece_type]} en {chess.square_name(sq)} porque detrás está su Rey."

    return ""

def narrar_linea_futura(board_actual, pv_moves, max_pasos=3):
    b = board_actual.copy()
    frases = []
    pasos_fens = []
    for m in pv_moves[:max_pasos]:
        if m not in b.legal_moves:
            break
        quien = "tú juegas" if b.turn == chess.WHITE else "el rival responde"
        txt = jugada_en_espanol(b, m)
        b.push(m)
        frases.append(f"{quien} {txt}")
        pasos_fens.append({"fen": b.fen(), "mov": m, "texto": f"Si {quien} {txt}"})
    resumen = ", luego ".join(frases)
    return resumen, pasos_fens

# --- DIBUJAR TABLERO CON BARRA DE EVALUACIÓN LATERAL E INSIGNIA EN CASILLA ---
def dibujar_tablero_premium(board, eval_peones, orientacion=chess.WHITE, ultimo_mov=None, mejor_mov=None, simbolo_badge="", color_badge="#81b64c"):
    flechas = []
    if mejor_mov:
        flechas.append(chess.svg.Arrow(mejor_mov.from_square, mejor_mov.to_square, color="#81b64c"))
    
    svg_tablero = chess.svg.board(
        board=board,
        orientation=orientacion,
        lastmove=ultimo_mov,
        arrows=flechas,
        size=340,
        colors={
            "square light": "#ebecd0",
            "square dark": "#739552",
            "square light lastmove": "#f5f682",
            "square dark lastmove": "#b9ca43"
        }
    )

    # Inyectar insignia flotante estilo Chess.com en la esquina de la casilla jugada
    if ultimo_mov and simbolo_badge:
        sq = ultimo_mov.to_square
        col_idx = chess.square_file(sq) if orientacion == chess.WHITE else (7 - chess.square_file(sq))
        row_idx = (7 - chess.square_rank(sq)) if orientacion == chess.WHITE else chess.square_rank(sq)
        cx = 15 + col_idx * 45 + 37
        cy = 15 + row_idx * 45 + 9
        insignia_svg = (
            f'<circle cx="{cx}" cy="{cy}" r="10.5" fill="{color_badge}" stroke="#ffffff" stroke-width="1.5"/>'
            f'<text x="{cx}" y="{cy+3.8}" font-family="Arial, sans-serif" font-size="10" font-weight="bold" '
            f'fill="#ffffff" text-anchor="middle">{simbolo_badge}</text></svg>'
        )
        svg_tablero = svg_tablero.replace("</svg>", insignia_svg)

    b64 = base64.b64encode(svg_tablero.encode("utf-8")).decode("utf-8")

    # Calcular altura de la Barra de Evaluación (Eval Bar)
    pct_blancas = max(5.0, min(95.0, cp_a_probabilidad_ganar(eval_peones * 100.0)))
    pct_negras = 100.0 - pct_blancas
    txt_eval = f"+{eval_peones:.1f}" if eval_peones > 0 else f"{eval_peones:.1f}"

    html_contenedor = f"""
    <div style="display:flex; justify-content:center; align-items:center; gap:8px; margin: 6px 0;">
        <div style="width:26px; height:336px; background:#262421; border-radius:6px; overflow:hidden; border:1px solid #555; display:flex; flex-direction:column; position:relative;">
            <div style="height:{pct_negras}%; background:#262421; transition: height 0.3s;"></div>
            <div style="height:{pct_blancas}%; background:#ebecd0; transition: height 0.3s;"></div>
            <div style="position:absolute; bottom:4px; width:100%; text-align:center; font-size:10px; font-weight:bold; color:{'#262421' if pct_blancas > 15 else '#ffffff'};">
                {txt_eval}
            </div>
        </div>
        <img src="data:image/svg+xml;base64,{b64}" style="width:100%; max-width:340px; border-radius:8px; box-shadow: 0 4px 10px rgba(0,0,0,0.4);"/>
    </div>
    """
    st.markdown(html_contenedor, unsafe_allow_html=True)

@st.cache_resource
def obtener_ruta_stockfish():
    return shutil.which("stockfish") or "/usr/games/stockfish"

# --- MOTOR COMPLETO DE REVISIÓN DIAMANTE ---
def analizar_partida_premium(pgn_texto):
    juego = chess.pgn.read_game(io.StringIO(pgn_texto))
    if not juego:
        return None, None
    tablero = juego.board()
    ruta_sf = obtener_ruta_stockfish()
    
    lista_uci = [m.uci() for m in juego.mainline_moves()]
    nombre_apertura = detectar_apertura(lista_uci)

    datos_jugadas = [{
        "fen": tablero.fen(),
        "fen_previo": tablero.fen(),
        "es_jugador": True,
        "ultimo_mov": None,
        "mejor_mov": None,
        "simbolo": "",
        "jugada_txt": "",
        "mejor_txt": "",
        "titulo": "Inicio de la Partida",
        "color_badge": "#81b64c",
        "explicacion": f"¡Revisión lista! En esta partida se jugó la **{nombre_apertura}**. Toca 'Sig. ➡️' para escuchar el análisis jugada por jugada.",
        "eval_blancas": 0.2,
        "precision": 100.0,
        "fase": "Apertura",
        "es_clave": False,
        "linea_futura": [],
        "opciones_quiz": []
    }]

    conteo_blancas = {"!!": 0, "!": 0, "★": 0, "👍": 0, "📖": 0, "?!": 0, "?": 0, "❌": 0, "??": 0}
    conteo_negras = {"!!": 0, "!": 0, "★": 0, "👍": 0, "📖": 0, "?!": 0, "?": 0, "❌": 0, "??": 0}
    rival_acaba_de_fallar = False

    with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
        infos_prev = motor.analyse(tablero, chess.engine.Limit(depth=10), multipv=2)
        info_top1_prev = infos_prev[0]
        info_top2_prev = infos_prev[1] if len(infos_prev) > 1 else infos_prev[0]

        for num, mov in enumerate(juego.mainline_moves()):
            es_blancas = (tablero.turn == chess.WHITE)
            fen_antes = tablero.fen()
            mat_mio_antes = material_bando(tablero, tablero.turn)
            mat_rival_antes = material_bando(tablero, not tablero.turn)

            mejor_mov_prev = info_top1_prev.get("pv", [mov])[0]
            segundo_mov_prev = info_top2_prev.get("pv", [mov])[0]

            cp_antes_1 = info_top1_prev["score"].pov(tablero.turn).score(mate_score=10000)
            cp_antes_2 = info_top2_prev["score"].pov(tablero.turn).score(mate_score=10000)
            prob_antes_1 = cp_a_probabilidad_ganar(cp_antes_1)
            prob_antes_2 = cp_a_probabilidad_ganar(cp_antes_2)

            texto_jugada_hecha = jugada_en_espanol(tablero, mov)
            texto_mejor_jugada = jugada_en_espanol(tablero, mejor_mov_prev)
            texto_segunda_jugada = jugada_en_espanol(tablero, segundo_mov_prev)

            motivo_tactico = detectar_motivo_tactico(tablero, mov)
            
            # Narrar qué habría pasado con la mejor jugada
            narracion_mejor, pasos_futuros_mejor = narrar_linea_futura(tablero, info_top1_prev.get("pv", []), max_pasos=3)

            tablero.push(mov)
            infos_desp = motor.analyse(tablero, chess.engine.Limit(depth=10), multipv=2)
            info_top1_desp = infos_desp[0]

            cp_desp = -info_top1_desp["score"].pov(tablero.turn).score(mate_score=10000)
            prob_desp = cp_a_probabilidad_ganar(cp_desp)
            eval_blancas = info_top1_desp["score"].white().score(mate_score=10000) / 100.0

            perdida_prob = max(0.0, prob_antes_1 - prob_desp)
            precision_mov = calcular_precision_jugada(perdida_prob)

            # Detectar fase del juego
            piezas_totales = len(tablero.piece_map())
            if num < 10:
                fase = "Apertura"
            elif piezas_totales <= 12:
                fase = "Final"
            else:
                fase = "Medio Juego"

            # Detectar si fue un Sacrificio real (el rival puede capturar material tuyo pero aun así tu posición es muy fuerte)
            es_sacrificio = False
            if "pv" in info_top1_desp and len(info_top1_desp["pv"]) > 0:
                resp_rival = info_top1_desp["pv"][0]
                if tablero.is_capture(resp_rival):
                    pieza_que_cae = tablero.piece_at(resp_rival.to_square)
                    if pieza_que_cae and VALORES_PIEZAS.get(pieza_que_cae.piece_type, 0) >= 3:
                        if perdida_prob < 4.0 and prob_desp > 52.0 and prob_antes_1 < 92.0:
                            es_sacrificio = True

            # Narrar consecuencia si fue un error
            narracion_castigo, pasos_futuros_castigo = narrar_linea_futura(tablero, info_top1_desp.get("pv", []), max_pasos=3)

            # --- CLASIFICACIÓN EXACTA DE LAS 10 INSIGNIAS DE CHESS.COM ---
            if tablero.is_checkmate():
                simbolo, titulo, color = "★", ("🏆 ¡Tu Jaque Mate!" if es_blancas else "🤖 Jaque Mate del Rival"), "#1baca6"
                explicacion = f"¡Partida definida con {texto_jugada_hecha}! {motivo_tactico}"
            elif num < 6 and perdida_prob < 5.0:
                simbolo, titulo, color = "📖", ("📖 Jugada de Libro" if es_blancas else "🤖 Rival: Jugada de Libro"), "#a88865"
                explicacion = f"{'Jugaste' if es_blancas else 'El rival jugó'} {texto_jugada_hecha}, siguiendo la teoría de la **{nombre_apertura}**."
            elif es_sacrificio and perdida_prob < 3.5:
                simbolo, titulo, color = "!!", ("!! ¡Jugada Brillante!" if es_blancas else "🤖 Rival: ¡Brillante!"), "#1baca6"
                explicacion = (
                    f"¡¡Sacrificio Brillante!! Con {texto_jugada_hecha} entregas material a propósito, "
                    f"porque si la secuencia sigue con {narracion_castigo}, quedas con un ataque ganador."
                )
            elif (mov == mejor_mov_prev or perdida_prob < 2.0) and (prob_antes_1 - prob_antes_2 >= 14.0) and len(infos_prev) > 1:
                simbolo, titulo, color = "!", ("! ¡Gran Jugada!" if es_blancas else "🤖 Rival: ¡Gran Jugada!"), "#5c8bb0"
                explicacion = (
                    f"¡Gran jugada! Encontraste {texto_jugada_hecha}, que era la **única jugada buena** en el tablero "
                    f"(cualquier otra como {texto_segunda_jugada} perdía ventaja). {motivo_tactico}"
                )
            elif mov == mejor_mov_prev or perdida_prob < 1.5:
                simbolo, titulo, color = "★", ("★ Mejor Jugada" if es_blancas else "🤖 Rival: Mejor Jugada"), "#81b64c"
                explicacion = f"¡Excelente! {'Hiciste' if es_blancas else 'El rival hizo'} {texto_jugada_hecha}, la jugada número 1 de Stockfish. {motivo_tactico}"
            elif perdida_prob < 5.5:
                simbolo, titulo, color = "👍", ("👍 Buena Jugada" if es_blancas else "🤖 Rival: Jugada Sólida"), "#96bc4b"
                explicacion = f"{'Jugaste' if es_blancas else 'El rival jugó'} {texto_jugada_hecha} manteniendo una buena posición. La línea ideal era {texto_mejor_jugada}."
            elif rival_acaba_de_fallar and perdida_prob >= 12.0 and prob_antes_1 >= 65.0:
                simbolo, titulo, color = "❌", ("❌ Oportunidad Perdida" if es_blancas else "🤖 Rival: Oportunidad Perdida"), "#e05252"
                explicacion = (
                    f"¡Perdonaste al rival! En el turno anterior se había equivocado y tenías la combinación ganadora: "
                    f"**{narracion_mejor}**. Con {texto_jugada_hecha} dejaste escapar esa oportunidad."
                )
            elif perdida_prob < 12.0:
                simbolo, titulo, color = "?!", ("?! Imprecisión" if es_blancas else "🤖 Imprecisión del Rival"), "#f7c631"
                if es_blancas:
                    explicacion = f"Jugaste {texto_jugada_hecha}, que es imprecisa porque permite que {narracion_castigo}. Era mejor jugar {texto_mejor_jugada}."
                else:
                    explicacion = f"Tu rival dudó con {texto_jugada_hecha}. ¡Aprovecha ahora que la continuación fuerte es: {narracion_castigo}!"
            elif perdida_prob < 22.0:
                simbolo, titulo, color = "?", ("? Error" if es_blancas else "🤖 ¡Error de tu Rival!"), "#e6912c"
                if es_blancas:
                    explicacion = f"Cuidado, {texto_jugada_hecha} es un error porque en la secuencia futura {narracion_castigo}. Debías jugar **{texto_mejor_jugada}**."
                else:
                    explicacion = f"¡Tu rival cometió un error con {texto_jugada_hecha}! Puedes castigarlo siguiendo este plan: **{narracion_castigo}**."
            else:
                simbolo, titulo, color = "??", ("?? Error Grave" if es_blancas else "🤖 ¡Regalo Grave del Rival!"), "#ca3431"
                if es_blancas:
                    explicacion = (
                        f"¡Grave error! Con {texto_jugada_hecha} tu probabilidad de ganar cae fuerte porque "
                        f"{narracion_castigo}. La jugada correcta para defenderte era **{texto_mejor_jugada}**."
                    )
                else:
                    explicacion = f"¡¡Tu rival regaló la posición con {texto_jugada_hecha}!! Castígalo de inmediato: **{narracion_castigo}**."

            # Registrar estadísticas
            dic_conteo = conteo_blancas if es_blancas else conteo_negras
            dic_conteo[simbolo] = dic_conteo.get(simbolo, 0) + 1
            rival_acaba_de_fallar = (perdida_prob >= 12.0)

            es_momento_clave = es_blancas and simbolo in ["!!", "!", "?", "❌", "??"]
            linea_mostrar = pasos_futuros_mejor if (es_blancas and perdida_prob >= 6.0) else pasos_futuros_castigo

            opciones_quiz = list(set([texto_mejor_jugada, texto_jugada_hecha, texto_segunda_jugada]))

            datos_jugadas.append({
                "fen": tablero.fen(),
                "fen_previo": fen_antes,
                "es_jugador": es_blancas,
                "ultimo_mov": mov,
                "mejor_mov": mejor_mov_prev if (es_blancas and perdida_prob >= 6.0) else None,
                "simbolo": simbolo,
                "jugada_txt": texto_jugada_hecha,
                "mejor_txt": texto_mejor_jugada,
                "titulo": titulo,
                "color_badge": color,
                "explicacion": explicacion,
                "eval_blancas": max(-10.0, min(10.0, eval_blancas)),
                "precision": precision_mov,
                "fase": fase,
                "es_clave": es_momento_clave,
                "linea_futura": linea_mostrar,
                "opciones_quiz": opciones_quiz
            })
            info_top1_prev = info_top1_desp
            info_top2_prev = infos_desp[1] if len(infos_desp) > 1 else info_top1_desp

    # Calcular resumen general (CAPS %, ELO Estimado y Fases)
    movs_b = [d for d in datos_jugadas[1:] if d["es_jugador"]]
    movs_n = [d for d in datos_jugadas[1:] if not d["es_jugador"]]
    acc_blancas = sum(d["precision"] for d in movs_b) / max(1, len(movs_b))
    acc_negras = sum(d["precision"] for d in movs_n) / max(1, len(movs_n))
    elo_estimado = int(max(400, min(2600, 400 + (acc_blancas ** 1.35) * 3.1)))

    fases_notas = {}
    for f_nom in ["Apertura", "Medio Juego", "Final"]:
        m_fase = [d["precision"] for d in movs_b if d["fase"] == f_nom]
        fases_notas[f_nom] = f"{sum(m_fase)/len(m_fase):.0f}%" if m_fase else "—"

    resumen = {
        "apertura": nombre_apertura,
        "acc_blancas": acc_blancas,
        "acc_negras": acc_negras,
        "elo_estimado": elo_estimado,
        "conteo_b": conteo_blancas,
        "conteo_n": conteo_negras,
        "fases": fases_notas,
        "evals": [d["eval_blancas"] for d in datos_jugadas]
    }
    return datos_jugadas, resumen

# --- RECIBIR PARTIDA DESDE EL TABLERO INTERACTIVO ---
if "analizar_pgn" in st.query_params:
    pgn_recibido = st.query_params["analizar_pgn"]
    st.query_params.clear()
    with st.spinner("💎 Ejecutando Revisión Diamante (Calculando sacrificios, tácticas y precisión con Stockfish)..."):
        jugadas, resumen = analizar_partida_premium(pgn_recibido)
        if jugadas:
            st.session_state["jugadas"] = jugadas
            st.session_state["resumen"] = resumen
            st.session_state["paso"] = 0
            st.session_state["paso_futuro"] = 0
            st.session_state["modo_actual"] = "💎 Revisión de Partida (Paquete Diamante)"

if "modo_actual" not in st.session_state:
    st.session_state["modo_actual"] = "🎮 Jugar contra el Robot (Con Ayudas)"

modo = st.radio(
    "Modo de la App:",
    ["🎮 Jugar contra el Robot (Con Ayudas)", "💎 Revisión de Partida (Paquete Diamante)"],
    index=0 if st.session_state["modo_actual"].startswith("🎮") else 1,
    horizontal=True
)
st.session_state["modo_actual"] = modo

# =========================================================
# MODO 1: JUGAR CONTRA EL ROBOT (DETECTOR DE SACRIFICIOS)
# =========================================================
if modo.startswith("🎮"):
    col1, col2 = st.columns(2)
    with col1:
        nivel_bot = st.selectbox("Nivel del Robot:", [
            "🐣 Principiante (400 ELO)",
            "🦊 Intermedio (1000 ELO)",
            "🦁 Avanzado (1500 ELO)",
            "🤖 Maestro (2200 ELO)"
        ])
    with col2:
        protector_activo = st.toggle("🛡️ Protector Inteligente (Detecta errores y sacrificios)", value=True)

    nivel_num = 1 if "400" in nivel_bot else (2 if "1000" in nivel_bot else (3 if "1500" in nivel_bot else 4))
    icono_bot = nivel_bot.split()[0]
    proteger_js = "true" if protector_activo else "false"

    html_juego = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
        <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
        <script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
        <style>
            body {{ background-color: #302e2b; color: white; font-family: sans-serif; margin: 0; padding: 4px; text-align: center; }}
            .coach {{
                background: #262421; border-radius: 12px; padding: 12px; margin-bottom: 10px;
                border-left: 6px solid #81b64c; display: flex; align-items: center; gap: 12px;
                text-align: left; max-width: 400px; margin-left: auto; margin-right: auto;
                box-shadow: 0 4px 8px rgba(0,0,0,0.3);
            }}
            .coach-danger {{ border-left-color: #ca3431 !important; background: #3a2020 !important; }}
            .coach-brilliant {{ border-left-color: #1baca6 !important; background: #1c3533 !important; }}
            .avatar {{ font-size: 34px; }}
            .msg {{ font-size: 14px; line-height: 1.4; color: #f1f1f1; }}
            #myBoard {{ width: 100%; max-width: 400px; margin: 0 auto; touch-action: none; }}
            .white-1e1d7 {{ background-color: #ebecd0 !important; color: #739552 !important; }}
            .black-3c85d {{ background-color: #739552 !important; color: #ebecd0 !important; }}
            .highlight-sq {{ box-shadow: inset 0 0 3px 3px #f5f682 !important; background-color: #f5f682 !important; }}
            .dot-sq {{ background-image: radial-gradient(rgba(20, 20, 20, 0.38) 19%, rgba(0, 0, 0, 0) 22%) !important; }}
            .capture-sq {{ box-shadow: inset 0 0 0 5px rgba(202, 52, 49, 0.65) !important; }}
            .btn-row {{ display: flex; gap: 8px; justify-content: center; max-width: 400px; margin: 12px auto 6px auto; }}
            button {{
                flex: 1; padding: 10px; border: none; border-radius: 8px; font-weight: bold;
                font-size: 14px; cursor: pointer; color: white; background: #454341;
            }}
            .btn-green {{ background: #81b64c; font-size: 15px; padding: 12px; width: 100%; max-width: 400px; margin: 6px auto; display: block; }}
            .btn-warning {{ background: #e6912c; font-size: 14px; padding: 10px; width: 100%; max-width: 400px; margin: 6px auto; display: none; }}
            #pgnBox {{
                display: none; background: #1e1c1a; padding: 12px; border-radius: 10px;
                max-width: 400px; margin: 10px auto; border: 1px solid #81b64c;
            }}
            textarea {{ width: 92%; height: 60px; background: #302e2b; color: white; border: 1px solid #555; border-radius: 6px; padding: 6px; }}
        </style>
    </head>
    <body>
        <div class="coach" id="coachCard">
            <div class="avatar" id="coachAvatar">{icono_bot}</div>
            <div class="msg" id="statusMsg">
                <b>¡Tablero Diamante listo!</b> Toca cualquier pieza blanca para ver sus puntitos de movimiento y capturas.
            </div>
        </div>

        <button class="btn-warning" id="btnCorregir" onclick="deshacerBlunder()">
            🛡️ ¡Corregir mi jugada y salvar mi pieza!
        </button>

        <div id="myBoard"></div>

        <div class="btn-row">
            <button onclick="deshacer()">↩️ Deshacer</button>
            <button onclick="darPista()">💡 Pista</button>
            <button onclick="reiniciar()">🔄 Reiniciar</button>
        </div>

        <button class="btn-green" onclick="mostrarAnalisis()">💎 Terminar y Abrir Revisión Diamante</button>

        <div id="pgnBox">
            <div style="font-size:13px; margin-bottom:6px; color:#96bc4b;">
                <b>¡Partida lista!</b> Copia este texto y pégalo en la pestaña 'Revisión de Partida':
            </div>
            <textarea id="pgnText" readonly></textarea>
            <button class="btn-green" style="margin-top:6px;" onclick="copiarYEnviar()">📋 Copiar Partida para el Narrador</button>
        </div>

        <script>
            var board = null;
            var game = new Chess();
            var botLevel = {nivel_num};
            var protector = {proteger_js};
            var selectedSq = null;

            var sndMove = new Audio('https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/move-self.mp3');
            var sndCapture = new Audio('https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/capture.mp3');
            var sndCheck = new Audio('https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/move-check.mp3');
            var sndIllegal = new Audio('https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/illegal.mp3');
            var sndGameEnd = new Audio('https://images.chesscomfiles.com/chess-themes/sounds/_MP3_/default/game-end.mp3');

            function playSound(moveObj) {{
                try {{
                    if (game.game_over()) sndGameEnd.play();
                    else if (game.in_check()) sndCheck.play();
                    else if (moveObj && moveObj.captured) sndCapture.play();
                    else sndMove.play();
                }} catch(e) {{}}
            }}

            var valores = {{ p: 100, n: 320, b: 330, r: 500, q: 900, k: 20000 }};
            function nombrePieza(p) {{
                var n = {{ p: 'peón', n: 'caballo', b: 'alfil', r: 'torre', q: 'Dama (Reina)', k: 'Rey' }};
                return n[p] || 'pieza';
            }}

            function limpiarResaltado() {{
                $('#myBoard .square-55d63').removeClass('highlight-sq dot-sq capture-sq');
            }}

            function mostrarPuntitos(sq) {{
                limpiarResaltado();
                var moves = game.moves({{ square: sq, verbose: true }});
                if (moves.length === 0) return;
                $('#myBoard .square-' + sq).addClass('highlight-sq');
                for (var i = 0; i < moves.length; i++) {{
                    if (moves[i].captured) $('#myBoard .square-' + moves[i].to).addClass('capture-sq');
                    else $('#myBoard .square-' + moves[i].to).addClass('dot-sq');
                }}
            }}

            function verificarFinDeJuego() {{
                if (!game.game_over()) return false;
                document.getElementById('btnCorregir').style.display = 'none';
                document.getElementById('coachCard').classList.remove('coach-danger');
                if (game.in_checkmate()) {{
                    if (game.turn() === 'b') {{
                        document.getElementById('coachCard').classList.add('coach-brilliant');
                        document.getElementById('statusMsg').innerHTML =
                            "🏆 <b>¡JAQUE MATE! ¡Ganaste la partida!</b> 🎉<br>Toca el botón verde abajo para abrir tu Revisión Diamante.";
                    }} else {{
                        document.getElementById('coachCard').classList.add('coach-danger');
                        document.getElementById('statusMsg').innerHTML =
                            "🏁 <b>¡Jaque Mate del Robot!</b><br>Toca el botón verde abajo para ver tu Revisión Diamante.";
                    }}
                }} else {{
                    document.getElementById('statusMsg').innerHTML =
                        "🤝 <b>¡Partida en Tablas (Empate)!</b> Toca el botón verde abajo para analizarla.";
                }}
                return true;
            }}

            function evaluarTablero(g) {{
                if (g.in_checkmate()) return g.turn() === 'w' ? -99999 : 99999;
                if (g.in_draw()) return 0;
                var total = 0;
                var b = g.board();
                for (var r = 0; r < 8; r++) {{
                    for (var c = 0; c < 8; c++) {{
                        var p = b[r][c];
                        if (p) {{
                            var val = valores[p.type];
                            if ((r === 3 || r === 4) && (c === 3 || c === 4)) val += 25;
                            total += (p.color === 'w' ? val : -val);
                        }}
                    }}
                }}
                return total;
            }}

            function minimax(g, depth, alpha, beta, isMax) {{
                if (depth === 0 || g.game_over()) return evaluarTablero(g);
                var moves = g.moves();
                if (isMax) {{
                    var maxEval = -1000000;
                    for (var i = 0; i < moves.length; i++) {{
                        g.move(moves[i]);
                        var ev = minimax(g, depth - 1, alpha, beta, false);
                        g.undo();
                        if (ev > maxEval) maxEval = ev;
                        if (ev > alpha) alpha = ev;
                        if (beta <= alpha) break;
                    }}
                    return maxEval;
                }} else {{
                    var minEval = 1000000;
                    for (var i = 0; i < moves.length; i++) {{
                        g.move(moves[i]);
                        var ev = minimax(g, depth - 1, alpha, beta, true);
                        g.undo();
                        if (ev < minEval) minEval = ev;
                        if (ev < beta) beta = ev;
                        if (beta <= alpha) break;
                    }}
                    return minEval;
                }}
            }}

            // Analiza 3 jugadas en el futuro para distinguir un Error de un Sacrificio Brillante
            function analizarPeligroOSacrificio() {{
                if (!protector || game.game_over()) return {{ tipo: 'ok' }};
                var evalEstaticaAhora = evaluarTablero(game);
                var respuestasRival = game.moves({{ verbose: true }});
                var peorAmenaza = null;
                var peorCaida = 0;
                var esSacrificioGanador = false;

                for (var i = 0; i < respuestasRival.length; i++) {{
                    var r = respuestasRival[i];
                    if (r.captured && (valores[r.captured] || 0) >= 300) {{
                        game.move(r);
                        // Mirar 2 jugadas más adelante tras la captura del rival
                        var evalFuturaTrasCaptura = minimax(game, 2, -1000000, 1000000, true);
                        game.undo();

                        var caidaReal = evalEstaticaAhora - evalFuturaTrasCaptura;
                        if (caidaReal >= 260 && caidaReal > peorCaida) {{
                            peorCaida = caidaReal;
                            peorAmenaza = r;
                        }} else if (evalFuturaTrasCaptura >= evalEstaticaAhora + 200) {{
                            esSacrificioGanador = true;
                        }}
                    }}
                }}
                if (peorAmenaza) return {{ tipo: 'error', amenaza: peorAmenaza }};
                if (esSacrificioGanador) return {{ tipo: 'sacrificio' }};
                return {{ tipo: 'ok' }};
            }}

            function elegirJugadaBot() {{
                var moves = game.moves({{ verbose: true }});
                if (moves.length === 0) return null;
                if (botLevel === 1 && Math.random() < 0.45) {{
                    return moves[Math.floor(Math.random() * moves.length)];
                }}
                var depth = botLevel === 1 ? 1 : (botLevel === 2 ? 2 : 3);
                var isWhite = game.turn() === 'w';
                var bestMove = moves[0];
                var bestVal = isWhite ? -1000000 : 1000000;
                moves.sort(function() {{ return 0.5 - Math.random(); }});
                for (var i = 0; i < moves.length; i++) {{
                    game.move(moves[i]);
                    var val = minimax(game, depth - 1, -1000000, 1000000, !isWhite);
                    game.undo();
                    if (isWhite && val > bestVal) {{ bestVal = val; bestMove = moves[i]; }}
                    if (!isWhite && val < bestVal) {{ bestVal = val; bestMove = moves[i]; }}
                }}
                return bestMove;
            }}

            function turnoBot() {{
                if (verificarFinDeJuego()) return;
                var m = elegirJugadaBot();
                if (m) {{
                    var res = game.move(m);
                    board.position(game.fen());
                    playSound(res);
                    if (verificarFinDeJuego()) return;
                    var texto = "Moví mi <b>" + nombrePieza(res.piece) + " a " + res.to + "</b>.";
                    if (res.captured) texto = "Capturé tu <b>" + nombrePieza(res.captured) + " en " + res.to + "</b>.";
                    if (game.in_check()) texto += " <b>¡Estás en jaque!</b>";
                    else texto += " ¡Te toca!";
                    document.getElementById('coachCard').classList.remove('coach-danger', 'coach-brilliant');
                    document.getElementById('statusMsg').innerHTML = texto;
                }}
            }}

            function procesarJugadaUsuario(move) {{
                limpiarResaltado();
                selectedSq = null;
                board.position(game.fen());
                playSound(move);

                if (verificarFinDeJuego()) return;

                var evaluacion = analizarPeligroOSacrificio();
                if (evaluacion.tipo === 'error') {{
                    var p = evaluacion.amenaza;
                    try {{ sndIllegal.play(); }} catch(e) {{}}
                    document.getElementById('coachCard').classList.add('coach-danger');
                    document.getElementById('btnCorregir').style.display = 'block';
                    $('#myBoard .square-' + p.to).addClass('capture-sq');
                    document.getElementById('statusMsg').innerHTML =
                        "🚨 <b>¡CUIDADO!</b> Con esa jugada pierdes tu <b>" + nombrePieza(p.captured) +
                        " en " + p.to + "</b> sin compensación táctica.<br>Toca el botón naranja abajo para salvarla.";
                    return;
                }} else if (evaluacion.tipo === 'sacrificio') {{
                    document.getElementById('coachCard').classList.add('coach-brilliant');
                    document.getElementById('statusMsg').innerHTML =
                        "🔥 <b>¡¡Sacrificio Táctico detectado!!</b> Entregas material pero tienes una continuación ganadora...";
                }} else {{
                    document.getElementById('coachCard').classList.remove('coach-danger', 'coach-brilliant');
                    document.getElementById('statusMsg').innerHTML = "Pensando mi respuesta...";
                }}

                document.getElementById('btnCorregir').style.display = 'none';
                window.setTimeout(turnoBot, 450);
            }}

            function deshacerBlunder() {{
                if (game.history().length >= 1 && game.turn() === 'b') {{
                    game.undo();
                    board.position(game.fen());
                    limpiarResaltado();
                    document.getElementById('btnCorregir').style.display = 'none';
                    document.getElementById('coachCard').classList.remove('coach-danger');
                    document.getElementById('statusMsg').innerHTML = "🛡️ <b>¡Pieza salvada!</b> Elige otra casilla más segura.";
                }}
            }}

            function onDragStart(source, piece) {{
                if (game.game_over()) return false;
                if (piece.search(/^b/) !== -1) return false;
                mostrarPuntitos(source);
            }}

            function onDrop(source, target) {{
                if (source === target) return;
                var move = game.move({{ from: source, to: target, promotion: 'q' }});
                if (move === null) {{
                    try {{ sndIllegal.play(); }} catch(e) {{}}
                    var msgIlegal = "⚠️ <b>Movimiento ilegal:</b> Esa pieza no puede ir a " + target + ".";
                    if (game.in_check()) msgIlegal = "⚠️ <b>¡Tu Rey está en jaque!</b> Debes defender a tu Rey.";
                    document.getElementById('statusMsg').innerHTML = msgIlegal;
                    return 'snapback';
                }}
                procesarJugadaUsuario(move);
            }}

            function onSnapEnd() {{ board.position(game.fen()); }}

            board = Chessboard('myBoard', {{
                draggable: true,
                position: 'start',
                pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{{piece}}.png',
                onDragStart: onDragStart,
                onDrop: onDrop,
                onSnapEnd: onSnapEnd
            }});

            $('#myBoard').on('click', '.square-55d63', function() {{
                if (game.game_over() || game.turn() !== 'w') return;
                var sq = $(this).attr('data-square');
                if (!sq) return;
                if (selectedSq && selectedSq !== sq) {{
                    var move = game.move({{ from: selectedSq, to: sq, promotion: 'q' }});
                    if (move !== null) {{ procesarJugadaUsuario(move); return; }}
                }}
                var piece = game.get(sq);
                if (piece && piece.color === 'w') {{
                    selectedSq = sq;
                    mostrarPuntitos(sq);
                }} else {{
                    limpiarResaltado();
                    selectedSq = null;
                }}
            }});

            function deshacer() {{
                document.getElementById('btnCorregir').style.display = 'none';
                document.getElementById('coachCard').classList.remove('coach-danger', 'coach-brilliant');
                if (game.turn() === 'b' && game.history().length >= 1) game.undo();
                else if (game.history().length >= 2) {{ game.undo(); game.undo(); }}
                board.position(game.fen());
                limpiarResaltado();
                document.getElementById('statusMsg').innerHTML = "↩️ Jugada deshecha.";
            }}

            function darPista() {{
                if (game.game_over()) return;
                var m = elegirJugadaBot();
                if (m) {{
                    limpiarResaltado();
                    $('#myBoard .square-' + m.from).addClass('highlight-sq');
                    $('#myBoard .square-' + m.to).addClass('highlight-sq');
                    document.getElementById('statusMsg').innerHTML = "💡 <b>Pista:</b> Mueve tu <b>" + nombrePieza(m.piece) + " de " + m.from + " a " + m.to + "</b>.";
                }}
            }}

            function reiniciar() {{
                game.reset();
                board.start();
                limpiarResaltado();
                document.getElementById('btnCorregir').style.display = 'none';
                document.getElementById('coachCard').classList.remove('coach-danger', 'coach-brilliant');
                document.getElementById('pgnBox').style.display = 'none';
                document.getElementById('statusMsg').innerHTML = "🔄 ¡Partida nueva!";
            }}

            function mostrarAnalisis() {{
                if (game.history().length === 0) {{
                    document.getElementById('statusMsg').innerHTML = "⚠️ ¡Haz al menos una jugada antes de analizar!";
                    return;
                }}
                var pgn = game.pgn();
                document.getElementById('pgnText').value = pgn;
                document.getElementById('pgnBox').style.display = 'block';
                try {{
                    var url = new URL(window.parent.location.href);
                    url.searchParams.set('analizar_pgn', pgn);
                    window.parent.location.href = url.toString();
                }} catch(e) {{}}
            }}

            function copiarYEnviar() {{
                var copyText = document.getElementById("pgnText");
                copyText.select();
                document.execCommand("copy");
                document.getElementById('statusMsg').innerHTML = "✅ <b>¡Copiado!</b> Toca arriba la pestaña <b>'💎 Revisión de Partida'</b>.";
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_juego, height=670, scrolling=True)

# =========================================================
# MODO 2: REVISIÓN DE PARTIDA (PAQUETE DIAMANTE COMPLETO)
# =========================================================
else:
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        voz_elegida = st.selectbox("Voz del Entrenador:", list(VOCES_HUMANAS.keys()))
    with col_v2:
        activar_voz = st.toggle("🔊 Narrador con voz humana", value=True)

    with st.expander("📥 Pegar o cargar otra partida (PGN)", expanded=("jugadas" not in st.session_state)):
        pgn_manual = st.text_area("Pega aquí la partida (PGN):", height=75, placeholder="1. e4 e5 2. Nf3 Nc6...")
        if st.button("💎 Ejecutar Revisión Diamante", type="primary", use_container_width=True) and pgn_manual.strip():
            with st.spinner("💎 Analizando sacrificios, precisión CAPS, ELO estimado y aperturas..."):
                jugadas, resumen = analizar_partida_premium(pgn_manual)
                if jugadas:
                    st.session_state["jugadas"] = jugadas
                    st.session_state["resumen"] = resumen
                    st.session_state["paso"] = 0
                    st.session_state["paso_futuro"] = 0
                    st.rerun()

    if "jugadas" in st.session_state and "resumen" in st.session_state:
        res = st.session_state["resumen"]
        paso = st.session_state.get("paso", 0)
        total = len(st.session_state["jugadas"]) - 1
        actual = st.session_state["jugadas"][paso]

        # 1. Banner con el Nombre Oficial de la Apertura en Español
        st.markdown(f'<div class="opening-banner">📘 Apertura jugada: <b>{res["apertura"]}</b> | Fase actual: <b>{actual["fase"]}</b></div>', unsafe_allow_html=True)

        # 2. Tarjeta Desplegable de Resumen Premium (Precisión %, ELO Estimado, Fases y Gráfico)
        with st.expander(f"📊 Ver Reporte General (Tu Precisión: {res['acc_blancas']:.1f}% | ELO Estimado: {res['elo_estimado']})", expanded=(paso == 0)):
            st.markdown(f"""
            <div class="summary-card">
                <div style="display:flex; justify-content:space-around; font-size:16px; margin-bottom:8px;">
                    <div>⚪ <b>Tú (Blancas):</b> {res['acc_blancas']:.1f}%</div>
                    <div>⚫ <b>Rival (Negras):</b> {res['acc_negras']:.1f}%</div>
                </div>
                <div class="elo-badge">🏆 Jugaste como un ELO de: {res['elo_estimado']}</div>
                <div style="margin-top:10px; font-size:13px; color:#ccc;">
                    <b>Notas por Fase:</b> Apertura: {res['fases']['Apertura']} | Medio Juego: {res['fases']['Medio Juego']} | Final: {res['fases']['Final']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            cb, cn = res["conteo_b"], res["conteo_n"]
            st.markdown(f"""
            | Insignia | ⚪ Tú | ⚫ Rival |
            | :--- | :---: | :---: |
            | **!! Brillante** | {cb['!!']} | {cn['!!']} |
            | **! Gran Jugada** | {cb['!']} | {cn['!']} |
            | **★ Mejor Jugada** | {cb['★']} | {cn['★']} |
            | **👍 Buena / Libro** | {cb['👍'] + cb['📖']} | {cn['👍'] + cn['📖']} |
            | **?! Imprecisión** | {cb['?!']} | {cn['?!']} |
            | **? Error / ❌ Perdida** | {cb['?'] + cb['❌']} | {cn['?'] + cn['❌']} |
            | **?? Error Grave** | {cb['??']} | {cn['??']} |
            """)
            st.caption("📈 Gráfico de Ventaja de la Partida (Arriba = Ventaja Blanca, Abajo = Ventaja Negra):")
            st.line_chart(res["evals"], height=140)

        # 3. Modo "Reintentar Error" (Adivinar la mejor jugada antes de ver la respuesta)
        es_error_jugador = actual["es_jugador"] and actual["simbolo"] in ["?", "❌", "??"]
        modo_quiz = st.toggle("🧩 Retarme a adivinar la jugada correcta cuando cometo un error", value=False)

        mostrar_solucion = True
        if modo_quiz and es_error_jugador and not st.session_state.get(f"resuelto_{paso}", False):
            mostrar_solucion = False
            st.warning(f"🤔 **¡Momento de aprendizaje!** Tu jugada ({actual['jugada_txt']}) fue **{actual['titulo']}**. ¿Cuál crees que era la mejor jugada en esta posición?")
            eleccion = st.radio("Elige la jugada correcta:", actual["opciones_quiz"], key=f"quiz_{paso}")
            if st.button("✅ Comprobar mi respuesta", use_container_width=True):
                if eleccion == actual["mejor_txt"]:
                    st.success("🎉 ¡Correcto! Encontraste la mejor jugada de Stockfish.")
                else:
                    st.error(f"Casi... La mejor jugada era **{actual['mejor_txt']}**.")
                st.session_state[f"resuelto_{paso}"] = True
                st.rerun()

        # 4. Caja del Entrenador + Voz Humana Neuronal
        if mostrar_solucion:
            icono_turno = "🧑‍🏫" if actual.get("es_jugador", True) else "🤖"
            st.markdown(f"""
            <div class="coach-box" style="border-left-color: {actual['color_badge']};">
                <div class="coach-avatar">{icono_turno}</div>
                <div class="coach-text">
                    <span class="badge" style="background-color: {actual['color_badge']}; color: #fff;">
                        {actual['titulo']}
                    </span><br>
                    {actual['explicacion']}
                </div>
            </div>
            """, unsafe_allow_html=True)

            if activar_voz:
                texto_limpio = f"{actual['titulo']}. {actual['explicacion']}".replace("!", "").replace("?", "").replace("★", "").replace("*", "")
                audio_mp3 = generar_audio_humano(texto_limpio, VOCES_HUMANAS[voz_elegida])
                st.audio(audio_mp3, format="audio/mp3", autoplay=True)

        # 5. Tablero con Barra de Evaluación Lateral + Ícono en Casilla + Botón "Mostrar Jugadas"
        paso_futuro = st.session_state.get("paso_futuro", 0)
        linea_futura = actual.get("linea_futura", [])

        if paso_futuro > 0 and paso_futuro <= len(linea_futura):
            estado_fut = linea_futura[paso_futuro - 1]
            st.info(f"📽️ **Viendo secuencia futura ({paso_futuro}/{len(linea_futura)}):** {estado_fut['texto']}")
            dibujar_tablero_premium(
                chess.Board(estado_fut["fen"]),
                eval_peones=actual["eval_blancas"],
                ultimo_mov=estado_fut["mov"],
                simbolo_badge="▶",
                color_badge="#5c8bb0"
            )
        else:
            dibujar_tablero_premium(
                chess.Board(actual["fen"]),
                eval_peones=actual["eval_blancas"],
                ultimo_mov=actual["ultimo_mov"],
                mejor_mov=actual["mejor_mov"] if mostrar_solucion else None,
                simbolo_badge=actual["simbolo"],
                color_badge=actual["color_badge"]
            )

        # Botón interactivo "Mostrar Jugadas" (Ver la línea futura sobre el tablero)
        if len(linea_futura) > 0 and mostrar_solucion:
            cf1, cf2 = st.columns(2)
            with cf1:
                if st.button("📽️ Mostrar qué pasaba (Avanzar línea)", use_container_width=True):
                    st.session_state["paso_futuro"] = (paso_futuro + 1) if paso_futuro < len(linea_futura) else 0
                    st.rerun()
            with cf2:
                if paso_futuro > 0 and st.button("↩️ Volver a la jugada real", use_container_width=True):
                    st.session_state["paso_futuro"] = 0
                    st.rerun()

        # 6. Controles de Navegación + Botón "Saltar al Siguiente Momento Clave"
        st.write(f"**Jugada {paso} de {total}**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("⏮️", use_container_width=True) and paso > 0:
                st.session_state["paso"] = 0
                st.session_state["paso_futuro"] = 0
                st.rerun()
        with col2:
            if st.button("⬅️ Ant.", use_container_width=True) and paso > 0:
                st.session_state["paso"] -= 1
                st.session_state["paso_futuro"] = 0
                st.rerun()
        with col3:
            if st.button("Sig. ➡️", type="primary", use_container_width=True) and paso < total:
                st.session_state["paso"] += 1
                st.session_state["paso_futuro"] = 0
                st.rerun()
        with col4:
            if st.button("⏭️", use_container_width=True) and paso < total:
                st.session_state["paso"] = total
                st.session_state["paso_futuro"] = 0
                st.rerun()

        if st.button("🎯 Saltar a mi siguiente Momento Clave (Brillante / Error)", use_container_width=True):
            claves = [i for i, d in enumerate(st.session_state["jugadas"]) if i > paso and d.get("es_clave", False)]
            if claves:
                st.session_state["paso"] = claves[0]
            else:
                claves_inicio = [i for i, d in enumerate(st.session_state["jugadas"]) if d.get("es_clave", False)]
                if claves_inicio:
                    st.session_state["paso"] = claves_inicio[0]
            st.session_state["paso_futuro"] = 0
            st.rerun()
