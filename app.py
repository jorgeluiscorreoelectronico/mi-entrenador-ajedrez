import streamlit as st
import chess
import chess.pgn
import chess.svg
import chess.engine
import requests
import io
import shutil
import base64
import random
from gtts import gTTS

st.set_page_config(page_title="Mi Ajedrez & Entrenador", page_icon="♟️", layout="centered")

# --- ESTILOS VISUALES TIPO CHESS.COM ---
st.markdown("""
<style>
    .stApp { background-color: #302e2b; color: white; }
    .coach-box {
        background-color: #262421;
        border-radius: 12px;
        padding: 14px;
        margin-bottom: 12px;
        border-left: 6px solid #81b64c;
        display: flex;
        align-items: center;
        gap: 12px;
        box-shadow: 0 4px 8px rgba(0,0,0,0.3);
    }
    .coach-avatar { font-size: 38px; }
    .coach-text { font-size: 15px; line-height: 1.4; color: #f1f1f1; }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-weight: bold;
        font-size: 13px;
        margin-bottom: 4px;
    }
</style>
""", unsafe_allow_html=True)

# --- DICCIONARIOS EN ESPAÑOL ---
NOMBRES_PIEZAS = {
    chess.PAWN: "el peón", chess.KNIGHT: "el caballo",
    chess.BISHOP: "el alfil", chess.ROOK: "la torre",
    chess.QUEEN: "la dama", chess.KING: "el rey"
}

ICONOS_PIEZAS = {
    chess.PAWN: "♟️ Peón", chess.KNIGHT: "🐴 Caballo",
    chess.BISHOP: "♝ Alfil", chess.ROOK: "🏰 Torre",
    chess.QUEEN: "👑 Dama", chess.KING: "🤴 Rey"
}

BOTS = {
    "🐣 Bot Benito (Principiante - 400 ELO)": {"skill": 0, "depth": 1, "azar": 0.35, "icono": "🐣"},
    "🦊 Bot Sofía (Intermedio - 1000 ELO)": {"skill": 4, "depth": 3, "azar": 0.10, "icono": "🦊"},
    "🦁 Bot Mateo (Avanzado - 1500 ELO)": {"skill": 10, "depth": 6, "azar": 0.0, "icono": "🦁"},
    "🤖 Stockfish Maestro (Máximo - 2500 ELO)": {"skill": 20, "depth": 12, "azar": 0.0, "icono": "🤖"}
}

def jugada_en_espanol(board, move):
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
            texto = f"captura de peón al paso en {casilla_destino}"
    
    board_copia = board.copy()
    board_copia.push(move)
    if board_copia.is_checkmate():
        texto += " dando ¡jaque mate!"
    elif board_copia.is_check():
        texto += " dando jaque"
    return texto

def dibujar_tablero(board, orientacion=chess.WHITE, ultimo_mov=None, mejor_mov=None):
    flechas = []
    if mejor_mov:
        flechas.append(chess.svg.Arrow(mejor_mov.from_square, mejor_mov.to_square, color="#81b64c"))
    svg_tablero = chess.svg.board(
        board=board,
        orientation=orientacion,
        lastmove=ultimo_mov,
        arrows=flechas,
        size=360,
        colors={
            "square light": "#ebecd0",
            "square dark": "#739552",
            "square light lastmove": "#f5f682",
            "square dark lastmove": "#b9ca43"
        }
    )
    b64 = base64.b64encode(svg_tablero.encode("utf-8")).decode("utf-8")
    st.markdown(f'<div style="text-align:center;"><img src="data:image/svg+xml;base64,{b64}" style="width:100%; max-width:380px; border-radius:8px;"/></div>', unsafe_allow_html=True)

@st.cache_resource
def obtener_ruta_stockfish():
    return shutil.which("stockfish") or "/usr/games/stockfish"

def mover_robot(board, config_bot):
    if board.is_game_over():
        return None
    movs_legales = list(board.legal_moves)
    if random.random() < config_bot["azar"]:
        mov = random.choice(movs_legales)
    else:
        ruta_sf = obtener_ruta_stockfish()
        with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
            motor.configure({"Skill Level": config_bot["skill"]})
            res = motor.play(board, chess.engine.Limit(depth=config_bot["depth"], time=0.3))
            mov = res.move
    texto = jugada_en_espanol(board, mov)
    board.push(mov)
    return texto

