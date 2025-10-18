from flask import Flask, render_template, request, redirect, url_for, flash ,session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user ,UserMixin
from flask_migrate import Migrate # type: ignore
from sqlalchemy import func
from datetime import datetime ,timezone
from random import shuffle
from flask_mail import Mail, Message # type: ignore


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///quiz.db'
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Redirect to login if unauthorized access
migrate = Migrate(app, db)

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # Use your email provider's SMTP server
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'educaddneyyattinkara@gmail.com'  # Your email address
app.config['MAIL_PASSWORD'] = 'Jan@2024'  # Your email password or app-specific password
app.config['MAIL_DEFAULT_SENDER'] = 'neyyattinkara@educadd.net'

# Initialize Flask-Mail
mail = Mail(app)

def send_email(subject, recipients, body):
    msg = Message(subject=subject, recipients=recipients)
    msg.body = body
    mail.send(msg)

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), nullable=False, unique=True)
    phone_number = db.Column(db.String(15), nullable=False)
    college = db.Column(db.String(150), nullable=False)
    password = db.Column(db.String(150), nullable=False)

    # Flask-Login required attributes
    def is_authenticated(self):
        return True  # Customize based on your app logic, typically returns True if logged in

    def is_active(self):
        # Assuming your app automatically considers users as active, return True for all
        return True  # Change logic if you plan to have an active/inactive state

    def is_anonymous(self):
        return False  # Return False, as your users are not anonymous

    def get_id(self):
        return str(self.id)  # Return the user ID as a string


def send_email(subject, recipients, body):
    try:
        msg = Message(subject, recipients=recipients)
        msg.body = body
        mail.send(msg)
        print(f"Email sent to {recipients}")
    except Exception as e:
        print(f"Failed to send email: {e}")


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    option_1 = db.Column(db.String(255), nullable=False)
    option_2 = db.Column(db.String(255), nullable=False)
    option_3 = db.Column(db.String(255), nullable=False)
    option_4 = db.Column(db.String(255), nullable=False)
    correct_option = db.Column(db.Integer, nullable=False)  # 1, 2, 3, or 4


class QuizAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    answers = db.Column(db.Text, nullable=False)  # Store answers as a string
    date_created= db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))  # Use timezone-aware datetime

user = db.relationship('User', backref=db.backref('quiz_attempts', lazy=True))

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    submitted_at = db.Column(db.DateTime, default=db.func.now())

# User loader function
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    return render_template('index.html')

from flask_login import login_user, current_user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')  # Use .get() to avoid BadRequestKeyError
        password = request.form.get('password')
        
        # Check if email and password are provided
        if email and password:
            # Try to find the user with the email
            user = User.query.filter_by(email=email).first()
            if user and user.password == password:  # Add proper password hashing check here
                login_user(user)  # Log the user in using Flask-Login
                return redirect(url_for('terms'))  # Redirect to the terms page
            else:
                flash('Invalid email or password', 'error')
        else:
            flash('Please enter both email and password', 'error')
        
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/terms', methods=['GET', 'POST'])
def terms():
    if request.method == 'POST':
        # If the user agrees to the terms, redirect them to the exam page
        return redirect(url_for('start_quiz'))

    return render_template('terms.html')

@app.route('/quiz/start', methods=['GET', 'POST'])
def start_quiz():
    # Initialize session variables if not set
    if 'questions_order' not in session:
        # Shuffle question IDs to randomize the order
        all_questions = Question.query.all()
        question_ids = [q.id for q in all_questions]
        shuffle(question_ids)  # Shuffle the question order
        session['questions_order'] = question_ids
        session['current_question_index'] = 0
        session['user_answers'] = {}  # To store answers

    # Get the questions in the shuffled order
    question_ids = session['questions_order']
    current_index = session['current_question_index']
    total_questions = len(question_ids)

    # Check if there are still more questions to display
    if current_index < total_questions:
        current_question = Question.query.get(question_ids[current_index])
    else:
        # Quiz is finished, calculate score
        score = 0
        questions = Question.query.all()
        for question in questions:
            qid = str(question.id)
            if session['user_answers'].get(qid) == str(question.correct_option):
                score += 2

        # Save the quiz attempt
        quiz_attempt = QuizAttempt(user_id=current_user.id, score=score, answers=str(session['user_answers']))
        db.session.add(quiz_attempt)
        db.session.commit()

        # Clear session and redirect to Thank You page
        session.pop('questions_order', None)
        session.pop('current_question_index', None)
        session.pop('user_answers', None)
        return redirect(url_for('thankyou'))

    # Handle form submission
    if request.method == 'POST':
        selected_answer = request.form.get('answer')
        session['user_answers'][str(current_question.id)] = selected_answer
        session['current_question_index'] += 1  # Move to the next question

        return redirect(url_for('start_quiz'))  # Refresh page to show the next question

    return render_template('question.html', question=current_question, total_questions=total_questions, current_index=current_index + 1)


