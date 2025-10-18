import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_pymongo import PyMongo
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
from random import shuffle
from bson.objectid import ObjectId

app = Flask(__name__)

# --- Configurations ---
app.config['SECRET_KEY'] = os.getenv("SECRET_KEY", "dev_secret")

# ✅ Ensure MONGO_URI exists
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise ValueError("❌ MONGO_URI environment variable not found! Please set it in Vercel.")

app.config["MONGO_URI"] = mongo_uri
mongo = PyMongo(app)

# --- Mail configuration ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_USERNAME")
mail = Mail(app)

# --- Flask-Login setup ---
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- MongoDB Collections ---
users = mongo.db.users
questions = mongo.db.questions
attempts = mongo.db.attempts


# --- Flask-Login User Wrapper ---
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data["_id"])
        self.name = user_data["name"]
        self.email = user_data["email"]
        self.password = user_data["password"]
        self.college = user_data.get("college", "")
        self.phone_number = user_data.get("phone_number", "")


@login_manager.user_loader
def load_user(user_id):
    user_data = users.find_one({"_id": ObjectId(user_id)})
    return User(user_data) if user_data else None


# --- Helper: Send Email ---
def send_email(subject, recipients, body):
    try:
        msg = Message(subject=subject, recipients=recipients)
        msg.body = body
        mail.send(msg)
    except Exception as e:
        print(f"⚠️ Failed to send email: {e}")


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user_data = users.find_one({'email': email})
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return redirect(url_for('terms'))
        else:
            flash('Invalid email or password', 'error')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/terms', methods=['GET', 'POST'])
def terms():
    if request.method == 'POST':
        return redirect(url_for('start_quiz'))
    return render_template('terms.html')

@app.route('/quiz/start', methods=['GET', 'POST'])
@login_required
def start_quiz():
    if 'questions_order' not in session:
        all_questions = list(questions.find())
        question_ids = [str(q["_id"]) for q in all_questions]
        shuffle(question_ids)
        session['questions_order'] = question_ids
        session['current_question_index'] = 0
        session['user_answers'] = {}

    question_ids = session['questions_order']
    current_index = session['current_question_index']
    total_questions = len(question_ids)

    if current_index < total_questions:
        current_question = questions.find_one({"_id": ObjectId(question_ids[current_index])})
    else:
        score = 0
        for qid, ans in session['user_answers'].items():
            question = questions.find_one({"_id": ObjectId(qid)})
            if str(question['correct_option']) == str(ans):
                score += 2

        attempts.insert_one({
            "user_id": ObjectId(current_user.id),
            "score": score,
            "answers": session['user_answers'],
            "date_created": datetime.now(timezone.utc)
        })

        session.pop('questions_order', None)
        session.pop('current_question_index', None)
        session.pop('user_answers', None)

        send_email(
            "Quiz Completed - Thank You!",
            [current_user.email],
            f"Hi {current_user.name},\n\nThank you for completing the quiz!\n\nYour score: {score}"
        )

        return redirect(url_for('thankyou'))

    if request.method == 'POST':
        selected_answer = request.form.get('answer')
        qid = question_ids[current_index]
        session['user_answers'][qid] = selected_answer
        session['current_question_index'] += 1
        return redirect(url_for('start_quiz'))

    return render_template(
        'question.html',
        question=current_question,
        total_questions=total_questions,
        current_index=current_index + 1
    )

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin123':
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    total_users = users.count_documents({})
    total_questions = questions.count_documents({})
    total_results = attempts.count_documents({})
    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_questions=total_questions,
        total_results=total_results
    )

@app.route('/admin/register_student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        phone = request.form['phone']
        college = request.form['college']
        password = request.form['password']

        if users.find_one({'email': email}):
            flash("This email is already registered.", "error")
            return render_template('register_student.html')

        hashed_pw = generate_password_hash(password)
        users.insert_one({
            "name": name,
            "email": email,
            "phone_number": phone,
            "college": college,
            "password": hashed_pw
        })

        try:
            send_email(
                "Welcome to Skill Fest!",
                [email],
                f"Hi {name},\n\nThank you for registering for Skill Fest!"
            )
        except Exception as e:
            print("Email not sent:", e)

        return redirect(url_for('manage_users'))

    return render_template('register_student.html')

@app.route('/admin/users')
def manage_users():
    all_users = list(users.find())
    return render_template('manage_users.html', users=all_users)

@app.route('/admin/manage_questions')
def manage_questions():
    all_questions = list(questions.find())
    return render_template('manage_questions.html', questions=all_questions)

@app.route('/admin/add_question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        q = {
            "question_text": request.form['question_text'],
            "option_1": request.form['option_1'],
            "option_2": request.form['option_2'],
            "option_3": request.form['option_3'],
            "option_4": request.form['option_4'],
            "correct_option": int(request.form['correct_option'])
        }
        questions.insert_one(q)
        return redirect(url_for('manage_questions'))
    return render_template('add_question.html')

@app.route('/admin/edit_question/<id>', methods=['GET', 'POST'])
def edit_question(id):
    question = questions.find_one({"_id": ObjectId(id)})
    if request.method == ['POST']:
        updated = {
            "question_text": request.form['question_text'],
            "option_1": request.form['option_1'],
            "option_2": request.form['option_2'],
            "option_3": request.form['option_3'],
            "option_4": request.form['option_4'],
            "correct_option": int(request.form['correct_option'])
        }
        questions.update_one({"_id": ObjectId(id)}, {"$set": updated})
        return redirect(url_for('manage_questions'))
    return render_template('edit_question.html', question=question)

@app.route('/admin/delete_question/<id>')
def delete_question(id):
    questions.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('manage_questions'))

@app.route('/admin/manage_results')
def manage_results():
    quiz_attempts = list(attempts.find())
    return render_template('manage_results.html', quiz_attempts=quiz_attempts)


# --- Run locally ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