def analizar_partida(pgn_texto):
    juego = chess.pgn.read_game(io.StringIO(pgn_texto))
    if not juego:
        return None, None
    tablero = juego.board()
    ruta_sf = obtener_ruta_stockfish()
    
    datos_jugadas = [{
        "fen": tablero.fen(),
        "ultimo_mov": None,
        "mejor_mov": None,
        "titulo": "Inicio de la partida",
        "color_badge": "#81b64c",
        "explicacion": "¡Hola! Soy tu entrenador. Toca 'Sig. ➡️' abajo del tablero para repasar tu partida jugada por jugada.",
        "eval_blancas": 0.2
    }]
    
    with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
        info_prev = motor.analyse(tablero, chess.engine.Limit(depth=12))
        
        for num, mov in enumerate(juego.mainline_moves()):
            mejor_mov_prev = info_prev.get("pv", [mov])[0]
            score_antes = info_prev["score"].pov(tablero.turn).score(mate_score=10000) / 100.0
            texto_jugada_hecha = jugada_en_espanol(tablero, mov)
            texto_mejor_jugada = jugada_en_espanol(tablero, mejor_mov_prev)
            
            tablero.push(mov)
            info_desp = motor.analyse(tablero, chess.engine.Limit(depth=12))
            
            score_desp = - (info_desp["score"].pov(tablero.turn).score(mate_score=10000) / 100.0)
            eval_blancas = info_desp["score"].white().score(mate_score=10000) / 100.0
            perdida = max(0.0, score_antes - score_desp)
            
            amenaza_rival = ""
            if "pv" in info_desp and len(info_desp["pv"]) > 0:
                mov_rival = info_desp["pv"][0]
                amenaza_rival = jugada_en_espanol(tablero, mov_rival)

            if num < 6 and perdida < 0.35:
                titulo, color = "📖 Jugada de Libro", "#a88865"
                explicacion = f"Jugaste {texto_jugada_hecha}. Es una jugada teórica de apertura para desarrollar tus piezas."
            elif mov == mejor_mov_prev:
                if perdida == 0 and score_desp > score_antes + 1.5:
                    titulo, color = "!! Jugada Brillante", "#1baca6"
                    explicacion = f"¡Increíble! Encontraste {texto_jugada_hecha}, la jugada más fuerte para castigar a tu rival."
                else:
                    titulo, color = "★ Mejor Jugada", "#81b64c"
                    explicacion = f"¡Muy bien! Hiciste {texto_jugada_hecha}, exactamente la mejor jugada en esta posición."
            elif perdida < 0.35:
                titulo, color = "👍 Excelente Jugada", "#96bc4b"
                explicacion = f"Jugaste {texto_jugada_hecha}, una buena decisión que mantiene sólida tu posición. Otra opción era {texto_mejor_jugada}."
            elif perdida < 0.9:
                titulo, color = "?! Imprecisión", "#f7c631"
                explicacion = f"Jugaste {texto_jugada_hecha}, que es imprecisa porque permite al rival responder con {amenaza_rival}. Era mejor {texto_mejor_jugada}."
            elif perdida < 2.0:
                titulo, color = "? Error", "#e6912c"
                explicacion = f"Cuidado, jugar {texto_jugada_hecha} es un error que empeora tu posición, ya que tu oponente ahora tiene {amenaza_rival}. Debías jugar {texto_mejor_jugada}."
            else:
                titulo, color = "?? Error Grave", "#ca3431"
                explicacion = f"¡Grave error! Con {texto_jugada_hecha} pierdes mucha ventaja porque permites que el rival haga {amenaza_rival}. Era necesario jugar {texto_mejor_jugada}."

            datos_jugadas.append({
                "fen": tablero.fen(),
                "ultimo_mov": mov,
                "mejor_mov": mejor_mov_prev if perdida >= 0.4 else None,
                "titulo": titulo,
                "color_badge": color,
                "explicacion": explicacion,
                "eval_blancas": max(-10.0, min(10.0, eval_blancas))
            })
            info_prev = info_desp
            
    return datos_jugadas, juego.headers

# --- INICIALIZAR VARIABLES DE PARTIDA ---
if "tablero_bot" not in st.session_state:
    st.session_state["tablero_bot"] = chess.Board()
    st.session_state["color_jugador"] = chess.WHITE
    st.session_state["mensaje_bot"] = "¡Hola! Elige tu pieza abajo y haz tu primera jugada."
    st.session_state["pista_mov"] = None

# --- NAVEGACIÓN PRINCIPAL ---
modo = st.radio(
    "Modo de la App:",
    ["🎮 Jugar contra el Robot", "🧑‍🏫 Revisión de Partida (Con Narrador)"],
    horizontal=True
)

