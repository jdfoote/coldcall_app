This is a Flask app designed to let you randomly call on students during class.

To install it, you will need to clone the git repository.

You will also need to install Flask and pandas via pip or similar.

Before running the app, you will need to set up folders for each class you'd like to use it for. The default structure is this: 

```
top-level-directory/
├── assessments/               # Root directory for all class data
│   ├── class_1/               # Directory for first class
│   │   └── class_1_students.csv    # CSV file containing student data for class 1
│   └── class_2/               # Directory for second class
│       └── class_2_students.csv    # CSV file containing student data for class 2
└── coldcall_app/              # Application directory
```

If you want to change the structure, you'll just need to change a few hardcoded paths in `app.py`

I just download a CSV file of the students in my class from the LMS a day or two before class starts. The CSV file is expecting to find a column called `name`. Any other columns will be ignored. Once the app is run, it will create a new (poorly named) file called `{class_name}.csv` in the class directory, which stores the outcomes of cold calls. I have an R script that creates Word Doc reports from these files which I'm happy to share. At some point, that reporting should probably move into the app.

The current version is designed to run locally. If everything is installed correctly, then it should work by running
```
flask run
```

from the coldcall_app directory.


To run it, you can go to http://127.0.0.1:5000/coldcaller/{class_name}

I also built a few other little tools.

http://127.0.0.1:5000/shuffler?course={class_name} will produce a randomized list of the students, and
http://127.0.0.1:5000/make_groups?course={class_name}&group_size={group_size} will produce a set of groups of size `group_size`.
