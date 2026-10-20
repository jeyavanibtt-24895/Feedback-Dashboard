"""
=====================================================================
 TRAINER FEEDBACK DASHBOARD  ·  Jeyavani B
=====================================================================

WHAT THIS APP DOES
------------------
Shows a summary dashboard of end-of-course feedback from all my
batches (corporate, EdTech, NGO, college). Visitors only see charts
and consented testimonials, never the raw responses.

It has two modes, controlled from Streamlit Secrets (no code change):
  • DEMO mode → reads "Synthetic_Course_Feedback.csv" from this GitHub
                repo and shows a yellow "Demo mode" banner.
  • LIVE mode → reads the real responses from my Google Sheet
                "Course Feedback – All Responses" and refreshes every
                5 minutes.

HOW THE DATA FLOWS (LIVE MODE)
------------------------------
  Learner fills the batch's Google Form
      → Apps Script (createBatchForms / onBatchFormSubmit) adds a row
        to the master sheet, with Organization + Course filled in
      → This app reads the FIRST tab of that sheet using a Google
        service account (read-only)
      → Dashboard updates within 5 minutes (REFRESH_SECONDS)

FILES IN THE GITHUB REPOSITORY
------------------------------
  app.py                          ← this file
  requirements.txt                ← streamlit, pandas, plotly, gspread
  Synthetic_Course_Feedback.csv   ← sample data used in demo mode
  (NEVER upload the service account JSON key file to GitHub)

=====================================================================
 HOW TO SWITCH FROM DEMO DATA TO LIVE (REAL) DATA
=====================================================================
  1. Go to https://share.streamlit.io and open this app.
  2. Click ⋮ (three dots) → Settings → Secrets.
  3. Change the first line from:
         data_source = "demo"
     to:
         data_source = "live"
     (or delete that line completely — "live" is the default)
  4. Click Save. The app restarts and shows real responses.
     The demo banner disappears automatically.
  To go back to demo, change it to "demo" again and Save.

=====================================================================
 SECRETS FORMAT (Streamlit → ⋮ → Settings → Secrets)
=====================================================================
  data_source = "demo"                 # "demo" or "live"
  sheet_id = "LONG_ID_FROM_SHEET_URL"  # text between /d/ and /edit
  # worksheet_name = "Tab name"        # optional: only if responses
  #                                    # are NOT in the first tab

  [gcp_service_account]
  type = "service_account"
  project_id = "..."
  private_key_id = "..."
  private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
  client_email = "dashboard-reader@....iam.gserviceaccount.com"
  client_id = "..."
  auth_uri = "https://accounts.google.com/o/oauth2/auth"
  token_uri = "https://oauth2.googleapis.com/token"
  auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
  client_x509_cert_url = "..."
  universe_domain = "googleapis.com"

  Rules: copy values from the JSON key file, use  name = "value"
  (no colons, no commas), keep private_key on ONE line with its \n.

=====================================================================
 ONE-TIME SETUP CHECKLIST (if I ever rebuild this from scratch)
=====================================================================
  GitHub
   1. Create a PUBLIC repository (e.g. feedback-dashboard).
   2. Add app.py, requirements.txt and Synthetic_Course_Feedback.csv.
  Google Cloud (console.cloud.google.com)
   3. Select/create a project.
   4. Enable "Google Sheets API" and "Google Drive API".
   5. IAM & Admin → Service Accounts → Create (e.g. dashboard-reader).
   6. Open it → Keys → Add key → Create new key → JSON (downloads).
  Google Sheet
   7. Share the master sheet with the service account email as VIEWER.
   8. Copy the sheet ID from the URL (between /d/ and /edit).
  Streamlit Community Cloud (share.streamlit.io)
   9. Continue with GitHub → Create app → choose repo, branch main,
      file app.py, and a custom URL.
  10. Advanced settings → Secrets → paste the secrets (format above).
  11. Deploy. Copy the app link into my portfolio.

=====================================================================
 COMMON TASKS
=====================================================================
  • Edit the dashboard: open app.py on GitHub → pencil icon → edit →
    Commit changes. The live app updates within about a minute.
  • Change refresh speed: edit REFRESH_SECONDS below.
  • Changed a question in the Google Form? Update the matching
    left-hand text in RATING_COLUMNS or OTHER_COLUMNS below, exactly
    as the column header appears in the sheet.
  • If a security key is ever shared or leaked: Google Cloud →
    Service Accounts → Keys → delete it → create a new JSON key →
    update private_key_id and private_key in Secrets.

=====================================================================
 TROUBLESHOOTING
=====================================================================
  "Couldn't load the feedback data"
     → Check Secrets for typos (quotes, private_key on one line),
       the sheet is shared with the service account email, and both
       APIs are enabled in the same Google Cloud project.
     → In demo mode: check Synthetic_Course_Feedback.csv is in the
       repo, next to app.py, with exactly that file name.
  "The response sheet is missing these columns"
     → A form question title was changed. Update the column maps.
  App shows a "wake up" screen
     → Normal for free apps after a few days without visitors.
       Click the button and wait about 30 seconds.
  See detailed errors: share.streamlit.io → open app → Manage app
     (bottom right) → logs.
=====================================================================
"""

