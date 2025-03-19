#!/usr/bin/env python

import pandas as pd
from random import choices, shuffle
from datetime import datetime
import csv
import os
from flask import Flask, render_template, request, abort

app = Flask(__name__)

@app.route("/")
def hello_world():
    return "<p>Hello, Test!</p>"


@app.route('/response_quality', methods=['POST'])
def response_quality():
    student_name = request.form['studentName']
    button_value = request.form['buttonValue']
    course = request.form['course']

    fn = f'../assessments/{course}/{course}.csv'

    if button_value == 'absent':
        answered = 'F'
        button_value = ''
    else:
        answered = 'T'

    if button_value != 'get_next':
        write_to_file(student_name, fn,
                answered=answered,
                assessment=button_value)
    student = coldcall_student(course)
    return student

@app.route("/coldcaller/<course>", methods=['POST','GET'])
def coldcaller(course):
    public = request.args.get('public')
    if request.method == "POST":
        student = coldcall_student(course)
        if not student:
            abort(404)
    else:
        student = ''
    return render_template('cold_caller.html', student=student, public=public)

def coldcall_student(course):
    if course not in ["com_304","com_411","com_674", "amap"]:
        return None
    weight = 2
    students = pd.read_csv(f'../assessments/{course}/{course}_students.csv').Name
    out_fn = f'../assessments/{course}/{course}.csv'
    caller = Caller(out_fn, students, weight)
    student = caller.get_random_student()
    return student

@app.route("/shuffler", methods=['POST','GET']) 
def shuffler():
    course = request.args.get('course')
    try:
        student_list = pd.read_csv(f'../assessments/{course}/{course}_students.csv').Name
    except FileNotFoundError:
        abort(404)
    shuffle(student_list)
    print(student_list)
    return render_template('shuffler.html', result=student_list)

@app.route("/make_groups", methods=['POST','GET'])
def make_groups():
    course = request.args.get('course')
    group_size = int(request.args.get('group_size'))
    print('running')
    try:
        student_list = pd.read_csv(f'../assessments/{course}/{course}_students.csv').Name
    except FileNotFoundError:
        abort(404)
    shuffle(student_list)
    print(student_list)
    print(range(0,len(student_list)//group_size + 1, group_size))
    result = []
    j = 1
    for i in range(0,len(student_list), group_size):
        result.append((j, student_list[i:i+group_size]))
        j += 1
    return render_template('group_maker.html', result=result)



class Caller:

    def __init__(self, out_fn, students, weight = 2):
        self.weight = weight
        self.fn = out_fn
        self.students = students
        self.last_chosen = None
        self.today = datetime.now().date()
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
            df.date = pd.to_datetime(df.date).dt.date
            times_called = df[(df.answered.isin(['T','TRUE']))|(df.date==self.today)].groupby('name').size()
            self.absent_today = df.loc[(df.date==self.today) & (df.answered.isin(['F', 'FALSE'])), 'name']
        except FileNotFoundError or IndexError:
            times_called = pd.DataFrame()
            self.absent_today = pd.DataFrame()
        return times_called

    def update_weight(self, student):
        self.weights_dict[student] /= self.weight

    def get_random_student(self, can_repeat=False):
        if not can_repeat:
            curr_weights = {k:v for k,v in self.weights_dict.items() if k != self.last_chosen}
        else:
            curr_weights = self.weights_dict
        for student in set(self.absent_today):
            if student != self.last_chosen:
                del curr_weights[student]
        rand_student = choices(list(curr_weights.keys()), weights=list(curr_weights.values()), k=1)[0]
        print(f"Weight of {rand_student}: {curr_weights[rand_student]}")
        self.update_weight(rand_student)
        return(rand_student)

def write_to_file(student, fn, answered, assessment):
    if not os.path.exists(fn):
        with open(fn, 'w') as f:
            f.write(','.join(['name', 'date', 'answered', 'assessment']))
            f.write('\n')
    with open(fn, 'a') as f:
        out_csv = csv.writer(f)
        out_csv.writerow([student,datetime.now().date(),answered,assessment])