# ==========================================
# MODO 1: JUGAR CONTRA EL ROBOT
# ==========================================
if modo == "🎮 Jugar contra el Robot":
    with st.expander("⚙️ Configurar Robot o Reiniciar Partida", expanded=False):
        bot_elegido = st.selectbox("Elige tu rival:", list(BOTS.keys()), index=0)
        color_str = st.radio("Tu color:", ["⚪ Blancas", "⚫ Negras"], horizontal=True)
        if st.button("🔄 Empezar Nueva Partida", type="primary", use_container_width=True):
            st.session_state["tablero_bot"] = chess.Board()
            st.session_state["color_jugador"] = chess.WHITE if "Blancas" in color_str else chess.BLACK
            st.session_state["pista_mov"] = None
            if st.session_state["color_jugador"] == chess.BLACK:
                txt = mover_robot(st.session_state["tablero_bot"], BOTS[bot_elegido])
                st.session_state["mensaje_bot"] = f"Empecé yo jugando {txt}. ¡Es tu turno!"
            else:
                st.session_state["mensaje_bot"] = "¡Nueva partida! Juegas con Blancas, haz tu primer movimiento."
            st.rerun()
    
    bot_actual = BOTS[st.session_state.get("bot_elegido", list(BOTS.keys())[0])] if "bot_elegido" in st.session_state else BOTS[bot_elegido]
    tablero = st.session_state["tablero_bot"]
    ultimo_mov = tablero.peek() if len(tablero.move_stack) > 0 else None

    # Caja de diálogo del Robot / Entrenador en vivo
    st.markdown(f"""
    <div class="coach-box">
        <div class="coach-avatar">{bot_actual['icono']}</div>
        <div class="coach-text">
            <span class="badge" style="background-color: #81b64c; color: #fff;">Partida en vivo</span><br>
            {st.session_state['mensaje_bot']}
        </div>
    </div>
    """, unsafe_allow_html=True)

    dibujar_tablero(tablero, orientacion=st.session_state["color_jugador"], ultimo_mov=ultimo_mov, mejor_mov=st.session_state.get("pista_mov"))

    # Verificar si terminó la partida
    if tablero.is_game_over():
        if tablero.is_checkmate():
            ganador = "¡Ganaste por Jaque Mate! 🎉" if tablero.turn != st.session_state["color_jugador"] else "El Robot ganó por Jaque Mate."
        else:
            ganador = "La partida terminó en Tablas (Empate)."
        st.success(f"🏁 **Fin de la partida:** {ganador}")
    else:
        # Controles sencillos para mover desde el celular sin escribir
        movs_legales = [m for m in tablero.legal_moves if m.promotion in (None, chess.QUEEN)]
        casillas_origen = sorted(list(set(m.from_square for m in movs_legales)))
        
        def etiqueta_origen(sq):
            p = tablero.piece_at(sq)
            return f"{ICONOS_PIEZAS.get(p.piece_type, 'Pieza')} en {chess.square_name(sq)}"

        col_a, col_b = st.columns(2)
        with col_a:
            origen_sq = st.selectbox("1️⃣ Pieza a mover:", casillas_origen, format_func=etiqueta_origen)
        
        movs_desde_origen = [m for m in movs_legales if m.from_square == origen_sq]
        
        def etiqueta_destino(m):
            if tablero.is_castling(m):
                return "🏰 Enroque"
            dest = chess.square_name(m.to_square)
            if tablero.is_capture(m):
                return f"⚔️ Capturar en {dest}"
            return f"➡️ Ir a {dest}"

        with col_b:
            mov_seleccionado = st.selectbox("2️⃣ A dónde mover:", movs_desde_origen, format_func=etiqueta_destino)

        if st.button("✅ Hacer Jugada", type="primary", use_container_width=True):
            st.session_state["pista_mov"] = None
            tablero.push(mov_seleccionado)
            if not tablero.is_game_over():
                txt_bot = mover_robot(tablero, bot_actual)
                st.session_state["mensaje_bot"] = f"Yo respondo con **{txt_bot}**. ¡Te toca!"
            else:
                st.session_state["mensaje_bot"] = "¡Partida terminada! Dale al botón de abajo para analizarla con el Entrenador."
            st.rerun()

        c1, c2 = st.columns(2)
        with c1:
            if st.button("💡 Pedir Pista", use_container_width=True):
                ruta_sf = obtener_ruta_stockfish()
                with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
                    res = motor.play(tablero, chess.engine.Limit(depth=10))
                    st.session_state["pista_mov"] = res.move
                    txt_pista = jugada_en_espanol(tablero, res.move)
                    st.session_state["mensaje_bot"] = f"💡 **Pista del Entrenador:** Te recomiendo jugar **{txt_pista}** (mira la flecha verde)."
                st.rerun()
        with c2:
            if st.button("↩️ Deshacer jugada", use_container_width=True) and len(tablero.move_stack) >= 2:
                tablero.pop()
                tablero.pop()
                st.session_state["pista_mov"] = None
                st.session_state["mensaje_bot"] = "Retrocedimos un turno. ¡Intenta otra jugada!"
                st.rerun()

    # Botón directo para mandar la partida contra el Robot al Narrador
    if len(tablero.move_stack) > 0:
        st.divider()
        if st.button("🔍 Analizar esta partida con el Entrenador y Voz", use_container_width=True):
            with st.spinner("El Entrenador está preparando la revisión completa de tu partida..."):
                juego_pgn = chess.pgn.Game.from_board(tablero)
                pgn_str = str(juego_pgn)
                jugadas, cabeceras = analizar_partida(pgn_str)
                st.session_state["jugadas"] = jugadas
                st.session_state["headers"] = cabeceras
                st.session_state["paso"] = 0
                st.success("¡Análisis listo! Toca arriba la pestaña '🧑‍🏫 Revisión de Partida (Con Narrador)' para escucharla.")

