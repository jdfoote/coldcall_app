#!/usr/bin/env python

import pandas as pd
from random import choices, shuffle
from datetime import datetime
import csv
import os
from pathlib import Path
from flask import Flask, render_template, request, abort
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'

# Enable Flask logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Configuration
BASE_DIR = Path(__file__).parent
ASSESSMENTS_DIR = BASE_DIR.parent / 'assessments'
ALLOWED_COURSES = ["com_304", "com_411", "com_674", "amap"]

# Store caller instances per course to maintain state
callers = {}

@app.route("/")
def hello_world():
    return "<p>Hello, Test!</p>"


@app.route('/response_quality', methods=['POST'])
def response_quality():
    try:
        student_name = request.form['studentName']
        button_value = request.form['buttonValue']
        course = request.form['course']
        
        course_path = get_course_path(course)
        fn = course_path / f'{course}.csv'

        if button_value == 'absent':
            answered = 'F'
            button_value = ''
            # Update the Caller object
            caller = get_caller(course)
            caller.mark_absent(student_name)
        else:
            answered = 'T'

        if button_value != 'get_next':
            write_to_file(student_name, fn,
                    answered=answered,
                    assessment=button_value)
        student = coldcall_student(course)
        return student
    except Exception as e:
        app.logger.error(f"Error in response_quality: {e}")
        abort(500)

@app.route("/coldcaller/<course>", methods=['POST','GET'])
def coldcaller(course):
    try:
        public = request.args.get('public')
        if request.method == "POST":
            student = coldcall_student(course)
            if not student:
                abort(404)
        else:
            student = ''
        return render_template('cold_caller.html', student=student, public=public)
    except FileNotFoundError:
        abort(404, description="Course files not found")
    except Exception as e:
        app.logger.error(f"Error in coldcaller: {e}")
        abort(500)

def get_course_path(course):
    """Safely get course path with validation"""
    if course not in ALLOWED_COURSES:
        abort(404, description="Invalid course")
    course_path = ASSESSMENTS_DIR / course
    if not course_path.exists():
        abort(404, description="Course directory not found")
    return course_path

def get_caller(course):
    """Get or create a Caller instance for the course (maintains state)"""
    if course not in callers:
        course_path = get_course_path(course)
        weight = 2
        students = pd.read_csv(course_path / f'{course}_students.csv').Name
        out_fn = course_path / f'{course}.csv'
        callers[course] = Caller(str(out_fn), students, weight)
    return callers[course]

def coldcall_student(course):
    """Get a weighted random student for the course"""
    caller = get_caller(course)
    student = caller.get_random_student()
    return student

@app.route("/shuffler", methods=['POST','GET']) 
def shuffler():
    try:
        course = request.args.get('course')
        course_path = get_course_path(course)
        student_list = list(pd.read_csv(course_path / f'{course}_students.csv').Name)
        shuffle(student_list)
        app.logger.info(f"Shuffled students for {course}")
        return render_template('shuffler.html', result=student_list)
    except FileNotFoundError:
        abort(404, description="Course files not found")
    except Exception as e:
        app.logger.error(f"Error in shuffler: {e}")
        abort(500)

@app.route("/make_groups", methods=['POST','GET'])
def make_groups():
    try:
        course = request.args.get('course')
        group_size = int(request.args.get('group_size'))
        
        if group_size < 1:
            abort(400, description="Group size must be at least 1")
        
        course_path = get_course_path(course)
        student_list = list(pd.read_csv(course_path / f'{course}_students.csv').Name)
        shuffle(student_list)
        
        result = []
        for i, idx in enumerate(range(0, len(student_list), group_size), 1):
            result.append((i, student_list[idx:idx+group_size]))
        
        app.logger.info(f"Created {len(result)} groups of size {group_size} for {course}")
        return render_template('group_maker.html', result=result)
    except FileNotFoundError:
        abort(404, description="Course files not found")
    except ValueError:
        abort(400, description="Invalid group size")
    except Exception as e:
        app.logger.error(f"Error in make_groups: {e}")
        abort(500)



class Caller:

    def __init__(self, out_fn, students, weight = 2):
        self.weight = weight
        self.fn = out_fn
        self.students = students
        self.last_chosen = None
        self.today = datetime.now().date()
        self.absent_students = set()  # Track absences in memory
        self.weights_dict = self.get_weights()

    def get_weights(self):
        times_called = self.get_times_called()
        weights_dict = {}
        for student in self.students:
            try:
                curr_tc = times_called[student]
            except KeyError:
                curr_tc = 0
            student_weight = (1/self.weight) ** curr_tc
            weights_dict[student] = student_weight
        return weights_dict

    def get_times_called(self):
        try:
            df = pd.read_csv(self.fn)
            if len(df) > 0:
                self.last_chosen = df.name.iloc[-1]
            df['date'] = pd.to_datetime(df['date']).dt.date
            times_called = df[(df.answered.isin(['T','TRUE']))|(df['date']==self.today)].groupby('name').size()
            self.absent_today = df.loc[(df['date']==self.today) & (df.answered.isin(['F', 'FALSE'])), 'name']
            # Initialize absent_students from file
            self.absent_students = set(self.absent_today.tolist())
        except (FileNotFoundError, IndexError):
            times_called = pd.DataFrame()
            self.absent_today = pd.DataFrame()
        return times_called

    def mark_absent(self, student):
        """Mark a student as absent today"""
        self.absent_students.add(student)

    def update_weight(self, student):
        self.weights_dict[student] /= self.weight

    def get_random_student(self, can_repeat=False):
        if not can_repeat:
            curr_weights = {k:v for k,v in self.weights_dict.items() if k != self.last_chosen}
        else:
            curr_weights = self.weights_dict.copy()
        
        # Remove absent students from current selection
        curr_weights = {k:v for k,v in curr_weights.items() if k not in self.absent_students}
        
        if not curr_weights:
            # Fallback: if all students filtered out, use all weights
            curr_weights = self.weights_dict.copy()
        
        app.logger.info(f"Getting random student with can_repeat={can_repeat}. Current weights: {self.weights_dict}\nAbsent students: {self.absent_students}")
        rand_student = choices(list(curr_weights.keys()), weights=list(curr_weights.values()), k=1)[0]
        print(f"Weight of {rand_student}: {curr_weights[rand_student]}")
        self.last_chosen = rand_student
        return(rand_student)

def write_to_file(student, fn, answered, assessment):
    if not os.path.exists(fn):
        with open(fn, 'w') as f:
            f.write(','.join(['name', 'date', 'answered', 'assessment']))
            f.write('\n')
    with open(fn, 'a') as f:
        out_csv = csv.writer(f)
        out_csv.writerow([student,datetime.now().date(),answered,assessment])


