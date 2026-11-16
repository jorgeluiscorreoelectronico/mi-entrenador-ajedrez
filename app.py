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
import asyncio
import edge_tts

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

# --- GENERADOR DE VOZ HUMANA NEURONAL (MICROSOFT EDGE TTS) ---
VOCES_HUMANAS = {
    "🎙️ Álvaro (Voz Humana - España)": "es-ES-AlvaroNeural",
    "🎙️ Dalia (Voz Humana - México)": "es-MX-DaliaNeural",
    "🎙️ Lorenzo (Voz Humana - Chile)": "es-CL-LorenzoNeural"
}

@st.cache_data(show_spinner=False)
def generar_audio_humano(texto, voz_id):
    async def _generar():
        comunicador = edge_tts.Communicate(texto, voz_id, rate="+12%")
         datos_audio = b""
        async for chunk in comunicador.stream():
            if chunk["type"] == "audio":
                datos_audio += chunk["data"]
        return datos_audio
    return asyncio.run(_generar())

# --- IA GRATUITA DE GOOGLE GEMINI (OPCIONAL) ---
def explicar_con_gemini(api_key, fen, jugada_hecha, mejor_jugada, clasificacion):
    if not api_key:
        return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key.strip()}"
        prompt = (
            f"Eres el entrenador de ajedrez de Chess.com hablando en español natural y cercano a un jugador novato. "
            f"En la posición FEN '{fen}', el jugador hizo '{jugada_hecha}' (clasificada como {clasificacion}). "
            f"La mejor jugada según Stockfish era '{mejor_jugada}'. "
            f"Explícale en máximo 2 oraciones breves y muy claras por qué su jugada tuvo esa clasificación y qué lograba la mejor jugada. No uses notación en inglés."
        )
        r = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=6)
        if r.status_code == 200:
            return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return None

# --- DICCIONARIOS EN ESPAÑOL ---
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

def dibujar_tablero_revision(board, orientacion=chess.WHITE, ultimo_mov=None, mejor_mov=None):
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

def analizar_partida(pgn_texto):
    juego = chess.pgn.read_game(io.StringIO(pgn_texto))
    if not juego:
        return None, None
    tablero = juego.board()
    ruta_sf = obtener_ruta_stockfish()
    
    datos_jugadas = [{
        "fen": tablero.fen(),
        "fen_previo": tablero.fen(),
        "ultimo_mov": None,
        "mejor_mov": None,
        "jugada_txt": "",
        "mejor_txt": "",
        "titulo": "Inicio de la partida",
        "color_badge": "#81b64c",
        "explicacion": "¡Hola! Soy tu entrenador con voz neuronal. Toca 'Sig. ➡️' abajo del tablero para repasar tu partida.",
        "eval_blancas": 0.2
    }]
    
    with chess.engine.SimpleEngine.popen_uci(ruta_sf) as motor:
        info_prev = motor.analyse(tablero, chess.engine.Limit(depth=12))
        
        for num, mov in enumerate(juego.mainline_moves()):
            fen_antes = tablero.fen()
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
                explicacion = f"Jugaste {texto_jugada_hecha}. Es una buena jugada de apertura para activar tus piezas."
            elif mov == mejor_mov_prev:
                if perdida == 0 and score_desp > score_antes + 1.5:
                    titulo, color = "!! Jugada Brillante", "#1baca6"
                    explicacion = f"¡Brillante! Encontraste {texto_jugada_hecha}, el golpe táctico más fuerte en el tablero."
                else:
                    titulo, color = "★ Mejor Jugada", "#81b64c"
                    explicacion = f"¡Excelente! Hiciste {texto_jugada_hecha}, que era exactamente la mejor jugada disponible."
            elif perdida < 0.35:
                titulo, color = "👍 Buena Jugada", "#96bc4b"
                explicacion = f"Jugaste {texto_jugada_hecha}, manteniendo bien tu posición. También podías considerar {texto_mejor_jugada}."
            elif perdida < 0.9:
                titulo, color = "?! Imprecisión", "#f7c631"
                explicacion = f"Hiciste {texto_jugada_hecha}, pero es una imprecisión porque deja que tu rival responda con {amenaza_rival}. Era mejor {texto_mejor_jugada}."
            elif perdida < 2.0:
                titulo, color = "? Error", "#e6912c"
                explicacion = f"Cuidado, {texto_jugada_hecha} es un error porque tu oponente ahora tiene {amenaza_rival}. Te convenía jugar {texto_mejor_jugada}."
            else:
                titulo, color = "?? Error Grave", "#ca3431"
                explicacion = f"¡Peligro! Con {texto_jugada_hecha} entregas material o ventaja, permitiendo que el rival juegue {amenaza_rival}. Debías hacer {texto_mejor_jugada}."

            datos_jugadas.append({
                "fen": tablero.fen(),
                "fen_previo": fen_antes,
                "ultimo_mov": mov,
                "mejor_mov": mejor_mov_prev if perdida >= 0.4 else None,
                "jugada_txt": texto_jugada_hecha,
                "mejor_txt": texto_mejor_jugada,
                "titulo": titulo,
                "color_badge": color,
                "explicacion": explicacion,
                "eval_blancas": max(-10.0, min(10.0, eval_blancas))
            })
            info_prev = info_desp
            
    return datos_jugadas, juego.headers

