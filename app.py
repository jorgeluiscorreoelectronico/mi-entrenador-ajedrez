import streamlit as st
import chess
import chess.pgn
import chess.svg
import chess.engine
import requests
import io
import shutil
import base64
from gtts import gTTS

st.set_page_config(page_title="Revisión de Partida", page_icon="♟️", layout="centered")

# --- ESTILOS VISUALES TIPO CHESS.COM PARA CELULAR ---
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

# --- TRADUCTOR DE JUGADAS A ESPAÑOL NATURAL ---
NOMBRES_PIEZAS = {
    chess.PAWN: "el peón", chess.KNIGHT: "el caballo",
    chess.BISHOP: "el alfil", chess.ROOK: "la torre",
    chess.QUEEN: "la dama", chess.KING: "el rey"
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

# --- MOTOR STOCKFISH ---
@st.cache_resource
def obtener_ruta_stockfish():
    return shutil.which("stockfish") or "/usr/games/stockfish"

def analizar_partida(pgn_texto):
    juego = chess.pgn.read_game(io.StringIO(pgn_texto))
    tablero = juego.board()
    ruta_sf = obtener_ruta_stockfish()
    
    datos_jugadas = [{
        "fen": tablero.fen(),
        "ultimo_mov": None,
        "mejor_mov": None,
        "titulo": "Inicio de la partida",
        "color_badge": "#81b64c",
        "explicacion": "¡Hola! Soy tu entrenador. Toca 'Siguiente' para repasar tu partida jugada por jugada.",
        "eval_blancas": 0.2
    }]
    
    with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
        info_prev = motor.analyse(tablero, chess.engine.Limit(depth=12))
        
        for num, mov in enumerate(juego.mainline_moves()):
            turno_blancas = tablero.turn == chess.WHITE
            mejor_mov_prev = info_prev.get("pv", [mov])[0]
            
            score_antes = info_prev["score"].pov(tablero.turn).score(mate_score=10000) / 100.0
            texto_jugada_hecha = jugada_en_espanol(tablero, mov)
            texto_mejor_jugada = jugada_en_espanol(tablero, mejor_mov_prev)
            
            tablero.push(mov)
            info_desp = motor.analyse(tablero, chess.engine.Limit(depth=12))
            
            # Evaluación desde el punto de vista de quien acaba de mover
            score_desp = - (info_desp["score"].pov(tablero.turn).score(mate_score=10000) / 100.0)
            eval_blancas = info_desp["score"].white().score(mate_score=10000) / 100.0
            perdida = max(0.0, score_antes - score_desp)
            
            # Respuesta que amenaza el rival ahora
            amenaza_rival = ""
            if "pv" in info_desp and len(info_desp["pv"]) > 0:
                mov_rival = info_desp["pv"][0]
                amenaza_rival = jugada_en_espanol(tablero, mov_rival)

            # Clasificación y explicación del Entrenador en Español
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
                explicacion = f"Jugaste {texto_jugada_hecha}, que es un poco imprecisa porque permite al rival responder con {amenaza_rival}. Era mejor {texto_mejor_jugada}."
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

# --- INTERFAZ DE LA APLICACIÓN ---
st.title("♟️ Revisión de Partida")

with st.expander("🔍 Cargar partida de Chess.com", expanded=("jugadas" not in st.session_state)):
    usuario = st.text_input("Tu usuario de Chess.com:", placeholder="Ej: Hikaru")
    if st.button("Buscar mis últimas partidas", use_container_width=True) and usuario:
        headers = {"User-Agent": "MiEntrenadorPython/1.0"}
        r = requests.get(f"https://api.chess.com/pub/player/{usuario.lower().strip()}/games/archives", headers=headers)
        if r.status_code == 200 and r.json().get("archives"):
            ultimo_mes = r.json()["archives"][-1]
            partidas = requests.get(ultimo_mes, headers=headers).json().get("games", [])[-10:]
            partidas.reverse()
            st.session_state["lista_partidas"] = partidas
        else:
            st.error("No se encontró el usuario o no tiene partidas públicas.")

    if "lista_partidas" in st.session_state:
        opciones = [
            f"⚪ {p['white']['username']} vs ⚫ {p['black']['username']}"
            for p in st.session_state["lista_partidas"]
        ]
        seleccion = st.selectbox("Elige la partida:", range(len(opciones)), format_func=lambda i: opciones[i])
        if st.button("🚀 Analizar con el Entrenador", type="primary", use_container_width=True):
            with st.spinner("El Entrenador está analizando tus jugadas con Stockfish..."):
                pgn = st.session_state["lista_partidas"][seleccion]["pgn"]
                st.session_state["jugadas"], st.session_state["headers"] = analizar_partida(pgn)
                st.session_state["paso"] = 0
                st.rerun()

# --- MOSTRAR TABLERO Y ENTRENADOR ---
if "jugadas" in st.session_state:
    paso = st.session_state.get("paso", 0)
    total = len(st.session_state["jugadas"]) - 1
    actual = st.session_state["jugadas"][paso]

    # 1. Caja del Entrenador estilo Chess.com
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

    # 2. Voz del Narrador en Español
    activar_voz = st.toggle("🔊 Narrador con voz en español", value=True)
    if activar_voz:
        tts = gTTS(text=f"{actual['titulo']}. {actual['explicacion']}", lang="es")
        audio_bytes = io.BytesIO()
        tts.write_to_fp(audio_bytes)
        st.audio(audio_bytes.getvalue(), format="audio/mp3", autoplay=True)

    # 3. Tablero verde estilo Chess.com + Flecha de mejor jugada
    tablero_actual = chess.Board(actual["fen"])
    flechas = []
    if actual["mejor_mov"]:
        flechas.append(chess.svg.Arrow(actual["mejor_mov"].from_square, actual["mejor_mov"].to_square, color="#81b64c"))
    
    svg_tablero = chess.svg.board(
        board=tablero_actual,
        lastmove=actual["ultimo_mov"],
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

    # 4. Botones grandes para celular
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
