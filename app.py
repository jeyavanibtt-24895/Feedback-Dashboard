import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="Trainer Feedback Dashboard",
    page_icon="📊",
    layout="wide"
)

# ---------------- Settings ----------------
REFRESH_SECONDS = 300  # fetch new responses every 5 minutes
TIMEZONE = "Asia/Kolkata"

RATING_COLUMNS = {
    "I understood the trainer's explanations.": "Understood explanations",
    "I can explain what I learned to someone else.": "Can explain to others",
    "The activities and examples were interesting.": "Activities interesting",
    "This course will help me in my studies or work.": "Useful for studies/work",
    "Overall, how would you rate this course?": "Overall rating",
}
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
RATINGS = list(RATING_COLUMNS.values())
QUESTIONS = RATINGS[:4]  # the four detailed questions (without overall)

PACE_ORDER = ["Too slow", "Just right", "Too fast"]
PACE_COLORS = {"Too slow": "#f4a261", "Just right": "#2a9d8f", "Too fast": "#e76f51"}
REC_ORDER = ["Yes", "Maybe", "No"]
REC_COLORS = {"Yes": "#2a9d8f", "Maybe": "#fcbf49", "No": "#e76f51"}
RATING_COLORS = {"1": "#d62828", "2": "#f77f00", "3": "#fcbf49", "4": "#90be6d", "5": "#2a9d8f"}


def normalize(text):
    """Makes column names match even with curly quotes, '…' or extra spaces."""
    return str(text).strip().replace("’", "'").replace("…", "...")


# ---------------- Fetch the latest responses from Google Sheets ----------------
@st.cache_data(ttl=REFRESH_SECONDS, show_spinner="Fetching the latest feedback...")
def load_sheet():
    client = gspread.service_account_from_dict(
        dict(st.secrets["gcp_service_account"]),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    spreadsheet = client.open_by_key(st.secrets["sheet_id"])
    worksheet_name = st.secrets.get("worksheet_name", "")
    worksheet = spreadsheet.worksheet(worksheet_name) if worksheet_name else spreadsheet.sheet1

    values = worksheet.get_all_values()
    fetched_at = datetime.now(ZoneInfo(TIMEZONE)).strftime("%d %b %Y, %I:%M %p")
    if not values:
        return pd.DataFrame(), fetched_at
    return pd.DataFrame(values[1:], columns=values[0]), fetched_at


@st.cache_data(ttl=REFRESH_SECONDS)
def prepare(raw):
    df = raw.copy()
    df.columns = [normalize(c) for c in df.columns]

    expected = {normalize(k): v for k, v in {**RATING_COLUMNS, **OTHER_COLUMNS}.items()}
    missing = [c for c in expected if c not in df.columns]
    if missing:
        return None, missing

    df = df.rename(columns=expected)
    df = df.replace(r"^\s*$", pd.NA, regex=True)  # blank cells -> empty
    df = df.dropna(subset=["timestamp"])           # skip fully empty rows
    df[RATINGS] = df[RATINGS].apply(pd.to_numeric, errors="coerce")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["batch"] = df["organization"] + " · " + df["course"]
    df["month"] = df["timestamp"].dt.to_period("M").dt.to_timestamp()
    for col in ["difficult", "useful", "idea", "comment"]:
        df[col] = df[col].astype("string").str.strip()
    return df, []


st.title("📊 Trainer Feedback Dashboard")
st.write("End-of-course feedback across all organizations and courses.")

DATA_SOURCE = st.secrets.get("data_source", "live")
DEMO = DATA_SOURCE == "demo"

try:
    if DEMO:
        raw = pd.read_csv("Synthetic_Course_Feedback.csv", dtype=str, keep_default_na=False)
    else:
        raw, fetched_at = load_sheet()
except Exception:
    st.error("Couldn't load the feedback data right now. Please try again in a few minutes.")
    st.stop()

df, missing = prepare(raw)
if missing:
    st.error("The response sheet is missing these columns: " + ", ".join(missing))
    st.stop()

if df.empty:
    st.info("No feedback responses yet. Check back soon!")
    st.stop()

if DEMO:
    st.warning(
        "**Demo mode:** this dashboard is showing synthetic sample data to demonstrate "
        "how the analyzer works. The organizations, ratings and comments are not real "
        "learner feedback."
    )
else:
    st.caption(f"Live data from the feedback form · Last updated {fetched_at} · Refreshes every 5 minutes")

# ---------------- Helpers ----------------
def show(fig, height=None):
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig)


def top_counts_chart(series, title, top_n=10, color="#4361ee"):
    counts = series.dropna().value_counts().head(top_n).sort_values()
    if counts.empty:
        st.caption(f"No answers yet for: {title}")
        return
    fig = px.bar(
        x=counts.values, y=counts.index, orientation="h", text=counts.values,
        labels={"x": "Learners", "y": ""}, title=title,
        color_discrete_sequence=[color]
    )
    show(fig, max(300, 35 * len(counts) + 100))