import streamlit as st                 # builds the web app
import pandas as pd                    # data cleaning and calculations
import plotly.express as px            # interactive charts
import gspread                         # reads Google Sheets
from datetime import datetime          # "Last updated" time
from zoneinfo import ZoneInfo          # shows that time in Indian time

# Page title, browser-tab icon and wide layout (uses the full screen width)
st.set_page_config(
    page_title="Trainer Feedback Dashboard",
    page_icon="📊",
    layout="wide"
)


# =====================================================================
# SETTINGS  (safe to change)
# =====================================================================
REFRESH_SECONDS = 300            # how often live data is re-fetched (300 = 5 minutes)
TIMEZONE = "Asia/Kolkata"        # time zone for the "Last updated" line
DEMO_FILE = "Synthetic_Course_Feedback.csv"   # sample data file in this GitHub repo

# ---------------------------------------------------------------------
# COLUMN MAPS
# Left side  = the column header EXACTLY as it appears in the sheet/CSV
#              (this is the question title from the Google Form).
# Right side = the short name used inside this code and on the charts.
# If you rename a question in the form, update the left side here.
# ---------------------------------------------------------------------

# The five 1–5 rating questions
RATING_COLUMNS = {
    "I understood the trainer's explanations.": "Understood explanations",
    "I can explain what I learned to someone else.": "Can explain to others",
    "The activities and examples were interesting.": "Activities interesting",
    "This course will help me in my studies or work.": "Useful for studies/work",
    "Overall, how would you rate this course?": "Overall rating",
}

# All other columns
OTHER_COLUMNS = {
    "Timestamp": "timestamp",
    "Organization name": "organization",
    "Course name": "course",
    "How was this course held?": "mode",
    "I am a...": "role",
    "Your first name": "name",
    "The speed of teaching was...": "pace",
    "Would you recommend this course to a friend or colleague?": "recommend",
    "What would have helped you most?": "helped_most",
    "Which topic was most difficult to understand?": "difficult",
    "Which topic was most useful for you?": "useful",
    "One idea to make this course better": "idea",
    "Anything you want to say about my teaching?": "comment",
    "Can I share your words as a review or testimonial?": "consent",
}

RATINGS = list(RATING_COLUMNS.values())   # all 5 rating short names
QUESTIONS = RATINGS[:4]                   # the 4 detailed questions (without "Overall rating")

# Fixed order and colors so charts look the same every time
PACE_ORDER = ["Too slow", "Just right", "Too fast"]
PACE_COLORS = {"Too slow": "#f4a261", "Just right": "#2a9d8f", "Too fast": "#e76f51"}
REC_ORDER = ["Yes", "Maybe", "No"]
REC_COLORS = {"Yes": "#2a9d8f", "Maybe": "#fcbf49", "No": "#e76f51"}
RATING_COLORS = {"1": "#d62828", "2": "#f77f00", "3": "#fcbf49", "4": "#90be6d", "5": "#2a9d8f"}


def normalize(text):
    """
    Cleans a column header so small differences don't break matching.
    Google Forms sometimes uses curly apostrophes (’) or the single
    "…" character; this turns them into ' and ... and removes extra spaces.
    """
    return str(text).strip().replace("’", "'").replace("…", "...")


