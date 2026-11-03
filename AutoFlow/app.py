import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import requests

from pathlib import Path
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

# ---------------- CONFIG ----------------

st.set_page_config(
    page_title="AutoFlow | Automation Hub",
    page_icon="⚡",
    layout="wide"
)

DB = Path(__file__).with_name("autoflow.db")


# ---------------- DATABASE ----------------

def db():
    return sqlite3.connect(DB, timeout=10)


def init_db():
    with db() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS workflows(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            task TEXT,
            frequency TEXT,
            condition_type TEXT,
            webhook TEXT,
            enabled INTEGER DEFAULT 1,
            created TEXT
        )
        """)

        con.execute("""
        CREATE TABLE IF NOT EXISTS logs(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id INTEGER,
            name TEXT,
            status TEXT,
            message TEXT,
            time TEXT
        )
        """)


init_db()


# ---------------- DATA ----------------

def get_workflows():
    with db() as con:
        return pd.read_sql_query(
            "SELECT * FROM workflows ORDER BY id DESC", con
        )


def get_logs():
    with db() as con:
        return pd.read_sql_query(
            "SELECT * FROM logs ORDER BY id DESC", con
        )


def save_log(wid, name, status, message):
    with db() as con:
        con.execute("""
        INSERT INTO logs(workflow_id,name,status,message,time)
        VALUES(?,?,?,?,?)
        """, (
            wid, name, status, message,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))


# ---------------- AUTOMATION ENGINE ----------------

def execute(wid):
    with db() as con:
        row = con.execute(
            "SELECT * FROM workflows WHERE id=?", (wid,)
        ).fetchone()

    if not row:
        return False, "Workflow not found"

    _, name, task, frequency, condition, webhook, enabled, created = row

    if not enabled:
        return False, "Workflow is disabled"

    try:
        if condition == "Never":
            save_log(wid, name, "Skipped", "Condition not met")
            return True, "Workflow skipped"

        if task == "Create Report":
            logs = get_logs()
            report = {
                "workflow": name,
                "generated_at": datetime.now().isoformat(),
                "previous_executions": len(logs)
            }
            Path(f"report_{wid}.json").write_text(
                pd.Series(report).to_json(indent=4),
                encoding="utf-8"
            )
            message = "Report created successfully"

        elif task == "Backup Workflow Data":
            data = get_workflows()
            Path(f"backup_{wid}.csv").write_text(
                data.to_csv(index=False),
                encoding="utf-8"
            )
            message = "Backup created successfully"

        elif task == "Show Reminder":
            message = "Reminder triggered successfully"

        elif task == "Send Webhook":
            if not webhook:
                raise ValueError("Webhook URL is required")

            response = requests.post(
                webhook,
                json={
                    "workflow": name,
                    "time": datetime.now().isoformat()
                },
                timeout=10
            )
            response.raise_for_status()
            message = f"Webhook sent: HTTP {response.status_code}"

        else:
            raise ValueError("Unknown task")

        save_log(wid, name, "Success", message)
        return True, message

    except Exception as e:
        save_log(wid, name, "Failed", str(e))
        return False, str(e)


# ---------------- SCHEDULER ----------------

@st.cache_resource
def get_scheduler():
    scheduler = BackgroundScheduler(daemon=True)
    scheduler.start()
    return scheduler


scheduler = get_scheduler()


def update_schedule(wid, frequency, enabled):
    job_id = f"workflow_{wid}"

    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if enabled and frequency in ["Hourly", "Daily", "Weekly"]:
        minutes = {
            "Hourly": 60,
            "Daily": 1440,
            "Weekly": 10080
        }[frequency]

        scheduler.add_job(
            execute,
            IntervalTrigger(minutes=minutes),
            args=[wid],
            id=job_id,
            replace_existing=True
        )


# Restore schedules when the app starts
for _, item in get_workflows().iterrows():
    update_schedule(
        int(item["id"]),
        item["frequency"],
        bool(item["enabled"])
    )


# ---------------- DESIGN ----------------

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

* {font-family:Inter,sans-serif;}
.stApp {background:#f4f6fc;}

[data-testid="stSidebar"] {
    background:linear-gradient(180deg,#111827,#292052);
}
[data-testid="stSidebar"] * {color:white;}

.main .block-container {
    max-width:1300px;
    padding-top:2rem;
}

div[data-testid="stMetric"] {
    background:white;
    padding:20px;
    border-radius:15px;
    border:1px solid #e5e7eb;
    box-shadow:0 4px 15px #00000008;
}

div[data-testid="stMetricValue"] {
    color:#5145d8;
    font-weight:800;
}

.stButton>button {
    background:linear-gradient(90deg,#5145d8,#8054df);
    color:white;
    border:0;
    border-radius:9px;
    font-weight:600;
}

.hero {
    background:linear-gradient(120deg,#171d3c,#4338ca,#8054df);
    color:white;
    padding:30px;
    border-radius:18px;
    margin-bottom:25px;
}
.hero h2 {color:white;}
.hero p {color:#e0e7ff;}
</style>
""", unsafe_allow_html=True)


