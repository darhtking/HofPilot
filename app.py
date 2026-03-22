import streamlit as st
import psycopg2
import pandas as pd
from io import BytesIO
from datetime import date

from supabase import create_client, Client
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

# =============================================================================
# SUPABASE AUTH
# =============================================================================
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def auth_form():
    st.title("HofPilot Zugang")
    tab1, tab2 = st.tabs(["Login", "Registrieren"])
    with tab1:
        email    = st.text_input("E-Mail", key="login_email")
        password = st.text_input("Passwort", type="password", key="login_pw")
        if st.button("Anmelden"):
            try:
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = response.user
                st.success("Willkommen zurueck!")
                st.rerun()
            except Exception as e:
                st.error(f"Login fehlgeschlagen: {e}")
    with tab2:
        new_email    = st.text_input("E-Mail", key="reg_email")
        new_password = st.text_input("Passwort (min. 6 Zeichen)", type="password", key="reg_pw")
        if st.button("Konto erstellen"):
            try:
                supabase.auth.sign_up({"email": new_email, "password": new_password})
                st.success("Konto erstellt! Du kannst dich jetzt einloggen.")
            except Exception as e:
                st.error(f"Registrierung fehlgeschlagen: {e}")

if "user" not in st.session_state:
    auth_form()
    st.stop()

st.sidebar.write(f"Nutzer: {st.session_state.user.email}")
if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    del st.session_state.user
    st.rerun()

# =============================================================================
# DATENBANK
# =============================================================================
DB_URI = st.secrets["DB_URI"]

def get_connection():
    return psycopg2.connect(DB_URI)

# --- N/P/K Bilanz ---

def load_all_schlage():
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT DISTINCT schlag_name FROM n_bilanz ORDER BY schlag_name ASC")
        rows = cur.fetchall(); cur.close(); conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        st.error(f"Fehler beim Laden der Schlage: {e}"); return []

