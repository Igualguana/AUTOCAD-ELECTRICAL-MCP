"""
Esquema completo de Arranque Directo Motor Trifasico 3~ 380V
Norma IEC 60617 - Circuito de Potencia + Circuito de Control
"""
import sys, array as ar, math
sys.path.insert(0, r"C:\Users\Randyl\MCP AutoCAD")
import win32com.client

# ── primitivas ─────────────────────────────────────────────────────────────

def pt(x, y):
    return (float(x), float(y), 0.0)

def L(ms, x1, y1, x2, y2, lay):
    e = ms.AddLine(pt(x1,y1), pt(x2,y2))
    e.Layer = lay
    return e

def C(ms, cx, cy, r, lay):
    e = ms.AddCircle(pt(cx,cy), float(r))
    e.Layer = lay
    return e

def T(ms, x, y, s, h=2.5, lay="TXT"):
    e = ms.AddText(str(s), pt(x,y), float(h))
    e.Layer = lay
    return e

def R(ms, x1, y1, x2, y2, lay):
    """Rectangle via 4 lines (avoids VARIANT marshalling issues)"""
    L(ms, x1,y1, x2,y1, lay)
    L(ms, x2,y1, x2,y2, lay)
    L(ms, x2,y2, x1,y2, lay)
    L(ms, x1,y2, x1,y1, lay)

def mk_layer(doc, name, color):
    try:
        return doc.Layers.Item(name)
    except Exception:
        ly = doc.Layers.Add(name)
        ly.Color = color
        return ly

# ── simbolos IEC ────────────────────────────────────────────────────────────

def sym_cb_pole(ms, x, y):
    """Polo de interruptor automatico (Q1)"""
    L(ms, x, y+7, x, y+3, "SYM")
    L(ms, x-3, y+3, x+3, y+3, "SYM")
    L(ms, x-3, y-3, x+3, y-3, "SYM")
    L(ms, x, y-3, x, y-7, "SYM")
    L(ms, x-2.5, y+2.5, x+2.5, y-2.5, "SYM")   # diagonal CB
    L(ms, x-3, y+4, x+3, y+4, "SYM")            # actuador

def sym_cttor_pole(ms, x, y):
    """Polo NO de contactor (KM1 potencia)"""
    L(ms, x, y+7, x, y+2, "SYM")
    L(ms, x-3, y+2, x+3, y+2, "SYM")
    L(ms, x-3, y-2, x+3, y-2, "SYM")
    L(ms, x, y-2, x, y-7, "SYM")
    L(ms, x-2.5, y+1.5, x+2.5, y-1.5, "SYM")   # contacto movil

def sym_ol_pole(ms, x, y):
    """Polo relé termico (F1)"""
    R(ms, x-3, y-5, x+3, y+5, "SYM")
    # zigzag interno
    zx = [x-2, x+2, x-2, x+2]
    zy = [y+3, y+1, y-1, y-3]
    for i in range(3):
        L(ms, zx[i], zy[i], zx[i+1], zy[i+1], "SYM")

def sym_no_contact(ms, x, y):
    """Contacto NO (normalmente abierto)"""
    L(ms, x, y+5, x, y+2, "SYM")
    L(ms, x-3, y+2, x+3, y+2, "SYM")
    L(ms, x-3, y-2, x+3, y-2, "SYM")
    L(ms, x, y-2, x, y-5, "SYM")
    L(ms, x-3.5, y+3, x+3.5, y+3, "SYM")        # operador NO (linea recta)

def sym_nc_contact(ms, x, y):
    """Contacto NC (normalmente cerrado)"""
    L(ms, x, y+5, x, y+2, "SYM")
    L(ms, x-3, y+2, x+3, y+2, "SYM")
    L(ms, x-3, y-2, x+3, y-2, "SYM")
    L(ms, x, y-2, x, y-5, "SYM")
    L(ms, x-2.5, y+1.5, x+2.5, y-1.5, "SYM")   # slash NC
    L(ms, x-3.5, y+3, x+3.5, y+4, "SYM")        # operador NC (diagonal)

def sym_pulsador_no(ms, x, y, label):
    """Pulsador NO (START)"""
    sym_no_contact(ms, x, y)
    L(ms, x, y+5, x, y+7, "SYM")
    C(ms, x, y+8.5, 1.8, "SYM")
    T(ms, x-3, y-8,  label,   2.0, "TXT")
    T(ms, x-2, y-10.5, "NO", 1.8, "TXT")

def sym_pulsador_nc(ms, x, y, label):
    """Pulsador NC (STOP)"""
    sym_nc_contact(ms, x, y)
    L(ms, x, y+5, x, y+7, "SYM")
    C(ms, x, y+8.5, 1.8, "SYM")
    T(ms, x-3, y-8,  label,   2.0, "TXT")
    T(ms, x-2, y-10.5, "NC", 1.8, "TXT")

