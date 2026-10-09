"""NutriPilot AI dashboard: a Streamlit client for the NutriPilot API.

Run:  streamlit run dashboard/app.py      (talks to the API at NUTRIPILOT_API_URL)
"""

from __future__ import annotations

import os
from typing import Any

import altair as alt
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_URL = (
    os.getenv("NUTRIPILOT_API_URL") or os.getenv("API_URL") or "http://localhost:8000"
).rstrip("/")
API_TOKEN = os.getenv("NUTRIPILOT_API_TOKEN") or os.getenv("API_TOKEN")
PREFIX = f"{API_URL}/v1/nutripilot"

GOALS = ["healthy eating", "weight loss", "maintenance", "muscle gain", "weight gain"]
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"]
BAR_COLOR = "#16A34A"  # one series, one hue (green-600: passes contrast on white)
INK_MUTED = "#64748B"

ERRORS = {
    401: "🔐 Authentication failed. Check NUTRIPILOT_API_TOKEN.",
    422: "⚠️ Some inputs are invalid",
    429: "⏳ The AI provider is busy. Wait a moment and try again.",
    502: "🛠️ The AI answer failed validation",
    503: "🛠️ The AI service is temporarily unavailable. Try again shortly.",
}

st.set_page_config(page_title="NutriPilot AI", page_icon="🥗", layout="wide")


# ============================================================
# API client
# ============================================================


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}


@st.cache_data(ttl=60, show_spinner=False)
def fetch_models() -> dict[str, Any] | None:
    try:
        response = requests.get(f"{PREFIX}/models", headers=_headers(), timeout=10)
        return response.json() if response.ok else None
    except requests.exceptions.RequestException:
        return None


def call_api(method: str, path: str, **kwargs: Any) -> dict[str, Any] | None:
    """Call the API with the model chosen in the sidebar; show a friendly error and
    return None on failure."""
    params = {**kwargs.pop("params", {}), **st.session_state.get("model_choice", {})}
    try:
        # Long timeout: a thinking model plus one repair can take a few minutes.
        response = requests.request(
            method, f"{PREFIX}{path}", headers=_headers(), params=params, timeout=180, **kwargs
        )
    except requests.exceptions.Timeout:
        st.error("⏱️ The request took too long. Please try again.")
        return None
    except requests.exceptions.RequestException:
        st.error(f"🌐 Could not reach the NutriPilot API at {API_URL}.")
        return None

    if response.ok:
        return response.json()

    message = ERRORS.get(response.status_code, f"⚠️ Request failed ({response.status_code}).")
    body = response.json() if "json" in response.headers.get("content-type", "") else {}
    details = body.get("problems") or [
        e.get("msg", "") for e in body.get("detail", []) if isinstance(e, dict)
    ]
    st.error(message + (":\n\n" + "\n".join(f"- {d}" for d in details) if details else "."))
    return None


def restriction_inputs(key: str) -> dict[str, str | None]:
    c1, c2 = st.columns(2)
    allergies = c1.text_input(
        "Allergies (never included)", placeholder="e.g. peanuts, shellfish", key=f"{key}_allergies"
    )
    dislikes = c2.text_input(
        "Dislikes (never included)", placeholder="e.g. mushrooms", key=f"{key}_dislikes"
    )
    return {"allergies": allergies or None, "dislikes": dislikes or None}


# ============================================================
# Rendering
# ============================================================


def macro_tiles(totals: dict[str, float], target: float | None = None) -> None:
    cols = st.columns(4)
    delta = f"{totals['calories'] - target:+.0f} vs target" if target else None
    cols[0].metric("Calories", f"{totals['calories']:.0f} kcal", delta, delta_color="off")
    kcal = max(totals["calories"], 1)
    for col, (label, field, factor) in zip(
        cols[1:],
        [("Protein", "protein_g", 4), ("Carbs", "carbs_g", 4), ("Fat", "fat_g", 9)],
        strict=True,
    ):
        share = totals[field] * factor / kcal
        col.metric(label, f"{totals[field]:.0f} g", f"{share:.0%} of kcal", delta_color="off")


def calories_chart(days: list[dict[str, Any]], target: int) -> alt.LayerChart:
    df = pd.DataFrame(
        {"Day": f"Day {d['day']}", "Calories": d["totals"]["calories"], "Meals": len(d["meals"])}
        for d in days
    )
    base = alt.Chart(df).encode(
        x=alt.X("Day:N", sort=None, title=None, axis=alt.Axis(labelAngle=0))
    )
    bars = base.mark_bar(
        color=BAR_COLOR, size=28, cornerRadiusTopLeft=4, cornerRadiusTopRight=4
    ).encode(
        y=alt.Y("Calories:Q", title="kcal", axis=alt.Axis(grid=True, gridOpacity=0.3)),
        tooltip=["Day", alt.Tooltip("Calories:Q", format=".0f"), "Meals"],
    )
    target_df = pd.DataFrame({"target": [target], "label": [f"Target {target} kcal"]})
    rule = (
        alt.Chart(target_df)
        .mark_rule(color=INK_MUTED, strokeDash=[4, 4], strokeWidth=2)
        .encode(y="target:Q")
    )
    label = (
        alt.Chart(target_df)
        .mark_text(align="right", baseline="bottom", dy=-4, color=INK_MUTED, x="width")
        .encode(y="target:Q", text="label:N")
    )
    return (bars + rule + label).properties(height=260)