# =====================================================================
# LOAD LIVE DATA FROM GOOGLE SHEETS
# @st.cache_data(ttl=...) remembers the result for REFRESH_SECONDS,
# so the sheet is not re-read on every click. After that time, the
# next visitor triggers a fresh read of the latest responses.
# =====================================================================
@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Fetching the latest feedback...")
def load_sheet():
    # Log in to Google using the service account details stored in
    # Streamlit Secrets ([gcp_service_account]). Read-only access.
    client = gspread.service_account_from_dict(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )

    # Open the master sheet using sheet_id from Secrets
    spreadsheet = client.open_by_key(st.secrets["sheet_id"])

    # Use the tab named in Secrets (worksheet_name), otherwise the FIRST tab
    worksheet_name = st.secrets.get("worksheet_name", "")
    worksheet = spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1

    # Read every cell as text. Row 1 = headers, the rest = responses.
    values = worksheet.get_all_values()
    fetched_at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d %b %Y, %I:%M %p")

    if not values:                               # completely empty sheet
        return pd.DataFrame(), fetched_at
    return pd.DataFrame(values[1:], columns=values[0]), fetched_at


# =====================================================================
# CLEAN AND PREPARE THE DATA
# Works the same for demo (CSV) and live (Google Sheet) data.
# Returns (clean_dataframe, list_of_missing_columns).
# =====================================================================
@st.cache_data(ttl=REFRESH_SECONDS)
def prepare(raw):
    df = raw.copy()
    df.columns = [normalize(c) for c in df.columns]

    # Check every expected column exists before doing anything else
    expected = {normalize(k): v for k, v in {**RATING_COLUMNS, **OTHER_COLUMNS}.items()}
    missing = [c for c in expected if c not in df.columns]
    if missing:
        return None, missing

    # Rename long question titles to short names (e.g. "timestamp", "pace")
    df = df.rename(columns=expected)

    # Blank or space-only cells become proper "empty" values,
    # so they are not counted as answers in the charts
    df = df.replace(r"^\s*$", pd.NA, regex=True)

    # Ignore rows with no timestamp (fully empty rows at the end of a sheet)
    df = df.dropna(subset=["timestamp"])

    # Convert ratings from text ("4") to numbers (4); anything invalid becomes empty
    df[RATINGS] = df[RATINGS].apply(pd.to_numeric, errors="coerce")

    # Convert the timestamp text into a real date-time
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")

    # Extra helper columns used by the charts
    df["batch"] = df["organization"] + " · " + df["course"]               # one batch = organization + course
    df["month"] = df["timestamp"].dt.to_period("M").dt.to_timestamp()     # month of the response

    # Tidy free-text answers (remove extra spaces at the start/end)
    for col in ["difficult", "useful", "idea", "comment"]:
        df[col] = df[col].astype("string").str.strip()

    return df, []


# =====================================================================
# PAGE HEADER + CHOOSE DATA SOURCE (DEMO OR LIVE)
# =====================================================================
st.title("📊 Trainer Feedback Dashboard")
st.write("End-of-course feedback across all organizations and courses.")

# Read "data_source" from Streamlit Secrets. Missing → "live".
# ► To go live: set  data_source = "live"  in Secrets (see top of file).
DATA_SOURCE = st.secrets.get("data_source", "live")
DEMO = DATA_SOURCE == "demo"

try:
    if DEMO:
        # Demo: sample CSV from this GitHub repo, read as text like the sheet
        raw = pd.read_csv(DEMO_FILE, dtype=str, keep_default_na=False)
    else:
        # Live: latest responses from the Google Sheet
        raw, fetched_at = load_sheet()
except Exception:
    # Friendly message for visitors. Real error details: Manage app → logs.
    st.error("Couldn't load the feedback data right now. Please try again in a few minutes.")
    st.stop()

df, missing = prepare(raw)

if missing:
    # Happens if a form question was renamed – update the column maps above
    st.error("The response sheet is missing these columns: " + ", ".join(missing))
    st.stop()

if df.empty:
    st.info("No feedback responses yet. Check back soon!")
    st.stop()

# Honest labelling: demo data always shows a clear banner
if DEMO:
    st.warning(
        "**Demo mode:** this dashboard is showing synthetic sample data to demonstrate "
        "how the analyzer works. The organizations, ratings and comments are not real "
        "learner feedback."
    )
else:
    st.caption(f"Live data from the feedback form · Last updated {fetched_at} · Refreshes every 5 minutes")


# =====================================================================
# HELPER FUNCTIONS (re-used by many charts)
# =====================================================================
def show(fig, height=None):
    """Displays a Plotly chart, optionally with a fixed height in pixels."""
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig)