# ---------------- SIDEBAR ----------------

with st.sidebar:
    st.markdown("# ⚡ AutoFlow")
    st.caption("AUTOMATION WORKSPACE")
    st.divider()

    page = st.radio("NAVIGATION", [
        "Dashboard",
        "AI Workflow Generator",
        "Create Workflow",
        "Templates",
        "Manage Workflows",
        "Execution History",
        "Analytics"
    ])

    st.divider()
    st.success("System Online")


# ---------------- LOAD DATA ----------------

workflows = get_workflows()
logs = get_logs()

success = len(logs[logs.status == "Success"]) if not logs.empty else 0
failed = len(logs[logs.status == "Failed"]) if not logs.empty else 0


# ---------------- DASHBOARD ----------------

if page == "Dashboard":

    st.markdown("""
    <div class="hero">
    <h2>Welcome to AutoFlow ⚡</h2>
    <p>Automate tasks. Manage workflows. Monitor performance.</p>
    </div>
    """, unsafe_allow_html=True)

    a, b, c, d = st.columns(4)
    a.metric("Workflows", len(workflows))
    b.metric("Executions", len(logs))
    c.metric("Successful", success)
    d.metric("Failed", failed)

    left, right = st.columns(2)

    with left:
        st.subheader("Your Workflows")
        if not workflows.empty:
            st.dataframe(
                workflows[["name", "task", "frequency", "enabled"]],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Create your first workflow.")

    with right:
        st.subheader("Execution Analytics")
        if not logs.empty:
            counts = logs.status.value_counts().reset_index()
            counts.columns = ["Status", "Count"]
            fig = px.pie(
                counts, names="Status", values="Count",
                hole=0.5
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No execution data yet.")

    st.subheader("Recent Activity")
    if not logs.empty:
        st.dataframe(logs.head(5), use_container_width=True, hide_index=True)


# ---------------- AI-STYLE GENERATOR ----------------

elif page == "AI Workflow Generator":

    st.title("🤖 Workflow Generator")
    prompt = st.text_input(
        "Describe what you want to automate"
    )

    if st.button("Generate Suggestion"):
        p = prompt.lower()

        if "backup" in p:
            task, freq = "Backup Workflow Data", "Weekly"
        elif "reminder" in p:
            task, freq = "Show Reminder", "Daily"
        elif "webhook" in p:
            task, freq = "Send Webhook", "Manual"
        else:
            task, freq = "Create Report", "Daily"

        st.success("Suggested workflow")
        st.write("Task:", task)
        st.write("Frequency:", freq)
        st.info("Use these settings in Create Workflow.")


# ---------------- CREATE WORKFLOW ----------------

elif page == "Create Workflow":

    st.title("＋ Create Workflow")

    with st.form("create_form"):
        name = st.text_input("Workflow Name")

        task = st.selectbox("Automation Task", [
            "Create Report",
            "Backup Workflow Data",
            "Show Reminder",
            "Send Webhook"
        ])

        freq = st.selectbox("Frequency", [
            "Manual", "Hourly", "Daily", "Weekly"
        ])

        condition = st.selectbox(
            "Execution Condition", ["Always", "Never"]
        )

        webhook = ""
        if task == "Send Webhook":
            webhook = st.text_input("Webhook URL")

        description = st.text_area("Description")

        submit = st.form_submit_button("Create Workflow")

        if submit:
            if not name.strip():
                st.error("Enter a workflow name.")
            elif name.strip().lower() in workflows.name.str.lower().tolist():
                st.error("Workflow name already exists.")
            else:
                try:
                    with db() as con:
                        cur = con.execute("""
                        INSERT INTO workflows
                        (name,task,frequency,condition_type,webhook,created)
                        VALUES(?,?,?,?,?,?)
                        """, (
                            name.strip(), task, freq, condition,
                            webhook, datetime.now().strftime("%Y-%m-%d %H:%M")
                        ))
                        wid = cur.lastrowid

                    update_schedule(wid, freq, True)
                    st.success("Workflow created successfully!")
                    st.rerun()

                except sqlite3.Error as e:
                    st.error(str(e))


# ---------------- TEMPLATES ----------------

elif page == "Templates":

    st.title("📚 Workflow Templates")

    templates = [
        ("Daily Report", "Create Report", "Daily"),
        ("Weekly Backup", "Backup Workflow Data", "Weekly"),
        ("Task Reminder", "Show Reminder", "Daily")
    ]

    for name, task, freq in templates:
        with st.container(border=True):
            st.write(f"**{name}** — {task} ({freq})")

            if st.button("Add Template", key=name):
                if name in workflows.name.tolist():
                    st.warning("Template already exists.")
                else:
                    with db() as con:
                        cur = con.execute("""
                        INSERT INTO workflows
                        (name,task,frequency,condition_type,created)
                        VALUES(?,?,?,?,?)
                        """, (
                            name, task, freq, "Always",
                            datetime.now().strftime("%Y-%m-%d %H:%M")
                        ))
                        wid = cur.lastrowid

                    update_schedule(wid, freq, True)
                    st.success("Template added!")
                    st.rerun()


# ---------------- MANAGE WORKFLOWS ----------------

elif page == "Manage Workflows":

    st.title("⚙️ Manage Workflows")

    if workflows.empty:
        st.info("No workflows available.")

    for _, wf in workflows.iterrows():

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])

            with c1:
                st.subheader(wf["name"])
                st.caption(f'{wf["task"]} · {wf["frequency"]}')

            with c2:
                if st.button("▶ Run", key=f'run{wf["id"]}'):
                    ok, msg = execute(int(wf["id"]))
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)
                    st.rerun()

            with c3:
                enabled = bool(wf["enabled"])
                if st.button(
                    "Disable" if enabled else "Enable",
                    key=f'toggle{wf["id"]}'
                ):
                    new_state = 0 if enabled else 1

                    with db() as con:
                        con.execute(
                            "UPDATE workflows SET enabled=? WHERE id=?",
                            (new_state, int(wf["id"]))
                        )

                    update_schedule(
                        int(wf["id"]), wf["frequency"], bool(new_state)
                    )
                    st.rerun()

            with c4:
                if st.button("Delete", key=f'del{wf["id"]}'):
                    if scheduler.get_job(f'workflow_{wf["id"]}'):
                        scheduler.remove_job(f'workflow_{wf["id"]}')

                    with db() as con:
                        con.execute(
                            "DELETE FROM workflows WHERE id=?",
                            (int(wf["id"]),)
                        )

                    st.rerun()