def show_meta(result: dict[str, Any]) -> None:
    for warning in result.get("warnings", []):
        st.warning(warning, icon="⚠️")
    m = result["meta"]
    st.caption(
        f"{m['provider']} · {m['model']} · {m['latency_ms'] / 1000:.1f} s · "
        f"{m['prompt_tokens'] + m['completion_tokens']:,} tokens · "
        f"repairs: {m['repairs']} · prompt v{m['prompt_version']}"
    )
    st.caption(result["disclaimer"])


def show_plan(result: dict[str, Any], target: int) -> None:
    days = result["data"]["days"]
    week_avg = {k: sum(d["totals"][k] for d in days) / len(days) for k in days[0]["totals"]}
    st.subheader("Daily average")
    macro_tiles(week_avg, target)
    st.subheader("Calories per day")
    st.altair_chart(calories_chart(days, target), width="stretch")

    for tab, day in zip(st.tabs([f"Day {d['day']}" for d in days]), days, strict=True):
        with tab:
            table = pd.DataFrame(
                {
                    "Meal": m["name"],
                    "Dish": m["dish"],
                    "Ingredients": ", ".join(m["ingredients"]),
                    "kcal": round(m["calories"]),
                    "Protein g": round(m["protein_g"]),
                    "Carbs g": round(m["carbs_g"]),
                    "Fat g": round(m["fat_g"]),
                }
                for m in day["meals"]
            )
            st.dataframe(table, hide_index=True, width="stretch")
    for note in result["data"].get("notes", []):
        st.markdown(f"- {note}")
    show_meta(result)


# ============================================================
# Pages
# ============================================================


def plan_page() -> None:
    st.header("🍽️ Weekly plan")
    st.caption(
        "A seven-day plan. Daily calories, meal count and excluded foods are checked in code."
    )
    with st.form("plan"):
        c1, c2, c3 = st.columns(3)
        calories = c1.number_input("Daily calories", 1000, 5000, 2000, step=100)
        meal_count = c2.number_input("Meals per day", 1, 6, 3)
        age = c3.number_input("Age", 2, 120, 35)
        c1, c2 = st.columns(2)
        goal = c1.selectbox("Goal", GOALS)
        preference = c2.text_input(
            "Diet style / cuisine", "any", placeholder="e.g. vegetarian, Mediterranean"
        )
        restrictions = restriction_inputs("plan")
        c1, c2 = st.columns(2)
        diseases = c1.text_input("Health conditions", placeholder="optional, e.g. type 2 diabetes")
        preferred = c2.text_input("Preferred foods", placeholder="optional")
        submitted = st.form_submit_button("Generate 7-day plan", type="primary", width="stretch")

    if submitted:
        profile = {
            "calories": calories,
            "meal_count": meal_count,
            "age": age,
            "goal": goal,
            "meal_preference": preference or "any",
            "diseases": diseases or None,
            "preferred_foods": preferred or None,
            **restrictions,
        }
        with st.spinner("Writing and checking your plan..."):
            result = call_api("POST", "/plan", json=profile)
        if result:
            st.session_state.update(plan_result=result, plan_profile=profile)

    if "plan_result" not in st.session_state:
        return
    profile = st.session_state.plan_profile
    show_plan(st.session_state.plan_result, profile["calories"])

    st.divider()
    st.subheader("🔄 Change this plan")
    with st.form("regenerate"):
        change = st.text_input(
            "What should change?", placeholder="e.g. no rice on weekdays, more fish"
        )
        if st.form_submit_button("Revise plan", width="stretch") and change.strip():
            payload = {
                "profile": profile,
                "existing_plan": st.session_state.plan_result["data"],
                "modification_request": change,
            }
            with st.spinner("Revising and re-checking..."):
                result = call_api("POST", "/plan/regenerate", json=payload)
            if result:
                st.session_state.plan_result = result
                st.rerun()