def sym_coil(ms, x, y, label):
    """Bobina de contactor"""
    L(ms, x, y+5, x, y+3, "SYM")
    R(ms, x-4, y-3, x+4, y+3, "SYM")
    L(ms, x, y-3, x, y-5, "SYM")
    T(ms, x-3.5, y-1.5, label, 2.5, "TXT")

def sym_lamp(ms, x, y, label):
    """Lampara piloto"""
    L(ms, x, y+5, x, y+3, "SYM")
    C(ms, x, y, 3, "SYM")
    L(ms, x-2.1, y+2.1, x+2.1, y-2.1, "SYM")
    L(ms, x-2.1, y-2.1, x+2.1, y+2.1, "SYM")
    L(ms, x, y-3, x, y-5, "SYM")
    T(ms, x-2.5, y-8, label, 2.0, "TXT")

def sym_motor(ms, cx, cy, r=13):
    """Motor trifasico"""
    C(ms, cx, cy, r, "SYM")
    T(ms, cx-4,   cy+3,  "M",   6.0, "TXT")
    T(ms, cx-4.5, cy-5,  "3~",  3.0, "TXT")

def sym_pe(ms, x, y):
    """Simbolo tierra/PE"""
    for i, w in enumerate([5,3.5,2,0.8]):
        yi = y - i*2
        L(ms, x-w, yi, x+w, yi, "SYM")

# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

import time

app = win32com.client.GetActiveObject("AutoCAD.Application")
app.Visible = True
time.sleep(0.5)

# ── Usar Drawing3 ya abierto (sin SaveAs previo) ────────────────────────────
doc = None
for i in range(app.Documents.Count):
    d = app.Documents.Item(i)
    if "Drawing3" in d.Name or "drawing3" in d.Name.lower():
        doc = d
        break

if doc is None:
    doc = app.Documents.Add()
    time.sleep(1)

app.ActiveDocument = doc
time.sleep(0.5)
ms = doc.ModelSpace
path = r"C:\Users\Randyl\Documents\Motor_Trifasico_380V.dwg"

# ── Capas ───────────────────────────────────────────────────────────────────
mk_layer(doc, "POW",  1)   # Rojo   – circuito potencia
mk_layer(doc, "CTL",  3)   # Verde  – circuito control
mk_layer(doc, "SYM",  4)   # Cian   – simbolos
mk_layer(doc, "TXT",  7)   # Blanco – texto
mk_layer(doc, "HDR",  2)   # Amarillo – titulos/marcos
mk_layer(doc, "FRM",  8)   # Gris   – borde

# ── Marco y cabecera ────────────────────────────────────────────────────────
R(ms,  3,  3, 294, 207, "FRM")
R(ms,  3,  3, 294,  18, "FRM")
L(ms,  3, 18, 294, 18, "FRM")
T(ms, 8, 10, "ARRANQUE DIRECTO - MOTOR TRIFASICO 3~ 380V  /  IEC 60617", 4.5, "HDR")
T(ms, 8,  5, "Circuito Potencia y Control  |  M1: 380V 50Hz 5.5kW IP55  |  Proy: MCP-AutoCAD-Electrical", 2.5, "TXT")

# Separador potencia / control
L(ms, 160, 18, 160, 207, "FRM")
T(ms,  30, 200, "CIRCUITO DE POTENCIA", 4.0, "HDR")
T(ms, 175, 200, "CIRCUITO DE CONTROL",  4.0, "HDR")

# ══════════════════════════════════════════════════════════════════════════════
# CIRCUITO DE POTENCIA
# ══════════════════════════════════════════════════════════════════════════════
L1x, L2x, L3x, PEx = 40, 63, 86, 110
BUS_TOP = 193
BUS_BOT =  45

# Bus de alimentacion superior
L(ms, L1x, BUS_TOP, L3x, BUS_TOP, "POW")
for lx, tag in [(L1x,"L1"),(L2x,"L2"),(L3x,"L3"),(PEx,"PE")]:
    T(ms, lx-3, BUS_TOP+1, tag, 3.0, "TXT")

# Bajadas al Q1
for lx in [L1x, L2x, L3x]:
    L(ms, lx, BUS_TOP, lx, 182, "POW")

# ── Q1 Interruptor automatico (y=177) ───────────────────────────────────────
Q1y = 177
for lx in [L1x, L2x, L3x]:
    sym_cb_pole(ms, lx, Q1y)