# --- RECIBIR PARTIDA DESDE EL TABLERO INTERACTIVO ---
if "analizar_pgn" in st.query_params:
    pgn_recibido = st.query_params["analizar_pgn"]
    st.query_params.clear()
    with st.spinner("🧑‍🏫 El Entrenador está analizando tu partida con Stockfish..."):
        jugadas, cabeceras = analizar_partida(pgn_recibido)
        if jugadas:
            st.session_state["jugadas"] = jugadas
            st.session_state["headers"] = cabeceras
            st.session_state["paso"] = 0
            st.session_state["modo_actual"] = "🧑‍🏫 Revisión de Partida (Con Narrador)"

if "modo_actual" not in st.session_state:
    st.session_state["modo_actual"] = "🎮 Jugar contra el Robot (Con Ayudas)"

modo = st.radio(
    "Modo de la App:",
    ["🎮 Jugar contra el Robot (Con Ayudas)", "🧑‍🏫 Revisión de Partida (Con Narrador)"],
    index=0 if st.session_state["modo_actual"].startswith("🎮") else 1,
    horizontal=True
)
st.session_state["modo_actual"] = modo

# =========================================================
# MODO 1: TABLERO CON PUNTITOS GUÍA + PROTECTOR DE DAMA
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
        protector_activo = st.toggle("🛡️ Avisarme si regalo la Dama o piezas", value=True)

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
            .avatar {{ font-size: 34px; }}
            .msg {{ font-size: 14px; line-height: 1.4; color: #f1f1f1; }}
            #myBoard {{ width: 100%; max-width: 400px; margin: 0 auto; touch-action: none; }}
            .white-1e1d7 {{ background-color: #ebecd0 !important; color: #739552 !important; }}
            .black-3c85d {{ background-color: #739552 !important; color: #ebecd0 !important; }}
            .highlight-sq {{ box-shadow: inset 0 0 3px 3px #f5f682 !important; background-color: #f5f682 !important; }}
            /* Puntitos estilo Chess.com para casillas vacías */
            .dot-sq {{
                background-image: radial-gradient(rgba(20, 20, 20, 0.38) 19%, rgba(0, 0, 0, 0) 22%) !important;
            }}
            /* Anillo estilo Chess.com para piezas que puedes comer */
            .capture-sq {{
                box-shadow: inset 0 0 0 5px rgba(202, 52, 49, 0.65) !important;
            }}
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
                <b>¡Toca cualquier pieza blanca!</b> Verás con <b>puntitos</b> a dónde puede moverse y con un <b>círculo rojo</b> qué piezas puedes capturar.
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

        <button class="btn-green" onclick="mostrarAnalisis()">🔍 Terminar y Analizar con el Entrenador</button>

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

            function playSound(moveObj) {{
                try {{
                    if (game.in_check()) sndCheck.play();
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
                    if (moves[i].captured) {{
                        $('#myBoard .square-' + moves[i].to).addClass('capture-sq');
                    }} else {{
                        $('#myBoard .square-' + moves[i].to).addClass('dot-sq');
                    }}
                }}
            }}

            // Verifica si la jugada del usuario regala la Dama o una pieza valiosa gratis
            function verificarPeligroPieza(ultimoMovJugador) {{
                if (!protector) return null;
                var respuestasRival = game.moves({{ verbose: true }});
                var peorPerdida = 0;
                var amenaza = null;

                for (var i = 0; i < respuestasRival.length; i++) {{
                    var r = respuestasRival[i];
                    if (r.captured) {{
                        var valorCapturado = valores[r.captured] || 0;
                        // Si nos capturan la Dama (900), Torre (500) o pieza menor en la casilla donde acabamos de mover o dejamos colgada
                        if (valorCapturado >= 300) {{
                            game.move(r);
                            // Ver si podemos recapturar en esa misma casilla
                            var misRecapturas = game.moves({{ verbose: true }}).filter(function(m) {{ return m.to === r.to; }});
                            game.undo();
                            var gananciaNetaRival = misRecapturas.length === 0 ? valorCapturado : (valorCapturado - (valores[r.piece] || 0));
                            if (gananciaNetaRival >= 300 && gananciaNetaRival > peorPerdida) {{
                                peorPerdida = gananciaNetaRival;
                                amenaza = r;
                            }}
                        }}
                    }}
                }}
                return amenaza;
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
                if (game.game_over()) return;
                var m = elegirJugadaBot();
                if (m) {{
                    var res = game.move(m);
                    board.position(game.fen());
                    playSound(res);
                    var texto = "Moví mi <b>" + nombrePieza(res.piece) + " a " + res.to + "</b>.";
                    if (res.captured) texto = "Capturé tu <b>" + nombrePieza(res.captured) + " en " + res.to + "</b>.";
                    if (game.in_checkmate()) texto += " <b>¡Jaque mate!</b>";
                    else if (game.in_check()) texto += " <b>¡Estás en jaque! Debes proteger a tu Rey.</b>";
                    else texto += " ¡Te toca!";
                    document.getElementById('coachCard').classList.remove('coach-danger');
                    document.getElementById('statusMsg').innerHTML = texto;
                }}
            }}

            function procesarJugadaUsuario(move) {{
                limpiarResaltado();
                selectedSq = null;
                board.position(game.fen());
                playSound(move);

                // Protector de Dama y Piezas en vivo
                var peligro = verificarPeligroPieza(move);
                if (peligro) {{
                    try {{ sndIllegal.play(); }} catch(e) {{}}
                    document.getElementById('coachCard').classList.add('coach-danger');
                    document.getElementById('btnCorregir').style.display = 'block';
                    $('#myBoard .square-' + peligro.to).addClass('capture-sq');
                    document.getElementById('statusMsg').innerHTML =
                        "🚨 <b>¡CUIDADO!</b> Con esa jugada dejas tu <b>" + nombrePieza(peligro.captured) +
                        " en " + peligro.to + "</b> sin defensa (el rival te la puede comer con su " +
                        nombrePieza(peligro.piece) + ").<br>Toca el botón naranja abajo para corregirla, o espera si quieres seguir.";
                    return;
                }}

                document.getElementById('btnCorregir').style.display = 'none';
                document.getElementById('coachCard').classList.remove('coach-danger');
                document.getElementById('statusMsg').innerHTML = "Pensando mi respuesta...";
                window.setTimeout(turnoBot, 350);
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
                    if (game.in_check()) msgIlegal = "⚠️ <b>¡Tu Rey está en jaque!</b> Solo puedes hacer jugadas que defiendan o muevan a tu Rey.";
                    document.getElementById('statusMsg').innerHTML = msgIlegal;
                    return 'snapback';
                }}
                procesarJugadaUsuario(move);
            }}

            function onSnapEnd() {{
                board.position(game.fen());
            }}

            var config = {{
                draggable: true,
                position: 'start',
                pieceTheme: 'https://chessboardjs.com/img/chesspieces/wikipedia/{{piece}}.png',
                onDragStart: onDragStart,
                onDrop: onDrop,
                onSnapEnd: onSnapEnd
            }};
            board = Chessboard('myBoard', config);

            // Tocar casilla para ver puntitos y tocar segundo punto para mover
            $('#myBoard').on('click', '.square-55d63', function() {{
                if (game.game_over() || game.turn() !== 'w') return;
                var sq = $(this).attr('data-square');
                if (!sq) return;

                if (selectedSq && selectedSq !== sq) {{
                    var move = game.move({{ from: selectedSq, to: sq, promotion: 'q' }});
                    if (move !== null) {{
                        procesarJugadaUsuario(move);
                        return;
                    }}
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
                document.getElementById('coachCard').classList.remove('coach-danger');
                if (game.turn() === 'b' && game.history().length >= 1) {{
                    game.undo();
                }} else if (game.history().length >= 2) {{
                    game.undo();
                    game.undo();
                }}
                board.position(game.fen());
                limpiarResaltado();
                document.getElementById('statusMsg').innerHTML = "↩️ Jugada deshecha. Toca una pieza para ver sus puntitos de movimiento.";
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
                document.getElementById('coachCard').classList.remove('coach-danger');
                document.getElementById('pgnBox').style.display = 'none';
                document.getElementById('statusMsg').innerHTML = "🔄 ¡Partida nueva! Toca cualquier pieza blanca para ver a dónde puede ir.";
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
                document.getElementById('statusMsg').innerHTML = "✅ <b>¡Copiado!</b> Ahora toca arriba la pestaña <b>'🧑‍🏫 Revisión de Partida'</b>.";
            }}
        </script>
    </body>
    </html>
    """
    components.html(html_juego, height=670, scrolling=True)

# =========================================================
# MODO 2: REVISIÓN CON VOZ HUMANA NEURONAL + IA GEMINI
# =========================================================
else:
    col_v1, col_v2 = st.columns(2)
    with col_v1:
        voz_elegida = st.selectbox("Voz del Entrenador:", list(VOCES_HUMANAS.keys()))
    with col_v2:
        activar_voz = st.toggle("🔊 Escuchar voz humana", value=True)

    with st.expander("🧠 Opcional: Conectar IA gratuita de Google Gemini (Explicaciones de Maestro)"):
        st.caption("Si quieres que la IA de Google redacte explicaciones personalizadas, pega tu clave gratuita de aistudio.google.com:")
        gemini_key = st.text_input("Tu API Key de Gemini (Opcional):", type="password")

    with st.expander("📥 Pegar o cargar partida para revisar", expanded=("jugadas" not in st.session_state)):
        pgn_manual = st.text_area("Pega aquí la partida (PGN):", height=80, placeholder="1. e4 e5 2. Nf3 Nc6...")
        if st.button("🚀 Analizar con el Entrenador", type="primary", use_container_width=True) and pgn_manual.strip():
            with st.spinner("🧑‍🏫 Analizando tus jugadas con Stockfish..."):
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

        texto_explicacion = actual["explicacion"]
        if gemini_key and paso > 0:
            exp_ia = explicar_con_gemini(
                gemini_key, actual["fen_previo"], actual["jugada_txt"], actual["mejor_txt"], actual["titulo"]
            )
            if exp_ia:
                texto_explicacion = exp_ia

        st.markdown(f"""
        <div class="coach-box" style="border-left-color: {actual['color_badge']};">
            <div class="coach-avatar">🧑‍🏫</div>
            <div class="coach-text">
                <span class="badge" style="background-color: {actual['color_badge']}; color: #fff;">
                    {actual['titulo']}
                </span><br>
                {texto_explicacion}
            </div>
        </div>
        """, unsafe_allow_html=True)

        if activar_voz:
            texto_limpio = f"{actual['titulo']}. {texto_explicacion}".replace("!", "").replace("?", "").replace("★", "")
            audio_mp3 = generar_audio_humano(texto_limpio, VOCES_HUMANAS[voz_elegida])
            st.audio(audio_mp3, format="audio/mp3", autoplay=True)

        tablero_actual = chess.Board(actual["fen"])
        dibujar_tablero_revision(
            tablero_actual,
            orientacion=chess.WHITE,
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
                