def top_counts_chart(series, title, top_n=10, color="#4361ee"):
    """
    Horizontal bar chart of the most common answers in one column
    (e.g. most difficult topics). Blank answers are ignored.
    """
    counts = series.dropna().value_counts().head(top_n).sort_values()
    if counts.empty:
        st.caption(f"No answers yet for: {title}")
        return
    fig = px.bar(
        x=counts.values, y=counts.index, orientation="h", text=counts.values,
        labels={"x": "Learners", "y": ""}, title=title,
        color_discrete_sequence=[color]
    )
    show(fig, max(300, 35 * len(counts) + 100))     # taller chart when there are more bars


def share_chart(data, group, column, order, colors, title):
    """
    100% stacked bar: for each group (e.g. each batch), shows what
    percentage of learners chose each answer (e.g. Too fast / Just right).
    order and colors are optional (pass None to let Plotly decide).
    """
    counts = data.groupby([group, column]).size().reset_index(name="Count")
    counts["Percent"] = counts["Count"] / counts.groupby(group)["Count"].transform("sum") * 100

    extra = {}
    if order:
        extra["category_orders"] = {column: order}
    if colors:
        extra["color_discrete_map"] = colors

    fig = px.bar(
        counts, x="Percent", y=group, color=column, orientation="h",
        title=title, **extra, labels={group: "", "Percent": "% of learners", column: ""},
        hover_data={"Count": True, "Percent": ":.0f"}
    )
    show(fig, max(320, 40 * data[group].nunique() + 120))


# =====================================================================
# DASHBOARD TABS
# =====================================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 Trainer Portfolio",
    "⭐ Teaching Quality",
    "🏢 Batch Insights",
    "👥 Learner Profile",
    "💬 Learner Voice",
])


# ---------------------------------------------------------------------
# TAB 1 · TRAINER PORTFOLIO  – my overall track record at a glance
# ---------------------------------------------------------------------
with tab1:
    recommend_pct = (df["recommend"] == "Yes").mean() * 100

    # Six headline numbers (KPI cards)
    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Organizations", df["organization"].nunique())
    k2.metric("Courses", df["course"].nunique())
    k3.metric("Batches", df["batch"].nunique())
    k4.metric("Learners", f"{len(df):,}")                    # one response = one learner
    k5.metric("Overall rating", f"{df['Overall rating'].mean():.2f} / 5")
    k6.metric("Would recommend", f"{recommend_pct:.0f}%")

    # Row 1: learners per organization  |  learners per course
    c1, c2 = st.columns(2)
    with c1:
        by_org = df["organization"].value_counts().sort_values()
        fig = px.bar(x=by_org.values, y=by_org.index, orientation="h", text=by_org.values,
                     title="Learners trained by organization",
                     labels={"x": "Learners", "y": ""},
                     color_discrete_sequence=["#4361ee"])
        show(fig, max(320, 40 * len(by_org) + 100))
    with c2:
        by_course = df["course"].value_counts().reset_index()
        by_course.columns = ["Course", "Learners"]
        fig = px.pie(by_course, names="Course", values="Learners", hole=0.5,
                     title="Learners by course")
        show(fig, 380)

    # Row 2: delivery mode  |  learners per month
    c1, c2 = st.columns(2)
    with c1:
        by_mode = df["mode"].value_counts().reset_index()
        by_mode.columns = ["Mode", "Learners"]
        fig = px.pie(by_mode, names="Mode", values="Learners", hole=0.5,
                     title="Delivery mode")
        show(fig, 350)
    with c2:
        monthly = df.groupby("month").size().reset_index(name="Learners")
        fig = px.bar(monthly, x="month", y="Learners", text="Learners",
                     title="Learners trained per month",
                     labels={"month": ""}, color_discrete_sequence=["#2a9d8f"])
        show(fig, 350)

    # Table: one row per batch (organization + course), oldest first
    st.subheader("Batch summary")
    summary = df.groupby(["organization", "course"]).agg(
        Completed=("timestamp", "max"),                                     # date of last response
        Learners=("timestamp", "size"),                                     # number of responses
        Overall=("Overall rating", "mean"),
        Recommend=("recommend", lambda s: (s == "Yes").mean() * 100),       # % who said Yes
        Too_fast=("pace", lambda s: (s == "Too fast").mean() * 100),        # % who said Too fast
        Mode=("mode", lambda s: s.mode().iat[0]),                           # most common mode
    ).reset_index().sort_values("Completed")

    # Format numbers nicely for display
    summary["Completed"] = summary["Completed"].dt.strftime("%d %b %Y")
    summary["Overall"] = summary["Overall"].round(2)
    summary["Recommend"] = summary["Recommend"].round(0).astype(int).astype(str) + "%"
    summary["Too_fast"] = summary["Too_fast"].round(0).astype(int).astype(str) + "%"
    summary = summary.rename(columns={
        "organization": "Organization", "course": "Course",
        "Overall": "Overall rating", "Recommend": "Would recommend",
        "Too_fast": "Said too fast", "Mode": "Main mode"
    })
    st.dataframe(summary, hide_index=True)