R(ms, L1x-7, Q1y-8, L3x+7, Q1y+8, "SYM")
T(ms,  8, Q1y+3, "Q1",    3.0, "TXT")
T(ms,  8, Q1y-1, "3P",    2.2, "TXT")
T(ms,  8, Q1y-5, "400V",  2.2, "TXT")

for lx in [L1x, L2x, L3x]:
    L(ms, lx, Q1y-8, lx, 162, "POW")

# ── KM1 Contactor principal (y=157) ─────────────────────────────────────────
KM1y = 157
for lx in [L1x, L2x, L3x]:
    sym_cttor_pole(ms, lx, KM1y)
R(ms, L1x-7, KM1y-8, L3x+7, KM1y+8, "SYM")
T(ms, 8, KM1y+3, "KM1",   3.0, "TXT")
T(ms, 8, KM1y-1, "3P NO", 2.2, "TXT")
T(ms, 8, KM1y-5, "Cttor", 2.2, "TXT")

for lx in [L1x, L2x, L3x]:
    L(ms, lx, KM1y-8, lx, 140, "POW")

# ── F1 Relé termico (y=134) ─────────────────────────────────────────────────
F1y = 134
for lx in [L1x, L2x, L3x]:
    sym_ol_pole(ms, lx, F1y)
R(ms, L1x-7, F1y-6, L3x+7, F1y+6, "SYM")
T(ms, 8, F1y+2, "F1",    3.0, "TXT")
T(ms, 8, F1y-2, "3P",    2.2, "TXT")
T(ms, 8, F1y-6, "Term.", 2.2, "TXT")

for lx in [L1x, L2x, L3x]:
    L(ms, lx, F1y-6, lx, 118, "POW")

# Bus horizontal a terminales motor
L(ms, L1x, 118, L3x, 118, "POW")
T(ms, L1x-9, 115, "U V W", 2.2, "TXT")

# ── M1 Motor trifasico ──────────────────────────────────────────────────────
Mcx = (L1x + L3x) / 2.0   # 63
Mcy = 75
Mr  = 14
sym_motor(ms, Mcx, Mcy, Mr)
T(ms, Mcx-14, Mcy-18, "M1  380V  50Hz  5.5kW  IP55  cos=0.86", 2.5, "TXT")

# Conexiones bus -> motor
ang = math.radians(30)
for lx in [L1x, L2x, L3x]:
    L(ms, lx, 118, lx, Mcy + Mr*0.85, "POW")

# PE bus vertical + conexion motor
L(ms, PEx, BUS_TOP, PEx, Mcy, "POW")
L(ms, Mcx + Mr, Mcy, PEx, Mcy, "POW")
sym_pe(ms, PEx, Mcy - 2)

# ══════════════════════════════════════════════════════════════════════════════
# CIRCUITO DE CONTROL  (carril izq=170, carril der=290)
# ══════════════════════════════════════════════════════════════════════════════
cL, cN = 170, 290
cTOP, cBOT = 193, 90

L(ms, cL, cTOP, cL, cBOT, "CTL")
L(ms, cN, cTOP, cN, cBOT, "CTL")
T(ms, cL-3, cTOP+1, "L",  3.0, "TXT")
T(ms, cN+1,  cTOP+1, "N", 3.0, "TXT")
T(ms, cL-2, cBOT-6, "24VDC / 120VAC", 2.0, "TXT")

# Numeracion de conductores
def wire_num(ms, x, y, n):
    C(ms, x, y, 2.2, "TXT")
    T(ms, x-1.5, y-1.2, str(n), 1.8, "TXT")

# ── RUNG 1 (y=178): S1 PARO(NC) → S2 MARCHA(NO) ┐→ F1-NC → KM1 Bobina ─────
#                                    KM1-aux(NO)  ┘
R1 = 178

# Hilo L → S1
L(ms, cL, R1, cL+8, R1, "CTL")
wire_num(ms, cL+4, R1+3, 1)

# S1 PARO (NC) en x=185
S1x = 185
L(ms, cL+8, R1, S1x, R1, "CTL")
sym_pulsador_nc(ms, S1x, R1, "S1-PARO")

# Nodo de union izquierdo paralelo (entre S1 y S2)
nodo_iz = S1x + 13
L(ms, S1x, R1-5, nodo_iz, R1, "CTL")
wire_num(ms, nodo_iz-4, R1+3, 2)

# S2 MARCHA (NO) en x=213
S2x = 213
L(ms, nodo_iz, R1, S2x, R1, "CTL")
sym_pulsador_no(ms, S2x, R1, "S2-MARCHA")

# Nodo de union derecho paralelo
nodo_de = S2x + 13
L(ms, S2x, R1-5, nodo_de, R1, "CTL")