def share_chart(data, group, column, order, colors, title):
    """100% stacked bar: share of each answer within each group."""
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


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🏆 Trainer Portfolio",
    "⭐ Teaching Quality",
    "🏢 Batch Insights",
    "👥 Learner Profile",
    "💬 Learner Voice",
])


# ---------------- Tab 1: Portfolio ----------------
with tab1:
    recommend_pct = (df["recommend"] == "Yes").mean() * 100

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Organizations", df["organization"].nunique())
    k2.metric("Courses", df["course"].nunique())
    k3.metric("Batches", df["batch"].nunique())
    k4.metric("Learners", f"{len(df):,}")
    k5.metric("Overall rating", f"{df['Overall rating'].mean():.2f} / 5")
    k6.metric("Would recommend", f"{recommend_pct:.0f}%")

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

    st.subheader("Batch summary")
    summary = df.groupby(["organization", "course"]).agg(
        Completed=("timestamp", "max"),
        Learners=("timestamp", "size"),
        Overall=("Overall rating", "mean"),
        Recommend=("recommend", lambda s: (s == "Yes").mean() * 100),
        Too_fast=("pace", lambda s: (s == "Too fast").mean() * 100),
        Mode=("mode", lambda s: s.mode().iat[0]),
    ).reset_index().sort_values("Completed")
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


# ---------------- Tab 2: Teaching quality ----------------
with tab2:
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

    dist = (
        df[RATINGS].melt(var_name="Question", value_name="Rating").dropna()
        .groupby(["Question", "Rating"]).size().reset_index(name="Count")
    )
    dist["Percent"] = dist["Count"] / dist.groupby("Question")["Count"].transform("sum") * 100
    dist["Rating"] = dist["Rating"].astype(int).astype(str)
    fig = px.bar(
        dist, x="Percent", y="Question", color="Rating", orientation="h",
        title="How learners rated each question (% of learners)",
        category_orders={"Rating": ["1", "2", "3", "4", "5"]},
        color_discrete_map=RATING_COLORS,
        labels={"Question": "", "Percent": "% of learners"}
    )
    show(fig, 380)

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

    batch_trend = df.groupby("batch").agg(
        Date=("timestamp", "max"), Rating=("Overall rating", "mean"), Learners=("batch", "size")
    ).reset_index().sort_values("Date")
    fig = px.line(batch_trend, x="Date", y="Rating", markers=True, hover_name="batch",
                  hover_data={"Learners": True, "Rating": ":.2f"},
                  title="Overall rating over time (one point per batch)",
                  labels={"Date": "", "Rating": "Overall rating"}, range_y=[1, 5])
    show(fig, 380)


# ---------------- Tab 3: Batch insights ----------------
with tab3:
    heat = df.groupby("batch")[RATINGS].mean()
    heat = heat.sort_values("Overall rating")
    fig = px.imshow(heat, text_auto=".2f", aspect="auto", color_continuous_scale="RdYlGn",
                    range_color=[3, 5], title="Batch × question heatmap (average rating)")
    fig.update_layout(xaxis_title="", yaxis_title="")
    show(fig, max(400, 45 * len(heat) + 150))

    share_chart(df, "batch", "pace", PACE_ORDER, PACE_COLORS, "Speed of teaching by batch")
    share_chart(df, "batch", "recommend", REC_ORDER, REC_COLORS, "Would recommend, by batch")

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


# ---------------- Tab 4: Learner profile ----------------
with tab4:
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

    share_chart(df, "role", "pace", PACE_ORDER, PACE_COLORS, "Speed of teaching by learner type")
    share_chart(df.dropna(subset=["helped_most"]), "role", "helped_most", None, None,
                "What would have helped most, by learner type")


# ---------------- Tab 5: Learner voice ----------------
with tab5:
    c1, c2 = st.columns(2)
    with c1:
        top_counts_chart(df["difficult"], "Most difficult topics", color="#e76f51")
    with c2:
        top_counts_chart(df["useful"], "Most useful topics", color="#2a9d8f")

    c1, c2 = st.columns(2)
    with c1:
        top_counts_chart(df["helped_most"], "What would have helped most", color="#4361ee")
    with c2:
        top_counts_chart(df["idea"], "Ideas to make the course better", color="#7b2cbf")

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
        picks = wall.sort_values(
            ["Overall rating", "timestamp"], ascending=[False, False]
        ).head(9)
        cols = st.columns(3)
        for i, (_, row) in enumerate(picks.iterrows()):
            with cols[i % 3]:
                with st.container(border=True):
                    st.markdown(f"“{row['comment']}”")
                    st.caption(f"— {row['shown_name']}, {row['role']} · {row['course']}")