# ---------------------------------------------------------------------
# TAB 2 · TEACHING QUALITY  – how learners rated my teaching
# ---------------------------------------------------------------------
with tab2:
    # Row 1: average per question  |  recommend Yes/Maybe/No
    c1, c2 = st.columns(2)
    with c1:
        avg = df[RATINGS].mean().sort_values()
        fig = px.bar(x=avg.values, y=avg.index, orientation="h", text=avg.round(2).values,
                     title="Average rating per question", range_x=[0, 5],
                     labels={"x": "Average (out of 5)", "y": ""},
                     color_discrete_sequence=["#4361ee"])
        show(fig, 380)
    with c2:
        rec = df["recommend"].value_counts().reindex(REC_ORDER).dropna().reset_index()
        rec.columns = ["Answer", "Learners"]
        fig = px.pie(rec, names="Answer", values="Learners", hole=0.5,
                     color="Answer", color_discrete_map=REC_COLORS,
                     title="Would you recommend this course?")
        show(fig, 380)

    # Full width: % of learners who gave 1, 2, 3, 4 or 5 for each question
    dist = (
        df[RATINGS].melt(var_name="Question", value_name="Rating").dropna()   # one row per rating
        .groupby(["Question", "Rating"]).size().reset_index(name="Count")
    )
    dist["Percent"] = dist["Count"] / dist.groupby("Question")["Count"].transform("sum") * 100
    dist["Rating"] = dist["Rating"].astype(int).astype(str)                  # "1"…"5" for colors
    fig = px.bar(
        dist, x="Percent", y="Question", color="Rating", orientation="h",
        title="How learners rated each question (% of learners)",
        category_orders={"Rating": ["1", "2", "3", "4", "5"]},
        color_discrete_map=RATING_COLORS,
        labels={"Question": "", "Percent": "% of learners"}
    )
    show(fig, 380)

    # Row 2: overall rating by course  |  pace split
    c1, c2 = st.columns(2)
    with c1:
        by_course = df.groupby("course")["Overall rating"].mean().sort_values()
        fig = px.bar(x=by_course.values, y=by_course.index, orientation="h",
                     text=by_course.round(2).values, range_x=[0, 5],
                     title="Overall rating by course",
                     labels={"x": "Average (out of 5)", "y": ""},
                     color_discrete_sequence=["#2a9d8f"])
        show(fig, 350)
    with c2:
        pace = df["pace"].value_counts().reindex(PACE_ORDER).dropna().reset_index()
        pace.columns = ["Pace", "Learners"]
        fig = px.pie(pace, names="Pace", values="Learners", hole=0.5,
                     color="Pace", color_discrete_map=PACE_COLORS,
                     title="Speed of teaching")
        show(fig, 350)

    # Full width: overall rating per batch over time (am I improving?)
    batch_trend = df.groupby("batch").agg(
        Date=("timestamp", "max"), Rating=("Overall rating", "mean"), Learners=("batch", "size")
    ).reset_index().sort_values("Date")
    fig = px.line(batch_trend, x="Date", y="Rating", markers=True, hover_name="batch",
                  hover_data={"Learners": True, "Rating": ":.2f"},
                  title="Overall rating over time (one point per batch)",
                  labels={"Date": "", "Rating": "Overall rating"}, range_y=[1, 5])
    show(fig, 380)


