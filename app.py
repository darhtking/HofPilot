import streamlit as st
import psycopg2
import pandas as pd
from io import BytesIO
from datetime import date

import streamlit as st
from supabase import create_client, Client

# --- SUPABASE AUTH SETUP ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(url, key)

def auth_form():
    st.title("🚜 HofPilot Zugang")
    
    tab1, tab2 = st.tabs(["Login", "Registrieren"])
    
    with tab1:
        email = st.text_input("E-Mail", key="login_email")
        password = st.text_input("Passwort", type="password", key="login_pw")
        if st.button("Anmelden"):
            try:
                # Supabase Login
                response = supabase.auth.sign_in_with_password({"email": email, "password": password})
                st.session_state.user = response.user
                st.success("Willkommen zurück!")
                st.rerun()
            except Exception as e:
                st.error(f"Login fehlgeschlagen: {e}")

    with tab2:
        new_email = st.text_input("E-Mail", key="reg_email")
        new_password = st.text_input("Passwort (min. 6 Zeichen)", type="password", key="reg_pw")
        if st.button("Konto erstellen"):
            try:
                # Supabase Registrierung
                response = supabase.auth.sign_up({"email": new_email, "password": new_password})
                st.success("Konto erstellt! Du kannst dich jetzt einloggen.")
            except Exception as e:
                st.error(f"Registrierung fehlgeschlagen: {e}")

# --- AUTH LOGIK ---
if "user" not in st.session_state:
    auth_form()
    st.stop()

# Ab hier ist der User eingeloggt
user_id = st.session_state.user.id
st.sidebar.write(f"Nutzer: {st.session_state.user.email}")

if st.sidebar.button("Logout"):
    supabase.auth.sign_out()
    del st.session_state.user
    st.rerun()
    
# --- 1. DATENBANK-KONFIGURATION ---
DB_URI = st.secrets["DB_URI"]

def get_connection():
    return psycopg2.connect(DB_URI)

# --- 2. DATENBANK-FUNKTIONEN ---
def save_to_supabase(schlag, datum, art, menge):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO n_bilanz (schlag_name, datum, duenger_art, n_menge) VALUES (%s, %s, %s, %s)",
            (schlag, datum, art, menge)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Fehler beim Speichern: {e}")

def load_from_supabase(schlag):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT datum, duenger_art, n_menge FROM n_bilanz WHERE schlag_name = %s ORDER BY datum ASC", 
            (schlag,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [{"Datum": r[0], "Art": r[1], "N_Menge": r[2]} for r in rows]
    except Exception as e:
        st.error(f"Fehler beim Laden: {e}")
        return []

def delete_history_from_supabase(schlag):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM n_bilanz WHERE schlag_name = %s", (schlag,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"Fehler beim Löschen: {e}")

# --- 3. APP-KONFIGURATION & DATEN ---
st.set_page_config(page_title="HofPilot Cloud", layout="centered", page_icon="🚜")

PLANT_DATA = {
    "Winterweizen": {"bedarf": 230, "ertrag": 80},
    "Wintergerste": {"bedarf": 180, "ertrag": 70},
    "Winterraps": {"bedarf": 200, "ertrag": 40},
    "Körnermais": {"bedarf": 200, "ertrag": 90},
    "Zuckerrüben": {"bedarf": 170, "ertrag": 650},
    "Kartoffeln": {"bedarf": 180, "ertrag": 400}
}

st.title("🚜 HofPilot Pro (Cloud)")

# --- 4. SIDEBAR & BEDARF ---
st.sidebar.header("Feldeinstellungen")
field_name = st.sidebar.text_input("Name des Schlags", "Hinterm Hof")
crop = st.sidebar.selectbox("Kultur wählen", list(PLANT_DATA.keys()))

# Automatisches Laden der Daten, wenn sich der Schlagname ändert
if "current_field" not in st.session_state or st.session_state.current_field != field_name:
    st.session_state.historie = load_from_supabase(field_name)
    st.session_state.current_field = field_name

base_demand = PLANT_DATA[crop]["bedarf"]
base_yield = PLANT_DATA[crop]["ertrag"]

st.subheader(f"Düngebedarf für {crop}")
actual_yield = st.number_input(f"Erwarteter Ertrag (dt/ha)", value=float(base_yield), step=1.0)

yield_diff = actual_yield - base_yield
adjusted_demand = base_demand + (yield_diff * 1.2)

st.info(f"Gesetzlicher Bedarf: **{adjusted_demand:.1f} kg N/ha**")

# --- 5. NEUE GABE HINZUFÜGEN ---
with st.expander("Neue Gabe hinzufügen", expanded=True):
    col_date, col_type, col_amount = st.columns([2, 2, 1])
    with col_date:
        datum_input = st.date_input("Datum", value=date.today())
    with col_type:
        art_input = st.selectbox("Düngerart", ["KAS", "Harnstoff", "Gülle", "Gärrest", "AHL"])
    with col_amount:
        menge_input = st.number_input("Menge (kg N/ha)", min_value=0, step=1)
    
    if st.button("Gabe in Cloud speichern"):
        save_to_supabase(field_name, datum_input, art_input, menge_input)
        st.session_state.historie = load_from_supabase(field_name)
        st.success("Erfolgreich in Supabase gespeichert!")
        st.rerun()

# --- 6. HISTORIE & SALDO ---
total_n = sum(item["N_Menge"] for item in st.session_state.historie)

if st.session_state.historie:
    st.write("### Historie (aus Cloud geladen)")
    st.table(pd.DataFrame(st.session_state.historie))
    
    if st.button("Gesamte Historie für diesen Schlag löschen"):
        delete_history_from_supabase(field_name)
        st.session_state.historie = []
        st.rerun()

st.divider()
saldo = total_n - adjusted_demand

col_a, col_b = st.columns(2)
col_a.metric("Summe Düngung", f"{total_n} kg N")
col_b.metric("N-Saldo", f"{saldo:.1f} kg N", delta=f"{saldo:.1f} kg", delta_color="inverse")

# --- 7. EXPORT ---
if st.session_state.historie:
    df_export = pd.DataFrame(st.session_state.historie)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_export.to_excel(writer, index=False, sheet_name='N-Bilanz')
    st.download_button("📥 Excel-Bericht exportieren", output.getvalue(), f"N-Bilanz_{field_name}.xlsx")