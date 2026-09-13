import os

import requests
import streamlit as st
from dotenv import load_dotenv


# ============================================================
# Configuration
# ============================================================

load_dotenv()

API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_TOKEN")


# ============================================================
# Page configuration
# ============================================================

st.set_page_config(
    page_title="NutriPilot AI",
    page_icon="🥗",
    layout="wide",
)


# ============================================================
# Configuration validation
# ============================================================

if not API_URL:
    st.error(
        "⚙️ API configuration is missing. "
        "Please check your .env file."
    )
    st.stop()

if not API_TOKEN:
    st.error(
        "🔐 API authentication configuration is missing. "
        "Please check your .env file."
    )
    st.stop()


# ============================================================
# API helpers
# ============================================================

def api_headers():
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }


def call_api(method, endpoint, payload=None):
    """
    Send a request to the NutriPilot API.

    Returns:
        response, error_message
    """

    try:
        response = requests.request(
            method=method,
            url=endpoint,
            headers=api_headers(),
            json=payload,
            timeout=60,
        )

        if response.status_code == 200:
            return response, None

        if response.status_code == 400:
            return None, (
                "⚠️ The request could not be processed. "
                "Please check your input and try again."
            )

        if response.status_code == 401:
            return None, (
                "🔐 Authentication failed. "
                "Please check the API configuration."
            )

        if response.status_code == 422:
            return None, (
                "⚠️ Some of the provided information is invalid. "
                "Please review your inputs and try again."
            )

        if response.status_code == 429:
            return None, (
                "⏳ Too many requests were sent. "
                "Please wait a moment and try again."
            )

        if 500 <= response.status_code < 600:
            return None, (
                "🛠️ The NutriPilot service is temporarily "
                "unavailable. Please try again shortly."
            )

        return None, (
            "⚠️ The request could not be completed. "
            "Please try again."
        )

    except requests.exceptions.Timeout:
        return None, (
            "⏱️ The request took too long to complete. "
            "Please try again."
        )

    except requests.exceptions.ConnectionError:
        return None, (
            "🌐 Could not connect to the NutriPilot API. "
            "Please check your internet connection and try again."
        )

    except requests.exceptions.RequestException:
        return None, (
            "🌐 An error occurred while communicating "
            "with the NutriPilot API. Please try again."
        )


def display_api_result(
    response,
    success_message,
    result_title,
    empty_message,
):
    """
    Display a successful API response.
    """

    try:
        result = response.json()

    except ValueError:
        st.error(
            "⚠️ The API returned an unexpected response. "
            "Please try again."
        )
        return

    st.success(success_message)

    st.divider()

    st.subheader(result_title)

    data = result.get("data")

    if data:
        st.markdown(data)
    else:
        st.info(empty_message)


# ============================================================
# Header
# ============================================================

st.title("🥗 NutriPilot AI")

st.markdown(
    "### AI-Powered Nutrition Planning"
)

st.write(
    "Create personalized meal plans, discover healthier food "
    "choices, and analyze nutrition with AI."
)

st.divider()


# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("🥗 NutriPilot AI")

st.sidebar.caption(
    "Your AI-powered nutrition assistant"
)

st.sidebar.divider()

st.sidebar.subheader("🧭 Navigation")

feature = st.sidebar.selectbox(
    "Choose a feature",
    [
        "Weekly Diet Plan",
        "Meal Suggestion",
        "Food Substitution",
        "Nutrition Analysis",
        "Quick Recommendations",
        "Regenerate Plan",
    ],
)

st.sidebar.divider()

st.sidebar.caption(
    "Powered by FastAPI • AWS Lambda • Groq"
)


# ============================================================
# Weekly Diet Plan
# ============================================================