@app.route('/quiz/<int:question_id>', methods=['GET', 'POST'])
@login_required
def quiz(question_id):
    # Fetch the current question and total questions
    time_left = 30 * 60  # 30 minutes in seconds
    question = Question.query.get_or_404(question_id)
    total_questions = Question.query.count()
    current_index = question_id  # Assuming question_id maps to the order

    if request.method == 'POST':
        # Process the answer and redirect to the next question
        selected_answer = request.form.get('answer')
        # Store user's answer logic here

        # Redirect to the next question or Thank You page
        next_question_id = question_id + 1
        if next_question_id > total_questions:
            return redirect(url_for('thankyou'))  # Go to Thank You page after last question
        return redirect(url_for('quiz', question_id=next_question_id))

 # Send quiz completion email
    user = current_user  # Assuming Flask-Login is used
    subject = "Quiz Completed - Thank You!"
    body = f"Hi {user.name},\n\nThank you for completing the quiz.\nWe hope you had a great experience!\n\nBest regards,\nThe Skill Fest Team"
    send_email(subject, [user.email], body)
    
    return render_template(
        'question.html',
        time_left=time_left,
        question=question,
        total_questions=total_questions,
        current_index=question_id
    )

@app.route('/thankyou')
def thankyou():
    return render_template('thankyou.html')

# Admin Panel Routes
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'admin123':  # Static credentials for now
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    total_users = User.query.count()
    total_questions = Question.query.count()
    total_results = QuizAttempt.query.count()
    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_questions=total_questions,
        total_results=total_results
    )

@app.route('/admin/register_student', methods=['GET', 'POST'])
def register_student():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone_number = request.form.get('phone')
        college = request.form.get('college')
        password = request.form.get('password')

        # Validate fields
        if not all([name, email, phone_number, college, password]):
            flash("All fields are required.", "error")
            return render_template('register_student.html')

        # Check if the email already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash("This email is already registered.", "error")
            return render_template('register_student.html')

        # Add the new student to the database
        try:
            new_user = User(
                name=name,
                email=email,
                phone_number=phone_number,
                college=college,
                password=password  # You can add hashing here if needed
            )
            db.session.add(new_user)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Database error: {e}", "error")
            return render_template('register_student.html')

        # Send registration email (wrapped in try/except)
        try:
            subject = "Welcome to Skill Fest!"
            body = f"Hi {name},\n\nThank you for registering for Skill Fest.\nWe are excited to have you participate!\n\nBest regards,\nThe Skill Fest Team"
            msg = Message(subject, recipients=[email])
            msg.body = body
            mail.send(msg)
        except Exception as e:
            print(f"Email failed to send: {e}")
            flash("Student registered but email could not be sent.", "warning")

        return redirect(url_for('manage_users'))

    return render_template('register_student.html')

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    user = User.query.get_or_404(user_id)  # Fetch the user or return 404 if not found

    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        user.phone_number = request.form['phone']
        user.college = request.form['college']
        db.session.commit()
        return redirect(url_for('manage_users'))  # Redirect back to manage users page

    return render_template('edit_user.html', user=user)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('manage_users'))

@app.route('/admin/users')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/manage_questions')
def manage_questions():
    questions = Question.query.all()
    return render_template('manage_questions.html', questions=questions)

@app.route('/admin/add_question', methods=['GET', 'POST'])
def add_question():
    if request.method == 'POST':
        question_text = request.form['question_text']
        option_1 = request.form['option_1']
        option_2 = request.form['option_2']
        option_3 = request.form['option_3']
        option_4 = request.form['option_4']
        correct_option = int(request.form['correct_option'])

        new_question = Question(
            question_text=question_text,
            option_1=option_1,
            option_2=option_2,
            option_3=option_3,
            option_4=option_4,
            correct_option=correct_option
        )
        db.session.add(new_question)
        db.session.commit()

        return redirect(url_for('manage_questions'))
    return render_template('add_question.html')

@app.route('/admin/edit_question/<int:id>', methods=['GET', 'POST'])
def edit_question(id):
    question = Question.query.get_or_404(id)
    if request.method == 'POST':
        question.question_text = request.form['question_text']
        question.option_1 = request.form['option_1']
        question.option_2 = request.form['option_2']
        question.option_3 = request.form['option_3']
        question.option_4 = request.form['option_4']
        question.correct_option = int(request.form['correct_option'])

        db.session.commit()
        return redirect(url_for('manage_questions'))
    return render_template('edit_question.html', question=question)

@app.route('/admin/delete_question/<int:id>')
def delete_question(id):
    question = Question.query.get_or_404(id)
    db.session.delete(question)
    db.session.commit()
    return redirect(url_for('manage_questions'))


@app.route('/admin/manage_results')
def manage_results():
    # Fetch all quiz attempts
    quiz_attempts = QuizAttempt.query.all()
    
    # Render the results page and pass the data to the template
    return render_template('manage_results.html', quiz_attempts=quiz_attempts)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Ensure all tables are created
    app.run(debug=True)
