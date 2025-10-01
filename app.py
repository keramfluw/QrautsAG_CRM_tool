
import streamlit as st
import pandas as pd
import sqlite3
from datetime import date
import matplotlib.pyplot as plt

DB_PATH = "qrauts_crm.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            industry TEXT,
            city TEXT,
            country TEXT,
            website TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            first_name TEXT,
            last_name TEXT,
            email TEXT UNIQUE,
            phone TEXT,
            role TEXT,
            company_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
        );""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            company_id INTEGER,
            contact_id INTEGER,
            amount_eur REAL DEFAULT 0,
            stage TEXT CHECK(stage IN ('New','Qualified','Proposal','Won','Lost')) NOT NULL DEFAULT 'New',
            probability INTEGER DEFAULT 10,
            expected_close DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL
        );""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            deal_id INTEGER,
            contact_id INTEGER,
            company_id INTEGER,
            activity_type TEXT CHECK(activity_type IN ('Note','Call','Meeting','Task')) NOT NULL DEFAULT 'Note',
            title TEXT NOT NULL,
            description TEXT,
            due_date DATE,
            done INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(deal_id) REFERENCES deals(id) ON DELETE SET NULL,
            FOREIGN KEY(contact_id) REFERENCES contacts(id) ON DELETE SET NULL,
            FOREIGN KEY(company_id) REFERENCES companies(id) ON DELETE SET NULL
        );""")
    conn.commit()
    conn.close()

def df_read(sql, params=None):
    conn = get_conn()
    df = pd.read_sql_query(sql, conn, params=params or [])
    conn.close()
    return df

def exec_sql(sql, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(sql, params or [])
    conn.commit()
    last_id = cur.lastrowid
    conn.close()
    return last_id

def exec_many(sql, params_list):
    conn = get_conn()
    cur = conn.cursor()
    cur.executemany(sql, params_list)
    conn.commit()
    conn.close()

def header():
    st.write("### Qrauts AG · CRM (MVP)")
    st.caption("Kontakte · Firmen · Deals · Aktivitäten · Pipeline")
    st.divider()

def sidebar():
    return st.sidebar.radio("Navigation",
        ["Dashboard","Firmen","Kontakte","Deals","Aktivitäten","Import/Export","Einstellungen"], index=0)

def ensure_sample_data():
    comp_count = df_read("SELECT COUNT(*) AS c FROM companies")["c"][0]
    if comp_count == 0:
        exec_many("INSERT INTO companies (name,industry,city,country,website) VALUES (?,?,?,?,?)",
                  [("Quartierkraft GmbH","Energy","Freiburg","DE","https://quartierkraft.de"),
                   ("EBNE Immobilien","Real Estate","Leipzig","DE","https://example.com")])
    contact_count = df_read("SELECT COUNT(*) AS c FROM contacts")["c"][0]
    if contact_count == 0:
        comps = df_read("SELECT id, name FROM companies")
        mp = {r['name']: r['id'] for _, r in comps.iterrows()}
        exec_many("INSERT INTO contacts (first_name,last_name,email,phone,role,company_id) VALUES (?,?,?,?,?,?)",
                  [("Annika","Klatte","annika@example.com","+49 761 1234","Projektleitung",mp.get("Quartierkraft GmbH")),
                   ("Gerd","Beispiel","gerd@example.com","+49 341 5678","Technik",mp.get("EBNE Immobilien"))])
    deal_count = df_read("SELECT COUNT(*) AS c FROM deals")["c"][0]
    if deal_count == 0:
        co = df_read("SELECT id FROM companies WHERE name='Quartierkraft GmbH'")
        co_id = int(co.iloc[0]['id']) if len(co) else None
        exec_sql("INSERT INTO deals (name,company_id,amount_eur,stage,probability,expected_close) VALUES (?,?,?,?,?,?)",
                 ("PV+Speicher – MFH Freiburg", co_id, 180000, "Qualified", 30, str(date.today())))

def page_dashboard():
    header()
    deals = df_read("SELECT * FROM deals")
    col1,col2,col3 = st.columns(3)
    won_sum = deals.loc[deals['stage']=="Won", 'amount_eur'].sum() if not deals.empty else 0.0
    open_sum = deals.loc[~deals['stage'].isin(["Won","Lost"]), 'amount_eur'].sum() if not deals.empty else 0.0
    col1.metric("Deals gesamt", len(deals))
    col2.metric("Pipeline (offen) €", f"{open_sum:,.0f}".replace(",","."))
    col3.metric("Gewonnen YTD €", f"{won_sum:,.0f}".replace(",","."))

    st.subheader("Pipeline nach Phase (€)")
    if deals.empty:
        st.info("Keine Deals vorhanden.")
    else:
        agg = deals.groupby("stage")["amount_eur"].sum().reset_index()
        fig, ax = plt.subplots()
        ax.bar(agg["stage"], agg["amount_eur"])
        ax.set_xlabel("Phase"); ax.set_ylabel("Summe (€)"); ax.set_title("Pipeline nach Phase")
        st.pyplot(fig)

    st.subheader("Nächste fällige Aktivitäten")
    acts = df_read("SELECT * FROM activities WHERE done=0 AND due_date IS NOT NULL ORDER BY due_date ASC LIMIT 10")
    st.dataframe(acts if not acts.empty else pd.DataFrame(columns=["info"], data=[["Keine offenen Aktivitäten."]]))

def page_companies():
    header(); st.write("#### Firmen")
    tab1, tab2 = st.tabs(["Übersicht", "Neu/Update"])
    with tab1:
        st.dataframe(df_read("SELECT * FROM companies ORDER BY created_at DESC"))
    with tab2:
        name = st.text_input("Name*"); industry=st.text_input("Branche"); city=st.text_input("Stadt")
        country = st.text_input("Land", value="DE"); website=st.text_input("Website (URL)")
        if st.button("Firma anlegen"):
            if not name: st.error("Name ist Pflicht.")
            else:
                try:
                    exec_sql("INSERT INTO companies (name,industry,city,country,website) VALUES (?,?,?,?,?)",
                             (name,industry,city,country,website)); st.success(f"Firma '{name}' angelegt.")
                except Exception as e: st.error(f"Fehler: {e}")

def page_contacts():
    header(); st.write("#### Kontakte")
    tab1, tab2 = st.tabs(["Übersicht", "Neu/Update"])
    with tab1:
        st.dataframe(df_read("""
            SELECT c.id, c.first_name, c.last_name, c.email, c.phone, c.role, co.name AS company, c.created_at
            FROM contacts c LEFT JOIN companies co ON c.company_id = co.id
            ORDER BY c.created_at DESC"""))
    with tab2:
        companies = df_read("SELECT id, name FROM companies ORDER BY name ASC")
        sels = ["-"] + companies["name"].tolist()
        first_name=st.text_input("Vorname"); last_name=st.text_input("Nachname")
        email=st.text_input("E-Mail"); phone=st.text_input("Telefon"); role=st.text_input("Rolle/Funktion")
        company_sel = st.selectbox("Firma", sels)
        company_id = int(companies.loc[companies["name"]==company_sel,"id"].iloc[0]) if company_sel!="-" and not companies.empty else None
        if st.button("Kontakt anlegen"):
            try:
                exec_sql("INSERT INTO contacts (first_name,last_name,email,phone,role,company_id) VALUES (?,?,?,?,?,?)",
                         (first_name,last_name,email,phone,role,company_id)); st.success("Kontakt angelegt.")
            except Exception as e: st.error(f"Fehler: {e}")

def page_deals():
    header(); st.write("#### Deals")
    tab1, tab2 = st.tabs(["Übersicht", "Neu/Update"])
    with tab1:
        st.dataframe(df_read("""
            SELECT d.id, d.name, co.name AS company, c.first_name||' '||c.last_name AS contact,
                   d.amount_eur, d.stage, d.probability, d.expected_close, d.created_at
            FROM deals d
            LEFT JOIN companies co ON d.company_id = co.id
            LEFT JOIN contacts c ON d.contact_id = c.id
            ORDER BY d.created_at DESC"""))
    with tab2:
        comps = df_read("SELECT id, name FROM companies ORDER BY name ASC")
        conts = df_read("SELECT id, first_name||' '||last_name AS name FROM contacts ORDER BY name ASC")
        company = st.selectbox("Firma", ["-"] + comps["name"].tolist())
        contact = st.selectbox("Kontakt", ["-"] + conts["name"].tolist())
        name = st.text_input("Deal-Name*")
        amount = st.number_input("Betrag (€)", min_value=0.0, value=0.0, step=1000.0, format="%.2f")
        stage = st.selectbox("Phase", ["New","Qualified","Proposal","Won","Lost"], index=0)
        probability = st.slider("Wahrscheinlichkeit (%)", 0, 100, 10, step=5)
        expected_close = st.date_input("Geplantes Abschlussdatum", value=date.today())
        if st.button("Deal anlegen"):
            if not name: st.error("Deal-Name ist Pflicht.")
            else:
                company_id = int(comps.loc[comps["name"]==company,"id"].iloc[0]) if company!="-"" and not comps.empty else None
                contact_id = int(conts.loc[conts["name"]==contact,"id"].iloc[0]) if contact!="-"" and not conts.empty else None
                try:
                    exec_sql("INSERT INTO deals (name,company_id,contact_id,amount_eur,stage,probability,expected_close) VALUES (?,?,?,?,?,?,?)",
                             (name,company_id,contact_id,amount,stage,probability,str(expected_close)))
                    st.success("Deal angelegt.")
                except Exception as e: st.error(f"Fehler: {e}")

def page_activities():
    header(); st.write("#### Aktivitäten")
    tab1, tab2 = st.tabs(["Übersicht", "Neu/Update"])
    with tab1:
        st.dataframe(df_read("""
            SELECT a.id, a.activity_type, a.title, a.description, a.due_date, a.done,
                   co.name AS company, d.name AS deal, c.first_name||' '||c.last_name AS contact, a.created_at
            FROM activities a
            LEFT JOIN companies co ON a.company_id = co.id
            LEFT JOIN deals d ON a.deal_id = d.id
            LEFT JOIN contacts c ON a.contact_id = c.id
            ORDER BY a.created_at DESC"""))
    with tab2:
        comps = df_read("SELECT id, name FROM companies ORDER BY name ASC")
        deals = df_read("SELECT id, name FROM deals ORDER BY created_at DESC")
        conts = df_read("SELECT id, first_name||' '||last_name AS name FROM contacts ORDER BY name ASC")
        activity_type = st.selectbox("Typ", ["Note","Call","Meeting","Task"])
        title = st.text_input("Titel*"); description = st.text_area("Beschreibung")
        due = st.date_input("Fällig am", value=date.today()); done = st.checkbox("Erledigt?")
        co_sel = st.selectbox("Firma", ["-"] + comps["name"].tolist())
        de_sel = st.selectbox("Deal", ["-"] + deals["name"].tolist())
        ct_sel = st.selectbox("Kontakt", ["-"] + conts["name"].tolist())
        if st.button("Aktivität anlegen"):
            if not title: st.error("Titel ist Pflicht.")
            else:
                co_id = int(comps.loc[comps["name"]==co_sel,"id"].iloc[0]) if co_sel!="-"" and not comps.empty else None
                de_id = int(deals.loc[deals["name"]==de_sel,"id"].iloc[0]) if de_sel!="-"" and not deals.empty else None
                ct_id = int(conts.loc[conts["name"]==ct_sel,"id"].iloc[0]) if ct_sel!="-"" and not conts.empty else None
                try:
                    exec_sql("INSERT INTO activities (deal_id,contact_id,company_id,activity_type,title,description,due_date,done) VALUES (?,?,?,?,?,?,?,?)",
                             (de_id,ct_id,co_id,activity_type,title,description,str(due),int(done)))
                    st.success("Aktivität angelegt.")
                except Exception as e: st.error(f"Fehler: {e}")

def page_import_export():
    header(); st.write("#### Import / Export (CSV)")
    action = st.selectbox("Tabelle", ["companies","contacts","deals","activities"])
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Export**")
        if st.button("CSV exportieren"):
            df = df_read(f"SELECT * FROM {action}")
            st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"),
                               file_name=f"{action}.csv", mime="text/csv")
    with c2:
        st.write("**Import**")
        uploaded = st.file_uploader("CSV auswählen", type=["csv"])
        if uploaded is not None:
            df = pd.read_csv(uploaded)
            try:
                conn = get_conn(); df.to_sql(action, conn, if_exists="append", index=False); conn.close()
                st.success(f"{len(df)} Zeilen in '{action}' importiert.")
            except Exception as e:
                st.error(f"Import-Fehler: {e}")

def page_settings():
    header(); st.write("#### Einstellungen")
    st.write("- Dieses MVP nutzt **SQLite** (Datei `qrauts_crm.db`).")
    if st.button("Datenbank initialisieren / Seed-Daten laden"):
        init_db(); ensure_sample_data(); st.success("Datenbank initialisiert und Beispiel-Daten hinzugefügt.")

def main():
    st.set_page_config(page_title="Qrauts CRM (MVP)", page_icon="📈", layout="wide")
    init_db()
    view = sidebar()
    if view == "Dashboard": page_dashboard()
    elif view == "Firmen": page_companies()
    elif view == "Kontakte": page_contacts()
    elif view == "Deals": page_deals()
    elif view == "Aktivitäten": page_activities()
    elif view == "Import/Export": page_import_export()
    elif view == "Einstellungen": page_settings()

if __name__ == "__main__":
    main()