if feature == "Weekly Diet Plan":

    st.header("🍽️ Weekly Diet Plan")

    st.write(
        "Enter your information below to generate a "
        "personalized seven-day diet plan."
    )

    with st.form("diet_plan_form"):

        col1, col2 = st.columns(2)

        with col1:

            meal_preference = st.text_input(
                "Meal preference",
                value="Indian",
            )

            calories = st.number_input(
                "Daily calories",
                min_value=500,
                max_value=5000,
                value=2000,
                step=100,
            )

            meal_count = st.number_input(
                "Meals per day",
                min_value=1,
                max_value=8,
                value=3,
                step=1,
            )

            goal = st.selectbox(
                "Goal",
                [
                    "Weight management",
                    "Weight loss",
                    "Muscle gain",
                    "Healthy eating",
                    "Maintenance",
                ],
            )

        with col2:

            age = st.number_input(
                "Age",
                min_value=1,
                max_value=120,
                value=35,
                step=1,
            )

            diseases = st.text_input(
                "Diseases / health conditions",
                placeholder="Optional",
            )

            dislikes = st.text_input(
                "Foods you dislike",
                placeholder="Optional",
            )

            preferred_foods = st.text_input(
                "Preferred foods",
                placeholder="e.g. chicken, rice, vegetables",
            )

        submitted = st.form_submit_button(
            "🚀 Generate 7-Day Plan",
            use_container_width=True,
        )

    if submitted:

        payload = {
            "meal_preference": meal_preference,
            "calories": calories,
            "meal_count": meal_count,
            "diseases": diseases or None,
            "goal": goal,
            "age": age,
            "dislikes": dislikes or None,
            "preferred_foods": preferred_foods or None,
        }

        endpoint = f"{API_URL}/v1/nutripilot/plan"

        with st.spinner(
            "🤖 Generating your personalized plan..."
        ):

            response, error = call_api(
                method="POST",
                endpoint=endpoint,
                payload=payload,
            )

            if response:

                display_api_result(
                    response=response,
                    success_message=(
                        "Your personalized diet plan is ready! 🎉"
                    ),
                    result_title="🤖 Your 7-Day Nutrition Plan",
                    empty_message="No plan was returned.",
                )

            else:

                st.error(error)


# ============================================================
# Meal Suggestion
# ============================================================

elif feature == "Meal Suggestion":

    st.header("🍽️ Meal Suggestion")

    st.write(
        "Get a personalized healthy meal suggestion "
        "based on your goal and daily calorie target."
    )

    with st.form("meal_suggestion_form"):

        col1, col2 = st.columns(2)

        with col1:

            goal = st.selectbox(
                "Goal",
                [
                    "Weight management",
                    "Weight loss",
                    "Muscle gain",
                    "Healthy eating",
                    "Maintenance",
                ],
            )

        with col2:

            calories = st.number_input(
                "Daily calories",
                min_value=500,
                max_value=5000,
                value=2000,
                step=100,
            )

        submitted = st.form_submit_button(
            "🚀 Suggest Meal",
            use_container_width=True,
        )

    if submitted:

        payload = {
            "meal_preference": "Indian",
            "calories": calories,
            "meal_count": 3,
            "diseases": None,
            "goal": goal,
            "age": 35,
            "dislikes": None,
            "preferred_foods": None,
        }

        endpoint = f"{API_URL}/v1/nutripilot/meal"

        with st.spinner(
            "🤖 Creating your meal suggestion..."
        ):

            response, error = call_api(
                method="POST",
                endpoint=endpoint,
                payload=payload,
            )

            if response:

                display_api_result(
                    response=response,
                    success_message=(
                        "Your meal suggestion is ready! 🎉"
                    ),
                    result_title="🤖 Recommended Meal",
                    empty_message=(
                        "No meal suggestion was returned."
                    ),
                )

            else:

                st.error(error)


# ============================================================
# Food Substitution
# ============================================================

elif feature == "Food Substitution":

    st.header("🥕 Food Substitution")

    st.write(
        "Enter one or more foods and get healthy alternatives "
        "from NutriPilot AI."
    )

    with st.form("food_substitution_form"):

        food_items = st.text_area(
            "Food items",
            placeholder=(
                "e.g. white rice, french fries, soda"
            ),
            height=100,
        )

        submitted = st.form_submit_button(
            "🚀 Find Healthy Substitutions",
            use_container_width=True,
        )

    if submitted:

        if not food_items.strip():

            st.warning(
                "⚠️ Please enter at least one food item."
            )

        else:

            payload = {
                "food_items": food_items,
            }

            endpoint = (
                f"{API_URL}/v1/nutripilot/substitute"
            )

            with st.spinner(
                "🤖 Finding healthy alternatives..."
            ):

                response, error = call_api(
                    method="POST",
                    endpoint=endpoint,
                    payload=payload,
                )

                if response:

                    display_api_result(
                        response=response,
                        success_message=(
                            "Healthy substitutions are ready! 🎉"
                        ),
                        result_title="🤖 Healthy Alternatives",
                        empty_message=(
                            "No substitutions were returned."
                        ),
                    )

                else:

                    st.error(error)