def save_to_supabase(schlag, datum, art, n_menge, p_menge, k_menge, bemerkung=""):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """INSERT INTO n_bilanz (schlag_name, datum, duenger_art, n_menge, p_menge, k_menge, bemerkung)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (schlag, datum, art, n_menge, p_menge, k_menge, bemerkung if bemerkung else None)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")

def load_from_supabase(schlag):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """SELECT datum, duenger_art, n_menge, p_menge, k_menge, bemerkung
               FROM n_bilanz WHERE schlag_name = %s ORDER BY datum ASC""", (schlag,))
        rows = cur.fetchall(); cur.close(); conn.close()
        return [{
            "Datum":     r[0].strftime("%d.%m.%Y") if r[0] else "",
            "Art":       r[1],
            "N_Menge":   float(r[2]) if r[2] is not None else 0.0,
            "P_Menge":   float(r[3]) if r[3] is not None else 0.0,
            "K_Menge":   float(r[4]) if r[4] is not None else 0.0,
            "Bemerkung": r[5] if r[5] else ""
        } for r in rows]
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}"); return []

def delete_history_from_supabase(schlag):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM n_bilanz WHERE schlag_name = %s", (schlag,))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        st.error(f"Fehler beim Loeschen: {e}")

# --- Schlagkartei ---

def load_schlagkartei(schlag):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """SELECT flaeche_ha, eigentumsart, bodenart, pachtpreis_ha,
                      pachtende, feldstruecknummer, gemarkung, bodenwertzahl, bemerkung
               FROM schlagkartei WHERE schlag_name = %s""", (schlag,))
        row = cur.fetchone(); cur.close(); conn.close()
        if row:
            return {
                "flaeche_ha":       float(row[0]) if row[0] is not None else 0.0,
                "eigentumsart":     row[1],
                "bodenart":         row[2],
                "pachtpreis_ha":    float(row[3]) if row[3] is not None else 0.0,
                "pachtende":        row[4],
                "feldstruecknummer": row[5],
                "gemarkung":        row[6],
                "bodenwertzahl":    float(row[7]) if row[7] is not None else 0.0,
                "bemerkung":        row[8] if row[8] else ""
            }
        return None
    except Exception as e:
        st.error(f"Fehler beim Laden der Schlagkartei: {e}"); return None

def save_schlagkartei(schlag, flaeche, eigentumsart, bodenart, pachtpreis,
                      pachtende, feldnummer, gemarkung, bodenwertzahl, bemerkung):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """INSERT INTO schlagkartei
               (schlag_name, flaeche_ha, eigentumsart, bodenart, pachtpreis_ha,
                pachtende, feldstruecknummer, gemarkung, bodenwertzahl, bemerkung)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (schlag_name) DO UPDATE SET
                 flaeche_ha       = EXCLUDED.flaeche_ha,
                 eigentumsart     = EXCLUDED.eigentumsart,
                 bodenart         = EXCLUDED.bodenart,
                 pachtpreis_ha    = EXCLUDED.pachtpreis_ha,
                 pachtende        = EXCLUDED.pachtende,
                 feldstruecknummer= EXCLUDED.feldstruecknummer,
                 gemarkung        = EXCLUDED.gemarkung,
                 bodenwertzahl    = EXCLUDED.bodenwertzahl,
                 bemerkung        = EXCLUDED.bemerkung""",
            (schlag, flaeche, eigentumsart, bodenart,
             pachtpreis if pachtpreis > 0 else None,
             pachtende if eigentumsart != "Eigentum" else None,
             feldnummer if feldnummer.strip() else None,
             gemarkung if gemarkung.strip() else None,
             bodenwertzahl if bodenwertzahl > 0 else None,
             bemerkung if bemerkung.strip() else None)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        st.error(f"Fehler beim Speichern der Schlagkartei: {e}")

# --- Fruchtfolge ---

def load_fruchtfolge(schlag):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """SELECT jahr, kultur, ertrag_dt_ha, saatdatum, erntedatum,
                      zwischenfrucht, bemerkung
               FROM fruchtfolge WHERE schlag_name = %s ORDER BY jahr DESC""", (schlag,))
        rows = cur.fetchall(); cur.close(); conn.close()
        return [{
            "Jahr":          r[0],
            "Kultur":        r[1],
            "Ertrag (dt/ha)": float(r[2]) if r[2] is not None else None,
            "Saatdatum":     r[3].strftime("%d.%m.%Y") if r[3] else "",
            "Erntedatum":    r[4].strftime("%d.%m.%Y") if r[4] else "",
            "Zwischenfrucht": r[5] if r[5] else "",
            "Bemerkung":     r[6] if r[6] else ""
        } for r in rows]
    except Exception as e:
        st.error(f"Fehler beim Laden der Fruchtfolge: {e}"); return []

def save_fruchtfolge(schlag, jahr, kultur, ertrag, saatdatum, erntedatum,
                     zwischenfrucht, bemerkung):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            """INSERT INTO fruchtfolge
               (schlag_name, jahr, kultur, ertrag_dt_ha, saatdatum, erntedatum,
                zwischenfrucht, bemerkung)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (schlag_name, jahr) DO UPDATE SET
                 kultur         = EXCLUDED.kultur,
                 ertrag_dt_ha   = EXCLUDED.ertrag_dt_ha,
                 saatdatum      = EXCLUDED.saatdatum,
                 erntedatum     = EXCLUDED.erntedatum,
                 zwischenfrucht = EXCLUDED.zwischenfrucht,
                 bemerkung      = EXCLUDED.bemerkung""",
            (schlag, jahr, kultur,
             ertrag if ertrag and ertrag > 0 else None,
             saatdatum if saatdatum else None,
             erntedatum if erntedatum else None,
             zwischenfrucht if zwischenfrucht.strip() else None,
             bemerkung if bemerkung.strip() else None)
        )
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        st.error(f"Fehler beim Speichern der Fruchtfolge: {e}")

def delete_fruchtfolge_eintrag(schlag, jahr):
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("DELETE FROM fruchtfolge WHERE schlag_name = %s AND jahr = %s", (schlag, jahr))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        st.error(f"Fehler beim Loeschen: {e}")

# =============================================================================
# FRUCHTFOLGE-BEWERTUNG
# =============================================================================

# Ungünstige Abfolgen: {Vorkultur: [Nachkulturen die problematisch sind]}
UNGUENSTIGE_FOLGEN = {
    "Winterraps":   ["Winterraps"],
    "Koernermais":  ["Koernermais"],
    "Zuckerrueben": ["Zuckerrueben"],
    "Kartoffeln":   ["Kartoffeln"],
    "Winterweizen": ["Winterweizen", "Winterweizen"],  # >2x Weizen in Folge
}

def bewerte_fruchtfolge(ff_liste):
    """Gibt eine Liste von Warnungen zurück."""
    if len(ff_liste) < 2:
        return []
    # Sortiert nach Jahr aufsteigend
    sortiert = sorted(ff_liste, key=lambda x: x["Jahr"])
    warnungen = []
    for i in range(1, len(sortiert)):
        vorkultur  = sortiert[i-1]["Kultur"]
        nachkultur = sortiert[i]["Kultur"]
        jahr       = sortiert[i]["Jahr"]
        if vorkultur == nachkultur:
            warnungen.append(
                f"⚠️ {jahr}: {nachkultur} nach {vorkultur} – "
                f"Selbstfolge erhöht Krankheits- und Schädlingsdruck!"
            )
    # 3x Weizen in Folge extra
    kulturen = [e["Kultur"] for e in sortiert]
    for i in range(2, len(kulturen)):
        if kulturen[i] == kulturen[i-1] == kulturen[i-2] == "Winterweizen":
            warnungen.append(
                f"🔴 {sortiert[i]['Jahr']}: 3x Winterweizen in Folge – "
                f"stark erhöhtes Risiko für Halmbruch und Ährenerkrankungen!"
            )
    return warnungen

# =============================================================================
# PDF-EXPORT
# =============================================================================

def generate_pdf(schlag, crop, kartei, adjusted_demand, adjusted_p, adjusted_k,
                 total_n, total_p, total_k, historie, fruchtfolge, betrieb_name=""):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    gruen = colors.HexColor("#2d6a2d")

    titel_style = ParagraphStyle("Titel", parent=styles["Title"],
                                 fontSize=16, textColor=gruen, spaceAfter=4)
    sub_style   = ParagraphStyle("Sub",   parent=styles["Normal"],
                                 fontSize=9, textColor=colors.grey, spaceAfter=12)
    h2_style    = ParagraphStyle("H2",    parent=styles["Heading2"],
                                 fontSize=11, textColor=gruen, spaceBefore=14, spaceAfter=4)
    body_style  = ParagraphStyle("Body",  parent=styles["Normal"], fontSize=9, spaceAfter=4)

    story = []
    flaeche = kartei["flaeche_ha"] if kartei and kartei["flaeche_ha"] else 0.0

    story.append(Paragraph("HofPilot Pro - Düngebedarfsermittlung", titel_style))
    story.append(Paragraph(
        "Erstellt am " + date.today().strftime("%d.%m.%Y")
        + (" | Betrieb: " + betrieb_name if betrieb_name else ""), sub_style))
    story.append(HRFlowable(width="100%", thickness=1, color=gruen, spaceAfter=10))

    # 1. Schlaginfo
    story.append(Paragraph("1. Schlag- und Kulturinformationen", h2_style))
    bodenwertzahl = kartei["bodenwertzahl"] if kartei else 0.0
    info_data = [
        ["Schlagbezeichnung", schlag],
        ["Kultur", crop],
        ["Schlagflaeche", f"{flaeche:.2f} ha" if flaeche else "k.A."],
        ["Bodenart", kartei["bodenart"] if kartei and kartei["bodenart"] else "k.A."],
        ["Bodenwertzahl (Ackerzahl)", str(int(bodenwertzahl)) if bodenwertzahl else "k.A."],
        ["Feldstruecknummer", kartei["feldstruecknummer"] if kartei and kartei["feldstruecknummer"] else "k.A."],
        ["Gemarkung", kartei["gemarkung"] if kartei and kartei["gemarkung"] else "k.A."],
        ["Wirtschaftsjahr", str(date.today().year)],
    ]
    info_table = Table(info_data, colWidths=[5.5*cm, 10.5*cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8f5e9")),
        ("FONTNAME",   (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUND", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("PADDING",    (0, 0), (-1, -1), 5),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.4*cm))

    # 2. Naehrstoffbedarf
    story.append(Paragraph("2. Naehrstoffbedarf (gesetzlicher Rahmen)", h2_style))
    bedarf_data = [
        ["Naehrstoff", "Bedarf (kg/ha)", "Bedarf gesamt (kg)"],
        ["Stickstoff (N)",  f"{adjusted_demand:.1f}", f"{adjusted_demand*flaeche:.1f}" if flaeche else "k.A."],
        ["Phosphor (P2O5)", f"{adjusted_p:.1f}",      f"{adjusted_p*flaeche:.1f}"      if flaeche else "k.A."],
        ["Kalium (K2O)",    f"{adjusted_k:.1f}",      f"{adjusted_k*flaeche:.1f}"      if flaeche else "k.A."],
    ]
    bedarf_table = Table(bedarf_data, colWidths=[6*cm, 4.5*cm, 5.5*cm])
    bedarf_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), gruen),
        ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 9),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUND", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
        ("ALIGN",         (1, 0), (-1, -1), "CENTER"),
        ("PADDING",       (0, 0), (-1, -1), 6),
    ]))
    story.append(bedarf_table)
    story.append(Spacer(1, 0.4*cm))

    # 3. Duengungshistorie
    story.append(Paragraph("3. Durchgefuehrte Duengungsmassnahmen", h2_style))
    if historie:
        hist_data = [["#", "Datum", "Duengerart", "N (kg/ha)", "P (kg/ha)", "K (kg/ha)"]]
        for i, h in enumerate(historie, 1):
            hist_data.append([str(i), h["Datum"], h["Art"],
                               str(h["N_Menge"]), str(h["P_Menge"]), str(h["K_Menge"])])
        hist_table = Table(hist_data, colWidths=[1*cm, 3*cm, 4*cm, 2.5*cm, 2.5*cm, 2.5*cm])
        hist_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), gruen),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUND", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (2, 1), (2, -1), "LEFT"),
            ("PADDING",       (0, 0), (-1, -1), 5),
        ]))
        story.append(hist_table)
    else:
        story.append(Paragraph("Noch keine Duengungsmassnahmen erfasst.", body_style))
    story.append(Spacer(1, 0.4*cm))

    # 4. Saldo
    story.append(Paragraph("4. Naehrstoffsaldo", h2_style))
    saldo_n = total_n - adjusted_demand
    saldo_p = total_p - adjusted_p
    saldo_k = total_k - adjusted_k

    def saldo_farbe(s):
        if s > 0:   return colors.HexColor("#c62828")
        if s < -20: return colors.HexColor("#f57f17")
        return colors.HexColor("#2e7d32")

    saldo_data = [
        ["Naehrstoff", "Bedarf", "Geduengt", "Saldo", "Bewertung"],
        ["N",    f"{adjusted_demand:.1f}", f"{total_n:.1f}", f"{saldo_n:+.1f}",
         "Ueberschuss" if saldo_n > 0 else ("Unterversorgung" if saldo_n < -20 else "Im Rahmen")],
        ["P2O5", f"{adjusted_p:.1f}",     f"{total_p:.1f}", f"{saldo_p:+.1f}",
         "Ueberschuss" if saldo_p > 0 else ("Unterversorgung" if saldo_p < -20 else "Im Rahmen")],
        ["K2O",  f"{adjusted_k:.1f}",     f"{total_k:.1f}", f"{saldo_k:+.1f}",
         "Ueberschuss" if saldo_k > 0 else ("Unterversorgung" if saldo_k < -20 else "Im Rahmen")],
    ]
    saldo_table = Table(saldo_data, colWidths=[3*cm, 3*cm, 3*cm, 3*cm, 4*cm])
    saldo_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), gruen),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID",       (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ALIGN",      (1, 0), (-1, -1), "CENTER"),
        ("PADDING",    (0, 0), (-1, -1), 6),
        ("TEXTCOLOR",  (3, 1), (3, 1), saldo_farbe(saldo_n)),
        ("TEXTCOLOR",  (3, 2), (3, 2), saldo_farbe(saldo_p)),
        ("TEXTCOLOR",  (3, 3), (3, 3), saldo_farbe(saldo_k)),
        ("FONTNAME",   (3, 1), (3, -1), "Helvetica-Bold"),
    ]))
    story.append(saldo_table)
    story.append(Spacer(1, 0.4*cm))

    # 5. Fruchtfolge
    if fruchtfolge:
        story.append(Paragraph("5. Fruchtfolge (letzte Jahre)", h2_style))
        ff_data = [["Jahr", "Kultur", "Ertrag (dt/ha)", "Zwischenfrucht"]]
        for f in sorted(fruchtfolge, key=lambda x: x["Jahr"], reverse=True)[:6]:
            ff_data.append([
                str(f["Jahr"]), f["Kultur"],
                str(int(f["Ertrag (dt/ha)"])) if f["Ertrag (dt/ha)"] else "k.A.",
                f["Zwischenfrucht"] if f["Zwischenfrucht"] else "–"
            ])
        ff_table = Table(ff_data, colWidths=[2.5*cm, 5*cm, 4*cm, 4.5*cm])
        ff_table.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), gruen),
            ("TEXTCOLOR",     (0, 0), (-1, 0), colors.white),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("ROWBACKGROUND", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f9f9f9")]),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ALIGN",         (1, 1), (1, -1), "LEFT"),
            ("PADDING",       (0, 0), (-1, -1), 5),
        ]))
        story.append(ff_table)
        story.append(Spacer(1, 0.4*cm))

    # Fusszeile
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=6))
    story.append(Paragraph(
        "Dieses Dokument wurde automatisch durch HofPilot Pro erstellt und dient als "
        "Grundlage fuer die Düngebedarfsermittlung gemäss Duengeverordnung (DüV).",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7, textColor=colors.grey)
    ))
    story.append(Spacer(1, 1*cm))
    sign_table = Table(
        [["Ort, Datum", "", "Unterschrift Betriebsleiter"],
         ["_______________________", "", "_______________________"]],
        colWidths=[7*cm, 2*cm, 7*cm]
    )
    sign_table.setStyle(TableStyle([
        ("FONTSIZE",   (0, 0), (-1, -1), 8),
        ("ALIGN",      (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 1), (-1, 1), 18),
    ]))
    story.append(sign_table)
    doc.build(story)
    buffer.seek(0)
    return buffer

# =============================================================================
# APP-KONFIGURATION
# =============================================================================
st.set_page_config(page_title="HofPilot Cloud", layout="centered", page_icon="🚜")

PLANT_DATA = {
    "Winterweizen": {"bedarf": 230, "ertrag": 80,  "p_bedarf": 100, "k_bedarf": 120},
    "Wintergerste": {"bedarf": 180, "ertrag": 70,  "p_bedarf": 85,  "k_bedarf": 100},
    "Winterraps":   {"bedarf": 200, "ertrag": 40,  "p_bedarf": 75,  "k_bedarf": 90},
    "Koernermais":  {"bedarf": 200, "ertrag": 90,  "p_bedarf": 90,  "k_bedarf": 130},
    "Zuckerrueben": {"bedarf": 170, "ertrag": 650, "p_bedarf": 120, "k_bedarf": 200},
    "Kartoffeln":   {"bedarf": 180, "ertrag": 400, "p_bedarf": 130, "k_bedarf": 250},
}

BODENARTEN = ["Lehmiger Sand (lS)", "Sandiger Lehm (sL)", "Lehm (L)",
              "Toniger Lehm (tL)", "Ton (T)", "Schluff (U)"]

ZWISCHENFRUECHTE = ["–", "Senf", "Phacelia", "Oelrettich", "Gruenroggen",
                    "Wintererbse", "Klee", "Sonstige"]

st.title("🚜 HofPilot Pro (Cloud)")

# =============================================================================
# SIDEBAR
# =============================================================================
st.sidebar.header("Schlagverwaltung")

with st.sidebar.expander("➕ Neuen Schlag anlegen"):
    neuer_schlag = st.text_input("Schlagname", key="neuer_schlag_input")
    if st.button("Schlag anlegen"):
        if neuer_schlag.strip():
            if "alle_schlage" not in st.session_state:
                st.session_state.alle_schlage = load_all_schlage()
            if neuer_schlag.strip() not in st.session_state.alle_schlage:
                st.session_state.alle_schlage.append(neuer_schlag.strip())
            st.session_state.ausgewaehlter_schlag = neuer_schlag.strip()
            st.success(f"Schlag '{neuer_schlag.strip()}' angelegt!")
            st.rerun()
        else:
            st.warning("Bitte einen Namen eingeben.")

if "alle_schlage" not in st.session_state:
    st.session_state.alle_schlage = load_all_schlage()

schlag_optionen = st.session_state.alle_schlage if st.session_state.alle_schlage else ["Hinterm Hof"]
vorauswahl_index = 0
if "ausgewaehlter_schlag" in st.session_state:
    if st.session_state.ausgewaehlter_schlag in schlag_optionen:
        vorauswahl_index = schlag_optionen.index(st.session_state.ausgewaehlter_schlag)

with st.sidebar.expander("🗺️ Schlag auswählen", expanded=True):
    field_name = st.selectbox("Schlag", schlag_optionen,
                              index=vorauswahl_index, label_visibility="collapsed")
    st.session_state.ausgewaehlter_schlag = field_name

st.sidebar.header("Feldeinstellungen")
with st.sidebar.expander("🌾 Kultur auswählen", expanded=True):
    crop = st.selectbox("Kultur", list(PLANT_DATA.keys()), label_visibility="collapsed")

if "current_field" not in st.session_state or st.session_state.current_field != field_name:
    st.session_state.historie      = load_from_supabase(field_name)
    st.session_state.schlagkartei  = load_schlagkartei(field_name)
    st.session_state.fruchtfolge   = load_fruchtfolge(field_name)
    st.session_state.current_field = field_name

# =============================================================================
# TABS
# =============================================================================
tab_bilanz, tab_kartei, tab_fruchtfolge, tab_pdf = st.tabs([
    "🌱 N/P/K-Bilanz", "📋 Schlagkartei", "🔄 Fruchtfolge", "📄 PDF-Export"
])

# =============================================================================
# TAB 1 – N/P/K-BILANZ
# =============================================================================
with tab_bilanz:
    base_demand = PLANT_DATA[crop]["bedarf"]
    base_yield  = PLANT_DATA[crop]["ertrag"]
    p_bedarf    = PLANT_DATA[crop]["p_bedarf"]
    k_bedarf    = PLANT_DATA[crop]["k_bedarf"]

    st.subheader(f"Düngebedarf für {crop} – Schlag: {field_name}")
    actual_yield    = st.number_input("Erwarteter Ertrag (dt/ha)", value=float(base_yield), step=5.0)
    yield_diff      = actual_yield - base_yield
    adjusted_demand = base_demand + (yield_diff * 1.2)
    adjusted_p      = p_bedarf    + (yield_diff * 1.0)
    adjusted_k      = k_bedarf    + (yield_diff * 1.5)

    col_n, col_p, col_k = st.columns(3)
    col_n.info(f"**N-Bedarf**\n\n{adjusted_demand:.1f} kg/ha")
    col_p.info(f"**P\u2082O\u2085-Bedarf**\n\n{adjusted_p:.1f} kg/ha")
    col_k.info(f"**K\u2082O-Bedarf**\n\n{adjusted_k:.1f} kg/ha")

    total_n = sum(item["N_Menge"] for item in st.session_state.historie)
    total_p = sum(item["P_Menge"] for item in st.session_state.historie)
    total_k = sum(item["K_Menge"] for item in st.session_state.historie)

    with st.expander("Neue Gabe hinzufügen", expanded=True):
        col_date, col_type, col_amount = st.columns([2, 2, 1])
        with col_date:
            datum_input = st.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
        with col_type:
            art_input = st.selectbox("Düngerart", ["KAS", "Harnstoff", "Gülle", "Gärrest", "AHL"])
        with col_amount:
            n_input = st.number_input("N (kg/ha)", min_value=0, step=5)

        col_p_in, col_k_in = st.columns(2)
        with col_p_in:
            p_input = st.number_input("P\u2082O\u2085 (kg/ha)", min_value=0, step=5)
        with col_k_in:
            k_input = st.number_input("K\u2082O (kg/ha)", min_value=0, step=5)

        bemerkung_aktiv = st.checkbox("📝 Bemerkung hinzufügen")
        bemerkung_input = ""
        if bemerkung_aktiv:
            bemerkung_input = st.text_area("Bemerkung",
                placeholder="z. B. nach Regen ausgebracht, Teilfläche behandelt ...", max_chars=300)

        warnungen = []
        if n_input > 0 and (total_n + n_input - adjusted_demand) > 0:
            warnungen.append(f"N: **+{total_n + n_input - adjusted_demand:.1f} kg/ha**")
        if p_input > 0 and (total_p + p_input - adjusted_p) > 0:
            warnungen.append(f"P\u2082O\u2085: **+{total_p + p_input - adjusted_p:.1f} kg/ha**")
        if k_input > 0 and (total_k + k_input - adjusted_k) > 0:
            warnungen.append(f"K\u2082O: **+{total_k + k_input - adjusted_k:.1f} kg/ha**")
        if warnungen:
            st.warning("⚠️ Diese Gabe würde folgende Salden überschreiten: " + " | ".join(warnungen))

        if st.button("Gabe in Cloud speichern"):
            save_to_supabase(field_name, datum_input, art_input,
                             n_input, p_input, k_input, bemerkung_input)
            st.session_state.alle_schlage = load_all_schlage()
            st.session_state.historie = load_from_supabase(field_name)
            st.success("Erfolgreich gespeichert!")
            st.rerun()

    if st.session_state.historie:
        st.write("### Historie")
        df_hist = pd.DataFrame(st.session_state.historie)
        df_hist.index = range(1, len(df_hist) + 1)
        cols_show = ["Datum", "Art", "N_Menge", "P_Menge", "K_Menge"]
        if df_hist["Bemerkung"].str.strip().any():
            cols_show.append("Bemerkung")
        st.table(df_hist[cols_show])
        if st.button("Gesamte Historie für diesen Schlag löschen"):
            delete_history_from_supabase(field_name)
            st.session_state.historie = []
            st.rerun()

    st.divider()
    total_n = sum(item["N_Menge"] for item in st.session_state.historie)
    total_p = sum(item["P_Menge"] for item in st.session_state.historie)
    total_k = sum(item["K_Menge"] for item in st.session_state.historie)
    saldo_n = total_n - adjusted_demand
    saldo_p = total_p - adjusted_p
    saldo_k = total_k - adjusted_k

    col1, col2, col3 = st.columns(3)
    col1.metric("N-Saldo",             f"{saldo_n:.1f} kg/ha", delta=f"{saldo_n:.1f}", delta_color="inverse")
    col2.metric("P\u2082O\u2085-Saldo", f"{saldo_p:.1f} kg/ha", delta=f"{saldo_p:.1f}", delta_color="inverse")
    col3.metric("K\u2082O-Saldo",       f"{saldo_k:.1f} kg/ha", delta=f"{saldo_k:.1f}", delta_color="inverse")

    if st.session_state.historie:
        df_export = pd.DataFrame(st.session_state.historie)
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_export.to_excel(writer, index=False, sheet_name="NPK-Bilanz")
        st.download_button("📥 Excel-Bericht exportieren", output.getvalue(),
                           f"NPK-Bilanz_{field_name}.xlsx")

# =============================================================================
# TAB 2 – SCHLAGKARTEI
# =============================================================================
with tab_kartei:
    st.subheader(f"📋 Schlagkartei – {field_name}")
    kartei = st.session_state.schlagkartei

    def kval(key, default):
        return kartei[key] if kartei and kartei.get(key) else default

    eigentumsarten   = ["Eigentum", "Pacht", "Teilpacht"]
    eigentumsart_val = kval("eigentumsart", "Eigentum")
    bodenart_val     = kval("bodenart", BODENARTEN[0])

    with st.form("schlagkartei_form"):
        st.markdown("**Grunddaten**")
        col_f, col_e = st.columns(2)
        with col_f:
            flaeche_input = st.number_input("Fläche (ha)", min_value=0.0,
                                            value=kval("flaeche_ha", 0.0), step=0.5, format="%.2f")
        with col_e:
            eigentumsart_input = st.selectbox("Eigentumsart", eigentumsarten,
                index=eigentumsarten.index(eigentumsart_val) if eigentumsart_val in eigentumsarten else 0)

        col_boden, col_bwz = st.columns(2)
        with col_boden:
            bodenart_input = st.selectbox("Bodenart", BODENARTEN,
                index=BODENARTEN.index(bodenart_val) if bodenart_val in BODENARTEN else 0)
        with col_bwz:
            bodenwertzahl_input = st.number_input("Bodenwertzahl (Ackerzahl)", min_value=0,
                                                  max_value=100, value=int(kval("bodenwertzahl", 0)), step=1)

        st.markdown("**Pacht & Identifikation**")
        col_pp, col_pe = st.columns(2)
        with col_pp:
            pachtpreis_input = st.number_input(
                "Pachtpreis (€/ha/Jahr)", min_value=0.0,
                value=kval("pachtpreis_ha", 0.0), step=10.0, format="%.2f",
                help="Nur relevant bei Pacht oder Teilpacht")
        with col_pe:
            pachtende_val = kval("pachtende", None)
            pachtende_input = st.date_input(
                "Pachtende", value=pachtende_val if pachtende_val else date.today(), format="DD.MM.YYYY",
                help="Nur relevant bei Pacht oder Teilpacht")

        col_fn, col_gm = st.columns(2)
        with col_fn:
            feldnummer_input = st.text_input("Feldstücknummer (InVeKoS)",
                                             value=kval("feldstruecknummer", "") or "")
        with col_gm:
            gemarkung_input = st.text_input("Gemarkung / Lage",
                                            value=kval("gemarkung", "") or "")

        bemerkung_kartei = st.text_area("Bemerkungen (z. B. Drainage, Hanglage, Besonderheiten)",
                                        value=kval("bemerkung", "") or "", max_chars=500)

        if st.form_submit_button("💾 Schlagkartei speichern"):
            save_schlagkartei(
                field_name, flaeche_input, eigentumsart_input, bodenart_input,
                pachtpreis_input,
                pachtende_input if eigentumsart_input != "Eigentum" else None,
                feldnummer_input, gemarkung_input,
                bodenwertzahl_input, bemerkung_kartei
            )
            st.session_state.schlagkartei = load_schlagkartei(field_name)
            st.success("Schlagkartei gespeichert!")
            st.rerun()

    if kartei:
        st.divider()
        st.markdown("**Aktuelle Stammdaten**")
        k1, k2, k3 = st.columns([1, 1, 2])
        k1.metric("Fläche", f"{kartei['flaeche_ha']:.2f} ha")
        k2.metric("Eigentumsart", kartei["eigentumsart"] or "–")
        k3.metric("Bodenart", kartei["bodenart"] or "–")

        k4, k5, k6 = st.columns(3)
        k4.metric("Bodenwertzahl", int(kartei["bodenwertzahl"]) if kartei["bodenwertzahl"] else "–")
        k5.metric("Pachtpreis", f"{kartei['pachtpreis_ha']:.0f} €/ha" if kartei["pachtpreis_ha"] else "–")
        k6.metric("Pachtende", kartei["pachtende"].strftime("%d.%m.%Y") if kartei["pachtende"] else "–")

        if kartei["feldstruecknummer"] or kartei["gemarkung"]:
            k7, k8 = st.columns(2)
            k7.metric("Feldstücknummer", kartei["feldstruecknummer"] or "–")
            k8.metric("Gemarkung", kartei["gemarkung"] or "–")

        if kartei["bemerkung"]:
            st.info(f"📝 {kartei['bemerkung']}")

        # Pacht-Warnung wenn Pachtende in weniger als 12 Monaten
        if kartei["pachtende"] and kartei["eigentumsart"] in ["Pacht", "Teilpacht"]:
            from datetime import timedelta
            tage_bis_ende = (kartei["pachtende"] - date.today()).days
            if tage_bis_ende < 365:
                st.warning(
                    f"⚠️ Pachtvertrag läuft in **{tage_bis_ende} Tagen** "
                    f"am {kartei['pachtende'].strftime('%d.%m.%Y')} aus!"
                )

# =============================================================================
# TAB 3 – FRUCHTFOLGE
# =============================================================================
with tab_fruchtfolge:
    st.subheader(f"🔄 Fruchtfolge – {field_name}")

    with st.form("fruchtfolge_form"):
        st.markdown("**Neuen Eintrag hinzufügen**")
        col_j, col_k2 = st.columns(2)
        with col_j:
            ff_jahr = st.number_input("Jahr", min_value=2000, max_value=date.today().year,
                                      value=date.today().year - 1, step=1)
        with col_k2:
            ff_kultur = st.selectbox("Kultur", list(PLANT_DATA.keys()))

        col_e, col_zf = st.columns(2)
        with col_e:
            ff_ertrag = st.number_input("Ertrag (dt/ha)", min_value=0.0, step=5.0, value=0.0,
                                        help="0 = nicht erfasst")
        with col_zf:
            ff_zwischenfrucht = st.selectbox("Zwischenfrucht nach Ernte", ZWISCHENFRUECHTE)

        col_sd, col_ed = st.columns(2)
        with col_sd:
            ff_saatdatum   = st.date_input("Saatdatum",   value=date(int(ff_jahr), 10, 1), format="DD.MM.YYYY")
        with col_ed:
            ff_erntedatum  = st.date_input("Erntedatum",  value=date(int(ff_jahr) + 1, 7, 31)
                                            if ff_kultur not in ["Zuckerrueben", "Kartoffeln", "Koernermais"]
                                            else date(int(ff_jahr), 10, 15), format="DD.MM.YYYY")

        ff_bemerkung = st.text_input("Bemerkung (optional)", placeholder="z. B. Trockenschäden, Hagel ...")

        if st.form_submit_button("➕ Eintrag speichern"):
            save_fruchtfolge(
                field_name, int(ff_jahr), ff_kultur,
                ff_ertrag if ff_ertrag > 0 else None,
                ff_saatdatum, ff_erntedatum,
                ff_zwischenfrucht if ff_zwischenfrucht != "–" else "",
                ff_bemerkung
            )
            st.session_state.fruchtfolge = load_fruchtfolge(field_name)
            st.success(f"{int(ff_jahr)}: {ff_kultur} gespeichert!")
            st.rerun()

    if st.session_state.fruchtfolge:
        # Fruchtfolge-Bewertung
        warnungen_ff = bewerte_fruchtfolge(st.session_state.fruchtfolge)
        if warnungen_ff:
            st.markdown("### 🚦 Fruchtfolge-Bewertung")
            for w in warnungen_ff:
                st.warning(w)
        else:
            st.success("✅ Fruchtfolge agronomisch unauffällig.")

        # Ertragsentwicklung
        ertraege = [(e["Jahr"], e["Ertrag (dt/ha)"]) for e in st.session_state.fruchtfolge
                    if e["Ertrag (dt/ha)"] is not None]
        if len(ertraege) >= 2:
            st.markdown("### 📈 Ertragsentwicklung")
            df_ertrag = pd.DataFrame(ertraege, columns=["Jahr", "Ertrag (dt/ha)"])
            df_ertrag = df_ertrag.sort_values("Jahr").set_index("Jahr")
            st.line_chart(df_ertrag)

        # Bodenwertzahl-Vergleich
        if kartei and kartei.get("bodenwertzahl") and ertraege:
            bwz = kartei["bodenwertzahl"]
            # Einfacher Richtwert: Ackerzahl / 3 ≈ erwarteter Weizenertrag in dt/ha
            richtwert = bwz / 3
            letzter_ertrag = ertraege[0][1]  # neuester Eintrag
            if letzter_ertrag:
                diff = letzter_ertrag - richtwert
                if diff < -10:
                    st.warning(
                        f"📊 Letzter Ertrag ({letzter_ertrag:.0f} dt/ha) liegt "
                        f"**{abs(diff):.0f} dt/ha unter** dem Richtwert der Bodenwertzahl "
                        f"({richtwert:.0f} dt/ha bei AZ {int(bwz)})."
                    )
                elif diff > 10:
                    st.success(
                        f"📊 Letzter Ertrag ({letzter_ertrag:.0f} dt/ha) liegt "
                        f"**{diff:.0f} dt/ha über** dem Richtwert der Bodenwertzahl "
                        f"({richtwert:.0f} dt/ha bei AZ {int(bwz)})."
                    )

        st.markdown("### Übersicht")
        df_ff = pd.DataFrame(st.session_state.fruchtfolge)
        df_ff = df_ff.sort_values("Jahr", ascending=False).reset_index(drop=True)
        df_ff.index = range(1, len(df_ff) + 1)
        # Spalten ohne leere Felder kompakt anzeigen
        cols_ff = ["Jahr", "Kultur", "Ertrag (dt/ha)", "Saatdatum", "Erntedatum", "Zwischenfrucht"]
        st.table(df_ff[cols_ff])

        st.markdown("**Eintrag löschen:**")
        jahre_liste = [str(e["Jahr"]) for e in st.session_state.fruchtfolge]
        del_jahr = st.selectbox("Jahr auswählen", jahre_liste, key="del_ff_jahr")
        if st.button("🗑️ Eintrag löschen"):
            delete_fruchtfolge_eintrag(field_name, int(del_jahr))
            st.session_state.fruchtfolge = load_fruchtfolge(field_name)
            st.rerun()
    else:
        st.info("Noch keine Fruchtfolge-Einträge für diesen Schlag vorhanden.")

# =============================================================================
# TAB 4 – PDF-EXPORT
# =============================================================================
with tab_pdf:
    st.subheader("📄 Düngebedarfsformular (PDF)")
    st.markdown("Erstelle ein offizielles Düngebedarfsformular gemäß Düngeverordnung (DüV).")

    betrieb_name = st.text_input("Betriebsname (optional)", placeholder="z. B. Hof Müller")

    kartei_pdf  = st.session_state.schlagkartei
    flaeche_pdf = float(kartei_pdf["flaeche_ha"]) if kartei_pdf and kartei_pdf["flaeche_ha"] else 0.0

    base_demand_pdf = PLANT_DATA[crop]["bedarf"]
    base_yield_pdf  = PLANT_DATA[crop]["ertrag"]
    p_bedarf_pdf    = PLANT_DATA[crop]["p_bedarf"]
    k_bedarf_pdf    = PLANT_DATA[crop]["k_bedarf"]
    adj_demand_pdf  = base_demand_pdf
    adj_p_pdf       = p_bedarf_pdf
    adj_k_pdf       = k_bedarf_pdf

    total_n_pdf = sum(item["N_Menge"] for item in st.session_state.historie)
    total_p_pdf = sum(item["P_Menge"] for item in st.session_state.historie)
    total_k_pdf = sum(item["K_Menge"] for item in st.session_state.historie)

    st.info(
        f"**Schlag:** {field_name}  |  **Kultur:** {crop}  |  "
        f"**Fläche:** {flaeche_pdf:.2f} ha  |  "
        f"**Einträge in Historie:** {len(st.session_state.historie)}"
    )

    if st.button("📄 PDF generieren"):
        pdf_buffer = generate_pdf(
            schlag=field_name, crop=crop, kartei=kartei_pdf,
            adjusted_demand=adj_demand_pdf, adjusted_p=adj_p_pdf, adjusted_k=adj_k_pdf,
            total_n=total_n_pdf, total_p=total_p_pdf, total_k=total_k_pdf,
            historie=st.session_state.historie,
            fruchtfolge=st.session_state.fruchtfolge,
            betrieb_name=betrieb_name
        )
        st.download_button(
            label="⬇️ PDF herunterladen",
            data=pdf_buffer,
            file_name=f"Duengebedarf_{field_name}_{date.today().strftime('%Y%m%d')}.pdf",
            mime="application/pdf"
        )