# ---------------- HISTORY + RETRY ----------------

elif page == "Execution History":

    st.title("📜 Execution History")

    if logs.empty:
        st.info("No execution records yet.")

    else:
        st.dataframe(logs, use_container_width=True, hide_index=True)

        for _, item in logs[logs.status == "Failed"].iterrows():
            if st.button("Retry " + item["name"], key=f'retry{item["id"]}'):
                ok, msg = execute(int(item["workflow_id"]))
                st.success(msg) if ok else st.error(msg)
                st.rerun()

        st.download_button(
            "Download CSV",
            logs.to_csv(index=False),
            "autoflow_history.csv",
            "text/csv"
        )


# ---------------- ANALYTICS ----------------

elif page == "Analytics":

    st.title("📊 Advanced Analytics")

    if logs.empty:
        st.info("Run workflows to generate analytics.")
    else:
        data = logs.copy()
        data["time"] = pd.to_datetime(data["time"])

        daily = (
            data.groupby(data.time.dt.date)
            .size()
            .reset_index(name="Executions")
        )

        fig = px.line(
            daily, x="time", y="Executions",
            markers=True,
            title="Daily Workflow Executions"
        )

        st.plotly_chart(fig, use_container_width=True)

        st.metric(
            "Success Rate",
            f"{success / len(logs) * 100:.1f}%"
        )


# ---------------- FOOTER ----------------

st.divider()
st.caption("AutoFlow | Intelligent Automation Workspace")