# ============================================================
# Nutrition Analysis
# ============================================================

elif feature == "Nutrition Analysis":

    st.header("📊 Nutrition Analysis")

    st.write(
        "Enter one or more foods and get an AI-powered "
        "nutritional analysis."
    )

    with st.form("nutrition_analysis_form"):

        food_items = st.text_area(
            "Food items",
            placeholder=(
                "e.g. chicken breast, brown rice, broccoli"
            ),
            height=100,
        )

        submitted = st.form_submit_button(
            "🚀 Analyze Nutrition",
            use_container_width=True,
        )

    if submitted:

        if not food_items.strip():

            st.warning(
                "⚠️ Please enter at least one food item."
            )

        else:

            payload = {
                "food_items": food_items,
            }

            endpoint = (
                f"{API_URL}/v1/nutripilot/analysis"
            )

            with st.spinner(
                "🤖 Analyzing nutritional information..."
            ):

                response, error = call_api(
                    method="POST",
                    endpoint=endpoint,
                    payload=payload,
                )

                if response:

                    display_api_result(
                        response=response,
                        success_message=(
                            "Nutrition analysis is ready! 🎉"
                        ),
                        result_title="📊 Nutritional Analysis",
                        empty_message=(
                            "No nutritional analysis was returned."
                        ),
                    )

                else:

                    st.error(error)


# ============================================================
# Quick Recommendations
# ============================================================

elif feature == "Quick Recommendations":

    st.header("💡 Quick Recommendations")

    st.write(
        "Get five quick, AI-powered healthy eating "
        "recommendations."
    )

    if st.button(
        "🚀 Get Recommendations",
        use_container_width=True,
    ):

        endpoint = (
            f"{API_URL}/v1/nutripilot/recommendations"
        )

        with st.spinner(
            "🤖 Generating healthy eating recommendations..."
        ):

            response, error = call_api(
                method="GET",
                endpoint=endpoint,
            )

            if response:

                display_api_result(
                    response=response,
                    success_message=(
                        "Your recommendations are ready! 🎉"
                    ),
                    result_title="🤖 Healthy Eating Tips",
                    empty_message=(
                        "No recommendations were returned."
                    ),
                )

            else:

                st.error(error)


# ============================================================
# Regenerate Plan
# ============================================================

elif feature == "Regenerate Plan":

    st.header("🔄 Regenerate Plan")

    st.write(
        "Modify an existing diet plan based on your "
        "specific request."
    )

    with st.form("regenerate_plan_form"):

        existing_plan = st.text_area(
            "Existing diet plan",
            placeholder=(
                "Paste your existing diet plan here..."
            ),
            height=250,
        )

        modification_request = st.text_area(
            "Modification request",
            placeholder=(
                "e.g. Replace chicken with vegetarian "
                "protein sources and reduce dairy."
            ),
            height=120,
        )

        submitted = st.form_submit_button(
            "🔄 Regenerate Plan",
            use_container_width=True,
        )

    if submitted:

        if not existing_plan.strip():

            st.warning(
                "⚠️ Please enter your existing diet plan."
            )

        elif not modification_request.strip():

            st.warning(
                "⚠️ Please describe how you want to "
                "modify the plan."
            )

        else:

            payload = {
                "existing_plan": existing_plan,
                "modification_request": modification_request,
            }

            endpoint = (
                f"{API_URL}/v1/nutripilot/plan/regenerate"
            )

            with st.spinner(
                "🤖 Regenerating your personalized plan..."
            ):

                response, error = call_api(
                    method="POST",
                    endpoint=endpoint,
                    payload=payload,
                )

                if response:

                    display_api_result(
                        response=response,
                        success_message=(
                            "Your modified plan is ready! 🎉"
                        ),
                        result_title="🤖 Updated Nutrition Plan",
                        empty_message=(
                            "No modified plan was returned."
                        ),
                    )

                else:

                    st.error(error)


# ============================================================
# Fallback
# ============================================================

else:

    st.header(f"🍽️ {feature}")

    st.info(
        f"{feature} will be connected to the NutriPilot API "
        "in the next step. 🚀"
    )