# KM1-aux (NO) en paralelo con S2  (rung secundario R1-14)
R1b = R1 - 14
L(ms, nodo_iz, R1,  nodo_iz, R1b, "CTL")   # baja izquierda
L(ms, nodo_de, R1,  nodo_de, R1b, "CTL")   # baja derecha
KMaux1x = (nodo_iz + nodo_de) / 2.0
L(ms, nodo_iz, R1b, KMaux1x, R1b, "CTL")
sym_no_contact(ms, KMaux1x, R1b)
T(ms, KMaux1x-7, R1b-8,  "KM1-aux", 2.0, "TXT")
T(ms, KMaux1x-2, R1b-10.5, "NO",    1.8, "TXT")
L(ms, KMaux1x, R1b-5, nodo_de, R1b, "CTL")

wire_num(ms, nodo_de+4, R1+3, 3)

# F1-contacto auxiliar NC en x=238
F1cx = 238
L(ms, nodo_de, R1, F1cx, R1, "CTL")
sym_nc_contact(ms, F1cx, R1)
T(ms, F1cx-3, R1-8,  "F1",    2.0, "TXT")
T(ms, F1cx-5, R1-10.5,"OL-NC",1.8, "TXT")
wire_num(ms, F1cx+7, R1+3, 4)

# KM1 Bobina en x=260
KM1bx = 260
L(ms, F1cx, R1-5, KM1bx, R1, "CTL")
sym_coil(ms, KM1bx, R1, "KM1")
T(ms, KM1bx-4, R1-12, "KM1",   2.5, "TXT")
T(ms, KM1bx-5, R1-15, "Bobina",2.0, "TXT")

# Hilo bobina → carril N
L(ms, KM1bx+4, R1, cN, R1, "CTL")
wire_num(ms, KM1bx+10, R1+3, 5)

# ── RUNG 2 (y=155): KM1-aux(NO) → PL1 Lampara MARCHA ───────────────────────
R2 = 155
L(ms, cL, R2, cL+8, R2, "CTL")

KMaux2x = cL + 22
L(ms, cL+8, R2, KMaux2x, R2, "CTL")
sym_no_contact(ms, KMaux2x, R2)
T(ms, KMaux2x-7, R2-8,  "KM1-aux", 2.0, "TXT")
T(ms, KMaux2x-2, R2-10.5, "NO",    1.8, "TXT")

PL1x = KMaux2x + 22
L(ms, KMaux2x, R2-5, PL1x, R2, "CTL")
sym_lamp(ms, PL1x, R2, "PL1-MARCHA")
L(ms, PL1x, R2-5, cN, R2, "CTL")

# ── RUNG 3 (y=132): F1-contacto NC → PL2 Lampara FALLA ─────────────────────
R3 = 132
L(ms, cL, R3, cL+8, R3, "CTL")

F1nc2x = cL + 22
L(ms, cL+8, R3, F1nc2x, R3, "CTL")
sym_nc_contact(ms, F1nc2x, R3)
T(ms, F1nc2x-3, R3-8,  "F1",     2.0, "TXT")
T(ms, F1nc2x-6, R3-10.5,"TRIP-NC",1.8, "TXT")

PL2x = F1nc2x + 22
L(ms, F1nc2x, R3-5, PL2x, R3, "CTL")
sym_lamp(ms, PL2x, R3, "PL2-FALLA")
L(ms, PL2x, R3-5, cN, R3, "CTL")

# ── Leyenda ──────────────────────────────────────────────────────────────────
ley_x, ley_y = 165, 87
R(ms, ley_x, ley_y-32, ley_x+120, ley_y+2, "FRM")
T(ms, ley_x+2, ley_y-2,  "LEYENDA:", 3.0, "HDR")
items = [
    "Q1  - Interruptor automatico 3P  400V",
    "KM1 - Contactor principal  3P NO 400V",
    "F1  - Rele termico  3P  Ajuste: 11A",
    "S1  - Pulsador PARO   (NC)  24VDC",
    "S2  - Pulsador MARCHA (NO)  24VDC",
    "PL1 - Lampara piloto VERDE  (Marcha)",
    "PL2 - Lampara piloto ROJA   (Falla/OL)",
    "M1  - Motor  380V 50Hz  5.5kW IP55",
]
for i, it in enumerate(items):
    T(ms, ley_x+3, ley_y-8-i*3, it, 2.0, "TXT")

# ── Guardar y zoom ───────────────────────────────────────────────────────────
app.ZoomExtents()
time.sleep(0.3)
try:
    doc.SaveAs(path)
except Exception:
    doc.Save()   # fallback: guardar con nombre actual
print("OK  Dibujo guardado:", path)
print("    Capas: POW / CTL / SYM / TXT / HDR / FRM")
print("    Elementos dibujados: potencia 3-polos + control + leyenda")