def meal_page() -> None:
    st.header("🥘 Single meal")
    with st.form("meal"):
        c1, c2, c3 = st.columns(3)
        meal_type = c1.selectbox("Meal", MEAL_TYPES, index=1)
        calories = c2.number_input("Calories", 100, 2000, 600, step=50)
        goal = c3.selectbox("Goal", GOALS)
        preference = st.text_input("Diet style / cuisine", "any")
        restrictions = restriction_inputs("meal")
        submitted = st.form_submit_button("Suggest a meal", type="primary", width="stretch")
    if submitted:
        payload = {
            "meal_type": meal_type,
            "calories": calories,
            "goal": goal,
            "meal_preference": preference or "any",
            **restrictions,
        }
        with st.spinner("Cooking up an idea..."):
            result = call_api("POST", "/meal", json=payload)
        if result:
            m = result["data"]
            st.subheader(f"{m['name'].title()}: {m['dish']}")
            macro_tiles(m, calories)
            st.markdown("**Ingredients:** " + ", ".join(m["ingredients"]))
            show_meta(result)


def analysis_page() -> None:
    st.header("📊 Nutrition analysis")
    st.caption("Per-item estimates from the model; the totals are summed in code.")
    with st.form("analysis"):
        foods = st.text_area(
            "Foods, with amounts", placeholder="e.g. 2 eggs, 1 slice whole-grain toast, 1 banana"
        )
        submitted = st.form_submit_button("Analyze", type="primary", width="stretch")
    if submitted and foods.strip():
        with st.spinner("Estimating nutrients..."):
            result = call_api("POST", "/analysis", json={"food_items": foods})
        if result:
            macro_tiles(result["data"]["totals"])
            table = pd.DataFrame(result["data"]["items"]).rename(
                columns={
                    "food": "Food",
                    "quantity": "Amount",
                    "calories": "kcal",
                    "protein_g": "Protein g",
                    "carbs_g": "Carbs g",
                    "fat_g": "Fat g",
                }
            )
            st.dataframe(table, hide_index=True, width="stretch")
            show_meta(result)


def substitute_page() -> None:
    st.header("🥕 Healthier swaps")
    with st.form("substitute"):
        foods = st.text_area("Foods to swap", placeholder="e.g. white rice, french fries, soda")
        goal = st.selectbox("Goal", GOALS)
        restrictions = restriction_inputs("substitute")
        submitted = st.form_submit_button("Find swaps", type="primary", width="stretch")
    if submitted and foods.strip():
        with st.spinner("Finding alternatives..."):
            result = call_api(
                "POST", "/substitute", json={"food_items": foods, "goal": goal, **restrictions}
            )
        if result:
            table = pd.DataFrame(result["data"]["substitutions"]).rename(
                columns={"original": "Instead of", "alternative": "Try", "why": "Why"}
            )
            st.dataframe(table, hide_index=True, width="stretch")
            show_meta(result)


def tips_page() -> None:
    st.header("💡 Quick tips")
    goal = st.selectbox("Goal", GOALS)
    if st.button("Get 5 tips", type="primary", width="stretch"):
        with st.spinner("Thinking..."):
            result = call_api("GET", "/recommendations", params={"goal": goal})
        if result:
            for i, t in enumerate(result["data"]["tips"], 1):
                st.markdown(f"**{i}. {t['tip']}**  \n{t['why']}")
            show_meta(result)


# ============================================================
# Layout
# ============================================================

PAGES = {
    "Weekly plan": plan_page,
    "Single meal": meal_page,
    "Nutrition analysis": analysis_page,
    "Healthier swaps": substitute_page,
    "Quick tips": tips_page,
}


def model_picker() -> None:
    """Sidebar model choice; only models whose provider key is configured are offered."""
    catalog = fetch_models()
    if not catalog:
        st.sidebar.caption("Model: the API's default")
        st.session_state.model_choice = {}
        return
    available = [m for m in catalog["models"] if m["available"]]
    missing = sorted({m["provider"] for m in catalog["models"] if not m["available"]})
    if not available:
        st.sidebar.warning("No LLM provider key is configured on the API.")
        st.session_state.model_choice = {}
        return
    default = catalog["default"]
    index = next(
        (
            i
            for i, m in enumerate(available)
            if (m["provider"], m["model"]) == tuple(default.values())
        ),
        0,
    )
    choice = st.sidebar.selectbox(
        "🧠 Model", available, index=index, format_func=lambda m: m["label"]
    )
    st.session_state.model_choice = {"provider": choice["provider"], "model": choice["model"]}
    if missing:
        st.sidebar.caption("Add an API key on the server to enable: " + ", ".join(missing))


st.sidebar.title("🥗 NutriPilot AI")
st.sidebar.caption("Structured, validated nutrition planning")
page = st.sidebar.radio("Feature", list(PAGES))
st.sidebar.divider()
model_picker()
st.sidebar.divider()
st.sidebar.caption(f"API: {API_URL}")
st.sidebar.caption("FastAPI · AWS Lambda · Groq / OpenAI / Claude · Streamlit")

PAGES[page]()