# ---------------------------------------------------------------------
# TAB 3 · BATCH INSIGHTS  – compare batches with each other
# ---------------------------------------------------------------------
with tab3:
    # Heatmap: every batch × every question (red = lower, green = higher)
    heat = df.groupby("batch")[RATINGS].mean()
    heat = heat.sort_values("Overall rating")
    fig = px.imshow(heat, text_auto=".2f", aspect="auto", color_continuous_scale="RdYlGn",
                    range_color=[3, 5], title="Batch × question heatmap (average rating)")
    fig.update_layout(xaxis_title="", yaxis_title="")
    show(fig, max(400, 45 * len(heat) + 150))

    # Pace and recommend split for each batch
    share_chart(df, "batch", "pace", PACE_ORDER, PACE_COLORS, "Speed of teaching by batch")
    share_chart(df, "batch", "recommend", REC_ORDER, REC_COLORS, "Would recommend, by batch")

    # Top 3 and bottom 3 batches by overall rating
    ranked = df.groupby("batch").agg(
        Overall=("Overall rating", "mean"),
        Learners=("batch", "size"),
    ).reset_index().rename(columns={"batch": "Batch", "Overall": "Overall rating"})
    ranked["Overall rating"] = ranked["Overall rating"].round(2)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🔺 Best-rated batches")
        st.dataframe(ranked.nlargest(3, "Overall rating"), hide_index=True)
    with c2:
        st.subheader("🔻 Batches to review")
        st.dataframe(ranked.nsmallest(3, "Overall rating"), hide_index=True)


# ---------------------------------------------------------------------
# TAB 4 · LEARNER PROFILE  – students vs professionals vs job seekers
# ---------------------------------------------------------------------
with tab4:
    # Row 1: who attended  |  ratings by learner type
    c1, c2 = st.columns(2)
    with c1:
        roles = df["role"].value_counts().reset_index()
        roles.columns = ["Learner type", "Learners"]
        fig = px.pie(roles, names="Learner type", values="Learners", hole=0.5,
                     title="Who attended")
        show(fig, 380)
    with c2:
        by_role = df.groupby("role")[QUESTIONS].mean().reset_index().melt(
            id_vars="role", var_name="Question", value_name="Average"
        )
        fig = px.bar(by_role, x="Average", y="Question", color="role", barmode="group",
                     orientation="h", range_x=[0, 5], text_auto=".2f",
                     title="Ratings by learner type",
                     labels={"Question": "", "role": "Learner type"})
        show(fig, 380)

    # Pace and "what would have helped" for each learner type
    share_chart(df, "role", "pace", PACE_ORDER, PACE_COLORS, "Speed of teaching by learner type")
    share_chart(df.dropna(subset=["helped_most"]), "role", "helped_most", None, None,
                "What would have helped most, by learner type")


# ---------------------------------------------------------------------
# TAB 5 · LEARNER VOICE  – what learners said in their own words
# ---------------------------------------------------------------------
with tab5:
    # Row 1: difficult topics  |  useful topics
    c1, c2 = st.columns(2)
    with c1:
        top_counts_chart(df["difficult"], "Most difficult topics", color="#e76f51")
    with c2:
        top_counts_chart(df["useful"], "Most useful topics", color="#2a9d8f")

    # Row 2: what would have helped  |  improvement ideas
    c1, c2 = st.columns(2)
    with c1:
        top_counts_chart(df["helped_most"], "What would have helped most", color="#4361ee")
    with c2:
        top_counts_chart(df["idea"], "Ideas to make the course better", color="#7b2cbf")

    # Testimonial wall (full width)
    # Shows ONLY learners who said "Yes" to sharing AND wrote a comment.
    #   "Yes, with my first name"   → shows their first name
    #   "Yes, but keep it anonymous" → shows "Anonymous"
    st.subheader("🌟 Testimonial wall")
    if DEMO:
        st.caption("Sample testimonials from synthetic data, shown for demonstration only.")
    else:
        st.caption("Only from learners who allowed their words to be shared.")

    consent = df["consent"].astype("string")
    wall = df[consent.str.startswith("Yes").fillna(False) & df["comment"].notna()].copy()

    if wall.empty:
        st.caption("No shareable testimonials yet.")
    else:
        wall["shown_name"] = wall["name"].where(
            consent.loc[wall.index] == "Yes, with my first name", "Anonymous"
        )
        # Highest-rated and most recent first; show 9 cards (change 9 for more/fewer)
        picks = wall.sort_values(
            ["Overall rating", "timestamp"], ascending=[False, False]
        ).head(9)

        cols = st.columns(3)                                   # 3 cards per row
        for i, (_, row) in enumerate(picks.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"“{row['comment']}”")
                    st.caption(f"— {row['shown_name']}, {row['role']} · {row['course']}")
