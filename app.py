from flask import Flask, request, jsonify, send_from_directory, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
import cohere
import tempfile
import docx2txt
import PyPDF2
import json
import re
from textblob import TextBlob
from dotenv import load_dotenv
from pymongo import MongoClient
app = Flask(__name__, static_folder='frontend')
CORS(app)
FRONTEND_PATH = os.path.join(os.path.dirname(__file__), 'frontend')


# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["resume_prep"]
questions_collection = db["user_questions"]
users_collection = db["users"]

# Set your Cohere API key
cohere_api_key = "aUfWyD6kQNR7QTj1rUQ4HNRYzbVH3o9s2QdopzD2"
co = cohere.Client(cohere_api_key)

# Extract text from file
def extract_text(file):
    ext = file.filename.split('.')[-1].lower()
    temp_path = os.path.join(tempfile.gettempdir(), file.filename)
    file.save(temp_path)

    if ext == "pdf":
        text = ""
        with open(temp_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
        return text
    elif ext == "docx":
        return docx2txt.process(temp_path)
    elif ext == "txt":
        with open(temp_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return ""

# Analyze resume to extract skills, projects, experience
def analyze_resume_text(resume_text):
    prompt = f"""
You are an expert in parsing resumes. Return your response in valid JSON (no explanation). Extract:

- 5 to 10 key skills.
- 2 to 5 projects with short descriptions.
- 2 to 5 job experiences with short summaries.

Only output valid JSON in this format:
{{
  "skills": [...],
  "projects": [...],
  "experiences": [...]
}}

Resume:
{resume_text}
"""

    response = co.generate(
        model="command-r-plus",
        prompt=prompt,
        max_tokens=600,
        temperature=0.5
    )
    return response.generations[0].text.strip()

# Generate interview questions
def generate_questions(prompt_text):
    response = co.generate(
        model="command-r-plus",
        prompt=prompt_text,
        max_tokens=1000,
        temperature=0.6
    )
    return response.generations[0].text.strip()

# Generate answers to questions
def generate_answers(prompt_text):
    response = co.generate(
        model="command-r-plus",
        prompt=prompt_text,
        max_tokens=2000,
        temperature=0.4
    )
    return response.generations[0].text.strip()

# Serve index.html as home page


# Analyze resume endpoint
@app.route("/api/analyze-resume", methods=["POST"])
def analyze_resume():
    try:
        resume_file = request.files.get("resume")
        if not resume_file:
            return jsonify({"success": False, "error": "No resume file provided"}), 400

        resume_text = extract_text(resume_file)
        cohere_output = analyze_resume_text(resume_text)

        try:
            analysis_result = json.loads(cohere_output)
            return jsonify({
                "success": True,
                "analysis": analysis_result
            })
        except json.JSONDecodeError:
            return jsonify({
                "success": False,
                "error": "Could not parse analysis result",
                "raw_output": cohere_output
            }), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Generate questions endpoint
@app.route("/api/generate-questions", methods=["POST"])
def generate_questions_endpoint():
    try:
        email = request.form.get("email", "")  # <-- Get email from form data
        job_title = request.form.get("jobTitle", "")
        question_type = request.form.get("questionType", "Technical")
        difficulty = request.form.get("difficulty", "Medium")
        num_questions = int(request.form.get("numQuestions", 5))
        resume_file = request.files.get("resume")
        resume_text = extract_text(resume_file) if resume_file else ""

        analysis_output = analyze_resume_text(resume_text)
        try:
            analysis_result = json.loads(analysis_output)
        except json.JSONDecodeError:
            return jsonify({"success": False, "error": "Could not parse analysis result", "raw_output": analysis_output}), 500

        extracted_skills = analysis_result.get("skills", [])
        prompt = f"""
You are an AI that generates {question_type.lower()} interview questions for the role of {job_title}.
The candidate has the following skills: {', '.join(extracted_skills)}.
Their key projects are:
{json.dumps(analysis_result.get('projects', []), indent=2)}

Their key experiences are:
{json.dumps(analysis_result.get('experiences', []), indent=2)}

Generate {num_questions} {difficulty.lower()}-level questions tailored to this resume and context.

Respond in JSON format like:
[
  {{
    "question": "Example question...",
    "type": "{question_type}",
    "difficulty": "{difficulty}"
  }},
  ...
]
        """

        cohere_output = generate_questions(prompt)
        try:
            questions = json.loads(cohere_output)
            # Save to MongoDB with user email
            questions_collection.insert_one({
                "email": email,
                "job_title": job_title,
                "question_type": question_type,
                "difficulty": difficulty,
                "num_questions": num_questions,
                "questions": questions
            })
            return jsonify({"success": True, "questions": questions})
        except json.JSONDecodeError:
            json_match = re.search(r'\[.*\]', cohere_output, re.DOTALL)
            if json_match:
                questions = json.loads(json_match.group())
                # Save to MongoDB with user email
                questions_collection.insert_one({
                    "email": email,
                    "job_title": job_title,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "num_questions": num_questions,
                    "questions": questions
                })
                return jsonify({"success": True, "questions": questions})
            else:
                return jsonify({"success": False, "error": "Could not parse questions", "raw_output": cohere_output}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Generate answers endpoint
@app.route("/api/generate-answers", methods=["POST"])
def generate_answers_endpoint():
    try:
        if "questions" in request.form:
            questions = json.loads(request.form.get("questions", "[]"))
        else:
            questions = request.json.get("questions", [])

        resume_file = request.files.get("resume")
        resume_text = extract_text(resume_file) if resume_file else ""

        if not questions:
            return jsonify({"success": False, "error": "No questions provided"}), 400

        questions_text = "\n".join([f"{idx+1}. {q['question']}" for idx, q in enumerate(questions)])
        prompt = f"""
Based on the following resume and questions, provide detailed answers to each question tailored to the candidate's experience.

Resume:
{resume_text}

Questions:
{questions_text}

Provide answers in JSON format like:
[
  {{
    "question": "Original question...",
    "answer": "Detailed answer based on resume...",
    "type": "Technical/Behavioral/etc",
    "difficulty": "Easy/Medium/Hard"
  }},
  ...
]
        """

        cohere_output = generate_answers(prompt)

        try:
            answers = json.loads(cohere_output)
            return jsonify({"success": True, "answers": answers})
        except json.JSONDecodeError:
            json_match = re.search(r'\[.*\]', cohere_output, re.DOTALL)
            if json_match:
                answers = json.loads(json_match.group())
                return jsonify({"success": True, "answers": answers})
            else:
                return jsonify({
                    "success": False,
                    "error": "Could not parse answers from Cohere output",
                    "raw_output": cohere_output
                }), 500

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/save-questions", methods=["POST"])
def save_questions():
    try:
        data = request.json
        email = data.get("email")
        questions = data.get("questions")

        if not email or not questions:
            return jsonify({"success": False, "error": "Email and questions are required"}), 400

        questions_collection.insert_one({
            "email": email,
            "questions": questions
        })

        return jsonify({"success": True, "message": "Questions saved to database."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    
@app.route("/api/signup", methods=["GET","POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")
    first_name = data.get("firstName")
    last_name = data.get("lastName")

    if not email or not password or not first_name or not last_name:
        return jsonify({"success": False, "message": "All fields are required"}), 400

    if users_collection.find_one({"email": email}):
        return jsonify({"success": False, "message": "Email already registered"}), 409

    hashed_password = generate_password_hash(password)
    users_collection.insert_one({
        "email": email,
        "password": hashed_password,
        "first_name": first_name,
        "last_name": last_name
    })
    return jsonify({"success": True, "message": "Signup successful"}), 201

@app.route("/api/signin", methods=["GET","POST"])
def signin():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required"}), 400

    user = users_collection.find_one({"email": email})
    if user and check_password_hash(user["password"], password):
        return jsonify({"success": True, "message": "Signin successful", "firstName": user["first_name"]}), 200
    else:
        return jsonify({"success": False, "message": "Invalid email or password"}), 401
# @app.route('/api/signup', methods=['POST'])
# def handle_signup():
#     try:
#         # Process signup data (validate, store in database, etc.)
#         email = request.form.get('email')
#         password = request.form.get('password')
        
#         # Add your signup logic here
#         # For now, we'll just return success
        
#         return jsonify({
#             'success': True,
#             'message': 'Signup successful'
#         })
#     except Exception as e:
#         return jsonify({
#             'success': False,
#             'message': str(e)
#         }), 400
        
@app.route('/')
def home():
    return redirect(url_for('serve_signup'))

# Signup route
@app.route('/signup')
def serve_signup():
    return send_from_directory(FRONTEND_PATH, 'signup.html')

# Login route
@app.route('/signin')
def serve_login():
    return send_from_directory(FRONTEND_PATH, 'signin.html')

# resume route
@app.route('/resume')
def resume():
    return send_from_directory(FRONTEND_PATH, 'resume.html')

# Index route (main page after signup)
@app.route('/index')
def serve_index():
    return send_from_directory(FRONTEND_PATH, 'index.html')

# Other pages
@app.route('/about')
def serve_about():
    return send_from_directory(FRONTEND_PATH, 'about.html')

@app.route('/features')
def serve_features():
    return send_from_directory(FRONTEND_PATH, 'features.html')

@app.route('/contact')
def serve_contact():
    return send_from_directory(FRONTEND_PATH, 'contact.html')

@app.route('/usecases')
def serve_usecases():
    return send_from_directory(FRONTEND_PATH, 'Use-cases.html')

@app.route('/faq')
def serve_faq():
    return send_from_directory(FRONTEND_PATH, 'faq.html')

@app.route('/benefits')
def serve_benefits():
    return send_from_directory(FRONTEND_PATH, 'benefits.html')

# Keep all your existing API endpoints (analyze-resume, generate-questions, etc.)

# Catch-all route should redirect to signup
@app.route('/<path:path>')
def catch_all(path):
    try:
        return send_from_directory(FRONTEND_PATH, path)
    except:
        return redirect(url_for('serve_signup'))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
