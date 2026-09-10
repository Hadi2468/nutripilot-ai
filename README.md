# NutriPilot AI

### Serverless Generative AI Nutrition Planning Platform

NutriPilot AI is a serverless Generative AI application that provides personalized nutrition planning and food analysis through a secure REST API.

The platform combines **FastAPI, AWS Lambda, API Gateway, and LLM inference** to provide AI-powered nutrition recommendations through a scalable serverless architecture.

---

## 🌟 Project Overview

NutriPilot AI allows users to:

* Generate personalized weekly diet plans
* Generate individual meal suggestions
* Regenerate and modify existing diet plans
* Analyze food nutritional information
* Suggest healthy food substitutions
* Receive healthy eating tips

The application uses an LLM to generate personalized responses based on user-provided information.

---

![##🔀 Architecture](assets/architecture.png) 

---

## 🤖 AI Engineering

The application uses an LLM inference service to generate nutrition-related responses.

The backend separates the API layer from the LLM service so that the inference provider can be replaced without changing the API contract.

The system is designed to evolve toward:

* Structured LLM outputs
* Deterministic response validation
* Prompt versioning
* LLM evaluation
* Latency and cost monitoring
* Automated testing

---

## 🔐 Security

The API uses Bearer Token authentication to protect endpoints.

Sensitive configuration is provided through environment variables:

```text
GROQ_API_KEY
API_TOKEN
```

Secrets are intentionally excluded from source control.

The repository uses `.gitignore` to prevent environment files, credentials, deployment artifacts, and other sensitive files from being committed.

---

## 📡 API Endpoints

| Method | Endpoint                         | Description                  |
| ------ | -------------------------------- | ---------------------------- |
| GET    | `/`                              | Health check                 |
| GET    | `/v1/nutripilot/recommendations` | Generate healthy eating tips |
| POST   | `/v1/nutripilot/plan`            | Generate weekly diet plan    |
| POST   | `/v1/nutripilot/meal`            | Generate a meal suggestion   |
| POST   | `/v1/nutripilot/plan/regenerate` | Modify an existing plan      |
| POST   | `/v1/nutripilot/substitute`      | Suggest food substitutions   |
| POST   | `/v1/nutripilot/analysis`        | Analyze food nutrition       |


---

## Example Example Request

### Generate a Diet Plan

```json
{
  "meal_preference": "vegetarian",
  "calories": 2000,
  "meal_count": 4,
  "goal": "weight loss",
  "age": 60
}
```

The API returns an AI-generated weekly nutrition plan.

---

## 🛠️ Technology Stack

### Backend

* Python
* FastAPI
* Pydantic
* Mangum

### Cloud

* AWS Lambda
* AWS API Gateway
* Amazon CloudWatch

### AI

* Groq
* GPT-OSS-20B

### Development

* Git
* GitHub
* Postman

### Planned

* Streamlit
* Pytest
* GitHub Actions
* Automated LLM evaluation

---

## 📁 Current Project Structure

```text
nutripilot-ai/
├── README.md
├── .gitignore
├── .env.example
├── main.py
└── requirements.txt
```

The project will be progressively refactored into a modular production-oriented architecture.

---

## 💻 Local Development

Clone the repository:

```bash
git clone https://github.com/Hadi2468/nutripilot-ai.git
cd nutripilot-ai
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create a `.env` file locally and configure:

```text
GROQ_API_KEY=your_key
API_TOKEN=your_token
```

Run the FastAPI application:

```bash
uvicorn main:app --reload
```

---

## 🕵🏻 Testing

Automated testing will be added as part of the project's engineering evolution.

Planned test coverage includes:

* API health checks
* Input validation
* Authentication
* API endpoints
* LLM service behavior
* Error handling

---

## 📦 Deployment

The backend is deployed using a serverless architecture:

```text
AWS API Gateway
       ↓
AWS Lambda
       ↓
FastAPI + Mangum
       ↓
LLM Inference
```

This architecture avoids managing traditional application servers and provides an independently scalable API layer.

---

## 🔜 Future Improvements

Planned improvements include:

1. Modular backend architecture
2. Streamlit user interface
3. Automated unit and integration tests
4. Structured LLM response validation
5. Prompt versioning
6. LLM evaluation framework
7. Cost and latency tracking
8. GitHub Actions CI/CD
9. Production deployment automation
10. Architecture documentation

---

## ⚠️ Disclaimer

NutriPilot AI is an educational and software engineering project.

AI-generated nutrition recommendations should not be considered medical advice. Users should consult qualified healthcare or nutrition professionals for medical or dietary conditions.

---

## 🎯 Engineering Focus

This project demonstrates practical experience with:

* Serverless architecture
* REST API development
* Generative AI integration
* LLM application engineering
* Cloud deployment
* API authentication
* Environment-based configuration
* Observability
* Software testing
* CI/CD
* Production-oriented AI system design

---

## 📄 License

This project is licensed under the MIT License.