# ==========================================
# MODO 2: REVISIÓN DE PARTIDA CON NARRADOR
# ==========================================
else:
    if "jugadas" not in st.session_state:
        st.info("👆 Primero juega unas jugadas en **'🎮 Jugar contra el Robot'** y toca **'🔍 Analizar esta partida'**, o carga una partida abajo:")

    with st.expander("📥 Importar otra partida (Chess.com o PGN)", expanded=("jugadas" not in st.session_state)):
        pgn_manual = st.text_area("Pega el PGN de cualquier partida:", height=100, placeholder="1. e4 e5 2. Nf3 Nc6...")
        if st.button("🚀 Analizar PGN", type="primary", use_container_width=True) and pgn_manual.strip():
            with st.spinner("Analizando con Stockfish..."):
                jugadas, cabeceras = analizar_partida(pgn_manual)
                if jugadas:
                    st.session_state["jugadas"] = jugadas
                    st.session_state["headers"] = cabeceras
                    st.session_state["paso"] = 0
                    st.rerun()

    if "jugadas" in st.session_state:
        paso = st.session_state.get("paso", 0)
        total = len(st.session_state["jugadas"]) - 1
        actual = st.session_state["jugadas"][paso]

        st.markdown(f"""
        <div class="coach-box" style="border-left-color: {actual['color_badge']};">
            <div class="coach-avatar">🧑‍🏫</div>
            <div class="coach-text">
                <span class="badge" style="background-color: {actual['color_badge']}; color: #fff;">
                    {actual['titulo']}
                </span><br>
                {actual['explicacion']}
            </div>
        </div>
        """, unsafe_allow_html=True)

        activar_voz = st.toggle("🔊 Narrador con voz en español", value=True)
        if activar_voz:
            tts = gTTS(text=f"{actual['titulo']}. {actual['explicacion']}", lang="es")
            audio_bytes = io.BytesIO()
            tts.write_to_fp(audio_bytes)
            st.audio(audio_bytes.getvalue(), format="audio/mp3", autoplay=True)

        tablero_actual = chess.Board(actual["fen"])
        dibujar_tablero(
            tablero_actual,
            orientacion=st.session_state.get("color_jugador", chess.WHITE),
            ultimo_mov=actual["ultimo_mov"],
            mejor_mov=actual["mejor_mov"]
        )

        st.write(f"**Jugada {paso} de {total}**")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("⏮️", use_container_width=True) and paso > 0:
                st.session_state["paso"] = 0
                st.rerun()
        with col2:
            if st.button("⬅️ Ant.", use_container_width=True) and paso > 0:
                st.session_state["paso"] -= 1
                st.rerun()
        with col3:
            if st.button("Sig. ➡️", type="primary", use_container_width=True) and paso < total:
                st.session_state["paso"] += 1
                st.rerun()
        with col4:
            if st.button("⏭️", use_container_width=True) and paso < total:
                st.session_state["paso"] = total
                st.rerun()
